"""
住宅価格予測 - 特徴量エンジニアリング v3（LinearRegression）
追加特徴量:
  - area_per_room  : 1部屋あたりの面積（area_m2 と rooms の多重共線性を整理）
  - effective_age  : リノベ済みの場合に築年数の影響を打ち消す交互作用項
  - log_station    : 駅距離の非線形変換（近いほど効果が大きい逓減関係を表現）
"""
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import KFold

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

# ── クロスバリデーション ────────────────────────────────────
# 200件と少ないデータのため 5-Fold CV で汎化性能を確認
kf = KFold(n_splits=5, shuffle=True, random_state=42)
cv_rmses = []
for fold, (tr_idx, val_idx) in enumerate(kf.split(X_train)):
    X_tr, X_val = X_train.iloc[tr_idx], X_train.iloc[val_idx]
    y_tr, y_val = y_train.iloc[tr_idx], y_train.iloc[val_idx]
    m = LinearRegression()
    m.fit(X_tr, y_tr)
    val_rmse = np.sqrt(mean_squared_error(y_val, m.predict(X_val)))
    cv_rmses.append(val_rmse)
    print(f"  Fold {fold+1} Val RMSE: {val_rmse:.2f}")
print(f"CV RMSE: {np.mean(cv_rmses):.2f} ± {np.std(cv_rmses):.2f}")

# ── 学習・評価 ─────────────────────────────────────────────
# CV 後に全学習データで最終モデルを学習
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
submission.to_csv("submission_feature_eng_v3.csv", index=False)
print(f"\n予測完了: submission_feature_eng_v3.csv ({len(submission)}件)")
