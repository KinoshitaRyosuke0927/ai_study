"""
JEPX 東京エリア電力スポット価格予測 - 特徴量エンジニアリング v10（LightGBM）
v9 から temp_sq を除外（重要度103でほぼノイズのため）
採用特徴量:
  需給バランス : supply_demand_ratio, surplus, contracted_ratio
  ラグ        : price_lag_17520
  気象        : temp, weather_enc
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

# ── weather 補間・エンコード ───────────────────────────────
test["tokyo_price"] = np.nan
combined_weather = pd.concat([train, test], ignore_index=True)
combined_weather["date"] = pd.to_datetime(combined_weather["date"])
combined_weather = combined_weather.sort_values(["date", "frame"]).reset_index(drop=True)
combined_weather["weather"] = combined_weather["weather"].ffill().bfill()
weather_map = {w: i for i, w in enumerate(sorted(combined_weather["weather"].dropna().unique()))}
combined_weather["weather_enc"] = combined_weather["weather"].map(weather_map)
train = train.merge(combined_weather[["id", "weather_enc"]], on="id")
test  = test.drop(columns=["tokyo_price"]).merge(combined_weather[["id", "weather_enc"]], on="id")

# ── 需給バランス特徴量 ─────────────────────────────────────
for df in [train, test]:
    df["supply_demand_ratio"] = df["sell_amount"] / df["buy_amount"]
    df["surplus"]             = df["sell_amount"] - df["buy_amount"]
    df["contracted_ratio"]    = df["contracted_amount"] / df["sell_amount"]

# ── ラグ特徴量 ─────────────────────────────────────────────
test["tokyo_price"] = np.nan
combined = pd.concat([train, test], ignore_index=True)
combined["date"] = pd.to_datetime(combined["date"])
combined = combined.sort_values(["date", "frame"]).reset_index(drop=True)
combined["price_lag_17520"] = combined["tokyo_price"].shift(17520)
train = train.merge(combined[["id", "price_lag_17520"]], on="id")
test  = test.drop(columns=["tokyo_price"]).merge(combined[["id", "price_lag_17520"]], on="id")

# ── 特徴量の定義 ───────────────────────────────────────────
features = [
    "frame", "dayofweek", "is_holiday",
    "temp", "weather_enc",
    "power_result", "power_prediction", "usage_rate", "power_supply",
    "sell_amount", "buy_amount", "contracted_amount",
    "supply_demand_ratio", "surplus", "contracted_ratio",
    "price_lag_17520",
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

print("\n特徴量の重要度:")
importances = sorted(zip(features, model.feature_importances_), key=lambda x: x[1], reverse=True)
for col, imp in importances:
    print(f"  {col}: {imp}")

# ── 予測・提出ファイル生成 ──────────────────────────────────
y_pred = model.predict(X_test)
submission = pd.DataFrame({"id": test["id"], "tokyo_price": y_pred.round(2)})
submission.to_csv("submission_feature_eng_v10.csv", index=False)
print(f"\n予測完了: submission_feature_eng_v10.csv ({len(submission)}件)")
