"""
JEPX 東京エリア電力スポット価格予測 - ベースラインモデル（LinearRegression）
- weather は欠損率85%のため除外
- temp は欠損2件を中央値で補完して使用
- 時系列データのため CV は TimeSeriesSplit を使用
"""
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import TimeSeriesSplit

# ── データ読み込み ─────────────────────────────────────────
train = pd.read_csv("../pre_eval.csv")
test  = pd.read_csv("../test_eval.csv")

# ── 特徴量の定義 ───────────────────────────────────────────
# weather は欠損率85%のため除外
features = [
    "frame", "dayofweek", "is_holiday",
    "temp",
    "power_result", "power_prediction", "usage_rate", "power_supply",
    "sell_amount", "buy_amount", "contracted_amount",
]

# ── 前処理 ─────────────────────────────────────────────────
# temp の欠損2件を中央値で補完
median_temp = train["temp"].median()
train["temp"] = train["temp"].fillna(median_temp)
test["temp"]  = test["temp"].fillna(median_temp)

X_train = train[features]
y_train = train["tokyo_price"]
X_test  = test[features]

# ── 時系列クロスバリデーション ─────────────────────────────
# 時系列データのため未来データがバリデーションに入るよう TimeSeriesSplit を使用
tscv = TimeSeriesSplit(n_splits=5)
cv_rmses = []

for fold, (tr_idx, val_idx) in enumerate(tscv.split(X_train)):
    X_tr, X_val = X_train.iloc[tr_idx], X_train.iloc[val_idx]
    y_tr, y_val = y_train.iloc[tr_idx], y_train.iloc[val_idx]
    m = LinearRegression()
    m.fit(X_tr, y_tr)
    val_rmse = np.sqrt(mean_squared_error(y_val, m.predict(X_val)))
    cv_rmses.append(val_rmse)
    print(f"  Fold {fold+1} Val RMSE: {val_rmse:.4f}")

print(f"CV RMSE: {np.mean(cv_rmses):.4f} ± {np.std(cv_rmses):.4f}")

# ── 全学習データで最終モデルを学習 ─────────────────────────
model = LinearRegression()
model.fit(X_train, y_train)

train_rmse = np.sqrt(mean_squared_error(y_train, model.predict(X_train)))
print(f"Train RMSE: {train_rmse:.4f}")

# 係数を絶対値の大きい順に表示
print("\n特徴量の係数:")
for col, coef in sorted(zip(features, model.coef_), key=lambda x: abs(x[1]), reverse=True):
    print(f"  {col}: {coef:.6f}")

# ── 予測・提出ファイル生成 ──────────────────────────────────
y_pred = model.predict(X_test)

submission = pd.DataFrame({"id": test["id"], "tokyo_price": y_pred.round(2)})
submission.to_csv("submission_baseline.csv", index=False)
print(f"\n予測完了: submission_baseline.csv ({len(submission)}件)")
