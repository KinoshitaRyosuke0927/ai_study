"""単元1(仮説検定の考え方)の解説・演習に使う数値を計算して確かめる。"""
from scipy import stats

z = stats.norm
print("パーセント点 z0.05", round(z.ppf(0.95), 3), "z0.025", round(z.ppf(0.975), 3), "z0.01", round(z.ppf(0.99), 3), "z0.005", round(z.ppf(0.995), 3))

# 解説: コイン 100 回で表 60 回(正規近似)
n, x, p0 = 100, 60, 0.5
mean, sd = n * p0, (n * p0 * (1 - p0)) ** 0.5
zz = (x - mean) / sd
print("コイン 平均", mean, "SD", sd, "z", zz, "両側p", round(2 * (1 - z.cdf(zz)), 4), "片側p", round(1 - z.cdf(zz), 4))
print("二項分布の正確な両側p", round(2 * (1 - stats.binom.cdf(59, n, p0)), 4))

# 演習2・3: コイン 400 回で表 225 回
n, x = 400, 225
mean, sd = n * 0.5, (n * 0.25) ** 0.5
zz = (x - mean) / sd
print("演習 平均", mean, "SD", sd, "z", zz, "両側p", round(2 * (1 - z.cdf(zz)), 4))
print("  5%両側 棄却?", abs(zz) > 1.96, " 1%両側 棄却?", abs(zz) > 2.576)
