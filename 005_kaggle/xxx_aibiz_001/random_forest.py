import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import KFold

train = pd.read_csv("pre_eval.csv")
test = pd.read_csv("test_eval.csv")


def add_features(df):
    df = df.copy()
    df["area_per_room"] = df["area_m2"] / df["rooms"]
    df["effective_age"] = df["age_years"] * (1 - df["renovation_done"])
    df["log_station"] = np.log(df["station_walk_min"])
    return df


train = add_features(train)
test = add_features(test)

features = ["area_m2", "age_years", "station_walk_min", "floor", "rooms",
            "is_south_facing", "has_parking", "renovation_done", "school_walk_min",
            "area_per_room", "effective_age", "log_station"]
categorical = ["ward_type"]

X_train = pd.get_dummies(train[features + categorical], columns=categorical)
X_test = pd.get_dummies(test[features + categorical], columns=categorical)
X_train, X_test = X_train.align(X_test, join="left", axis=1, fill_value=0)

y_train = train["price_10kyen"]

kf = KFold(n_splits=5, shuffle=True, random_state=42)
cv_rmses = []
for fold, (tr_idx, val_idx) in enumerate(kf.split(X_train)):
    X_tr, X_val = X_train.iloc[tr_idx], X_train.iloc[val_idx]
    y_tr, y_val = y_train.iloc[tr_idx], y_train.iloc[val_idx]
    m = RandomForestRegressor(n_estimators=100, random_state=42)
    m.fit(X_tr, y_tr)
    val_rmse = np.sqrt(mean_squared_error(y_val, m.predict(X_val)))
    cv_rmses.append(val_rmse)
    print(f"  Fold {fold+1} Val RMSE: {val_rmse:.2f}")
print(f"CV RMSE: {np.mean(cv_rmses):.2f} ± {np.std(cv_rmses):.2f}")

model = RandomForestRegressor(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

y_pred_train = model.predict(X_train)
rmse = np.sqrt(mean_squared_error(y_train, y_pred_train))
print(f"Train RMSE: {rmse:.2f}")

print("\n特徴量の重要度:")
importances = sorted(zip(X_train.columns, model.feature_importances_), key=lambda x: x[1], reverse=True)
for col, imp in importances:
    print(f"  {col}: {imp:.4f}")

y_pred_test = model.predict(X_test)

submission = pd.DataFrame({"id": test["id"], "price_10kyen": y_pred_test.astype(int)})
submission.to_csv("submission_random_forest.csv", index=False)
print(f"\n予測完了: submission_random_forest.csv ({len(submission)}件)")
