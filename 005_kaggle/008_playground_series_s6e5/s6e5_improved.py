"""
F1 ピットストップ予測 - 外部データ活用 + CV戦略修正 + num_boost_round増加版
既存コードは一切変更しない。

s6e5_external_data.py からの変更点:
  1. CV戦略の修正:
       Before: [コンペデータ + 外部データ] を 5-Fold で分割
               → バリデーションに外部データが混入し OOF が過大評価
       After : コンペデータのみを 5-Fold で分割
               → 各Foldの訓練 = コンペ訓練折 + 全外部データ
               → 各Foldのバリデーション = コンペ検証折のみ
               → OOF がテストデータ（合成データ）の分布に対して正直な評価になる

  2. num_boost_round の増加: 3000 → 8000
       Before: 全フォールドで best_iter=3000（上限到達）→ 学習途中で強制停止
       After : 上限を広げて Early Stopping に任せる
"""
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score
import lightgbm as lgb
from catboost import CatBoostClassifier, Pool
import kagglehub

# ── パス設定 ──────────────────────────────────────────────
DATA_DIR   = Path(__file__).parent.parent / "competitions" / "playground-series-s6e5"
OUTPUT_DIR = Path(__file__).parent
OUTPUT_DIR.mkdir(exist_ok=True)

TARGET = "PitNextLap"
ID_COL = "id"

# ── データ読み込み ─────────────────────────────────────────
print("データ読み込み中...")
train_comp = pd.read_csv(DATA_DIR / "train.csv")
test       = pd.read_csv(DATA_DIR / "test.csv")

orig_path = kagglehub.dataset_download(
    "aadigupta1601/f1-strategy-dataset-pit-stop-prediction"
)
orig = pd.read_csv(Path(orig_path) / "f1_strategy_dataset_v4.csv")

print(f"  コンペ訓練データ : {train_comp.shape}")
print(f"  元F1データ       : {orig.shape}")
print(f"  テストデータ     : {test.shape}")

# ── 元データの前処理 ──────────────────────────────────────
orig[ID_COL] = -1
orig = orig.drop(columns=["Normalized_TyreLife"], errors="ignore")
orig = orig.sort_values(["Driver", "Race", "Year", "LapNumber"])
orig["Compound"] = (
    orig.groupby(["Driver", "Race", "Year", "Stint"])["Compound"]
    .transform(lambda s: s.ffill().bfill())
)
orig["Compound"] = orig["Compound"].fillna("UNKNOWN")
common_cols = [c for c in train_comp.columns if c in orig.columns]
orig = orig[common_cols]

# ── 特徴量エンジニアリング（全データに適用） ──────────────
def add_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["TyreLife_sq"]         = df["TyreLife"] ** 2
    df["TyreLife_sqrt"]       = np.sqrt(df["TyreLife"].clip(0))
    df["Degradation_Rate"]    = df["Cumulative_Degradation"] / (df["TyreLife"] + 1)
    compound_durability       = {"SOFT": 1, "MEDIUM": 2, "HARD": 3,
                                 "INTERMEDIATE": 4, "WET": 5, "UNKNOWN": 2}
    df["Compound_Dur"]        = df["Compound"].map(compound_durability).fillna(2)
    df["TyreLife_x_Dur"]      = df["TyreLife"] / df["Compound_Dur"]
    df["LapTime_Norm"]        = df["LapTime (s)"] / df["LapTime (s)"].mean()
    df["Position_sq"]         = df["Position"] ** 2
    df["Progress_x_TyreLife"] = df["RaceProgress"] * df["TyreLife"]
    return df

train_comp = add_features(train_comp)
orig       = add_features(orig)
test       = add_features(test)

# ── カテゴリ変数のリスト ───────────────────────────────────
CAT_COLS  = ["Driver", "Compound", "Race"]
DROP_COLS = [ID_COL, TARGET]
FEATURES  = [c for c in train_comp.columns if c not in DROP_COLS]

# ── Label Encoding（LightGBM用） ──────────────────────────
# train_comp + orig + test の全カテゴリを fit して未知カテゴリを防ぐ
train_comp_lgb = train_comp.copy()
orig_lgb       = orig.copy()
test_lgb       = test.copy()

encoders = {}
for col in CAT_COLS:
    le = LabelEncoder()
    combined = pd.concat(
        [train_comp_lgb[col], orig_lgb[col], test_lgb[col]], axis=0
    ).astype(str)
    le.fit(combined)
    train_comp_lgb[col] = le.transform(train_comp_lgb[col].astype(str))
    orig_lgb[col]       = le.transform(orig_lgb[col].astype(str))
    test_lgb[col]       = le.transform(test_lgb[col].astype(str))
    encoders[col]       = le

# CatBoost 用: 文字列のまま保持
train_comp_cb = train_comp.copy()
orig_cb       = orig.copy()
test_cb       = test.copy()
for col in CAT_COLS:
    train_comp_cb[col] = train_comp_cb[col].astype(str)
    orig_cb[col]       = orig_cb[col].astype(str)
    test_cb[col]       = test_cb[col].astype(str)

# コンペデータの特徴量・ターゲット（CV の分割基準）
X_comp      = train_comp_lgb[FEATURES].values
y_comp      = train_comp[TARGET].values
X_orig_lgb  = orig_lgb[FEATURES].values
y_orig      = orig[TARGET].values
X_test_lgb  = test_lgb[FEATURES].values

X_comp_cb   = train_comp_cb[FEATURES]
X_orig_cb   = orig_cb[FEATURES]
X_test_cb   = test_cb[FEATURES]

print(f"\n使用特徴量: {len(FEATURES)} 個")

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

NUM_BOOST_ROUND = 8000   # 3000 → 8000: Early Stopping に任せる

# ── 修正後の CV 戦略 ──────────────────────────────────────
# コンペデータのみを StratifiedKFold で分割する。
# 訓練: コンペ訓練折 + 全外部データ
# バリデーション: コンペ検証折のみ（純粋な合成データで評価）
skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

oof_lgbm  = np.zeros(len(y_comp))  # コンペデータのみの OOF
oof_cb    = np.zeros(len(y_comp))
test_lgbm = np.zeros(len(X_test_lgb))
test_cb   = np.zeros(len(X_test_cb))

lgbm_scores = []
cb_scores   = []

print("\n=== 5-Fold Cross Validation（CV戦略修正版）===")
print("  バリデーション = コンペデータのみ（合成データで正直な評価）")
print("  訓練 = コンペ訓練折 + 全外部データ（101K行を毎回追加）")

for fold, (tr_idx, val_idx) in enumerate(skf.split(X_comp, y_comp), 1):
    print(f"\n--- Fold {fold}/5 ---")

    # バリデーション: コンペ検証折のみ
    X_val_l = X_comp[val_idx]
    y_val   = y_comp[val_idx]
    X_val_c = X_comp_cb.iloc[val_idx]

    # 訓練: コンペ訓練折 + 全外部データ を結合
    X_tr_l = np.vstack([X_comp[tr_idx], X_orig_lgb])
    y_tr   = np.concatenate([y_comp[tr_idx], y_orig])
    X_tr_c = pd.concat([X_comp_cb.iloc[tr_idx], X_orig_cb], ignore_index=True)

    print(f"  訓練サイズ: {len(y_tr):,}行  バリデーションサイズ: {len(y_val):,}行")

    # ── LightGBM ─────────────────────────────────────────
    dtrain = lgb.Dataset(X_tr_l,  label=y_tr,  feature_name=FEATURES)
    dval   = lgb.Dataset(X_val_l, label=y_val, reference=dtrain)

    lgbm_model = lgb.train(
        LGBM_PARAMS,
        dtrain,
        num_boost_round=NUM_BOOST_ROUND,
        valid_sets=[dval],
        callbacks=[
            lgb.early_stopping(stopping_rounds=100, verbose=False),
            lgb.log_evaluation(period=1000),
        ],
    )
    lgbm_val_pred     = lgbm_model.predict(X_val_l)
    lgbm_auc          = roc_auc_score(y_val, lgbm_val_pred)
    lgbm_scores.append(lgbm_auc)
    oof_lgbm[val_idx] = lgbm_val_pred
    test_lgbm        += lgbm_model.predict(X_test_lgb) / skf.n_splits
    print(f"  LightGBM  best_iter={lgbm_model.best_iteration:4d}  AUC={lgbm_auc:.5f}")

    # ── CatBoost ─────────────────────────────────────────
    train_pool = Pool(X_tr_c,  label=y_tr,  cat_features=CAT_COLS)
    val_pool   = Pool(X_val_c, label=y_val, cat_features=CAT_COLS)

    cb_model = CatBoostClassifier(
        iterations=NUM_BOOST_ROUND,
        learning_rate=0.05,
        depth=8,
        l2_leaf_reg=3.0,
        min_data_in_leaf=20,
        random_strength=1.0,
        bagging_temperature=1.0,
        od_type="Iter",
        od_wait=200,             # 100 → 200: 大きなデータでは余裕を持たせる
        eval_metric="AUC",
        auto_class_weights="Balanced",
        random_seed=42,
        verbose=False,
    )
    cb_model.fit(train_pool, eval_set=val_pool, use_best_model=True)

    cb_val_pred      = cb_model.predict_proba(X_val_c)[:, 1]
    cb_auc           = roc_auc_score(y_val, cb_val_pred)
    cb_scores.append(cb_auc)
    oof_cb[val_idx]  = cb_val_pred
    test_cb         += cb_model.predict_proba(X_test_cb)[:, 1] / skf.n_splits
    print(f"  CatBoost  best_iter={cb_model.best_iteration_:4d}  AUC={cb_auc:.5f}")

# ── 各モデルの OOF スコア ────────────────────────────────
oof_lgbm_auc = roc_auc_score(y_comp, oof_lgbm)
oof_cb_auc   = roc_auc_score(y_comp, oof_cb)

print(f"\n=== 単体モデル OOF AUC（コンペデータのみで評価）===")
print(f"  LightGBM : {oof_lgbm_auc:.5f}  (各Fold: {np.mean(lgbm_scores):.5f} +/- {np.std(lgbm_scores):.5f})")
print(f"  CatBoost : {oof_cb_auc:.5f}  (各Fold: {np.mean(cb_scores):.5f} +/- {np.std(cb_scores):.5f})")

# ── アンサンブル重みの最適化 ─────────────────────────────
best_auc = 0.0
best_w   = 0.5
for w in np.linspace(0, 1, 101):
    auc = roc_auc_score(y_comp, w * oof_lgbm + (1 - w) * oof_cb)
    if auc > best_auc:
        best_auc = auc
        best_w   = w

print(f"\n=== アンサンブル重み最適化 ===")
print(f"  最適重み: LightGBM={best_w:.2f}  CatBoost={1-best_w:.2f}")
print(f"  OOF AUC (均等 0.5/0.5) : {roc_auc_score(y_comp, 0.5*oof_lgbm + 0.5*oof_cb):.5f}")
print(f"  OOF AUC (最適重み)     : {best_auc:.5f}")
print(f"  外部データ旧CV版        : 0.95933  (参考: 過大評価されていた値)")
print(f"  アンサンブル (外部データなし): 0.94992")
print(f"  改善幅 (vs 外部データなし): {best_auc - 0.94992:+.5f}")

corr = np.corrcoef(oof_lgbm, oof_cb)[0, 1]
print(f"\nLightGBM vs CatBoost の OOF 予測相関: {corr:.4f}")

# ── 提出ファイル作成 ──────────────────────────────────────
test_blend = best_w * test_lgbm + (1 - best_w) * test_cb
submission = pd.DataFrame({"id": test[ID_COL], "PitNextLap": test_blend})
out_path   = OUTPUT_DIR / "submission_improved.csv"
submission.to_csv(out_path, index=False)
print(f"\nSubmission saved -> {out_path}")
print(f"予測確率の統計: mean={test_blend.mean():.4f}  min={test_blend.min():.4f}  max={test_blend.max():.4f}")
