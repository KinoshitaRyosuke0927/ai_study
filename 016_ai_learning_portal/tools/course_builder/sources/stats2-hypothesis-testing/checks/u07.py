"""単元7(適合度検定)の解説・演習に使う数値を計算して確かめる。"""
import numpy as np
from scipy import stats

C = stats.chi2
for df in (1, 2, 3, 4, 5):
    print(f"chi2 df={df}: 上側0.05 {C.ppf(0.95, df):.3f}  上側0.01 {C.ppf(0.99, df):.3f}")


def gof(o, e):
    o, e = np.asarray(o, float), np.asarray(e, float)
    parts = (o - e) ** 2 / e
    return parts.round(4).tolist(), round(parts.sum(), 4)


# 解説: サイコロ 60 回
print("サイコロ", gof([8, 12, 9, 11, 6, 14], [10] * 6), "p", round(1 - C.cdf(4.2, 5), 4))
# 解説: 血液型 4:2:3:1、n = 200
e = np.array([4, 2, 3, 1]) / 10 * 200
parts, chi = gof([90, 34, 56, 20], e)
print("血液型 期待", e.tolist(), parts, chi, "p", round(1 - C.cdf(chi, 3), 4))

# 演習1: 1:2:1、n = 80、観測 25, 35, 20
e = np.array([1, 2, 1]) / 4 * 80
print("演習1 期待", e.tolist(), gof([25, 35, 20], e))
# 演習5: 図の観測度数 62, 45, 41, 52(期待度数 50)
print("演習5", gof([62, 45, 41, 52], [50] * 4))
