"""単元1〜2(単回帰モデル、回帰係数の検定と区間推定)の解説・演習に使う数値を計算して確かめる。"""
import math

import numpy as np
from scipy import stats

T = stats.t

# 単元1・2 の例:「記述統計」の講座の 5 組のデータ
x = np.array([1, 2, 3, 4, 5])
y = np.array([2, 4, 5, 4, 5])
sxx = ((x - x.mean()) ** 2).sum()
b = ((x - x.mean()) * (y - y.mean())).sum() / sxx
a = y.mean() - b * x.mean()
se_res = ((y - a - b * x) ** 2).sum()
s2 = se_res / (len(x) - 2)
se_b = math.sqrt(s2 / sxx)
se_a = math.sqrt(s2 * (1 / len(x) + x.mean() ** 2 / sxx))
print("u1 例 b", b, "a", a, "Sxx", sxx, "SE", round(se_res, 4), "s2", round(s2, 4), "s", round(math.sqrt(s2), 4))
print("u1 例 se(b)", round(se_b, 4), "se(a)", round(se_a, 4))
print("u1 演習 SE=36 n=11 s2", 36 / 9, "se(b) s2=4 Sxx=25", math.sqrt(4 / 25))
print("u1 演習 y=10+2x, sd 3, x=5 P(y>23) = P(Z>1)", round(stats.norm.sf(1), 4))

t = b / se_b
print("u2 例 t", round(t, 4), "t0.025(3)", round(T.ppf(0.975, 3), 3), "p", round(2 * T.sf(t, 3), 4), "F=t2", round(t * t, 4))
print("u2 例 CI", round(b - T.ppf(0.975, 3) * se_b, 3), round(b + T.ppf(0.975, 3) * se_b, 3))
print("u2 例 記述統計の出力 t", round(2.1528 / 0.241, 3), "t0.025(118)", round(T.ppf(0.975, 118), 3))
print("u2 演習 t", 1.8 / 0.6, "t0.025(10)", round(T.ppf(0.975, 10), 3), "上限", round(1.8 + T.ppf(0.975, 10) * 0.6, 4), "下限", round(1.8 - T.ppf(0.975, 10) * 0.6, 4))
print("u2 演習 F=6.25 |t|", math.sqrt(6.25))
# 演習の出力(n = 20、自由度 18)
for name, coef, se in (("const", 12.4, 3.1), ("x", 0.85, 0.25)):
    tv = coef / se
    print("u2 出力", name, "t", round(tv, 3), "p", round(2 * T.sf(abs(tv), 18), 4), "CI", round(coef - T.ppf(0.975, 18) * se, 3), round(coef + T.ppf(0.975, 18) * se, 3))
print("t0.025(18)", round(T.ppf(0.975, 18), 3))
