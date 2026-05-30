"""
JEPX 東京エリア電力スポット価格予測 - 特徴量エンジニアリング v1（LightGBM）
追加特徴量:
  需給バランス
  - supply_demand_ratio : sell_amount / buy_amount（需給比率。1超で供給過多→価格低下）
  - surplus             : sell_amount - buy_amount（需給超過量）
  - contract_rate       : contracted_amount / buy_amount（約定率。需要の充足度）
  季節性
  - month               : 月（1〜12）
  - season              : 季節（1=春, 2=夏, 3=秋, 4=冬）
"""
import pandas as pd
import numpy as np
from lightgbm import LGBMRegressor, early_stopping
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import TimeSeriesSplit

# ── データ読み込み ─────────────────────────────────────────
train = pd.read_csv("../pre_eval.csv")
test  = pd.read_csv("../test_eval.csv")


# ── 特徴量エンジニアリング ─────────────────────────────────
def add_features(df):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])

    # 需給バランス特徴量
    df["supply_demand_ratio"] = df["sell_amount"] / df["buy_amount"]
    df["surplus"]             = df["sell_amount"] - df["buy_amount"]
    df["contract_rate"]       = df["contracted_amount"] / df["buy_amount"]

    # 季節性特徴量
    df["month"]  = df["date"].dt.month
    df["season"] = df["month"].map({
        12: 4, 1: 4, 2: 4,   # 冬
         3: 1, 4: 1, 5: 1,   # 春
         6: 2, 7: 2, 8: 2,   # 夏
         9: 3, 10: 3, 11: 3, # 秋
    })

    return df


train = add_features(train)
test  = add_features(test)

# ── 特徴量の定義 ───────────────────────────────────────────
features = [
    "frame", "dayofweek", "is_holiday",
    "temp",
    "power_result", "power_prediction", "usage_rate", "power_supply",
    "sell_amount", "buy_amount", "contracted_amount",
    "supply_demand_ratio", "surplus", "contract_rate",
    "month", "season",
]

# ── 前処理 ─────────────────────────────────────────────────
median_temp = train["temp"].median()
train["temp"] = train["temp"].fillna(median_temp)
test["temp"]  = test["temp"].fillna(median_temp)

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
submission.to_csv("submission_feature_eng_v1.csv", index=False)
print(f"\n予測完了: submission_feature_eng_v1.csv ({len(submission)}件)")
