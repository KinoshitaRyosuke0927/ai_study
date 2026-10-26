"""単元3(散らばり・箱ひげ図)の解説・演習に使う数値を計算して確かめる。

四分位数は「中央値で分けた下半分・上半分の中央値」で求める(データの個数が奇数のときは中央値を両側に含めない)。
"""
import numpy as np
import pandas as pd


def quartiles(values):
    """下半分・上半分の中央値で四分位数を求める。"""
    v = np.sort(np.asarray(values, dtype=float))
    n = len(v)
    lower, upper = v[: n // 2], v[(n + 1) // 2:]
    return np.median(lower), np.median(v), np.median(upper)


# 解説: 分散の手計算
x = np.array([4, 7, 7, 9, 13])
d = x - x.mean()
print("分散例 平均", x.mean(), "偏差", d.tolist(), "偏差の2乗", (d ** 2).tolist(), "偏差平方和", (d ** 2).sum())
print("  分散(n)", (d ** 2).sum() / 5, "不偏分散", (d ** 2).sum() / 4, "標準偏差(不偏)", round(np.sqrt((d ** 2).sum() / 4), 3))
print("  2乗の平均", (x ** 2).mean(), "平均の2乗", x.mean() ** 2, "差", (x ** 2).mean() - x.mean() ** 2)

# 解説: 四分位数と外れ値
y = [2, 4, 5, 7, 8, 10, 12, 13, 15, 20]
q1, q2, q3 = quartiles(y)
iqr = q3 - q1
print("四分位例", q1, q2, q3, "IQR", iqr, "基準", q1 - 1.5 * iqr, q3 + 1.5 * iqr)
y2 = [2, 4, 5, 7, 8, 10, 12, 13, 15, 30]
q1, q2, q3 = quartiles(y2)
print("四分位例(30)", q1, q2, q3, "上の基準", q3 + 1.5 * (q3 - q1))

# 解説: 平均が同じで散らばりが違う2つの分布(図に使う)
rng = np.random.default_rng(1)
a = rng.normal(60, 5, 300)
b = rng.normal(60, 15, 300)
print("A 平均", round(a.mean(), 1), "SD", round(a.std(ddof=1), 1), " B 平均", round(b.mean(), 1), "SD", round(b.std(ddof=1), 1))

# 演習1: 不偏分散
e = np.array([3, 7, 8, 10, 12])
de = e - e.mean()
print("演習1 平均", e.mean(), "偏差平方和", (de ** 2).sum(), "不偏分散", (de ** 2).sum() / 4)

# 演習2: Σx と Σx² から分散
n, sx, sxx = 10, 50, 290
print("演習2 平均", sx / n, "分散(n)", sxx / n - (sx / n) ** 2)

# 演習3: 12 個のデータの四分位数と外れ値
z = [3, 5, 6, 8, 9, 10, 11, 12, 14, 15, 18, 35]
q1, q2, q3 = quartiles(z)
iqr = q3 - q1
print("演習3", q1, q2, q3, "IQR", iqr, "下", q1 - 1.5 * iqr, "上", q3 + 1.5 * iqr, "外れ値", [v for v in z if v < q1 - 1.5 * iqr or v > q3 + 1.5 * iqr])

# 演習5: クラス別の数学の点数の箱ひげ図(図に使う。pandas の四分位数=線形補間)
st = pd.read_csv("students.csv")
for c, g in st.groupby("class")["math"]:
    q = g.quantile([0, 0.25, 0.5, 0.75, 1]).round(1).tolist()
    iqr = q[3] - q[1]
    out = g[(g < q[1] - 1.5 * iqr) | (g > q[3] + 1.5 * iqr)].tolist()
    print("class", c, "5数", q, "IQR", round(iqr, 2), "範囲", q[4] - q[0], "外れ値", out, "平均", round(g.mean(), 1))
