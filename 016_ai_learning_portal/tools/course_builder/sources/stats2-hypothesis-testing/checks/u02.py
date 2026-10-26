"""単元2(2種類の過誤と検出力)の解説・演習に使う数値を計算して確かめる。"""
from scipy import stats

N = stats.norm
# 解説: H0: μ = 50、σ = 6、右片側 5%。真の μ = 53
for n in (16, 64):
    se = 6 / n ** 0.5
    c = 50 + 1.645 * se
    beta = N.cdf((c - 53) / se)
    print(f"n={n} SE={se} 棄却の境界={c:.4f} 標準化={(c - 53) / se:.4f} β={beta:.4f} 検出力={1 - beta:.4f}")
# 有意水準 1% にした場合(n = 16)
se = 1.5
c = 50 + 2.326 * se
print("α=1% 境界", round(c, 4), "β", round(N.cdf((c - 53) / se), 4))

# 演習2: H0: μ = 100、σ = 10、n = 25、右片側 5%。真の μ = 105
se = 10 / 25 ** 0.5
c = 100 + 1.645 * se
zb = (c - 105) / se
print("演習2 SE", se, "境界", c, "標準化", round(zb, 4), "検出力", round(1 - N.cdf(zb), 4), "Φ(0.855)", round(N.cdf(0.855), 4))
