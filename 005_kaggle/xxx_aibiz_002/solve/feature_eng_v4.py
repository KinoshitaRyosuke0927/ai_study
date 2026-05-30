"""
JEPX 東京エリア電力スポット価格予測 - 特徴量エンジニアリング v4（LightGBM）
v3 の問題（ラグ特徴量のCV/本番間の分布乖離）を修正

v3 の問題:
  price_lag_48/96/336 はテスト期間の大部分でNaN → 本番スコアが大幅悪化

解決策:
  テスト期間全行（最大39日先）で有効なラグのみ使用
  - price_lag_17520 : 1年前（365日×48フレーム）の価格
      テスト最終行 2026/5/9 → 参照先 2025/5/9（学習データ内）✓
  - price_lag_35040 : 2年前（730日×48フレーム）の価格
      テスト最終行 2026/5/9 → 参照先 2024/5/9（学習データ内）✓
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


# ── 需給バランス特徴量 ─────────────────────────────────────
def add_demand_features(df):
    df = df.copy()
    df["supply_demand_ratio"] = df["sell_amount"] / df["buy_amount"]
    df["surplus"]             = df["sell_amount"] - df["buy_amount"]
    return df


train = add_demand_features(train)
test  = add_demand_features(test)

# ── ラグ特徴量の計算 ───────────────────────────────────────
# 学習・テストを結合してラグを計算
# 1年前・2年前のラグはテスト期間全行で参照先が学習データ内に収まる
test["tokyo_price"] = np.nan
combined = pd.concat([train, test], ignore_index=True)
combined["date"] = pd.to_datetime(combined["date"])
combined = combined.sort_values(["date", "frame"]).reset_index(drop=True)

combined["price_lag_17520"] = combined["tokyo_price"].shift(17520)  # 1年前
combined["price_lag_35040"] = combined["tokyo_price"].shift(35040)  # 2年前

lag_cols = ["id", "price_lag_17520", "price_lag_35040"]
train = train.merge(combined[lag_cols], on="id")
test  = test.drop(columns=["tokyo_price"]).merge(combined[lag_cols], on="id")

# ラグ特徴量の欠損状況を確認
for col in ["price_lag_17520", "price_lag_35040"]:
    nan_count = test[col].isna().sum()
    print(f"テストデータ {col} NaN数: {nan_count} / {len(test)}")

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

# 特徴量重要度を大きい順に表示
print("\n特徴量の重要度:")
importances = sorted(zip(features, model.feature_importances_), key=lambda x: x[1], reverse=True)
for col, imp in importances:
    print(f"  {col}: {imp}")

# ── 予測・提出ファイル生成 ──────────────────────────────────
y_pred = model.predict(X_test)

submission = pd.DataFrame({"id": test["id"], "tokyo_price": y_pred.round(2)})
submission.to_csv("submission_feature_eng_v4.csv", index=False)
print(f"\n予測完了: submission_feature_eng_v4.csv ({len(submission)}件)")
