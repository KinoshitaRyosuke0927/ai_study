"""
Step1: frame/month の sin/cos エンコーディング追加
ベース: walk_forward.py (RMSE 3.1831)
追加特徴量: frame_sin, frame_cos, month_sin, month_cos
"""
import pandas as pd
import numpy as np
from lightgbm import LGBMRegressor, early_stopping
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import TimeSeriesSplit

train = pd.read_csv("../pre_eval.csv")
test  = pd.read_csv("../test_eval.csv")

train["date"] = pd.to_datetime(train["date"])
test["date"]  = pd.to_datetime(test["date"])

median_temp = train["temp"].median()
train["temp"] = train["temp"].fillna(median_temp)
test["temp"]  = test["temp"].fillna(median_temp)

test["tokyo_price"] = np.nan
combined_weather = pd.concat([train, test], ignore_index=True)
combined_weather = combined_weather.sort_values(["date", "frame"]).reset_index(drop=True)
combined_weather["weather"] = combined_weather["weather"].ffill().bfill()
weather_map = {w: i for i, w in enumerate(sorted(combined_weather["weather"].dropna().unique()))}
combined_weather["weather_enc"] = combined_weather["weather"].map(weather_map)
train = train.merge(combined_weather[["id", "weather_enc"]], on="id")
test  = test.drop(columns=["tokyo_price"]).merge(combined_weather[["id", "weather_enc"]], on="id")

for df in [train, test]:
    df["supply_demand_ratio"] = df["sell_amount"] / df["buy_amount"]
    df["surplus"]             = df["sell_amount"] - df["buy_amount"]
    df["contracted_ratio"]    = df["contracted_amount"] / df["sell_amount"]
    df["temp_sq"]             = df["temp"] ** 2
    # ── Step1: sin/cos エンコーディング ──
    df["frame_sin"]  = np.sin(2 * np.pi * df["frame"] / 48)
    df["frame_cos"]  = np.cos(2 * np.pi * df["frame"] / 48)
    df["month_sin"]  = np.sin(2 * np.pi * df["date"].dt.month / 12)
    df["month_cos"]  = np.cos(2 * np.pi * df["date"].dt.month / 12)

train_sorted = train.sort_values(["date", "frame"]).reset_index(drop=True)
train_sorted["price_lag_48"]    = train_sorted["tokyo_price"].shift(48)
train_sorted["price_lag_96"]    = train_sorted["tokyo_price"].shift(96)
train_sorted["price_lag_336"]   = train_sorted["tokyo_price"].shift(336)
train_sorted["price_lag_17520"] = train_sorted["tokyo_price"].shift(17520)

lag_cols = ["price_lag_48", "price_lag_96", "price_lag_336", "price_lag_17520"]
base_features = [
    "frame", "dayofweek", "is_holiday",
    "temp", "temp_sq", "weather_enc",
    "power_result", "power_prediction", "usage_rate", "power_supply",
    "sell_amount", "buy_amount", "contracted_amount",
    "supply_demand_ratio", "surplus", "contracted_ratio",
    "frame_sin", "frame_cos", "month_sin", "month_cos",  # Step1追加
]
features = base_features + lag_cols

X_train = train_sorted[features]
y_train = train_sorted["tokyo_price"]

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

model = LGBMRegressor(n_estimators=1000, learning_rate=0.05, random_state=42, verbose=-1)
model.fit(X_train, y_train)

train_rmse = np.sqrt(mean_squared_error(y_train, model.predict(X_train)))
print(f"Train RMSE: {train_rmse:.4f}")

price_buffer = {
    (row["date"], row["frame"]): row["tokyo_price"]
    for _, row in train_sorted.iterrows()
}

test_dates = sorted(test["date"].unique())
all_preds  = []

print(f"\nウォークフォワード予測開始: {len(test_dates)} 日分")

for date in test_dates:
    day_df = test[test["date"] == date].sort_values("frame").copy()

    for lag_name, delta_days in [("price_lag_48",    1),
                                  ("price_lag_96",    2),
                                  ("price_lag_336",   7),
                                  ("price_lag_17520", 365)]:
        ref_date = date - pd.Timedelta(days=delta_days)
        day_df[lag_name] = day_df["frame"].map(
            lambda f, rd=ref_date: price_buffer.get((rd, f), np.nan)
        )

    preds = model.predict(day_df[features])

    for frame, pred in zip(day_df["frame"], preds):
        price_buffer[(date, frame)] = pred

    all_preds.append(day_df[["id"]].assign(tokyo_price=preds.round(2)))
    print(f"  {date.date()} 予測完了")

submission = pd.concat(all_preds, ignore_index=True)
submission.to_csv("submission_step1.csv", index=False)
print(f"\n予測完了: submission_step1.csv ({len(submission)}件)")
