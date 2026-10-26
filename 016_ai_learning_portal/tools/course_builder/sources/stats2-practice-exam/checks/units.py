"""単元1〜5(分野別の本番形式の問題)に使う数値を計算して確かめる。選択肢の誤答(よくある間違い)の値も計算する。"""
import math

import numpy as np
from scipy import stats

N, T, C, F = stats.norm, stats.t, stats.chi2, stats.f

print("===== 単元1 記述統計")
x = np.array([4, 7, 9, 10, 15])
print("1-3 平均", x.mean(), "不偏分散", x.var(ddof=1), "n で割る", x.var(), "標準偏差", round(x.std(ddof=1), 3))
print("1-4 変動係数 A 8/50", 8 / 50, "B 15/120", 15 / 120)
print("1-5 z", (72 - 60) / 8, "偏差値", 50 + 10 * (72 - 60) / 8)
print("1-6 相関 -9/(3*5)", -9 / 15)
b = 24 / 16
print("1-7 b", b, "a", 50 - b * 20, "予測 x=26", 50 - b * 20 + b * 26)
g = (1.2 * 0.9 * 1.25) ** (1 / 3)
print("1-8 幾何平均", round(g, 4), "成長率%", round((g - 1) * 100, 2), "算術平均%", round((20 - 10 + 25) / 3, 2))

print("===== 単元2 データ収集と確率")
print("2-3 P(A∩B)=0.25*0.4", 0.25 * 0.4, "P(A∪B)", 0.5 + 0.4 - 0.1)
pos = 0.02 * 0.95 + 0.98 * 0.10
print("2-4 P(+)", round(pos, 4), "P(D|+)", round(0.02 * 0.95 / pos, 4))
print("2-5 E[4-2X]", 4 - 2 * 3, "V", 4 * 2)
print("2-6 B(4,0.5) P(X>=3)", stats.binom.sf(2, 4, 0.5))
print("2-7 Po(1.5) P(X>=2)", round(1 - math.exp(-1.5) * 2.5, 4), "e^-1.5", round(math.exp(-1.5), 4), "P(X>=2) with given 0.2231", round(1 - 0.2231 * 2.5, 4))
print("2-8 指数 平均4 中央値 4 ln2", round(4 * math.log(2), 3), "with 0.693", 4 * 0.693)

print("===== 単元3 標本分布と推定")
print("3-1 SE", 12 / 6, "z", (53 - 50) / 2, "P", round(N.sf(1.5), 4))
print("3-3 z0.10", round(N.ppf(0.9), 3), "上位10%", 500 + 100 * 1.282)
tq = T.ppf(0.975, 15)
print("3-4 t0.025(15)", round(tq, 3), "CI", 24 - 2.131 * 4 / 4, 24 + 2.131 * 4 / 4)
se = math.sqrt(0.3 * 0.7 / 400)
print("3-5 SE", round(se, 5), "CI", round(0.3 - 1.96 * se, 3), round(0.3 + 1.96 * se, 3))
print("3-6 n", (1.96 / 0.03) ** 2 * 0.25, math.ceil((1.96 / 0.03) ** 2 * 0.25))
lo, hi = C.ppf(0.025, 9), C.ppf(0.975, 9)
print("3-7 χ2 下側 2.5%点", round(lo, 3), "上側 2.5%点", round(hi, 3), "CI", round(81 / 19.023, 3), round(81 / 2.700, 3))

print("===== 単元4 仮説検定")
t = (52.4 - 50) / (5 / 5)
print("4-3 t", t, "t0.025(24)", round(T.ppf(0.975, 24), 3), "t0.005(24)", round(T.ppf(0.995, 24), 3), "p", round(2 * T.sf(t, 24), 4))
z = (0.6 - 0.5) / math.sqrt(0.25 / 200)
print("4-4 z", round(z, 3), "z0.005", round(N.ppf(0.995), 3), "p", round(2 * N.sf(z), 4))
sp2 = (9 * 10 + 9 * 8) / 18
t = (30 - 26) / math.sqrt(sp2 * (1 / 10 + 1 / 10))
print("4-5 sp2", sp2, "t", round(t, 3), "t0.025(18)", round(T.ppf(0.975, 18), 3))
t = 1.5 / (2 / math.sqrt(8))
print("4-6 t", round(t, 3), "t0.025(7)", round(T.ppf(0.975, 7), 3))
obs = np.array([[30, 20], [20, 30]])
chi2, p, dof, exp = stats.chi2_contingency(obs, correction=False)
print("4-7 χ2", round(chi2, 3), "df", dof, "p", round(p, 4), "χ2_0.05(1)", round(C.ppf(0.95, 1), 3))
crit = 100 + 1.645 * 2
print("4-8 棄却の境界", crit, "検出力 P(Z > (crit-105)/2)", round(N.sf((crit - 105) / 2), 4), "z", (crit - 105) / 2)

print("===== 単元5 回帰と実験計画")
for name, coef, se_ in (("const", 15.2, 4.0), ("x1", 1.26, 0.42), ("x2", 0.35, 0.25)):
    tv = coef / se_
    print("5-1 出力", name, "t", round(tv, 3), "p", round(2 * T.sf(abs(tv), 37), 4))
print("5-1 t0.025(37)", round(T.ppf(0.975, 37), 3), "予測 15.2+1.26*10+0.35*20", 15.2 + 1.26 * 10 + 0.35 * 20)
print("5-2 R2 1-120/400", 1 - 120 / 400, "F", ((400 - 120) / 2) / (120 / 27), "F0.05(2,27)", round(F.ppf(0.95, 2, 27), 3))
print("5-3 adj A p=3 R2=.70 n=31", round(1 - 0.30 * 30 / 27, 4), "B p=6 R2=.72", round(1 - 0.28 * 30 / 24, 4))
print("5-4 ダミー 予測 40+0.8*50+12", 40 + 0.8 * 50 + 12, "-6", 40 + 0.8 * 50 - 6)
va, ve = 84 / 2, 180 / 15
print("5-6 VA", va, "VE", ve, "F", va / ve, "F0.05(2,15)", round(F.ppf(0.95, 2, 15), 3))
print("5-7 誤差自由度 3*2*(3-1)", 3 * 2 * 2)
print("5-8 VIF 12.5 R2", 1 - 1 / 12.5)
print("4-8 P(Z>0.855)", round(N.sf(0.855), 4))
# 問題文で与える分布表の値(誤答の選択肢用を含む)
print("表 P(Z>0.25)", round(N.sf(0.25), 4), "z0.05", round(N.ppf(0.95), 3), "t0.025(16)", round(T.ppf(0.975, 16), 3), "t0.025(9)", round(T.ppf(0.975, 9), 3))
print("表 t0.025(14)", round(T.ppf(0.975, 14), 3), "χ2_0.05(4)", round(C.ppf(0.95, 4), 3), "F0.05(2,17)", round(F.ppf(0.95, 2, 17), 3))
