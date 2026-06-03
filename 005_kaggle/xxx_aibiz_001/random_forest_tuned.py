import numpy as np
import pandas as pd
from sklearn.metrics import mean_squared_error
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import KFold, GridSearchCV

# データ読み込み
train = pd.read_csv("pre_eval.csv")
test = pd.read_csv("test_eval.csv")


# 特徴量追加
def add_features(df):
    df = df.copy()
    # 1部屋あたりの広さ
    df["area_per_room"] = df["area_m2"] / df["rooms"]
    # リノベ済み(renovation_done=1)なら実効築年数を0に
    df["effective_age"] = df["age_years"] * (1 - df["renovation_done"])
    # 駅距離は近いほど価格への影響が大きいため対数変換で逓減関係を表現
    df["log_station"] = np.log(df["station_walk_min"])
    return df

# 特徴量追加
train = add_features(train)
test = add_features(test)

# 特徴量選択
features = [
    "area_m2",
    "age_years",
    "station_walk_min",
    "floor",
    "rooms",
    "is_south_facing",
    "has_parking",
    "renovation_done",
    "school_walk_min",
    "area_per_room",
    "effective_age",
    "log_station"
]
categorical = ["ward_type"]

# 前処理
X_train = pd.get_dummies(train[features + categorical], columns=categorical)
X_test = pd.get_dummies(test[features + categorical], columns=categorical)

# 目的変数
y_train = train["price_10kyen"]

# ハイパーパラメータ探索
param_grid = {
    "n_estimators": [100, 300],
    "max_depth": [3, 5, 7, 10],
    "min_samples_leaf": [5, 10, 20],
    "max_features": [0.5, 0.8, 1.0],
}
kf = KFold(n_splits=5, shuffle=True, random_state=42)
grid_search = GridSearchCV(
    RandomForestRegressor(random_state=42),
    param_grid,
    cv=kf,
    scoring="neg_root_mean_squared_error",
    n_jobs=-1,
    verbose=1,
)
grid_search.fit(X_train, y_train)
print(f"\nBest params: {grid_search.best_params_}")
print(f"Best CV RMSE: {-grid_search.best_score_:.2f}")

# 最適モデルで学習・評価
model = grid_search.best_estimator_
# 学習データでRMSE計算
y_pred_train = model.predict(X_train)
train_rmse = np.sqrt(mean_squared_error(y_train, y_pred_train))
print(f"Train RMSE: {train_rmse:.2f}")

# 予測
y_pred_test = model.predict(X_test)
# 提出用ファイル作成
submission = pd.DataFrame({"id": test["id"], "price_10kyen": y_pred_test.astype(int)})
submission.to_csv("submission_rf_tuned.csv", index=False)
print(f"\n予測完了: submission_rf_tuned.csv ({len(submission)}件)")
