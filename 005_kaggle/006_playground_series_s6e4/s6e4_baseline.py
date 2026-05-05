import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import balanced_accuracy_score

"""
https://www.kaggle.com/competitions/playground-series-s6e4/overview
"""

# ── パス設定 ──────────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent / "competitions" / "playground-series-s6e4"
OUTPUT_DIR = Path(__file__).parent
OUTPUT_DIR.mkdir(exist_ok=True)

# ── データ読み込み ─────────────────────────────────────────
train = pd.read_csv(DATA_DIR / "train.csv")
test  = pd.read_csv(DATA_DIR / "test.csv")

TARGET = "Irrigation_Need"
ID_COL = "id"

# ── カテゴリ変数のエンコード ────────────────────────────────
cat_cols = train.select_dtypes(include="object").columns.tolist()
cat_cols = [c for c in cat_cols if c != TARGET]

encoders = {}
for col in cat_cols:
    le = LabelEncoder()
    train[col] = le.fit_transform(train[col].astype(str))
    test[col]  = le.transform(test[col].astype(str))
    encoders[col] = le

# ターゲットもエンコード（High=0, Low=1, Medium=2 → そのまま保持）
le_target = LabelEncoder()
train[TARGET] = le_target.fit_transform(train[TARGET])
# クラス確認
print("Target classes:", le_target.classes_)  # ['High', 'Low', 'Medium']

FEATURES = [c for c in train.columns if c not in [ID_COL, TARGET]]
X = train[FEATURES]
y = train[TARGET]
X_test = test[FEATURES]

# ── モデル定義（class_weight='balanced'） ──────────────────
model = RandomForestClassifier(
    n_estimators=300,
    max_depth=None,
    class_weight="balanced",   # 少数クラスを自動で重み付け
    random_state=42,
    n_jobs=-1,
)

# ── CV で balanced_accuracy_score を評価 ───────────────────
skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

cv_scores = cross_val_score(
    model, X, y,
    cv=skf,
    scoring="balanced_accuracy",
    n_jobs=-1,
)

print(f"\n=== 5-Fold CV Balanced Accuracy ===")
for i, s in enumerate(cv_scores, 1):
    print(f"  Fold {i}: {s:.4f}")
print(f"  Mean : {cv_scores.mean():.4f}  ±{cv_scores.std():.4f}")

# ── 全データで再学習して予測 ───────────────────────────────
model.fit(X, y)

# 学習データへの適合確認
train_pred = model.predict(X)
train_score = balanced_accuracy_score(y, train_pred)
print(f"\nTrain Balanced Accuracy : {train_score:.4f}")

# ── 特徴量重要度 Top15 ────────────────────────────────────
importances = pd.Series(model.feature_importances_, index=FEATURES)
print("\n=== Feature Importances (Top 15) ===")
print(importances.nlargest(15).to_string())

# ── 提出ファイル生成 ───────────────────────────────────────
pred_labels = le_target.inverse_transform(model.predict(X_test))

submission = pd.DataFrame({
    ID_COL: test[ID_COL],
    TARGET: pred_labels,
})
out_path = OUTPUT_DIR / "submission_baseline.csv"
submission.to_csv(out_path, index=False)
print(f"\nSubmission saved → {out_path}")
print(submission[TARGET].value_counts())
