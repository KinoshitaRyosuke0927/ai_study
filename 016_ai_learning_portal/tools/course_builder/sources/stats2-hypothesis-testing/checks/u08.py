"""単元8(独立性の検定)の解説・演習に使う数値を計算して確かめる。"""
import numpy as np
from scipy import stats


def independence(table):
    t = np.asarray(table, float)
    row, col, n = t.sum(1), t.sum(0), t.sum()
    e = np.outer(row, col) / n
    chi = ((t - e) ** 2 / e).sum()
    df = (t.shape[0] - 1) * (t.shape[1] - 1)
    return e, chi, df, 1 - stats.chi2.cdf(chi, df)


# 解説: 性別 × 購入(2 × 2)
e, chi, df, p = independence([[12, 28], [27, 33]])
print("2x2 期待度数", e.round(2).tolist(), "χ2", round(chi, 3), "df", df, "p", round(p, 4))
print("  (O-E)^2/E", ((np.array([[12, 28], [27, 33]]) - e) ** 2 / e).round(3).tolist())
chi_y, p_y, _, _ = stats.chi2_contingency([[12, 28], [27, 33]], correction=True)
print("  イェーツの補正あり χ2", round(chi_y, 3), "p", round(p_y, 4))

# 演習3: 30/20/20/30
e, chi, df, p = independence([[30, 20], [20, 30]])
print("演習3 期待度数", e.tolist(), "χ2", chi, "p", round(p, 4))
# 演習5: 年代 × 利用(3 × 2)
table = [[30, 20], [25, 25], [15, 35]]
e, chi, df, p = independence(table)
print("演習5 期待度数", e.round(2).tolist(), "χ2", round(chi, 3), "df", df, "p", round(p, 4))
print("  上側5%", round(stats.chi2.ppf(0.95, 2), 3), "上側1%", round(stats.chi2.ppf(0.99, 2), 3))
# 演習1: 期待度数
print("演習1", 60 * 50 / 150)
