"""小テストに使う数値を計算して確かめる。"""
import math

from scipy import stats

print("問2 比例配分 技術 280/800*40", 280 / 800 * 40)
print("問5 独立 P(A∪B) 0.6+0.3-0.18", round(0.6 + 0.3 - 0.6 * 0.3, 4))
print("問6 P(A|B) 0.15/0.6", 0.15 / 0.6)
p_def = 0.7 * 0.01 + 0.3 * 0.04
print("問7 P(不良) 0.7*0.01+0.3*0.04", round(p_def, 4))
print("問8 P(B|不良)", round(0.3 * 0.04 / p_def, 4))
e = 1 * 0.2 + 2 * 0.5 + 3 * 0.3
e2 = 1 * 0.2 + 4 * 0.5 + 9 * 0.3
print("問9 E", round(e, 4), "E[X2]", round(e2, 4), "V", round(e2 - e * e, 4))
print("問10 V[X-2Y] 独立 4+4*1", 4 + 4 * 1)
print("問11 B(20,0.1) 分散", round(20 * 0.1 * 0.9, 4))
print("問12 ポアソン λ=4 P(X=2)", round(stats.poisson.pmf(2, 4), 4), "e^-4=0.0183 で", round(8 * 0.0183, 4))
print("問14 指数 平均10 P(X>5)", round(math.exp(-0.5), 4))
print("問15 無記憶性 P(X>30|X>20)=P(X>10)", round(math.exp(-1), 4))
