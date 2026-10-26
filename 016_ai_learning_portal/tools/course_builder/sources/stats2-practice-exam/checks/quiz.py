"""模擬試験(小テスト)に使う数値を計算して確かめる。選択肢の誤答の値も計算する。"""
import math

import numpy as np
from scipy import stats

N, T, C, F = stats.norm, stats.t, stats.chi2, stats.f

x = np.array([3, 5, 6, 8, 9, 10, 12, 13, 15, 18, 30])
print("問1 平均", round(x.mean(), 3), "中央値", np.median(x))
print("問3 加重平均", (30 * 62 + 20 * 72) / 50, "単純平均", (62 + 72) / 2)
print("問4 華氏 平均", 1.8 * 20 + 32, "標準偏差", 1.8 * 5, "誤:+32", 1.8 * 5 + 32, "分散", (1.8 * 5) ** 2)
print("問5 b = r sy/sx", 0.8 * 10 / 5, "誤 r sx/sy", 0.8 * 5 / 10)
print("問6 賛成のうち女性", 90 / 150, "男性の賛成率", 60 / 100, "女性の賛成率", 90 / 150)

print("問8 ちょうど一方", 0.3 * 0.4 + 0.7 * 0.6)
pd_ = 0.4 * 0.03 + 0.6 * 0.01
print("問9 P(不良)", pd_, "P(M1|不良)", round(0.4 * 0.03 / pd_, 4))
print("問10 cov", 0.5 * 3 * 4, "V[X+Y]", 9 + 16 + 2 * 6)
z = (27.5 - 20) / 4
print("問11 z", z, "P", round(N.sf(z), 4), "P(Z>=1.88)", round(N.sf(1.88), 4), "正確", round(stats.binom.sf(27, 100, 0.2), 4))
print("問12", round(math.comb(8, 2) / math.comb(10, 2), 4))

print("問13 SE", 16 / 8, "z", 3 / 2, "P", round(2 * N.sf(1.5), 4))
print("問14 CI", 80 - 1.96 * 2, 80 + 1.96 * 2)
print("問16 t0.025(8)", round(T.ppf(0.975, 8), 3), "CI", round(15 - 2.306, 3), round(15 + 2.306, 3))
se = math.sqrt(0.6 * 0.4 / 200 + 0.5 * 0.5 / 200)
print("問17 SE", round(se, 4), "CI", round(0.1 - 1.96 * se, 3), round(0.1 + 1.96 * se, 3))
print("問18 F0.05(8,5)", round(F.ppf(0.95, 8, 5), 3), "下側5%点 F(5,8)", round(F.ppf(0.05, 5, 8), 4), "1/4.818", round(1 / 4.818, 4))

print("問19 z=1.80 片側 1.645 両側 1.96 p片側", round(N.sf(1.8), 4))
t = (103 - 100) / (6 / 4)
print("問20 t", t, "t0.025(15)", round(T.ppf(0.975, 15), 3), "t0.05(15)", round(T.ppf(0.95, 15), 3))
print("問21 χ2", 10 * 18 / 10, "χ2_0.05(10)", round(C.ppf(0.95, 10), 3))
print("問22 F", 24 / 8, "F0.025(12,10)", round(F.ppf(0.975, 12, 10), 3))
obs = np.array([8, 12, 9, 11, 6, 14])
print("問23 χ2", ((obs - 10) ** 2 / 10).sum(), "χ2_0.05(5)", round(C.ppf(0.95, 5), 3))

for name, coef, se_ in (("const", 20.5, 5.0), ("x1", 2.10, 0.50), ("x2", -1.20, 0.80), ("x3", 0.90, 0.30)):
    tv = coef / se_
    print("問25", name, "t", round(tv, 3), "p", round(2 * T.sf(abs(tv), 46), 4))
print("問25 t0.025(46)", round(T.ppf(0.975, 46), 3))
print("問26 F", round((0.6 / 3) / (0.4 / 20), 4), "F0.05(3,20)", round(F.ppf(0.95, 3, 20), 3))
print("問27", 50 + 3 * 10 - 8)
va, ve = 45 / 3, 80 / 16
print("問28 F", va / ve, "F0.05(3,16)", round(F.ppf(0.95, 3, 16), 3))
print("問29", 2 * 5)
print("問30 se", math.sqrt(8 / 50), "t", 1.2 / math.sqrt(8 / 50))
# 問題文で与える分布表の値(誤答の選択肢用を含む)
print("表 P(Z>0.1875)", round(N.sf(0.1875), 4), "P(Z>=2.0)", round(N.sf(2.0), 4), "P(Z>=2.125)", round(N.sf(2.125), 4))
print("表 F0.05(5,8)", round(F.ppf(0.95, 5, 8), 3), "F0.025(13,11)", round(F.ppf(0.975, 13, 11), 3), "F0.05(4,20)", round(F.ppf(0.95, 4, 20), 3))
print("表 t0.025(9)", round(T.ppf(0.975, 9), 3), "χ2_0.05(11)", round(C.ppf(0.95, 11), 3), "χ2_0.05(6)", round(C.ppf(0.95, 6), 3))
