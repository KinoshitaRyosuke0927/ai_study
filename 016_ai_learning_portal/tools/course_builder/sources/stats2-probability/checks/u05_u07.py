"""単元5〜7(確率変数・離散型・連続型の分布)の解説・演習に使う数値を計算して確かめる。"""
import math

from scipy import stats

# 単元5: 確率分布表から期待値・分散
def ev(xs, ps):
    e = sum(x * p for x, p in zip(xs, ps))
    e2 = sum(x * x * p for x, p in zip(xs, ps))
    return e, e2, e2 - e * e


print("u5 例 サイコロ", ev(range(1, 7), [1 / 6] * 6))
print("u5 例 くじ 1000円:0.1, 100円:0.3, 0円:0.6", ev([1000, 100, 0], [0.1, 0.3, 0.6]))
e, e2, v = ev([0, 1, 2, 3], [0.1, 0.3, 0.4, 0.2])
print("u5 演習 E", round(e, 4), "E[X2]", round(e2, 4), "V", round(v, 4), "V[2X-3]", round(4 * v, 4))
print("u5 例 V[X+Y] 4+9+2*3", 4 + 9 + 2 * 3, "V[X-Y]", 4 + 9 - 2 * 3, "相関", 3 / (2 * 3))
print("u5 演習 V[X+Y] 5+3+2*(-1)", 5 + 3 + 2 * (-1), "相関 cov=6 sx=3 sy=5", 6 / 15)

# 単元6: 離散型の分布
print("u6 例 B(10,0.3) 平均", 3, "分散", 10 * 0.3 * 0.7, "P(X=2)", round(stats.binom.pmf(2, 10, 0.3), 4))
print("u6 演習 B(5,0.2) P(X=2)", round(stats.binom.pmf(2, 5, 0.2), 4), math.comb(5, 2) * 0.2 ** 2 * 0.8 ** 3)
print("u6 例 ポアソン λ=3 P(X=0)", round(math.exp(-3), 4), "P(X=1)", round(3 * math.exp(-3), 4), "P(X=2)", round(9 / 2 * math.exp(-3), 4))
print("u6 演習 ポアソン λ=2 P(X=0)", round(math.exp(-2), 4), "P(X<=1)", round(3 * math.exp(-2), 4))
print("u6 例 幾何 p=1/6 平均", 6, "P(X=3)", round((5 / 6) ** 2 / 6, 4))
print("u6 演習 幾何 p=0.25 平均", 4)
print("u6 例 超幾何 N=20 M=5 n=4 平均", 4 * 5 / 20, "P(X=0)", round(math.comb(15, 4) / math.comb(20, 4), 4))
print("u6 演習 超幾何 10個中3不良 2個 不良なし", round(math.comb(7, 2) / math.comb(10, 2), 4), math.comb(7, 2), math.comb(10, 2))
print("u6 負の二項 r=2 p=0.5 平均(失敗回数)", 2 * 0.5 / 0.5, "(試行回数)", 2 / 0.5)
print("u6 二項の近似 B(1000,0.002) と Po(2) P(0)", round(stats.binom.pmf(0, 1000, 0.002), 4), round(math.exp(-2), 4))

# 単元7: 連続型の分布
print("u7 例 一様 U(0,10) 平均", 5, "分散", round(100 / 12, 4), "P(2<X<5)", 3 / 10)
print("u7 演習 U(0,12) 分散", 144 / 12, "U(2,8) P(X>6.5)", (8 - 6.5) / 6)
print("u7 例 指数 平均 5分 P(X>10)", round(math.exp(-2), 4), "P(X<=5)", round(1 - math.exp(-1), 4))
print("u7 演習 指数 平均2 P(X>2)", round(math.exp(-1), 4), "λ=0.5 分散", 1 / 0.25)
print("u7 無記憶性 P(X>15|X>10) = P(X>5)", round(math.exp(-1), 4))
