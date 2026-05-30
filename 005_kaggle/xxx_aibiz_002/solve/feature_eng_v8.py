"""
JEPX 東京エリア電力スポット価格予測 - 特徴量エンジニアリング v8（LightGBM）
v7 に交互作用特徴量を追加
追加候補:
  - frame_dow      : frame × dayofweek の組み合わせ（平日夕方 vs 休日夕方の価格差を表現）
  - frame_holiday  : frame × is_holiday の組み合わせ（祝日の時間帯別価格パターン）
  - temp_frame     : temp × frame（気温の影響が時間帯によって異なる効果を表現）

各候補を個別に検証し、CV RMSEが改善するもののみ採用する
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


# ── weather 補間・エンコード（v7 から継続） ────────────────
test["tokyo_price"] = np.nan
combined_weather = pd.concat([train, test], ignore_index=True)
combined_weather["date"] = pd.to_datetime(combined_weather["date"])
combined_weather = combined_weather.sort_values(["date", "frame"]).reset_index(drop=True)
combined_weather["weather"] = combined_weather["weather"].ffill().bfill()
weather_map = {w: i for i, w in enumerate(sorted(combined_weather["weather"].dropna().unique()))}
combined_weather["weather_enc"] = combined_weather["weather"].map(weather_map)
enc_cols = ["id", "weather_enc"]
train = train.merge(combined_weather[enc_cols], on="id")
test  = test.drop(columns=["tokyo_price"]).merge(combined_weather[enc_cols], on="id")

# ── 需給バランス特徴量（v7 から継続） ─────────────────────
for df in [train, test]:
    df["supply_demand_ratio"] = df["sell_amount"] / df["buy_amount"]
    df["surplus"]             = df["sell_amount"] - df["buy_amount"]

# ── ラグ特徴量（v7 から継続） ──────────────────────────────
test["tokyo_price"] = np.nan
combined = pd.concat([train, test], ignore_index=True)
combined["date"] = pd.to_datetime(combined["date"])
combined = combined.sort_values(["date", "frame"]).reset_index(drop=True)
combined["price_lag_17520"] = combined["tokyo_price"].shift(17520)
train = train.merge(combined[["id", "price_lag_17520"]], on="id")
test  = test.drop(columns=["tokyo_price"]).merge(combined[["id", "price_lag_17520"]], on="id")

# ── 交互作用特徴量の生成 ───────────────────────────────────
for df in [train, test]:
    # frame（1〜48）× dayofweek（0〜6）の組み合わせを一意な整数で表現
    df["frame_dow"]     = df["frame"] * 7 + df["dayofweek"]
    # frame × is_holiday の組み合わせ
    df["frame_holiday"] = df["frame"] * 2 + df["is_holiday"]
    # 気温 × frame: 朝夕の気温と価格の交互作用
    df["temp_frame"]    = df["temp"] * df["frame"]

# ── ベースライン特徴量 ─────────────────────────────────────
base_features = [
    "frame", "dayofweek", "is_holiday",
    "temp", "weather_enc",
    "power_result", "power_prediction", "usage_rate", "power_supply",
    "sell_amount", "buy_amount", "contracted_amount",
    "supply_demand_ratio", "surplus",
    "price_lag_17520",
]
candidate_features = ["frame_dow", "frame_holiday", "temp_frame"]

y_train = train["tokyo_price"]
tscv = TimeSeriesSplit(n_splits=5)


def cv_rmse(features):
    X = train[features]
    rmses = []
    for tr_idx, val_idx in tscv.split(X):
        X_tr, X_val = X.iloc[tr_idx], X.iloc[val_idx]
        y_tr, y_val = y_train.iloc[tr_idx], y_train.iloc[val_idx]
        m = LGBMRegressor(n_estimators=1000, learning_rate=0.05, random_state=42, verbose=-1)
        m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
              callbacks=[early_stopping(50, verbose=False)])
        rmses.append(np.sqrt(mean_squared_error(y_val, m.predict(X_val))))
    return np.mean(rmses)


# ── 各交互作用特徴量を個別に検証 ──────────────────────────
print("交互作用特徴量の効果を検証中...\n")
baseline_score = cv_rmse(base_features)
print(f"{'ベースライン（追加なし）':<30} CV RMSE: {baseline_score:.4f}")
print("-" * 55)

adopted = []
for feat in candidate_features:
    score = cv_rmse(base_features + [feat])
    diff  = score - baseline_score
    mark  = "✓ 採用" if diff < 0 else "✗ 除外"
    print(f"  + {feat:<28} CV RMSE: {score:.4f}  ({diff:+.4f})  {mark}")
    if diff < 0:
        adopted.append(feat)

print(f"\n採用特徴量: {adopted if adopted else 'なし（ベースラインのまま）'}")

# ── 採用特徴量で最終モデルを学習 ──────────────────────────
final_features = base_features + adopted
X_train = train[final_features]
X_test  = test[final_features]

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

print("\n特徴量の重要度:")
importances = sorted(zip(final_features, model.feature_importances_), key=lambda x: x[1], reverse=True)
for col, imp in importances:
    print(f"  {col}: {imp}")

# ── 予測・提出ファイル生成 ──────────────────────────────────
y_pred = model.predict(X_test)
submission = pd.DataFrame({"id": test["id"], "tokyo_price": y_pred.round(2)})
submission.to_csv("submission_feature_eng_v8.csv", index=False)
print(f"\n予測完了: submission_feature_eng_v8.csv ({len(submission)}件)")
