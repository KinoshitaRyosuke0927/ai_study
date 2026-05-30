"""
追加特徴量の効果を1つずつ検証するスクリプト
ベースライン特徴量に各候補を1つずつ追加してCV RMSEを比較する
"""
import pandas as pd
import numpy as np
from lightgbm import LGBMRegressor, early_stopping
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import TimeSeriesSplit

# ── データ読み込み・前処理 ─────────────────────────────────
train = pd.read_csv("../pre_eval.csv")
test  = pd.read_csv("../test_eval.csv")

train["date"] = pd.to_datetime(train["date"])
test["date"]  = pd.to_datetime(test["date"])

median_temp = train["temp"].median()
train["temp"] = train["temp"].fillna(median_temp)
test["temp"]  = test["temp"].fillna(median_temp)

# ── 候補特徴量の生成 ───────────────────────────────────────
for df in [train, test]:
    df["supply_demand_ratio"] = df["sell_amount"] / df["buy_amount"]
    df["surplus"]             = df["sell_amount"] - df["buy_amount"]
    df["contract_rate"]       = df["contracted_amount"] / df["buy_amount"]
    df["month"]               = df["date"].dt.month
    df["season"]              = df["month"].map({
        12: 4, 1: 4, 2: 4,
         3: 1, 4: 1, 5: 1,
         6: 2, 7: 2, 8: 2,
         9: 3, 10: 3, 11: 3,
    })

# ── ベースライン特徴量 ─────────────────────────────────────
base_features = [
    "frame", "dayofweek", "is_holiday",
    "temp",
    "power_result", "power_prediction", "usage_rate", "power_supply",
    "sell_amount", "buy_amount", "contracted_amount",
]

# ── 検証対象の候補特徴量 ───────────────────────────────────
candidate_features = [
    "supply_demand_ratio",
    "surplus",
    "contract_rate",
    "month",
    "season",
]

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


# ── ベースラインのCV RMSE を計算 ───────────────────────────
print("特徴量の個別効果を検証中...\n")
baseline_score = cv_rmse(base_features)
print(f"{'ベースライン（追加なし）':<30} CV RMSE: {baseline_score:.4f}")
print("-" * 50)

# ── 各候補特徴量を1つずつ追加して比較 ─────────────────────
results = []
for feat in candidate_features:
    score = cv_rmse(base_features + [feat])
    diff  = score - baseline_score
    mark  = "✓ 改善" if diff < 0 else "✗ 悪化"
    print(f"  + {feat:<28} CV RMSE: {score:.4f}  ({diff:+.4f})  {mark}")
    results.append({"feature": feat, "cv_rmse": score, "diff": diff})

# ── 結果サマリ ─────────────────────────────────────────────
print("\n" + "=" * 50)
print("【採用推奨特徴量（ベースラインより改善）】")
improved = [r for r in results if r["diff"] < 0]
if improved:
    for r in sorted(improved, key=lambda x: x["diff"]):
        print(f"  {r['feature']}: {r['cv_rmse']:.4f}  ({r['diff']:+.4f})")
else:
    print("  改善する特徴量はありませんでした")
