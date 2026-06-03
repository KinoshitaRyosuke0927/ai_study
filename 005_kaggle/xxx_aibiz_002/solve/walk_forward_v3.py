"""
JEPX 東京エリア電力スポット価格予測 - ウォークフォワード予測 v3

【v2 からの変更点】
  - Optuna による LightGBM ハイパーパラメータ最適化
  - アンサンブルは廃止し LightGBM 単体に戻す（v2 検証結果より）

【チューニング対象パラメータ】
  num_leaves, min_child_samples, feature_fraction, bagging_fraction,
  reg_alpha, reg_lambda, learning_rate
"""
import pandas as pd
import numpy as np
import optuna
from lightgbm import LGBMRegressor, early_stopping as lgb_early_stopping
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import TimeSeriesSplit

optuna.logging.set_verbosity(optuna.logging.WARNING)

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

# ── 学習データのラグ特徴量（Step2採用分） ─────────────────
train_sorted = train.sort_values(["date", "frame"]).reset_index(drop=True)
train_sorted["price_lag_48"]    = train_sorted["tokyo_price"].shift(48)
train_sorted["price_lag_96"]    = train_sorted["tokyo_price"].shift(96)
train_sorted["price_lag_144"]   = train_sorted["tokyo_price"].shift(144)
train_sorted["price_lag_192"]   = train_sorted["tokyo_price"].shift(192)
train_sorted["price_lag_240"]   = train_sorted["tokyo_price"].shift(240)
train_sorted["price_lag_288"]   = train_sorted["tokyo_price"].shift(288)
train_sorted["price_lag_336"]   = train_sorted["tokyo_price"].shift(336)
train_sorted["price_lag_17520"] = train_sorted["tokyo_price"].shift(17520)

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

X_train = train_sorted[features]
y_train = train_sorted["tokyo_price"]

# ── Optuna 目的関数 ────────────────────────────────────────
tscv = TimeSeriesSplit(n_splits=5)

def objective(trial):
    params = {
        "n_estimators":      1000,
        "learning_rate":     trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
        "num_leaves":        trial.suggest_int("num_leaves", 16, 256),
        "min_child_samples": trial.suggest_int("min_child_samples", 5, 100),
        "feature_fraction":  trial.suggest_float("feature_fraction", 0.5, 1.0),
        "bagging_fraction":  trial.suggest_float("bagging_fraction", 0.5, 1.0),
        "bagging_freq":      1,
        "reg_alpha":         trial.suggest_float("reg_alpha", 1e-4, 10.0, log=True),
        "reg_lambda":        trial.suggest_float("reg_lambda", 1e-4, 10.0, log=True),
        "random_state":      42,
        "verbose":           -1,
    }
    cv_rmses = []
    for tr_idx, val_idx in tscv.split(X_train):
        X_tr, X_val = X_train.iloc[tr_idx], X_train.iloc[val_idx]
        y_tr, y_val = y_train.iloc[tr_idx], y_train.iloc[val_idx]
        m = LGBMRegressor(**params)
        m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
              callbacks=[lgb_early_stopping(50, verbose=False)])
        cv_rmses.append(np.sqrt(mean_squared_error(y_val, m.predict(X_val))))
    return np.mean(cv_rmses)

# ── 最適化実行 ─────────────────────────────────────────────
N_TRIALS = 50
print(f"Optuna チューニング開始: {N_TRIALS} trials")
study = optuna.create_study(direction="minimize")
study.optimize(objective, n_trials=N_TRIALS, show_progress_bar=True)

print(f"\nBest CV RMSE : {study.best_value:.4f}")
print(f"Best params  : {study.best_params}")

# ── 最適パラメータで最終モデルを学習 ──────────────────────
best_params = {
    "n_estimators":      1000,
    "bagging_freq":      1,
    "random_state":      42,
    "verbose":           -1,
    **study.best_params,
}

# CV スコアを表示（最適パラメータ）
print("\n=== 最適パラメータでの CV ===")
cv_rmses = []
for fold, (tr_idx, val_idx) in enumerate(tscv.split(X_train)):
    X_tr, X_val = X_train.iloc[tr_idx], X_train.iloc[val_idx]
    y_tr, y_val = y_train.iloc[tr_idx], y_train.iloc[val_idx]
    m = LGBMRegressor(**best_params)
    m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
          callbacks=[lgb_early_stopping(50, verbose=False)])
    val_rmse = np.sqrt(mean_squared_error(y_val, m.predict(X_val)))
    cv_rmses.append(val_rmse)
    print(f"  Fold {fold+1} Val RMSE: {val_rmse:.4f}")
print(f"CV RMSE: {np.mean(cv_rmses):.4f} ± {np.std(cv_rmses):.4f}")

model = LGBMRegressor(**best_params)
model.fit(X_train, y_train)

train_rmse = np.sqrt(mean_squared_error(y_train, model.predict(X_train)))
print(f"Train RMSE: {train_rmse:.4f}")

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

    preds = model.predict(day_df[features])

    for frame, pred in zip(day_df["frame"], preds):
        price_buffer[(date, frame)] = pred

    all_preds.append(day_df[["id"]].assign(tokyo_price=preds.round(2)))
    print(f"  {date.date()} 予測完了")

# ── 提出ファイル生成 ───────────────────────────────────────
submission = pd.concat(all_preds, ignore_index=True)
submission.to_csv("submission_v3.csv", index=False)
print(f"\n予測完了: submission_v3.csv ({len(submission)}件)")
