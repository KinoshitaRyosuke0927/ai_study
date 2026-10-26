"""単元8(2つの母集団の区間推定)の解説・演習に使う数値を計算して確かめる。"""
import math

from scipy import stats

T, F = stats.t, stats.f
# 解説: 平均の差(等分散)n1 = 10、x̄1 = 75、s1² = 36 / n2 = 12、x̄2 = 70、s2² = 40
sp2 = (9 * 36 + 11 * 40) / 20
se = math.sqrt(sp2 * (1 / 10 + 1 / 12))
t = T.ppf(0.975, 20)
print("平均の差 sp2", sp2, "SE", round(se, 4), "t0.025(20)", round(t, 3), "区間", round(5 - t * se, 3), round(5 + t * se, 3))
# 解説: 分散の比 n1 = 11、s1² = 24 / n2 = 16、s2² = 10
r = 24 / 10
f1, f2 = F.ppf(0.975, 10, 15), F.ppf(0.975, 15, 10)
print("分散比 F0.025(10,15)", round(f1, 3), "F0.025(15,10)", round(f2, 3), "区間", round(r / f1, 4), round(r * f2, 4))
# 解説: 比率の差 60/200 と 45/200
p1, p2 = 0.3, 0.225
se = math.sqrt(p1 * (1 - p1) / 200 + p2 * (1 - p2) / 200)
print("比率の差 SE", round(se, 5), "区間", round(0.075 - 1.96 * se, 4), round(0.075 + 1.96 * se, 4))

# 演習1: 差 6、σ1²/n1 = 4、σ2²/n2 = 5
print("演習1 SE", math.sqrt(9), "下限", 6 - 1.96 * 3)
# 演習2: 0.5(n = 100)と 0.4(n = 100)
se = math.sqrt(0.25 / 100 + 0.24 / 100)
print("演習2 SE", round(se, 4), "下限", round(0.1 - 1.96 * se, 4), "上限", round(0.1 + 1.96 * se, 4))
# 演習4: 分散比 2、n1 = 11、n2 = 16
print("演習4 上限", round(2 * F.ppf(0.975, 15, 10), 3), "下限", round(2 / F.ppf(0.975, 10, 15), 4))
