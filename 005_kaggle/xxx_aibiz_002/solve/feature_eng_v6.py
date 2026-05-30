"""
JEPX 東京エリア電力スポット価格予測 - 特徴量エンジニアリング v6（LightGBM + Optuna）
v4 の特徴量をベースに Optuna でハイパーパラメータを自動チューニング

事前インストール: pip install optuna
"""
import pandas as pd
import numpy as np
import optuna
from lightgbm import LGBMRegressor, early_stopping
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import TimeSeriesSplit

optuna.logging.set_verbosity(optuna.logging.WARNING)

# ── データ読み込み ─────────────────────────────────────────
train = pd.read_csv("../pre_eval.csv")
test  = pd.read_csv("../test_eval.csv")

median_temp = train["temp"].median()
train["temp"] = train["temp"].fillna(median_temp)
test["temp"]  = test["temp"].fillna(median_temp)


# ── 需給バランス特徴量 ─────────────────────────────────────
def add_demand_features(df):
    df = df.copy()
    df["supply_demand_ratio"] = df["sell_amount"] / df["buy_amount"]
    df["surplus"]             = df["sell_amount"] - df["buy_amount"]
    return df


train = add_demand_features(train)
test  = add_demand_features(test)

# ── ラグ特徴量の計算 ───────────────────────────────────────
test["tokyo_price"] = np.nan
combined = pd.concat([train, test], ignore_index=True)
combined["date"] = pd.to_datetime(combined["date"])
combined = combined.sort_values(["date", "frame"]).reset_index(drop=True)

combined["price_lag_17520"] = combined["tokyo_price"].shift(17520)
combined["price_lag_35040"] = combined["tokyo_price"].shift(35040)

lag_cols = ["id", "price_lag_17520", "price_lag_35040"]
train = train.merge(combined[lag_cols], on="id")
test  = test.drop(columns=["tokyo_price"]).merge(combined[lag_cols], on="id")

# ── 特徴量の定義 ───────────────────────────────────────────
features = [
    "frame", "dayofweek", "is_holiday",
    "temp",
    "power_result", "power_prediction", "usage_rate", "power_supply",
    "sell_amount", "buy_amount", "contracted_amount",
    "supply_demand_ratio", "surplus",
    "price_lag_17520", "price_lag_35040",
]

X_train = train[features]
y_train = train["tokyo_price"]
X_test  = test[features]

tscv = TimeSeriesSplit(n_splits=5)

# ── Optuna の目的関数 ──────────────────────────────────────
def objective(trial):
    params = {
        "n_estimators":      1000,
        "learning_rate":     trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
        "num_leaves":        trial.suggest_int("num_leaves", 16, 256),
        "max_depth":         trial.suggest_int("max_depth", 3, 12),
        "min_child_samples": trial.suggest_int("min_child_samples", 5, 100),
        "subsample":         trial.suggest_float("subsample", 0.5, 1.0),
        "colsample_bytree":  trial.suggest_float("colsample_bytree", 0.5, 1.0),
        "reg_alpha":         trial.suggest_float("reg_alpha", 1e-4, 10.0, log=True),
        "reg_lambda":        trial.suggest_float("reg_lambda", 1e-4, 10.0, log=True),
        "random_state":      42,
        "verbose":           -1,
    }

    rmses = []
    for tr_idx, val_idx in tscv.split(X_train):
        X_tr, X_val = X_train.iloc[tr_idx], X_train.iloc[val_idx]
        y_tr, y_val = y_train.iloc[tr_idx], y_train.iloc[val_idx]
        m = LGBMRegressor(**params)
        m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
              callbacks=[early_stopping(50, verbose=False)])
        rmses.append(np.sqrt(mean_squared_error(y_val, m.predict(X_val))))

    return np.mean(rmses)


# ── Optuna チューニング実行 ────────────────────────────────
print("Optuna チューニング開始（100 trials）...")
study = optuna.create_study(direction="minimize")
study.optimize(objective, n_trials=100, show_progress_bar=True)

print(f"\nBest CV RMSE: {study.best_value:.4f}")
print(f"Best params:")
for k, v in study.best_params.items():
    print(f"  {k}: {v}")

# ── ベストパラメータで最終モデルを学習 ─────────────────────
best_params = {
    "n_estimators":  1000,
    "random_state":  42,
    "verbose":       -1,
    **study.best_params,
}

cv_rmses = []
for fold, (tr_idx, val_idx) in enumerate(tscv.split(X_train)):
    X_tr, X_val = X_train.iloc[tr_idx], X_train.iloc[val_idx]
    y_tr, y_val = y_train.iloc[tr_idx], y_train.iloc[val_idx]
    m = LGBMRegressor(**best_params)
    m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
          callbacks=[early_stopping(50, verbose=False)])
    val_rmse = np.sqrt(mean_squared_error(y_val, m.predict(X_val)))
    cv_rmses.append(val_rmse)
    print(f"  Fold {fold+1} Val RMSE: {val_rmse:.4f}")

print(f"CV RMSE: {np.mean(cv_rmses):.4f} ± {np.std(cv_rmses):.4f}")

model = LGBMRegressor(**best_params)
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
submission.to_csv("submission_feature_eng_v6.csv", index=False)
print(f"\n予測完了: submission_feature_eng_v6.csv ({len(submission)}件)")
