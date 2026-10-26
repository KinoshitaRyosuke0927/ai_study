"""小テストに使う数値を計算して確かめる。"""
import math

from scipy import stats

T, F = stats.t, stats.f
print("問1 s2 SE=45 n=17", 45 / 15)
print("問2 se(b) s2=9 Sxx=100", math.sqrt(9 / 100))
print("問3 下限 0.9 - t0.025(20)*0.3", round(0.9 - T.ppf(0.975, 20) * 0.3, 4), "t0.025(20)", round(T.ppf(0.975, 20), 3))
print("問4 F=t2 t=-3.2", round(3.2 ** 2, 4))
print("問5 残差自由度 n=36 p=5", 36 - 5 - 1)
print("問7 調整済み n=41 p=4 R2=0.64", round(1 - 0.36 * 40 / 36, 4))
print("問8 F", round((0.64 / 4) / (0.36 / 36), 4), "F0.05(4,36)", round(F.ppf(0.95, 4, 36), 3))
print("問9 VIF R2=0.75", 1 / (1 - 0.75))
print("問11 一元配置 k=5 各6 誤差自由度", 30 - 5)
fv = (60 / 3) / (90 / 18)
print("問12 F", fv, "F0.05(3,18)", round(F.ppf(0.95, 3, 18), 3), "p", round(F.sf(fv, 3, 18), 4))
print("問14 繰り返しなし a=4 b=5 誤差自由度", 3 * 4)
