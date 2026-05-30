import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error

train = pd.read_csv("pre_eval.csv")
test = pd.read_csv("test_eval.csv")

features = ["area_m2", "rooms"]

X_train = train[features]
y_train = train["price_10kyen"]
X_test = test[features]

model = LinearRegression()
model.fit(X_train, y_train)

y_pred_train = model.predict(X_train)
rmse = np.sqrt(mean_squared_error(y_train, y_pred_train))
print(f"Train RMSE: {rmse:.2f}")

y_pred_test = model.predict(X_test)

submission = pd.DataFrame({"id": test["id"], "price_10kyen": y_pred_test.astype(int)})
submission.to_csv("submission_baseline.csv", index=False)
print(f"予測完了: submission_baseline.csv ({len(submission)}件)")
