import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import balanced_accuracy_score
import lightgbm as lgb

from features import add_features

# ── パス設定 ──────────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent / "competitions" / "playground-series-s6e4"
OUTPUT_DIR = Path(__file__).parent
OUTPUT_DIR.mkdir(exist_ok=True)

# ── データ読み込み ─────────────────────────────────────────
train = pd.read_csv(DATA_DIR / "train.csv")
test  = pd.read_csv(DATA_DIR / "test.csv")

TARGET = "Irrigation_Need"
ID_COL = "id"

# ── 特徴量エンジニアリング（エンコード前に適用） ────────────
train = add_features(train)
test  = add_features(test)

# ── カテゴリ変数のエンコード ────────────────────────────────
cat_cols = train.select_dtypes(include="object").columns.tolist()
cat_cols = [c for c in cat_cols if c != TARGET]

encoders = {}
for col in cat_cols:
    le = LabelEncoder()
    train[col] = le.fit_transform(train[col].astype(str))
    test[col]  = le.transform(test[col].astype(str))
    encoders[col] = le

le_target = LabelEncoder()
train[TARGET] = le_target.fit_transform(train[TARGET])
print("Target classes:", le_target.classes_)

FEATURES = [c for c in train.columns if c not in [ID_COL, TARGET]]
print(f"Feature count: {len(FEATURES)}  (baseline: 19, added: {len(FEATURES) - 19})")

X = train[FEATURES].values
y = train[TARGET].values
X_test = test[FEATURES].values

# ── LightGBM パラメータ（s6e4_lgbm.py と同一） ────────────
params = {
    "objective": "multiclass",
    "num_class": 3,
    "metric": "multi_logloss",
    "learning_rate": 0.05,
    "num_leaves": 127,
    "max_depth": -1,
    "min_child_samples": 20,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "lambda_l1": 0.1,
    "lambda_l2": 0.1,
    "is_unbalance": True,
    "verbose": -1,
    "seed": 42,
}

# ── 5-Fold CV ──────────────────────────────────────────────
skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

oof_probs  = np.zeros((len(X), 3))
test_probs = np.zeros((len(X_test), 3))
cv_scores  = []

for fold, (tr_idx, val_idx) in enumerate(skf.split(X, y), 1):
    X_tr, X_val = X[tr_idx], X[val_idx]
    y_tr, y_val = y[tr_idx], y[val_idx]

    dtrain = lgb.Dataset(X_tr, label=y_tr, feature_name=FEATURES)
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

    val_prob = model.predict(X_val)
    oof_probs[val_idx] = val_prob

    val_pred = np.argmax(val_prob, axis=1)
    score = balanced_accuracy_score(y_val, val_pred)
    cv_scores.append(score)
    print(f"  Fold {fold}: {score:.4f}  (best iter={model.best_iteration})")

    test_probs += model.predict(X_test) / 5

# ── CV 結果サマリ ──────────────────────────────────────────
oof_pred  = np.argmax(oof_probs, axis=1)
oof_score = balanced_accuracy_score(y, oof_pred)

print(f"\n=== 5-Fold CV Balanced Accuracy ===")
for i, s in enumerate(cv_scores, 1):
    print(f"  Fold {i}: {s:.4f}")
print(f"  Mean : {np.mean(cv_scores):.4f}  ±{np.std(cv_scores):.4f}")
print(f"  OOF  : {oof_score:.4f}")
print(f"\n  baseline (lgbm) : 0.96179")
print(f"  this    (lgbm+fe): {oof_score:.5f}  ({'+' if oof_score > 0.96179 else ''}{oof_score - 0.96179:+.5f})")

# ── 特徴量重要度 Top20 ────────────────────────────────────
importances = pd.Series(
    model.feature_importance(importance_type="gain"), index=FEATURES
)
print("\n=== Feature Importances / gain (Top 20) ===")
print(importances.nlargest(20).to_string())

# ── 追加特徴量の重要度確認 ────────────────────────────────
added_features = [f for f in FEATURES if f not in [
    "Soil_Type", "Soil_pH", "Soil_Moisture", "Organic_Carbon",
    "Electrical_Conductivity", "Temperature_C", "Humidity", "Rainfall_mm",
    "Sunlight_Hours", "Wind_Speed_kmh", "Crop_Type", "Crop_Growth_Stage",
    "Season", "Irrigation_Type", "Water_Source", "Field_Area_hectare",
    "Mulching_Used", "Previous_Irrigation_mm", "Region",
]]
print("\n=== 追加特徴量の重要度 ===")
print(importances[added_features].sort_values(ascending=False).to_string())

# ── 提出ファイル生成 ───────────────────────────────────────
test_pred   = np.argmax(test_probs, axis=1)
pred_labels = le_target.inverse_transform(test_pred)

submission = pd.DataFrame({ID_COL: test[ID_COL], TARGET: pred_labels})
out_path = OUTPUT_DIR / "submission_lgbm_fe.csv"
submission.to_csv(out_path, index=False)
print(f"\nSubmission saved → {out_path}")
print(submission[TARGET].value_counts())
