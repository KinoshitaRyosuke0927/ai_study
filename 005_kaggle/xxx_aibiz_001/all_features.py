import numpy as np
import pandas as pd
from sklearn.metrics import mean_squared_error
from sklearn.linear_model import LinearRegression

# データ読み込み
train = pd.read_csv("pre_eval.csv")
test = pd.read_csv("test_eval.csv")

# 特徴量選択
features = ["area_m2", "age_years", "station_walk_min", "floor", "rooms", "is_south_facing", "has_parking", "renovation_done", "school_walk_min"]
categorical = ["ward_type"]

# 前処理
X_train = pd.get_dummies(train[features + categorical], columns=categorical)
X_test = pd.get_dummies(test[features + categorical], columns=categorical)

# 目的変数
y_train = train["price_10kyen"]

# 学習
model = LinearRegression()
model.fit(X_train, y_train)
# 学習データでRMSE計算
y_pred_train = model.predict(X_train)
rmse = np.sqrt(mean_squared_error(y_train, y_pred_train))
print(f"Train RMSE: {rmse:.2f}")

# 予測
y_pred_test = model.predict(X_test)
# 提出用ファイル作成
submission = pd.DataFrame({"id": test["id"], "price_10kyen": y_pred_test.astype(int)})
submission.to_csv("submission_all_features.csv", index=False)
print(f"\n予測完了: submission_all_features.csv ({len(submission)}件)")
