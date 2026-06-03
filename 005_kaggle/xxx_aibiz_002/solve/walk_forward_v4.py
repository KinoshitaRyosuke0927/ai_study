"""
JEPX 東京エリア電力スポット価格予測 - ウォークフォワード予測 v4

【v3 からの変更点】
  - Expanding Window 再学習: テスト日を1日予測するたびにモデルを再学習
    Day1 予測 → (訓練データ + Day1予測値) で再学習 → Day2 予測 → ...
  - ハイパーパラメータは v3 の Optuna 最適解を流用

【効果の期待】
  通常のウォークフォワードはモデルを1回だけ学習するため、
  テスト期間（2026年）の傾向を学習できない。
  毎日再学習することで直近の予測値を学習に組み込み、
  ドリフト（価格水準の変化）への適応を狙う。

【注意】
  テスト期間の予測値を正解として再学習するため、
  予測精度が低い日があると誤差が蓄積するリスクもある。
"""
import pandas as pd
import numpy as np
from lightgbm import LGBMRegressor, early_stopping as lgb_early_stopping
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

# ── 学習データのラグ特徴量 ────────────────────────────────
train_sorted = train.sort_values(["date", "frame"]).reset_index(drop=True)
train_sorted["price_lag_48"]    = train_sorted["tokyo_price"].shift(48)
train_sorted["price_lag_96"]    = train_sorted["tokyo_price"].shift(96)
train_sorted["price_lag_144"]   = train_sorted["tokyo_price"].shift(144)
train_sorted["price_lag_192"]   = train_sorted["tokyo_price"].shift(192)
train_sorted["price_lag_240"]   = train_sorted["tokyo_price"].shift(240)
train_sorted["price_lag_288"]   = train_sorted["tokyo_price"].shift(288)
train_sorted["price_lag_336"]   = train_sorted["tokyo_price"].shift(336)
train_sorted["price_lag_17520"] = train_sorted["tokyo_price"].shift(17520)

# ── 特徴量の定義 ───────────────────────────────────────────
lag_spec = [
    ("price_lag_48",    1),
    ("price_lag_96",    2),
    ("price_lag_144",   3),
    ("price_lag_192",   4),
    ("price_lag_240",   5),
    ("price_lag_288",   6),
    ("price_lag_336",   7),
    ("price_lag_17520", 365),
]
lag_cols = [name for name, _ in lag_spec]
base_features = [
    "frame", "dayofweek", "is_holiday",
    "temp", "temp_sq", "weather_enc",
    "power_result", "power_prediction", "usage_rate", "power_supply",
    "sell_amount", "buy_amount", "contracted_amount",
    "supply_demand_ratio", "surplus", "contracted_ratio",
]
features = base_features + lag_cols

# ── v3 Optuna 最適パラメータ ──────────────────────────────
best_params = {
    "n_estimators":      1000,
    "learning_rate":     0.023775265176627945,
    "num_leaves":        31,
    "min_child_samples": 21,
    "feature_fraction":  0.9671697416591167,
    "bagging_fraction":  0.5687603604182755,
    "bagging_freq":      1,
    "reg_alpha":         0.007026196710769309,
    "reg_lambda":        0.0161448344504412,
    "random_state":      42,
    "verbose":           -1,
}

# ── Early stopping 用の固定バリデーションセット ────────────
# 元の訓練データ末尾14日（672行）を validation として固定
EVAL_DAYS = 14
eval_cutoff = train_sorted["date"].max() - pd.Timedelta(days=EVAL_DAYS)
static_val_mask = train_sorted["date"] > eval_cutoff
X_static_val = train_sorted.loc[static_val_mask, features]
y_static_val = train_sorted.loc[static_val_mask, "tokyo_price"]

# ── 初回モデル学習（元の訓練データのみ） ─────────────────
print("=== 初回モデル学習 ===")
X_init = train_sorted[features]
y_init = train_sorted["tokyo_price"]
model = LGBMRegressor(**best_params)
model.fit(X_init, y_init,
          eval_set=[(X_static_val, y_static_val)],
          callbacks=[lgb_early_stopping(50, verbose=False)])
train_rmse = np.sqrt(mean_squared_error(y_init, model.predict(X_init)))
print(f"初回 Train RMSE: {train_rmse:.4f}")

# ── 価格バッファの初期化 ───────────────────────────────────
price_buffer = {
    (row["date"], row["frame"]): row["tokyo_price"]
    for _, row in train_sorted.iterrows()
}

# ── Expanding Window ウォークフォワード予測 ────────────────
test_dates      = sorted(test["date"].unique())
all_preds       = []
predicted_rows  = []   # 再学習に使う予測済み行を蓄積

print(f"\nExpanding Window ウォークフォワード予測開始: {len(test_dates)} 日分")

for i, date in enumerate(test_dates):

    # ── 当日のラグ特徴量をバッファから取得 ──────────────
    day_df = test[test["date"] == date].sort_values("frame").copy()
    for lag_name, delta_days in lag_spec:
        ref_date = date - pd.Timedelta(days=delta_days)
        day_df[lag_name] = day_df["frame"].map(
            lambda f, rd=ref_date: price_buffer.get((rd, f), np.nan)
        )

    # ── 予測 ─────────────────────────────────────────────
    preds = model.predict(day_df[features])

    # ── 予測値をバッファと蓄積リストに追加 ───────────────
    for frame, pred in zip(day_df["frame"], preds):
        price_buffer[(date, frame)] = pred

    pred_row = day_df[base_features + ["date"]].copy()
    pred_row["tokyo_price"] = preds
    for lag_name, delta_days in lag_spec:
        ref_date = date - pd.Timedelta(days=delta_days)
        pred_row[lag_name] = pred_row["frame"].map(
            lambda f, rd=ref_date: price_buffer.get((rd, f), np.nan)
        )
    predicted_rows.append(pred_row)

    all_preds.append(day_df[["id"]].assign(tokyo_price=preds.round(2)))
    print(f"  [{i+1:2d}/90] {date.date()} 予測完了 → 拡張訓練データで再学習中...")

    # ── 翌日予測のために再学習（Expanding Window） ───────
    if i < len(test_dates) - 1:
        expanded = pd.concat([train_sorted] + predicted_rows, ignore_index=True)
        X_exp = expanded[features]
        y_exp = expanded["tokyo_price"]
        model = LGBMRegressor(**best_params)
        model.fit(X_exp, y_exp,
                  eval_set=[(X_static_val, y_static_val)],
                  callbacks=[lgb_early_stopping(50, verbose=False)])

print(f"\n再学習完了（合計 {len(test_dates)} 回）")

# ── 提出ファイル生成 ───────────────────────────────────────
submission = pd.concat(all_preds, ignore_index=True)
submission.to_csv("submission_v4.csv", index=False)
print(f"予測完了: submission_v4.csv ({len(submission)}件)")
