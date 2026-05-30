import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error

train = pd.read_csv("pre_eval.csv")
test = pd.read_csv("test_eval.csv")


def add_features(df):
    df = df.copy()
    df["area_per_room"] = df["area_m2"] / df["rooms"]
    df["effective_age"] = df["age_years"] * (1 - df["renovation_done"])
    return df


train = add_features(train)
test = add_features(test)

features = ["area_m2", "age_years", "station_walk_min", "floor", "rooms",
            "is_south_facing", "has_parking", "renovation_done", "school_walk_min",
            "area_per_room", "effective_age"]
categorical = ["ward_type"]

X_train = pd.get_dummies(train[features + categorical], columns=categorical)
X_test = pd.get_dummies(test[features + categorical], columns=categorical)
X_train, X_test = X_train.align(X_test, join="left", axis=1, fill_value=0)

y_train = train["price_10kyen"]

model = LinearRegression()
model.fit(X_train, y_train)

y_pred_train = model.predict(X_train)
rmse = np.sqrt(mean_squared_error(y_train, y_pred_train))
print(f"Train RMSE: {rmse:.2f}")

print("\n特徴量の係数:")
for col, coef in sorted(zip(X_train.columns, model.coef_), key=lambda x: abs(x[1]), reverse=True):
    print(f"  {col}: {coef:.2f}")

y_pred_test = model.predict(X_test)

submission = pd.DataFrame({"id": test["id"], "price_10kyen": y_pred_test.astype(int)})
submission.to_csv("submission_feature_eng_v2.csv", index=False)
print(f"\n予測完了: submission_feature_eng_v2.csv ({len(submission)}件)")
