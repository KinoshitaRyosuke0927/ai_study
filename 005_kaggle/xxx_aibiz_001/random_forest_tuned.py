"""
住宅価格予測 - Random Forest ハイパーパラメータ調整
GridSearchCV で以下を探索:
  - max_depth       : 木の深さ上限（小さいほど過学習を抑制）
  - min_samples_leaf: 葉の最小サンプル数（大きいほど汎化しやすい）
  - max_features    : 各分岐で使う特徴量の割合（小さいほど多様な木が生成される）
  - n_estimators    : 決定木の本数
"""
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import KFold, GridSearchCV

# ── データ読み込み ─────────────────────────────────────────
train = pd.read_csv("pre_eval.csv")
test = pd.read_csv("test_eval.csv")


# ── 特徴量エンジニアリング ─────────────────────────────────
def add_features(df):
    df = df.copy()
    # 1部屋あたりの広さ: area_m2 と rooms の相関が高いため合成特徴量を作成
    df["area_per_room"] = df["area_m2"] / df["rooms"]
    # リノベ済み(renovation_done=1)なら実効築年数を 0 に圧縮
    df["effective_age"] = df["age_years"] * (1 - df["renovation_done"])
    # 駅距離は近いほど価格への影響が大きいため対数変換で逓減関係を表現
    df["log_station"] = np.log(df["station_walk_min"])
    return df


train = add_features(train)
test = add_features(test)

# ── 特徴量の定義 ───────────────────────────────────────────
features = ["area_m2", "age_years", "station_walk_min", "floor", "rooms",
            "is_south_facing", "has_parking", "renovation_done", "school_walk_min",
            "area_per_room", "effective_age", "log_station"]
categorical = ["ward_type"]

# ── 前処理（One-Hot エンコード） ────────────────────────────
X_train = pd.get_dummies(train[features + categorical], columns=categorical)
X_test = pd.get_dummies(test[features + categorical], columns=categorical)
X_train, X_test = X_train.align(X_test, join="left", axis=1, fill_value=0)

y_train = train["price_10kyen"]

# ── ハイパーパラメータ探索（GridSearchCV） ──────────────────
# 2×4×3×3 = 72通りを 5-Fold CV で評価
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

# ── 学習・評価 ─────────────────────────────────────────────
# GridSearchCV が選んだベストパラメータで全学習データを再学習済みのモデルを使用
model = grid_search.best_estimator_

y_pred_train = model.predict(X_train)
train_rmse = np.sqrt(mean_squared_error(y_train, y_pred_train))
print(f"Train RMSE: {train_rmse:.2f}")

# 特徴量重要度を大きい順に表示
print("\n特徴量の重要度:")
importances = sorted(zip(X_train.columns, model.feature_importances_), key=lambda x: x[1], reverse=True)
for col, imp in importances:
    print(f"  {col}: {imp:.4f}")

# ── 予測・提出ファイル生成 ──────────────────────────────────
y_pred_test = model.predict(X_test)

submission = pd.DataFrame({"id": test["id"], "price_10kyen": y_pred_test.astype(int)})
submission.to_csv("submission_rf_tuned.csv", index=False)
print(f"\n予測完了: submission_rf_tuned.csv ({len(submission)}件)")
