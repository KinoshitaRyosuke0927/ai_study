"""単元9(時系列)の解説・演習に使う数値を計算して確かめる。"""
import numpy as np
import pandas as pd


def acf_k(x, k):
    """自己相関係数(分母は系列全体の偏差平方和)。"""
    d = np.asarray(x, dtype=float) - np.mean(x)
    return (d[:-k] * d[k:]).sum() / (d ** 2).sum()


# 解説: 年間売上と成長率
df = pd.read_csv("monthly_sales.csv")
df["year"] = df["month"].str[:4].astype(int)
total = df.groupby("year")["sales"].sum().round(1)
g = total.pct_change().dropna()
print("年間売上", total.to_dict())
print("成長率(%)", (g * 100).round(2).to_dict())
print("算術平均", round(g.mean() * 100, 3), "幾何平均", round(((total[2025] / total[2018]) ** (1 / 7) - 1) * 100, 3))
# 解説: 前月比・前年同月比
s = df.set_index("month")["sales"]
tbl = pd.DataFrame({"sales": s, "mom": (s.pct_change() * 100).round(1), "yoy": (s.pct_change(12) * 100).round(1)})
print(tbl.loc["2024-11":"2025-02"].to_string())
# 解説: 幾何平均の例
print("+50% -50%", round((1.5 * 0.5) ** 0.5 - 1, 4))
# 解説: 3項移動平均の例
v = np.array([12, 15, 18, 14, 16, 20, 17])
print("3項移動平均", [round(v[i - 1:i + 2].mean(), 2) for i in range(1, 6)])
# 解説: 自己相関の手計算の例
x = np.array([4, 8, 6, 10, 12])
d = x - x.mean()
print("自己相関例 平均", x.mean(), "偏差", d.tolist(), "偏差平方和", (d ** 2).sum(), "ラグ1の積", (d[:-1] * d[1:]).tolist(), "r1", acf_k(x, 1))

# 演習1: 幾何平均
print("演習1", round(((133.1 / 100) ** (1 / 3) - 1) * 100, 4))
# 演習2: 3項移動平均
w = np.array([21, 25, 20, 24, 28, 30])
print("演習2 4番目の3項移動平均", w[2:5].mean())
# 演習3: 4項の中心化移動平均
u = np.array([10, 14, 12, 18, 16])
print("演習3", (0.5 * u[0] + u[1] + u[2] + u[3] + 0.5 * u[4]) / 4)
# 小テスト: 自己相関
q = np.array([3, 5, 4, 8, 10])
dq = q - q.mean()
print("小テスト 偏差", dq.tolist(), "平方和", (dq ** 2).sum(), "積", (dq[:-1] * dq[1:]).tolist(), "r1", round(acf_k(q, 1), 4))
