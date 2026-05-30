"""
住宅価格予測 - 全特徴量使用モデル（LinearRegression）
特徴量: 数値列9つ + ward_type を One-Hot エンコード
"""
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error

# ── データ読み込み ─────────────────────────────────────────
train = pd.read_csv("pre_eval.csv")
test = pd.read_csv("test_eval.csv")

# ── 特徴量の定義 ───────────────────────────────────────────
# ward_type はカテゴリ変数のため One-Hot エンコードで別途処理
features = ["area_m2", "age_years", "station_walk_min", "floor", "rooms",
            "is_south_facing", "has_parking", "renovation_done", "school_walk_min"]
categorical = ["ward_type"]

# ── 前処理（One-Hot エンコード） ────────────────────────────
# テストデータに存在しないカテゴリが学習データにある場合に備え align で列を揃える
X_train = pd.get_dummies(train[features + categorical], columns=categorical)
X_test = pd.get_dummies(test[features + categorical], columns=categorical)
X_train, X_test = X_train.align(X_test, join="left", axis=1, fill_value=0)

y_train = train["price_10kyen"]

# ── 学習・評価 ─────────────────────────────────────────────
model = LinearRegression()
model.fit(X_train, y_train)

y_pred_train = model.predict(X_train)
rmse = np.sqrt(mean_squared_error(y_train, y_pred_train))
print(f"Train RMSE: {rmse:.2f}")

# 係数を絶対値の大きい順に表示し、各特徴量の影響度を確認
print("\n特徴量の係数:")
for col, coef in sorted(zip(X_train.columns, model.coef_), key=lambda x: abs(x[1]), reverse=True):
    print(f"  {col}: {coef:.2f}")

# ── 予測・提出ファイル生成 ──────────────────────────────────
y_pred_test = model.predict(X_test)

submission = pd.DataFrame({"id": test["id"], "price_10kyen": y_pred_test.astype(int)})
submission.to_csv("submission_all_features.csv", index=False)
print(f"\n予測完了: submission_all_features.csv ({len(submission)}件)")
