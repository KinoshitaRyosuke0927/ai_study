"""
JEPX 東京エリア電力スポット価格予測 - 特徴量エンジニアリング v3（LightGBM）
feature_eng_v2 にラグ特徴量・ローリング統計量を追加
追加特徴量:
  - price_lag_48          : 48フレーム前（24時間前）の価格
  - price_lag_96          : 96フレーム前（48時間前）の価格
  - price_lag_336         : 336フレーム前（1週間前）の価格
  - price_rolling_mean_48 : 直近48フレームの価格移動平均

注意: テストデータのラグ特徴量は参照先がテスト期間内の行は NaN になる。
      LightGBM は NaN を欠損値として扱えるため、学習・予測ともに問題なし。
"""
import pandas as pd
import numpy as np
from lightgbm import LGBMRegressor, early_stopping
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import TimeSeriesSplit

# ── データ読み込み ─────────────────────────────────────────
train = pd.read_csv("../pre_eval.csv")
test  = pd.read_csv("../test_eval.csv")

median_temp = train["temp"].median()
train["temp"] = train["temp"].fillna(median_temp)
test["temp"]  = test["temp"].fillna(median_temp)


# ── 需給バランス特徴量（v2から継続） ──────────────────────
def add_demand_features(df):
    df = df.copy()
    df["supply_demand_ratio"] = df["sell_amount"] / df["buy_amount"]
    df["surplus"]             = df["sell_amount"] - df["buy_amount"]
    return df


train = add_demand_features(train)
test  = add_demand_features(test)

# ── ラグ特徴量の計算 ───────────────────────────────────────
# 学習・テストを結合してラグを計算し、テスト期間のラグ先も訓練データから参照できるようにする
test["tokyo_price"] = np.nan
combined = pd.concat([train, test], ignore_index=True)

# shift はデータの並び順（date/frame 昇順）に依存するため事前にソート
combined["date"] = pd.to_datetime(combined["date"])
combined = combined.sort_values(["date", "frame"]).reset_index(drop=True)

combined["price_lag_48"]          = combined["tokyo_price"].shift(48)
combined["price_lag_96"]          = combined["tokyo_price"].shift(96)
combined["price_lag_336"]         = combined["tokyo_price"].shift(336)
# shift(1) で当該フレームの価格リークを防いだうえでローリング平均を計算
combined["price_rolling_mean_48"] = combined["tokyo_price"].shift(1).rolling(48, min_periods=1).mean()

# 学習・テストに分割
lag_cols = ["id", "price_lag_48", "price_lag_96", "price_lag_336", "price_rolling_mean_48"]
train = train.drop(columns=["tokyo_price"], errors="ignore")
train["tokyo_price"] = combined.loc[combined["id"].isin(train["id"]), "tokyo_price"].values

train = train.merge(combined[lag_cols], on="id")
test  = test.drop(columns=["tokyo_price"]).merge(combined[lag_cols], on="id")

# ── 特徴量の定義 ───────────────────────────────────────────
features = [
    "frame", "dayofweek", "is_holiday",
    "temp",
    "power_result", "power_prediction", "usage_rate", "power_supply",
    "sell_amount", "buy_amount", "contracted_amount",
    "supply_demand_ratio", "surplus",
    "price_lag_48", "price_lag_96", "price_lag_336",
    "price_rolling_mean_48",
]

X_train = train[features]
y_train = train["tokyo_price"]
X_test  = test[features]

# ── 時系列クロスバリデーション ─────────────────────────────
tscv = TimeSeriesSplit(n_splits=5)
cv_rmses = []

for fold, (tr_idx, val_idx) in enumerate(tscv.split(X_train)):
    X_tr, X_val = X_train.iloc[tr_idx], X_train.iloc[val_idx]
    y_tr, y_val = y_train.iloc[tr_idx], y_train.iloc[val_idx]
    m = LGBMRegressor(n_estimators=1000, learning_rate=0.05, random_state=42, verbose=-1)
    m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
          callbacks=[early_stopping(50, verbose=False)])
    val_rmse = np.sqrt(mean_squared_error(y_val, m.predict(X_val)))
    cv_rmses.append(val_rmse)
    print(f"  Fold {fold+1} Val RMSE: {val_rmse:.4f}")

print(f"CV RMSE: {np.mean(cv_rmses):.4f} ± {np.std(cv_rmses):.4f}")

# ── 全学習データで最終モデルを学習 ─────────────────────────
model = LGBMRegressor(n_estimators=1000, learning_rate=0.05, random_state=42, verbose=-1)
model.fit(X_train, y_train)

train_rmse = np.sqrt(mean_squared_error(y_train, model.predict(X_train)))
print(f"Train RMSE: {train_rmse:.4f}")

# 特徴量重要度を大きい順に表示
print("\n特徴量の重要度:")
importances = sorted(zip(features, model.feature_importances_), key=lambda x: x[1], reverse=True)
for col, imp in importances:
    print(f"  {col}: {imp}")

# ── 予測・提出ファイル生成 ──────────────────────────────────
y_pred = model.predict(X_test)

submission = pd.DataFrame({"id": test["id"], "tokyo_price": y_pred.round(2)})
submission.to_csv("submission_feature_eng_v3.csv", index=False)
print(f"\n予測完了: submission_feature_eng_v3.csv ({len(submission)}件)")
