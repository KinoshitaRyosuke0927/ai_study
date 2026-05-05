"""
https://www.kaggle.com/competitions/playground-series-s6e5/overview
F1 ピットストップ予測 ベースライン
目標: PitNextLap の確率を予測（評価指標: ROC-AUC）

アプローチ:
  - LightGBM + StratifiedKFold (5-Fold)
  - カテゴリ変数: Driver, Compound, Race → Label Encoding
  - クラス不均衡 (PitNextLap=1 が約 20%) → is_unbalance=True
  - F1 ドメイン知識に基づく特徴量エンジニアリング
"""
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score
import lightgbm as lgb

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
print(f"Target 分布:\n{train[TARGET].value_counts(normalize=True).round(4)}")

# ── 特徴量エンジニアリング ─────────────────────────────────
def add_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # タイヤ劣化の非線形性: タイヤは後半ほど急速に劣化する
    df["TyreLife_sq"]   = df["TyreLife"] ** 2
    df["TyreLife_sqrt"] = np.sqrt(df["TyreLife"].clip(0))

    # 劣化速度 = 累積劣化 / タイヤ寿命（1周あたりの平均劣化量）
    df["Degradation_Rate"] = df["Cumulative_Degradation"] / (df["TyreLife"] + 1)

    # コンパウンドの耐久性を順序数値に変換
    # SOFT=1(最も劣化が速い) < MEDIUM=2 < HARD=3 < INTERMEDIATE=4 < WET=5
    compound_durability = {"SOFT": 1, "MEDIUM": 2, "HARD": 3, "INTERMEDIATE": 4, "WET": 5}
    df["Compound_Dur"] = df["Compound"].map(compound_durability).fillna(2)

    # タイヤ寿命 × コンパウンド耐久性（コンパウンドを考慮した消耗度）
    df["TyreLife_x_Dur"] = df["TyreLife"] / df["Compound_Dur"]

    # スティント内の相対的な位置（この周が何%消化されたか）
    # RaceProgress を利用（各スティントの始まりは把握できないため代替）
    df["LapTime_Norm"] = df["LapTime (s)"] / (df["LapTime (s)"].mean())

    # ピット直前シグナル: 現在ピットした周 (PitStop=1) の翌周も高確率でピット？
    # → PitStop=1 のデータは「今の周にピットした」→ 次周もピットする可能性は低い
    # ただし連続ピットも稀にあるため特徴として残す

    # 位置が悪いほど戦略的ピット（アンダーカット）の動機が強い
    df["Position_sq"] = df["Position"] ** 2

    # レース進行度 × タイヤ寿命（ピット戦略の合理的なタイミング）
    df["Progress_x_TyreLife"] = df["RaceProgress"] * df["TyreLife"]

    return df

train = add_features(train)
test  = add_features(test)

# ── カテゴリ変数のエンコード ────────────────────────────────
cat_cols = ["Driver", "Compound", "Race"]
encoders = {}
for col in cat_cols:
    le = LabelEncoder()
    combined = pd.concat([train[col], test[col]], axis=0).astype(str)
    le.fit(combined)
    train[col] = le.transform(train[col].astype(str))
    test[col]  = le.transform(test[col].astype(str))
    encoders[col] = le

# ── 特徴量リスト ──────────────────────────────────────────
DROP_COLS = [ID_COL, TARGET]
FEATURES  = [c for c in train.columns if c not in DROP_COLS]
print(f"\n使用特徴量 ({len(FEATURES)} 個): {FEATURES}")

X      = train[FEATURES].values
y      = train[TARGET].values
X_test = test[FEATURES].values

# ── LightGBM パラメータ ────────────────────────────────────
params = {
    "objective":        "binary",
    "metric":           "auc",
    "learning_rate":    0.05,
    "num_leaves":       127,
    "max_depth":        -1,
    "min_child_samples": 20,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq":     1,
    "lambda_l1":        0.1,
    "lambda_l2":        0.1,
    "is_unbalance":     True,   # クラス不均衡を自動補正（PitNextLap=1 が約 20%）
    "verbose":          -1,
    "seed":             42,
}

# ── 5-Fold CV ──────────────────────────────────────────────
skf        = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
oof_probs  = np.zeros(len(X))
test_probs = np.zeros(len(X_test))
cv_scores  = []

print("\n=== 5-Fold Cross Validation ===")

for fold, (tr_idx, val_idx) in enumerate(skf.split(X, y), 1):
    X_tr,  X_val  = X[tr_idx],  X[val_idx]
    y_tr,  y_val  = y[tr_idx],  y[val_idx]

    dtrain = lgb.Dataset(X_tr,  label=y_tr,  feature_name=FEATURES)
    dval   = lgb.Dataset(X_val, label=y_val, reference=dtrain)

    model = lgb.train(
        params,
        dtrain,
        num_boost_round=2000,
        valid_sets=[dval],
        callbacks=[
            lgb.early_stopping(stopping_rounds=100, verbose=False),
            lgb.log_evaluation(period=200),
        ],
    )

    val_pred  = model.predict(X_val)
    fold_auc  = roc_auc_score(y_val, val_pred)
    cv_scores.append(fold_auc)
    oof_probs[val_idx] = val_pred

    test_probs += model.predict(X_test) / skf.n_splits

    print(f"  Fold {fold}  best_iter={model.best_iteration:4d}  AUC={fold_auc:.5f}")

oof_auc = roc_auc_score(y, oof_probs)
print(f"\nOOF AUC: {oof_auc:.5f}  (各Fold平均: {np.mean(cv_scores):.5f} ± {np.std(cv_scores):.5f})")

# ── 特徴量重要度 ───────────────────────────────────────────
fi = pd.DataFrame({"feature": FEATURES, "importance": model.feature_importance("gain")})
fi = fi.sort_values("importance", ascending=False)
print("\n=== 特徴量重要度 (Top 15) ===")
print(fi.head(15).to_string(index=False))

# ── 提出ファイル作成 ──────────────────────────────────────
submission = pd.DataFrame({"id": test[ID_COL], "PitNextLap": test_probs})
out_path   = OUTPUT_DIR / "submission_baseline.csv"
submission.to_csv(out_path, index=False)
print(f"\nSubmission saved → {out_path}")
print(f"予測確率の統計: mean={test_probs.mean():.4f}  min={test_probs.min():.4f}  max={test_probs.max():.4f}")
