"""単元4(t 分布・カイ二乗分布・F 分布)の解説・演習に使う数値を計算して確かめる。"""
from scipy import stats

C, T, F = stats.chi2, stats.t, stats.f
for df in (5, 10, 15):
    print(f"chi2 df={df}: 平均 {df} 分散 {2 * df} 上側0.05 {C.ppf(0.95, df):.3f} 上側0.025 {C.ppf(0.975, df):.3f} 下側0.025 {C.ppf(0.025, df):.3f}")
for df in (5, 10, 30):
    print(f"t df={df}: 上側0.05 {T.ppf(0.95, df):.3f} 上側0.025 {T.ppf(0.975, df):.3f}")
print("z 0.05", round(stats.norm.ppf(0.95), 3), "0.025", round(stats.norm.ppf(0.975), 3))
for d1, d2 in [(5, 10), (10, 5), (8, 12), (12, 8)]:
    print(f"F({d1},{d2}) 上側0.05 {F.ppf(0.95, d1, d2):.3f}")
print("t^2 と F: t0.025(10)^2", round(T.ppf(0.975, 10) ** 2, 3), "F0.05(1,10)", round(F.ppf(0.95, 1, 10), 3))
print("F(5,10) の下側 5% 点", round(1 / F.ppf(0.95, 10, 5), 4), round(F.ppf(0.05, 5, 10), 4))

# 演習
print("演習2 しきい値", round(C.ppf(0.95, 10) * 4 / 10, 4))
print("演習3 F(8,12) の下側5%点 = 1/F0.05(12,8)", round(1 / F.ppf(0.95, 12, 8), 4), "F0.05(12,8)", round(F.ppf(0.95, 12, 8), 3))
