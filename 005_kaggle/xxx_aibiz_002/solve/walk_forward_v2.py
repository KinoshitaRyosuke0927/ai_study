"""
JEPX 東京エリア電力スポット価格予測 - ウォークフォワード予測 v2（Walk-Forward Prediction v2）

walk_forward.py からの改善点:
  短期ラグへの過度な依存を防ぐため、学習時に短期ラグにノイズを注入する
  （Noise Injection / ノイズ注入）

【ノイズ注入の考え方】
  ウォークフォワード予測では短期ラグに予測誤差が混入する（誤差の伝播）
  学習時に意図的に誤差相当のノイズを短期ラグに加えることで、
  モデルが「ノイズのある短期ラグ」に依存しすぎない構造を学習する
  → 短期ラグが不正確でも他の特徴量で補完できるモデルになる

  ノイズの大きさ: walk_forward.py の CV RMSE（≈2.0 円）相当を基準に設定
"""
import pandas as pd
import numpy as np
from lightgbm import LGBMRegressor, early_stopping
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import TimeSeriesSplit

NOISE_STD   = 25.0   # 短期ラグに加えるノイズの標準偏差（円/kWh）
N_NOISE_RUNS = 5    # ノイズを変えて複数回学習し平均をとる（モデルの安定化）
RANDOM_SEED  = 42

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

# ── 学習データのラグ特徴量を構築 ──────────────────────────
train_sorted = train.sort_values(["date", "frame"]).reset_index(drop=True)
train_sorted["price_lag_48"]    = train_sorted["tokyo_price"].shift(48)
train_sorted["price_lag_96"]    = train_sorted["tokyo_price"].shift(96)
train_sorted["price_lag_336"]   = train_sorted["tokyo_price"].shift(336)
train_sorted["price_lag_17520"] = train_sorted["tokyo_price"].shift(17520)

SHORT_LAG_COLS = ["price_lag_48", "price_lag_96", "price_lag_336"]
lag_cols       = SHORT_LAG_COLS + ["price_lag_17520"]

base_features = [
    "frame", "dayofweek", "is_holiday",
    "temp", "temp_sq", "weather_enc",
    "power_result", "power_prediction", "usage_rate", "power_supply",
    "sell_amount", "buy_amount", "contracted_amount",
    "supply_demand_ratio", "surplus", "contracted_ratio",
]
features = base_features + lag_cols

X_base = train_sorted[features].copy()
y_train = train_sorted["tokyo_price"]

# ── ノイズ注入しながら複数モデルを学習（アンサンブル） ────
# 毎回ノイズを変えて学習し、複数モデルの予測を平均することで
# 「ノイズに頑健なモデル」を得る
print(f"ノイズ注入学習（std={NOISE_STD}）× {N_NOISE_RUNS} runs")
tscv = TimeSeriesSplit(n_splits=5)
models = []
rng = np.random.default_rng(RANDOM_SEED)

for run in range(N_NOISE_RUNS):
    X_noisy = X_base.copy()
    # 短期ラグにのみノイズを注入（lag_17520 は実績値のため注入しない）
    for col in SHORT_LAG_COLS:
        noise = rng.normal(0, NOISE_STD, len(X_noisy))
        X_noisy[col] = X_noisy[col] + np.where(X_noisy[col].notna(), noise, 0)

    # CV RMSE は最初の run のみ表示
    if run == 0:
        cv_rmses = []
        for fold, (tr_idx, val_idx) in enumerate(tscv.split(X_noisy)):
            X_tr, X_val = X_noisy.iloc[tr_idx], X_noisy.iloc[val_idx]
            y_tr, y_val = y_train.iloc[tr_idx], y_train.iloc[val_idx]
            m = LGBMRegressor(n_estimators=1000, learning_rate=0.05, random_state=RANDOM_SEED, verbose=-1)
            m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
                  callbacks=[early_stopping(50, verbose=False)])
            val_rmse = np.sqrt(mean_squared_error(y_val, m.predict(X_val)))
            cv_rmses.append(val_rmse)
            print(f"  Run{run+1} Fold {fold+1} Val RMSE: {val_rmse:.4f}")
        print(f"  Run{run+1} CV RMSE: {np.mean(cv_rmses):.4f} ± {np.std(cv_rmses):.4f}")

    model = LGBMRegressor(n_estimators=1000, learning_rate=0.05,
                          random_state=RANDOM_SEED + run, verbose=-1)
    model.fit(X_noisy, y_train)
    models.append(model)
    print(f"  Run {run+1}/{N_NOISE_RUNS} 学習完了")

# ── 価格バッファの初期化 ───────────────────────────────────
price_buffer = {
    (row["date"], row["frame"]): row["tokyo_price"]
    for _, row in train_sorted.iterrows()
}

# ── ウォークフォワード予測（複数モデルの平均を使用） ────────
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

    # 複数モデルの予測を平均（アンサンブル）
    preds_all = np.array([m.predict(day_df[features]) for m in models])
    preds = preds_all.mean(axis=0)

    for frame, pred in zip(day_df["frame"], preds):
        price_buffer[(date, frame)] = pred

    all_preds.append(day_df[["id"]].assign(tokyo_price=preds.round(2)))
    print(f"  {date.date()} 予測完了")

# ── 提出ファイル生成 ───────────────────────────────────────
submission = pd.concat(all_preds, ignore_index=True)
submission.to_csv("submission_walk_forward_v2.csv", index=False)
print(f"\n予測完了: submission_walk_forward_v2.csv ({len(submission)}件)")
