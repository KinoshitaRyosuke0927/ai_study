"""単元8(単回帰)の解説・演習に使う数値を計算して確かめる。"""
import numpy as np
import pandas as pd
import statsmodels.api as sm

# 解説: 最小二乗法の手計算(単元6と同じ 5 組のデータ)
x = np.array([1, 2, 3, 4, 5], dtype=float)
y = np.array([2, 4, 5, 4, 5], dtype=float)
sxy = ((x - x.mean()) * (y - y.mean())).sum()
sxx = ((x - x.mean()) ** 2).sum()
b = sxy / sxx
a = y.mean() - b * x.mean()
pred = a + b * x
res = y - pred
print("b", b, "a", round(a, 4), "予測", pred.round(2).tolist(), "残差", res.round(2).tolist(), "残差の和", round(res.sum(), 10))
st_ = ((y - y.mean()) ** 2).sum()
se = (res ** 2).sum()
sr = ((pred - y.mean()) ** 2).sum()
print("ST", st_, "SR", round(sr, 4), "SE", round(se, 4), "R2", round(sr / st_, 4), "r2", round(np.corrcoef(x, y)[0, 1] ** 2, 4))
print("VR", round(sr, 4), "VE", round(se / 3, 4), "F", round(sr / (se / 3), 4), "残差の標準誤差", round(np.sqrt(se / 3), 4))
print("b = r sy/sx", round(np.corrcoef(x, y)[0, 1] * y.std(ddof=1) / x.std(ddof=1), 4))

# 解説: statsmodels の出力(数学 ~ 学習時間)
st = pd.read_csv("students.csv")
m = sm.OLS(st["math"], sm.add_constant(st["study_hours"])).fit()
print(m.params.round(4).to_dict(), m.bse.round(3).to_dict(), m.tvalues.round(3).to_dict())
print("R2", round(m.rsquared, 3), "adjR2", round(m.rsquared_adj, 3), "F", round(m.fvalue, 2), "n", int(m.nobs), "残差SE", round(np.sqrt(m.mse_resid), 3))
print("10時間の予測", round(m.params["const"] + m.params["study_hours"] * 10, 1))

# 解説: 変数変換(会員数)
t = np.arange(1, 13)
mem = np.array([1020, 1105, 1230, 1310, 1450, 1590, 1710, 1880, 2050, 2240, 2410, 2650])
bl, al = np.polyfit(t, np.log(mem), 1)
print("対数回帰 b", round(bl, 4), "成長率", round((np.exp(bl) - 1) * 100, 2), "R2 対数", round(np.corrcoef(t, np.log(mem))[0, 1] ** 2, 4),
      "R2 そのまま", round(np.corrcoef(t, mem)[0, 1] ** 2, 4))

# 演習1: 要約統計量から予測
b1 = 5 / 2.5
a1 = 40 - b1 * 6
print("演習1 b", b1, "a", a1, "x=10 の予測", a1 + b1 * 10)
# 演習2: 分散分析表の F
print("演習2 SR", 200 - 50, "VE", 50 / 10, "F", (200 - 50) / (50 / 10), "R2", 150 / 200)
# 演習5: 対数変換の成長率
print("演習5", round((np.exp(0.05) - 1) * 100, 4))
