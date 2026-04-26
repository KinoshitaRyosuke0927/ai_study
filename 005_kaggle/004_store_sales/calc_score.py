"""
submission.csv の精度を submission_1st.csv を正解として RMSLE で測定する。

RMSLE（Root Mean Squared Log Error）:
  Kaggle の store-sales-time-series-forecasting の公式評価指標。

  RMSLE = sqrt( 1/n * sum( (log(1 + y_pred) - log(1 + y_true))^2 ) )

  log1p(sales) を目的変数にして学習しているため、
  RMSE ≈ RMSLE という関係が成立する。
"""

import numpy as np
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).parent

true_df = pd.read_csv(BASE_DIR / "submission_1st.csv")
pred_df = pd.read_csv(BASE_DIR / "submission.csv")

df = true_df.merge(pred_df, on="id", suffixes=("_true", "_pred"))

y_true = df["sales_true"].values
y_pred = df["sales_pred"].values

# 負値は clip（モデル出力が万一マイナスになってもエラーにならないよう）
y_true = np.clip(y_true, 0, None)
y_pred = np.clip(y_pred, 0, None)

rmsle = np.sqrt(np.mean((np.log1p(y_pred) - np.log1p(y_true)) ** 2))

print(f"対象サンプル数 : {len(df):,}")
print(f"RMSLE          : {rmsle:.6f}")
