"""単元6〜7(一元配置・二元配置の分散分析)の解説・演習に使う数値を計算して確かめる。"""
import numpy as np
from scipy import stats

F = stats.f

# 単元6 の例:3 群 × 4 個
groups = {"A": [5, 7, 6, 6], "B": [9, 11, 10, 10], "C": [7, 8, 9, 8]}
allv = np.concatenate([np.array(v) for v in groups.values()])
gm = allv.mean()
sb = sum(len(v) * (np.mean(v) - gm) ** 2 for v in groups.values())
sw = sum(((np.array(v) - np.mean(v)) ** 2).sum() for v in groups.values())
st = ((allv - gm) ** 2).sum()
fv = (sb / 2) / (sw / 9)
print("u6 例 平均", {k: np.mean(v) for k, v in groups.items()}, "全体", gm)
print("u6 例 SB", sb, "SW", sw, "ST", st, "F", round(fv, 3), "F0.05(2,9)", round(F.ppf(0.95, 2, 9), 3), "p", F.sf(fv, 2, 9))
print("scipy", stats.f_oneway(*groups.values()))

# 単元6 の演習:4 群 × 5 個、群平均 12, 15, 14, 19(全体 15)、SW = 96
means = np.array([12, 15, 14, 19])
sb = 5 * ((means - means.mean()) ** 2).sum()
fv = (sb / 3) / (96 / 16)
print("u6 演習 全体平均", means.mean(), "SB", sb, "VB", round(sb / 3, 4), "VW", 96 / 16, "F", round(fv, 4), "F0.05(3,16)", round(F.ppf(0.95, 3, 16), 3), "p", round(F.sf(fv, 3, 16), 4))

# 単元7 の例:繰り返しのない二元配置(A 3 水準 × ブロック 4)
y = np.array([[11, 11, 13, 13], [12, 15, 17, 16], [10, 13, 12, 13]])
gm = y.mean()
sa = 4 * ((y.mean(axis=1) - gm) ** 2).sum()
sbk = 3 * ((y.mean(axis=0) - gm) ** 2).sum()
st = ((y - gm) ** 2).sum()
se = st - sa - sbk
print("u7 例 行平均", y.mean(axis=1), "列平均", y.mean(axis=0), "全体", gm)
print("u7 例 SA", sa, "SB", sbk, "SE", se, "ST", st, "FA", (sa / 2) / (se / 6), "FB", (sbk / 3) / (se / 6))
print("u7 例 F0.05(2,6)", round(F.ppf(0.95, 2, 6), 3), "F0.05(3,6)", round(F.ppf(0.95, 3, 6), 3))

# 単元7 の演習:繰り返しのある二元配置(A 2 水準 × B 3 水準 × 4 回、N = 24)
ss = {"A": (48, 1), "B": (60, 2), "AB": (36, 2), "E": (90, 18)}
ve = 90 / 18
for k in ("A", "B", "AB"):
    s, d = ss[k]
    fv = (s / d) / ve
    print("u7 演習", k, "MS", s / d, "F", round(fv, 3), "F0.05", round(F.ppf(0.95, d, 18), 3), "p", round(F.sf(fv, d, 18), 4))
print("u7 演習 誤差自由度 24 - 1 - (1 + 2 + 2)", 24 - 1 - 5)
