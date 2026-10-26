"""単元4(母比率・母分散の検定)の解説・演習に使う数値を計算して確かめる。"""
from scipy import stats

N, C = stats.norm, stats.chi2
# カイ二乗分布のパーセント点
for df in (9, 15, 19):
    print(f"chi2 df={df}: 上側0.975 {C.ppf(0.025, df):.3f}  上側0.05 {C.ppf(0.95, df):.3f}  上側0.025 {C.ppf(0.975, df):.3f}  平均 {df}")

# 解説: 母比率(支持率)p0 = 0.4、n = 600、標本比率 0.44
se = (0.4 * 0.6 / 600) ** 0.5
z = (0.44 - 0.4) / se
print("比率 SE", round(se, 4), "z", round(z, 3), "両側p", round(2 * (1 - N.cdf(z)), 4))
# 解説: 母分散 n = 10、s2 = 6.0、σ0² = 4
chi = 9 * 6.0 / 4
print("分散 χ2", chi, "両側p", round(2 * min(C.cdf(chi, 9), 1 - C.cdf(chi, 9)), 4))

# 演習1: p0 = 0.5、n = 400、x = 176
ph = 176 / 400
se = (0.25 / 400) ** 0.5
z = (ph - 0.5) / se
print("演習1 標本比率", ph, "SE", se, "z", z, "左片側p", round(N.cdf(z), 4))
# 演習3: n = 16、s2 = 9、σ0² = 6
chi = 15 * 9 / 6
print("演習3 χ2", chi, "右片側p", round(1 - C.cdf(chi, 15), 4))
