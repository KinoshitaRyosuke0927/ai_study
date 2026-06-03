"""
JEPX 東京エリア電力スポット価格予測 - ピーク/オフピーク分離モデル（Walk-Forward v3）

walk_forward_v2.py からの改善点:
  電力スポット価格のピーク/オフピーク特性に合わせて別々のモデルを学習する

【ピーク/オフピークの定義】
  ピーク   : 平日（is_holiday=0, dayofweek=0-4）かつ コマ17〜40（8:00〜20:00）
  オフピーク: それ以外（休日・祝日のすべてのコマ、平日のコマ1-16 / 41-48）

【アプローチ】
  1. 学習データをピーク/オフピークに分割し、それぞれ独立したLightGBMモデルを学習
  2. ノイズ注入（NOISE_STD=25.0）× 5モデルのアンサンブルは walk_forward_v2 と同じ
  3. ウォークフォワード予測時に各コマのピーク/オフピーク判定をして対応モデルを適用
  4. price_buffer は全コマの予測値を保持し、ラグ特徴量は両モデルで共有
"""
import pandas as pd
import numpy as np
from lightgbm import LGBMRegressor, early_stopping
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import TimeSeriesSplit

NOISE_STD    = 25.0
N_NOISE_RUNS = 5
RANDOM_SEED  = 42


def is_peak_mask(df: pd.DataFrame) -> pd.Series:
    """平日かつコマ17〜40 = ピーク"""
    return (df["dayofweek"] < 5) & (df["is_holiday"] == 0) & df["frame"].between(17, 40)


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

# ── ラグ特徴量（学習データ） ───────────────────────────────
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

# ── ピーク/オフピーク分割 ─────────────────────────────────
peak_mask_train = is_peak_mask(train_sorted)
train_peak    = train_sorted[peak_mask_train].copy()
train_offpeak = train_sorted[~peak_mask_train].copy()

print(f"学習データ: ピーク {len(train_peak):,} 行 / オフピーク {len(train_offpeak):,} 行")

X_peak    = train_peak[features].copy()
y_peak    = train_peak["tokyo_price"]
X_offpeak = train_offpeak[features].copy()
y_offpeak = train_offpeak["tokyo_price"]


def train_ensemble(X: pd.DataFrame, y: pd.Series, label: str) -> list:
    """ノイズ注入 × N_NOISE_RUNS のアンサンブルを学習して返す"""
    tscv = TimeSeriesSplit(n_splits=5)
    models = []
    rng = np.random.default_rng(RANDOM_SEED)

    print(f"\n【{label}】ノイズ注入学習（std={NOISE_STD}）× {N_NOISE_RUNS} runs")

    for run in range(N_NOISE_RUNS):
        X_noisy = X.copy()
        for col in SHORT_LAG_COLS:
            noise = rng.normal(0, NOISE_STD, len(X_noisy))
            X_noisy[col] = X_noisy[col] + np.where(X_noisy[col].notna(), noise, 0)

        if run == 0:
            cv_rmses = []
            for fold, (tr_idx, val_idx) in enumerate(tscv.split(X_noisy)):
                X_tr, X_val = X_noisy.iloc[tr_idx], X_noisy.iloc[val_idx]
                y_tr, y_val = y.iloc[tr_idx], y.iloc[val_idx]
                m = LGBMRegressor(n_estimators=1000, learning_rate=0.05,
                                  random_state=RANDOM_SEED, verbose=-1)
                m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
                      callbacks=[early_stopping(50, verbose=False)])
                val_rmse = np.sqrt(mean_squared_error(y_val, m.predict(X_val)))
                cv_rmses.append(val_rmse)
                print(f"  Run1 Fold {fold+1} Val RMSE: {val_rmse:.4f}")
            print(f"  Run1 CV RMSE: {np.mean(cv_rmses):.4f} ± {np.std(cv_rmses):.4f}")

        model = LGBMRegressor(n_estimators=1000, learning_rate=0.05,
                              random_state=RANDOM_SEED + run, verbose=-1)
        model.fit(X_noisy, y)
        models.append(model)
        print(f"  Run {run+1}/{N_NOISE_RUNS} 学習完了")

    return models


peak_models    = train_ensemble(X_peak,    y_peak,    "ピーク")
offpeak_models = train_ensemble(X_offpeak, y_offpeak, "オフピーク")

# ── price_buffer 初期化（全学習データの実績値） ──────────────
price_buffer = {
    (row["date"], row["frame"]): row["tokyo_price"]
    for _, row in train_sorted.iterrows()
}

# ── ウォークフォワード予測 ────────────────────────────────
test_dates = sorted(test["date"].unique())
all_preds  = []

print(f"\nウォークフォワード予測開始: {len(test_dates)} 日分")

for date in test_dates:
    day_df = test[test["date"] == date].sort_values("frame").copy()

    # ラグ特徴量をバッファから補完
    for lag_name, delta_days in [("price_lag_48",    1),
                                  ("price_lag_96",    2),
                                  ("price_lag_336",   7),
                                  ("price_lag_17520", 365)]:
        ref_date = date - pd.Timedelta(days=delta_days)
        day_df[lag_name] = day_df["frame"].map(
            lambda f, rd=ref_date: price_buffer.get((rd, f), np.nan)
        )

    # ピーク/オフピーク判定して各モデルで予測
    mask_peak = is_peak_mask(day_df)
    preds = np.zeros(len(day_df))

    # ピーク予測
    if mask_peak.any():
        rows_peak = day_df[mask_peak]
        preds_peak = np.array([m.predict(rows_peak[features]) for m in peak_models]).mean(axis=0)
        preds[mask_peak.values] = preds_peak

    # オフピーク予測
    if (~mask_peak).any():
        rows_offpeak = day_df[~mask_peak]
        preds_offpeak = np.array([m.predict(rows_offpeak[features]) for m in offpeak_models]).mean(axis=0)
        preds[~mask_peak.values] = preds_offpeak

    for frame, pred in zip(day_df["frame"], preds):
        price_buffer[(date, frame)] = pred

    all_preds.append(day_df[["id"]].assign(tokyo_price=preds.round(2)))
    print(f"  {date.date()} 予測完了")

# ── 提出ファイル生成 ───────────────────────────────────────
submission = pd.concat(all_preds, ignore_index=True)
submission.to_csv("submission_walk_forward_v3.csv", index=False)
print(f"\n予測完了: submission_walk_forward_v3.csv ({len(submission)}件)")
