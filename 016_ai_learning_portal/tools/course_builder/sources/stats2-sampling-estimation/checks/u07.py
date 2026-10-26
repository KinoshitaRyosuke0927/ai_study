"""単元7(母比率・母分散・相関係数の区間推定)の解説・演習に使う数値を計算して確かめる。"""
import math

from scipy import stats

C = stats.chi2
# 解説: 母比率 n = 400、標本比率 0.3
se = math.sqrt(0.3 * 0.7 / 400)
print("比率 SE", round(se, 5), "95%", round(0.3 - 1.96 * se, 4), round(0.3 + 1.96 * se, 4))
# 解説: 必要な標本の大きさ(p = 0.5、誤差 0.03)
print("必要な n", (1.96 * 0.5 / 0.03) ** 2, math.ceil((1.96 * 0.5 / 0.03) ** 2))
# 解説: 母分散 n = 10、s² = 4
lo, hi = C.ppf(0.025, 9), C.ppf(0.975, 9)
print("χ2(9) 下側2.5%", round(lo, 3), "上側2.5%", round(hi, 3), "区間", round(36 / hi, 4), round(36 / lo, 4))
# 解説: 相関係数 r = 0.6、n = 28
z = math.atanh(0.6)
se = 1 / math.sqrt(25)
print("フィッシャー z", round(z, 4), "SE", se, "z の区間", round(z - 1.96 * se, 4), round(z + 1.96 * se, 4),
      "r の区間", round(math.tanh(z - 1.96 * se), 4), round(math.tanh(z + 1.96 * se), 4))

# 演習1: n = 100、標本比率 0.4
se = math.sqrt(0.4 * 0.6 / 100)
print("演習1 SE", round(se, 5), "上限", round(0.4 + 1.96 * se, 4))
# 演習2: 誤差 0.05
print("演習2", (1.96 * 0.5 / 0.05) ** 2, math.ceil((1.96 * 0.5 / 0.05) ** 2))
# 演習3: n = 16、s² = 9
lo = C.ppf(0.025, 15)
print("演習3 χ2(15) 下側2.5%", round(lo, 3), "上限", round(135 / lo, 3), "下限", round(135 / C.ppf(0.975, 15), 3))
# 演習4: r = 0.5、n = 19
z = math.atanh(0.5)
print("演習4 z", round(z, 4), "下限(z)", round(z - 1.96 / 4, 4), "r の下限", round(math.tanh(z - 1.96 / 4), 4))
