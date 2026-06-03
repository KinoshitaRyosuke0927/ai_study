import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
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
    # 1部屋あたりの面積: 広い部屋ほど高価格になりやすい
    df["area_per_room"] = df["area_m2"] / df["rooms"].clip(lower=1)

    # 面積 × リノベーション: リノベ済みの広い物件は価値が高い
    df["area_x_renovation"] = df["area_m2"] * df["renovation_done"]

    # 築年数 × リノベーション: 古くてもリノベ済みなら価値が回復する
    df["age_x_renovation"] = df["age_years"] * df["renovation_done"]

    # 駅距離 × 面積: 駅近かつ広い物件は希少で高価格
    df["station_x_area"] = df["station_walk_min"] * df["area_m2"]

    # 階数 × 南向き: 高層階かつ南向きは日当たりが良く価値が高い
    df["floor_x_south"] = df["floor"] * df["is_south_facing"]

    # --- 非線形変換 ---
    # 面積のlog変換: 面積と価格の関係は線形ではなく対数的な傾向がある
    df["log_area"] = np.log1p(df["area_m2"])

    # 築年数のlog変換: 築浅での価値低下が大きく、古くなるほど緩やかになる
    df["log_age"] = np.log1p(df["age_years"])

    # 駅距離のlog変換: 駅近ほど急激に価値が上がる非線形関係を捉える
    df["log_station"] = np.log1p(df["station_walk_min"])

    # --- ward_type のOne-Hot Encoding ---
    # カテゴリ変数として扱い、各区分の価格傾向の違いを学習させる
    for wt in [1, 2, 3]:
        df[f"ward_{wt}"] = (df["ward_type"] == wt).astype(int)

    return df


# 特徴量作成
train_fe = create_features(train)
test_fe = create_features(test)

# 学習に使用する全特徴量カラム（元の特徴量 + 新規特徴量）
feature_cols = [
    # 元の数値特徴量
    "area_m2", "age_years", "station_walk_min", "floor",
    "rooms", "is_south_facing", "has_parking",
    "renovation_done", "school_walk_min",
    # 交互作用特徴量
    "area_per_room", "area_x_renovation", "age_x_renovation",
    "station_x_area", "floor_x_south",
    # 非線形変換（log）
    "log_area", "log_age", "log_station",
    # ward_type のOne-Hot（元のward_typeは除外し、ダミー変数を使用）
    "ward_1", "ward_2", "ward_3",
]

X_train = train_fe[feature_cols]
X_test = test_fe[feature_cols]

# =============================================================================
# ターゲット変換（log変換）
# 価格データは右に裾が長い分布を取りやすいため、log変換で正規分布に近づける。
# これにより、モデルが極端な値に引っ張られにくくなり、予測精度が向上する。
# =============================================================================
y_train_log = np.log1p(train["price_10kyen"])

# モデル学習（log変換したターゲットで学習）
model = GradientBoostingRegressor(
    n_estimators=500,
    max_depth=4,
    learning_rate=0.05,
    subsample=0.8,
    min_samples_leaf=5,
    random_state=42
)
model.fit(X_train, y_train_log)

# 交差検証スコア表示（log空間でのRMSE）
scores = cross_val_score(model, X_train, y_train_log, cv=5, scoring="neg_root_mean_squared_error")
print(f"CV RMSE (log空間): {-scores.mean():.4f} (+/- {scores.std():.4f})")

# 予測（log空間で予測した後、expm1で元のスケールに逆変換）
predictions_log = model.predict(X_test)
predictions = np.expm1(predictions_log)

# 結果をCSVに出力
submission = pd.DataFrame({"id": test["id"], "price_10kyen": predictions})
submission.to_csv("submission.csv", index=False)
print(f"予測完了: submission.csv に {len(submission)} 件出力しました")
