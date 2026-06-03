import pandas as pd
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_score

# データ読み込み
train = pd.read_csv("pre_eval.csv")
test = pd.read_csv("test_eval.csv")

# =============================================================================
# 特徴量エンジニアリング
# =============================================================================

def create_features(df):
    """元の特徴量に加え、交互作用・非線形変換の特徴量を追加する"""
    df = df.copy()

    # --- 交互作用特徴量 ---
    df["area_per_room"] = df["area_m2"] / df["rooms"].clip(lower=1)
    df["area_x_renovation"] = df["area_m2"] * df["renovation_done"]
    df["age_x_renovation"] = df["age_years"] * df["renovation_done"]
    df["station_x_area"] = df["station_walk_min"] * df["area_m2"]
    df["floor_x_south"] = df["floor"] * df["is_south_facing"]

    # --- 非線形変換 ---
    df["log_area"] = np.log1p(df["area_m2"])
    df["log_age"] = np.log1p(df["age_years"])
    df["log_station"] = np.log1p(df["station_walk_min"])

    # --- ward_type のOne-Hot Encoding ---
    for wt in [1, 2, 3]:
        df[f"ward_{wt}"] = (df["ward_type"] == wt).astype(int)

    return df


# 特徴量作成
train_fe = create_features(train)
test_fe = create_features(test)

# 学習に使用する特徴量カラム
feature_cols = [
    "area_m2", "age_years", "station_walk_min", "floor",
    "rooms", "is_south_facing", "has_parking",
    "renovation_done", "school_walk_min",
    "area_per_room", "area_x_renovation", "age_x_renovation",
    "station_x_area", "floor_x_south",
    "log_area", "log_age", "log_station",
    "ward_1", "ward_2", "ward_3",
]

X_train = train_fe[feature_cols]
X_test = test_fe[feature_cols]

# =============================================================================
# ターゲット変換（log変換）
# =============================================================================
y_train_log = np.log1p(train["price_10kyen"])

# =============================================================================
# 標準化（Ridge回帰は特徴量のスケールに敏感なため、標準化が必須）
# =============================================================================
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

# =============================================================================
# Ridge回帰モデル
# L2正則化により過学習を抑制し、少ないデータでも安定した予測が可能
# =============================================================================
model = Ridge(alpha=10.0, random_state=42)
model.fit(X_train_scaled, y_train_log)

# 交差検証スコア表示（log空間でのRMSE）
scores = cross_val_score(model, X_train_scaled, y_train_log, cv=5, scoring="neg_root_mean_squared_error")
print(f"CV RMSE (log空間): {-scores.mean():.4f} (+/- {scores.std():.4f})")

# 予測（log空間で予測した後、expm1で元のスケールに逆変換）
predictions_log = model.predict(X_test_scaled)
predictions = np.expm1(predictions_log)

# 結果をCSVに出力
submission = pd.DataFrame({"id": test["id"], "price_10kyen": predictions})
submission.to_csv("submission.csv", index=False)
print(f"予測完了: submission.csv に {len(submission)} 件出力しました")
