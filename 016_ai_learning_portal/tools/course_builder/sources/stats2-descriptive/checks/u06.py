"""単元6(散布図と相関)の解説・演習に使う数値を計算して確かめる。"""
import numpy as np
import pandas as pd

# 解説: 共分散・相関係数の手計算
x = np.array([1, 2, 3, 4, 5])
y = np.array([2, 4, 5, 4, 5])
dx, dy = x - x.mean(), y - y.mean()
print("手計算 平均", x.mean(), y.mean(), "dx", dx.tolist(), "dy", dy.tolist(), "dxdy", (dx * dy).tolist())
sxy, sxx, syy = (dx * dy).sum(), (dx ** 2).sum(), (dy ** 2).sum()
print("  Sxy", sxy, "Sxx", sxx, "Syy", syy, "共分散(n-1)", sxy / 4, "r", round(sxy / np.sqrt(sxx * syy), 4))

# 解説: 相関行列(students.csv)
st = pd.read_csv("students.csv")
cols = ["study_hours", "math", "english", "science", "sleep_hours"]
print(st[cols].corr().round(2).to_string())

# 解説: 見かけの相関(kids.csv)
kids = pd.read_csv("kids.csv")
r_xy = kids["foot_cm"].corr(kids["vocab"])
r_xz = kids["foot_cm"].corr(kids["grade"])
r_yz = kids["vocab"].corr(kids["grade"])
partial = (r_xy - r_xz * r_yz) / np.sqrt((1 - r_xz ** 2) * (1 - r_yz ** 2))
within = kids.groupby("grade").apply(lambda g: g["foot_cm"].corr(g["vocab"]))
print("kids r_xy", round(r_xy, 3), "r_xz", round(r_xz, 3), "r_yz", round(r_yz, 3), "偏相関", round(partial, 3))
print("  学年内の相関", within.round(2).tolist())
# 偏相関の手計算の例(丸めた値で)
a, b, c = 0.83, 0.92, 0.94
print("偏相関例(丸め)", round((a - b * c) / np.sqrt((1 - b ** 2) * (1 - c ** 2)), 3))

# 演習1: 相関係数
print("演習1 r", -24 / np.sqrt(16 * 64))
# 演習2: 散布図 A〜D の相関係数(図と同じ乱数)
rng = np.random.default_rng(21)
n = 80
base = rng.normal(0, 1, n)
targets = {"A": 0.9, "B": 0.0, "C": -0.7, "D": 0.5}
for k, r in targets.items():
    noise = rng.normal(0, 1, n)
    yy = r * base + np.sqrt(1 - r ** 2) * noise
    print("演習2", k, round(np.corrcoef(base, yy)[0, 1], 2))
# 演習3: 偏相関
print("演習3 偏相関", (0.6 - 0.8 * 0.75) / np.sqrt((1 - 0.8 ** 2) * (1 - 0.75 ** 2)))
# 演習5: 相関行列の読み取り(students.csv の値をそのまま使う)
m = st[["study_hours", "math", "english", "sleep_hours"]].corr().round(2)
print(m.to_string())
