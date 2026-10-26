"""小テストに使う数値を計算して確かめる。"""
import math

from scipy import stats

N, C, F = stats.norm, stats.chi2, stats.f
print("問1", 20 / 100 ** 0.5)
print("問3", 1 / 16)
print("問5 z", (60 - 70) / 5, round(N.cdf(-2), 4))
print("問6 z", (40.5 - 50) / 5, round(N.cdf(-1.9), 4), "正確", round(stats.binom.cdf(40, 100, 0.5), 4))
print("問7 F0.05(5,10)", round(F.ppf(0.95, 5, 10), 3), "下側", round(1 / F.ppf(0.95, 5, 10), 4), round(F.ppf(0.05, 10, 5), 4))
print("問9", 20 * 9 / 10)
print("問11", 1.96 * 15 / 5)
print("問12", (1.96 * 5 / 1) ** 2, math.ceil((1.96 * 5 / 1) ** 2))
print("問13 SE", math.sqrt(0.25 / 400), "下限", 0.5 - 1.96 * math.sqrt(0.25 / 400))
print("問14 χ2(10) 上側2.5%", round(C.ppf(0.975, 10), 3), "下限", round(80 / C.ppf(0.975, 10), 4))
