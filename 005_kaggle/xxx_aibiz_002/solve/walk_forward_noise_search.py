"""
JEPX 東京エリア電力スポット価格予測 - ウォークフォワード ノイズ強度探索
NOISE_STD を複数試して最良スコアの提出ファイルを生成する
alert 特徴量追加後の再探索版
"""
import pandas as pd
import numpy as np
from lightgbm import LGBMRegressor, early_stopping
from sklearn.metrics import mean_squared_error

N_NOISE_RUNS = 5
RANDOM_SEED  = 42
# 20付近の細かい探索 + 100超の探索
NOISE_CANDIDATES = [17.0, 18.0, 19.0, 20.0, 21.0, 22.0, 23.0, 100.0, 120.0, 150.0, 200.0]

# ── データ読み込み・前処理（共通） ─────────────────────────
train = pd.read_csv("../pre_eval.csv")
test  = pd.read_csv("../test_eval.csv")
answer = pd.read_csv("../test_eval_ans.csv")[["id", "tokyo_price"]]

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

# ── ラグ特徴量（学習データ） ───────────────────────────────
train_sorted = train.sort_values(["date", "frame"]).reset_index(drop=True)
train_sorted["price_lag_48"]    = train_sorted["tokyo_price"].shift(48)
train_sorted["price_lag_96"]    = train_sorted["tokyo_price"].shift(96)
train_sorted["price_lag_336"]   = train_sorted["tokyo_price"].shift(336)
train_sorted["price_lag_17520"] = train_sorted["tokyo_price"].shift(17520)

SHORT_LAG_COLS = ["price_lag_48", "price_lag_96", "price_lag_336"]
lag_cols       = SHORT_LAG_COLS + ["price_lag_17520"]
base_features  = [
    "frame", "dayofweek", "is_holiday",
    "temp", "temp_sq", "weather_enc",
    "power_result", "power_prediction", "usage_rate", "power_supply",
    "sell_amount", "buy_amount", "contracted_amount",
    "supply_demand_ratio", "surplus", "contracted_ratio",
]
features  = base_features + lag_cols
X_base    = train_sorted[features].copy()
y_train   = train_sorted["tokyo_price"]
test_dates = sorted(test["date"].unique())


def run_walk_forward(noise_std):
    """指定した NOISE_STD でモデルを学習し、ウォークフォワード予測を行う"""
    rng = np.random.default_rng(RANDOM_SEED)
    models = []
    for run in range(N_NOISE_RUNS):
        X_noisy = X_base.copy()
        for col in SHORT_LAG_COLS:
            if noise_std > 0:
                noise = rng.normal(0, noise_std, len(X_noisy))
                X_noisy[col] = X_noisy[col] + np.where(X_noisy[col].notna(), noise, 0)
        m = LGBMRegressor(n_estimators=1000, learning_rate=0.05,
                          random_state=RANDOM_SEED + run, verbose=-1)
        m.fit(X_noisy, y_train)
        models.append(m)

    # 価格バッファ初期化
    price_buffer = {
        (row["date"], row["frame"]): row["tokyo_price"]
        for _, row in train_sorted.iterrows()
    }

    # ウォークフォワード予測
    all_preds = []
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
        preds = np.array([m.predict(day_df[features]) for m in models]).mean(axis=0)
        for frame, pred in zip(day_df["frame"], preds):
            price_buffer[(date, frame)] = pred
        all_preds.append(day_df[["id"]].assign(tokyo_price=preds.round(2)))

    return pd.concat(all_preds, ignore_index=True)


# ── 各 NOISE_STD を評価 ────────────────────────────────────
print(f"{'NOISE_STD':<12} {'RMSE':>8}")
print("-" * 25)

results = []
for noise_std in NOISE_CANDIDATES:
    pred = run_walk_forward(noise_std)
    merged = answer.merge(
        pred.rename(columns={"tokyo_price": "pred"}), on="id"
    )
    rmse = np.sqrt(mean_squared_error(merged["tokyo_price"], merged["pred"]))
    results.append({"noise_std": noise_std, "rmse": rmse, "pred": pred})
    print(f"  {noise_std:<10} {rmse:>8.4f}")

# ── 最良の NOISE_STD を特定 ───────────────────────────────
best = min(results, key=lambda x: x["rmse"])
print(f"\n最良 NOISE_STD: {best['noise_std']}  RMSE: {best['rmse']:.4f}")

best["pred"].to_csv("submission_walk_forward_v2.csv", index=False)
print(f"出力完了: submission_walk_forward_v2.csv（NOISE_STD={best['noise_std']}）")
