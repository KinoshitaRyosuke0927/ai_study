"""
JEPX 東京エリア電力スポット価格予測 - ウォークフォワード予測 v2

【v1 からの変更点】
  - ラグ特徴量を拡充（3〜6日前: lag_144/192/240/288）
  - LightGBM + XGBoost のアンサンブル（単純平均）

【アンサンブルの意図】
  LightGBM と XGBoost は木の構築アルゴリズムが異なるため
  予測誤差の相関が低くなりやすく、平均を取ると分散が下がる
"""
import pandas as pd
import numpy as np
from lightgbm import LGBMRegressor, early_stopping as lgb_early_stopping
from xgboost import XGBRegressor
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import TimeSeriesSplit

# ── データ読み込み ─────────────────────────────────────────
train = pd.read_csv("../pre_eval.csv")
test  = pd.read_csv("../test_eval.csv")

train["date"] = pd.to_datetime(train["date"])
test["date"]  = pd.to_datetime(test["date"])

median_temp = train["temp"].median()
train["temp"] = train["temp"].fillna(median_temp)
test["temp"]  = test["temp"].fillna(median_temp)

# ── weather 補間・エンコード ───────────────────────────────
test["tokyo_price"] = np.nan
combined_weather = pd.concat([train, test], ignore_index=True)
combined_weather = combined_weather.sort_values(["date", "frame"]).reset_index(drop=True)
combined_weather["weather"] = combined_weather["weather"].ffill().bfill()
weather_map = {w: i for i, w in enumerate(sorted(combined_weather["weather"].dropna().unique()))}
combined_weather["weather_enc"] = combined_weather["weather"].map(weather_map)
train = train.merge(combined_weather[["id", "weather_enc"]], on="id")
test  = test.drop(columns=["tokyo_price"]).merge(combined_weather[["id", "weather_enc"]], on="id")

# ── 需給バランス・派生特徴量 ───────────────────────────────
for df in [train, test]:
    df["supply_demand_ratio"] = df["sell_amount"] / df["buy_amount"]
    df["surplus"]             = df["sell_amount"] - df["buy_amount"]
    df["contracted_ratio"]    = df["contracted_amount"] / df["sell_amount"]
    df["temp_sq"]             = df["temp"] ** 2

# ── 学習データのラグ特徴量を shift() で構築 ────────────────
train_sorted = train.sort_values(["date", "frame"]).reset_index(drop=True)
train_sorted["price_lag_48"]    = train_sorted["tokyo_price"].shift(48)
train_sorted["price_lag_96"]    = train_sorted["tokyo_price"].shift(96)
train_sorted["price_lag_144"]   = train_sorted["tokyo_price"].shift(144)   # 3日前
train_sorted["price_lag_192"]   = train_sorted["tokyo_price"].shift(192)   # 4日前
train_sorted["price_lag_240"]   = train_sorted["tokyo_price"].shift(240)   # 5日前
train_sorted["price_lag_288"]   = train_sorted["tokyo_price"].shift(288)   # 6日前
train_sorted["price_lag_336"]   = train_sorted["tokyo_price"].shift(336)   # 7日前
train_sorted["price_lag_17520"] = train_sorted["tokyo_price"].shift(17520) # 1年前

# ── 特徴量の定義 ───────────────────────────────────────────
lag_cols = [
    "price_lag_48", "price_lag_96",
    "price_lag_144", "price_lag_192", "price_lag_240", "price_lag_288",
    "price_lag_336", "price_lag_17520",
]
base_features = [
    "frame", "dayofweek", "is_holiday",
    "temp", "temp_sq", "weather_enc",
    "power_result", "power_prediction", "usage_rate", "power_supply",
    "sell_amount", "buy_amount", "contracted_amount",
    "supply_demand_ratio", "surplus", "contracted_ratio",
]
features = base_features + lag_cols

# ── 学習 ───────────────────────────────────────────────────
X_train = train_sorted[features]
y_train = train_sorted["tokyo_price"]

tscv = TimeSeriesSplit(n_splits=5)
lgb_cv_rmses = []
xgb_cv_rmses = []
ens_cv_rmses = []

print("=== Cross Validation ===")
for fold, (tr_idx, val_idx) in enumerate(tscv.split(X_train)):
    X_tr, X_val = X_train.iloc[tr_idx], X_train.iloc[val_idx]
    y_tr, y_val = y_train.iloc[tr_idx], y_train.iloc[val_idx]

    # LightGBM
    lgb_m = LGBMRegressor(n_estimators=1000, learning_rate=0.05, random_state=42, verbose=-1)
    lgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
              callbacks=[lgb_early_stopping(50, verbose=False)])
    lgb_pred = lgb_m.predict(X_val)

    # XGBoost
    xgb_m = XGBRegressor(
        n_estimators=1000, learning_rate=0.05, random_state=42,
        verbosity=0, early_stopping_rounds=50,
    )
    xgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
    xgb_pred = xgb_m.predict(X_val)

    ens_pred = (lgb_pred + xgb_pred) / 2

    lgb_rmse = np.sqrt(mean_squared_error(y_val, lgb_pred))
    xgb_rmse = np.sqrt(mean_squared_error(y_val, xgb_pred))
    ens_rmse = np.sqrt(mean_squared_error(y_val, ens_pred))
    lgb_cv_rmses.append(lgb_rmse)
    xgb_cv_rmses.append(xgb_rmse)
    ens_cv_rmses.append(ens_rmse)
    print(f"  Fold {fold+1}  LGB: {lgb_rmse:.4f}  XGB: {xgb_rmse:.4f}  Ensemble: {ens_rmse:.4f}")

print(f"CV RMSE  LGB: {np.mean(lgb_cv_rmses):.4f} ± {np.std(lgb_cv_rmses):.4f}")
print(f"CV RMSE  XGB: {np.mean(xgb_cv_rmses):.4f} ± {np.std(xgb_cv_rmses):.4f}")
print(f"CV RMSE  Ens: {np.mean(ens_cv_rmses):.4f} ± {np.std(ens_cv_rmses):.4f}")

# ── 全データで最終モデルを学習 ─────────────────────────────
print("\n=== 最終モデル学習 ===")
lgb_model = LGBMRegressor(n_estimators=1000, learning_rate=0.05, random_state=42, verbose=-1)
lgb_model.fit(X_train, y_train)

xgb_model = XGBRegressor(
    n_estimators=1000, learning_rate=0.05, random_state=42, verbosity=0
)
xgb_model.fit(X_train, y_train)

lgb_train_rmse = np.sqrt(mean_squared_error(y_train, lgb_model.predict(X_train)))
xgb_train_rmse = np.sqrt(mean_squared_error(y_train, xgb_model.predict(X_train)))
ens_train_pred = (lgb_model.predict(X_train) + xgb_model.predict(X_train)) / 2
ens_train_rmse = np.sqrt(mean_squared_error(y_train, ens_train_pred))
print(f"Train RMSE  LGB: {lgb_train_rmse:.4f}  XGB: {xgb_train_rmse:.4f}  Ens: {ens_train_rmse:.4f}")

# ── 価格バッファの初期化 ───────────────────────────────────
price_buffer = {
    (row["date"], row["frame"]): row["tokyo_price"]
    for _, row in train_sorted.iterrows()
}

# ── ウォークフォワード予測 ─────────────────────────────────
test_dates = sorted(test["date"].unique())
all_preds  = []

print(f"\nウォークフォワード予測開始: {len(test_dates)} 日分")

for date in test_dates:
    day_df = test[test["date"] == date].sort_values("frame").copy()

    for lag_name, delta_days in [("price_lag_48",    1),
                                  ("price_lag_96",    2),
                                  ("price_lag_144",   3),
                                  ("price_lag_192",   4),
                                  ("price_lag_240",   5),
                                  ("price_lag_288",   6),
                                  ("price_lag_336",   7),
                                  ("price_lag_17520", 365)]:
        ref_date = date - pd.Timedelta(days=delta_days)
        day_df[lag_name] = day_df["frame"].map(
            lambda f, rd=ref_date: price_buffer.get((rd, f), np.nan)
        )

    lgb_preds = lgb_model.predict(day_df[features])
    xgb_preds = xgb_model.predict(day_df[features])
    preds = (lgb_preds + xgb_preds) / 2

    for frame, pred in zip(day_df["frame"], preds):
        price_buffer[(date, frame)] = pred

    all_preds.append(day_df[["id"]].assign(tokyo_price=preds.round(2)))
    print(f"  {date.date()} 予測完了")

# ── 提出ファイル生成 ───────────────────────────────────────
submission = pd.concat(all_preds, ignore_index=True)
submission.to_csv("submission_v2.csv", index=False)
print(f"\n予測完了: submission_v2.csv ({len(submission)}件)")
