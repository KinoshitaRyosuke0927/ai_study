"""
F1 ピットストップ予測 - LightGBM + CatBoost アンサンブル
既存コード (s6e5_baseline.py / s6e5_optuna.py) は一切変更しない。

アンサンブルの考え方:
  - LightGBM と CatBoost は異なるアルゴリズムでツリーを構築するため、
    同じデータでも異なるパターンを学習し、互いの弱点を補い合える。
  - 各モデルの予測確率（OOF・テスト）を加重平均することで
    単体モデルより安定した予測が得られる。

CatBoost の特徴:
  - カテゴリ変数（Driver, Compound, Race）を Label Encoding なしで直接扱える
  - Ordered Boosting により過学習が起きにくい
  - 欠損値を自動処理（今回は欠損なしだが将来の拡張に対応）

LightGBM パラメータ:
  - s6e5_optuna.py で探索したベストパラメータを使用
"""
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score
import lightgbm as lgb
from catboost import CatBoostClassifier, Pool

# ── パス設定 ──────────────────────────────────────────────
DATA_DIR   = Path(__file__).parent.parent / "competitions" / "playground-series-s6e5"
OUTPUT_DIR = Path(__file__).parent
OUTPUT_DIR.mkdir(exist_ok=True)

# ── データ読み込み ─────────────────────────────────────────
train = pd.read_csv(DATA_DIR / "train.csv")
test  = pd.read_csv(DATA_DIR / "test.csv")

TARGET = "PitNextLap"
ID_COL = "id"

print(f"Train: {train.shape}  Test: {test.shape}")

# ── ベースラインと同じ特徴量エンジニアリング ──────────────
def add_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["TyreLife_sq"]         = df["TyreLife"] ** 2
    df["TyreLife_sqrt"]       = np.sqrt(df["TyreLife"].clip(0))
    df["Degradation_Rate"]    = df["Cumulative_Degradation"] / (df["TyreLife"] + 1)
    compound_durability       = {"SOFT": 1, "MEDIUM": 2, "HARD": 3, "INTERMEDIATE": 4, "WET": 5}
    df["Compound_Dur"]        = df["Compound"].map(compound_durability).fillna(2)
    df["TyreLife_x_Dur"]      = df["TyreLife"] / df["Compound_Dur"]
    df["LapTime_Norm"]        = df["LapTime (s)"] / df["LapTime (s)"].mean()
    df["Position_sq"]         = df["Position"] ** 2
    df["Progress_x_TyreLife"] = df["RaceProgress"] * df["TyreLife"]
    return df

train = add_features(train)
test  = add_features(test)

# ── カテゴリ変数のリスト ───────────────────────────────────
# LightGBM 用: Label Encoding が必要
# CatBoost 用: 文字列のまま渡せる（cat_features に列名を指定するだけ）
CAT_COLS  = ["Driver", "Compound", "Race"]
DROP_COLS = [ID_COL, TARGET]

# ── LightGBM 用: Label Encoding ──────────────────────────
train_lgb = train.copy()
test_lgb  = test.copy()

encoders = {}
for col in CAT_COLS:
    le = LabelEncoder()
    combined = pd.concat([train_lgb[col], test_lgb[col]], axis=0).astype(str)
    le.fit(combined)
    train_lgb[col] = le.transform(train_lgb[col].astype(str))
    test_lgb[col]  = le.transform(test_lgb[col].astype(str))
    encoders[col]  = le

FEATURES  = [c for c in train_lgb.columns if c not in DROP_COLS]
X_lgb     = train_lgb[FEATURES].values
y         = train[TARGET].values
X_lgb_test= test_lgb[FEATURES].values

# ── CatBoost 用: 文字列カテゴリのまま保持 ───────────────
# カテゴリ列以外は数値のまま。CatBoost が内部でエンコードする。
train_cb = train.copy()
test_cb  = test.copy()

# CatBoost は文字列型のカテゴリを扱える（数値への変換不要）
for col in CAT_COLS:
    train_cb[col] = train_cb[col].astype(str)
    test_cb[col]  = test_cb[col].astype(str)

X_cb      = train_cb[FEATURES]   # DataFrame のまま渡す
X_cb_test = test_cb[FEATURES]
cat_feature_indices = [FEATURES.index(c) for c in CAT_COLS]

print(f"使用特徴量: {len(FEATURES)} 個")
print(f"カテゴリ特徴量: {CAT_COLS}")

# ── LightGBM ベストパラメータ（s6e5_optuna.py の探索結果）──
LGBM_PARAMS = {
    "objective":         "binary",
    "metric":            "auc",
    "is_unbalance":      True,
    "verbose":           -1,
    "seed":              42,
    "learning_rate":     0.011239540190196115,
    "num_leaves":        206,
    "min_child_samples": 11,
    "feature_fraction":  0.6551668299060227,
    "bagging_fraction":  0.7523976445015709,
    "bagging_freq":      6,
    "lambda_l1":         5.045897126785404,
    "lambda_l2":         0.010318662217974258,
    "min_split_gain":    0.6442249135882291,
    "max_depth":         12,
}

# ── 5-Fold CV ──────────────────────────────────────────────
skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

oof_lgbm  = np.zeros(len(y))
oof_cb    = np.zeros(len(y))
test_lgbm = np.zeros(len(X_lgb_test))
test_cb   = np.zeros(len(X_cb_test))

lgbm_scores = []
cb_scores   = []

print("\n=== 5-Fold Cross Validation ===")

for fold, (tr_idx, val_idx) in enumerate(skf.split(X_lgb, y), 1):
    print(f"\n--- Fold {fold}/5 ---")

    # ── LightGBM ─────────────────────────────────────────
    X_tr_l, X_val_l = X_lgb[tr_idx], X_lgb[val_idx]
    y_tr,   y_val   = y[tr_idx],     y[val_idx]

    dtrain = lgb.Dataset(X_tr_l,  label=y_tr,  feature_name=FEATURES)
    dval   = lgb.Dataset(X_val_l, label=y_val, reference=dtrain)

    lgbm_model = lgb.train(
        LGBM_PARAMS,
        dtrain,
        num_boost_round=3000,
        valid_sets=[dval],
        callbacks=[
            lgb.early_stopping(stopping_rounds=50, verbose=False),
            lgb.log_evaluation(period=500),
        ],
    )

    lgbm_val_pred  = lgbm_model.predict(X_val_l)
    lgbm_auc       = roc_auc_score(y_val, lgbm_val_pred)
    lgbm_scores.append(lgbm_auc)
    oof_lgbm[val_idx] = lgbm_val_pred
    test_lgbm += lgbm_model.predict(X_lgb_test) / skf.n_splits
    print(f"  LightGBM  best_iter={lgbm_model.best_iteration:4d}  AUC={lgbm_auc:.5f}")

    # ── CatBoost ─────────────────────────────────────────
    X_tr_c  = X_cb.iloc[tr_idx]
    X_val_c = X_cb.iloc[val_idx]

    train_pool = Pool(X_tr_c,  label=y_tr,  cat_features=CAT_COLS)
    val_pool   = Pool(X_val_c, label=y_val, cat_features=CAT_COLS)

    cb_model = CatBoostClassifier(
        iterations=3000,
        learning_rate=0.05,
        depth=8,
        l2_leaf_reg=3.0,
        min_data_in_leaf=20,
        random_strength=1.0,
        bagging_temperature=1.0,
        od_type="Iter",          # Early Stopping の方式
        od_wait=100,             # 100 iteration 改善なしで停止
        eval_metric="AUC",
        auto_class_weights="Balanced",   # クラス不均衡の自動補正
        random_seed=42,
        verbose=False,
    )
    cb_model.fit(train_pool, eval_set=val_pool, use_best_model=True)

    cb_val_pred = cb_model.predict_proba(X_val_c)[:, 1]
    cb_auc      = roc_auc_score(y_val, cb_val_pred)
    cb_scores.append(cb_auc)
    oof_cb[val_idx] = cb_val_pred
    test_cb += cb_model.predict_proba(X_cb_test)[:, 1] / skf.n_splits
    print(f"  CatBoost  best_iter={cb_model.best_iteration_:4d}  AUC={cb_auc:.5f}")

# ── 各モデルの OOF スコア ────────────────────────────────
oof_lgbm_auc = roc_auc_score(y, oof_lgbm)
oof_cb_auc   = roc_auc_score(y, oof_cb)

print(f"\n=== 単体モデル OOF AUC ===")
print(f"  LightGBM : {oof_lgbm_auc:.5f}  (各Fold: {np.mean(lgbm_scores):.5f} +/- {np.std(lgbm_scores):.5f})")
print(f"  CatBoost : {oof_cb_auc:.5f}  (各Fold: {np.mean(cb_scores):.5f} +/- {np.std(cb_scores):.5f})")

# ── アンサンブル重みの最適化 ─────────────────────────────
# OOF 予測を使って LightGBM と CatBoost の最適な混合比率を探索する。
# グリッドサーチで w を 0〜1 で変化させ、AUC が最大になる w を選ぶ。
best_auc = 0.0
best_w   = 0.5
for w in np.linspace(0, 1, 101):
    oof_blend = w * oof_lgbm + (1 - w) * oof_cb
    auc = roc_auc_score(y, oof_blend)
    if auc > best_auc:
        best_auc = auc
        best_w   = w

print(f"\n=== アンサンブル重み最適化 ===")
print(f"  最適重み: LightGBM={best_w:.2f}  CatBoost={1-best_w:.2f}")
print(f"  OOF AUC (均等 0.5/0.5) : {roc_auc_score(y, 0.5*oof_lgbm + 0.5*oof_cb):.5f}")
print(f"  OOF AUC (最適重み)     : {best_auc:.5f}")
print(f"  Baseline               : 0.94840")
print(f"  Optuna (LightGBM only) : 0.94937")
print(f"  改善幅 (vs Optuna)     : {best_auc - 0.94937:+.5f}")

# ── 提出ファイル作成（最適重みで混合） ──────────────────
test_blend = best_w * test_lgbm + (1 - best_w) * test_cb
submission = pd.DataFrame({"id": test[ID_COL], "PitNextLap": test_blend})
out_path   = OUTPUT_DIR / "submission_ensemble.csv"
submission.to_csv(out_path, index=False)
print(f"\nSubmission saved -> {out_path}")
print(f"予測確率の統計: mean={test_blend.mean():.4f}  min={test_blend.min():.4f}  max={test_blend.max():.4f}")

# ── 相関確認（モデルの多様性チェック）────────────────────
corr = np.corrcoef(oof_lgbm, oof_cb)[0, 1]
print(f"\nLightGBM vs CatBoost の OOF 予測相関: {corr:.4f}")
print("（相関が低いほどアンサンブル効果が高い）")
