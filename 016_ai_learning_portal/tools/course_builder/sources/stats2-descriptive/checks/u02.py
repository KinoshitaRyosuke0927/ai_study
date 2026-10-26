"""単元2(代表値)の解説・演習に使う数値を計算して確かめる。"""
import numpy as np
import pandas as pd

# 解説: 外れ値を含む小さなデータ
x = np.array([3, 5, 5, 6, 8, 9, 40])
print("例1 平均", round(x.mean(), 2), "中央値", np.median(x), "最頻値 5", "合計", x.sum())
print("例1 40を除く 平均", round(x[:-1].mean(), 2), "中央値", np.median(x[:-1]))
print("例1 偏差", (x - x.mean()).round(2).tolist(), "偏差の合計", round((x - x.mean()).sum(), 10))

# 解説: 度数分布表からの代表値(滞在時間)
mids = np.array([5, 15, 25, 35, 45])
f = np.array([6, 15, 9, 7, 3])
n = f.sum()
print("滞在時間 n", n, "平均", (mids * f).sum() / n, "Σ階級値×度数", (mids * f).sum(), "累積", f.cumsum().tolist())
# 中央値の階級内の比例配分(線形補間)
L, F, fm, h = 10, 6, 15, 10
print("補間した中央値", round(L + (n / 2 - F) / fm * h, 2))

# 解説: 年収の平均・中央値・最頻値(図に使う)
hh = pd.read_csv("households.csv")
inc = hh["income"]
freq = pd.cut(inc, bins=np.arange(0, 2200, 100), right=False).value_counts().sort_index()
top = freq.idxmax()
print("年収 平均", round(inc.mean(), 1), "中央値", inc.median(), "最頻階級", top, "階級値", (top.left + top.right) / 2)
print("10%トリム平均", round(float(pd.Series(np.sort(inc)[20:-20]).mean()), 1))

# 演習1・2: 通勤時間の度数分布表
mids = np.array([7.5, 22.5, 37.5, 52.5, 67.5, 82.5])
f = np.array([4, 9, 15, 11, 7, 4])
n = f.sum()
print("通勤 n", n, "平均", (mids * f).sum() / n, "Σ", (mids * f).sum(), "累積", f.cumsum().tolist())
print("通勤 累積相対度数", (f.cumsum() / n).round(2).tolist())
print("通勤 45分以上の割合", f[3:].sum() / n)

# 演習3: 加重平均
sizes = np.array([25, 40, 35])
means = np.array([72.0, 58.5, 64.0])
w = (sizes * means).sum() / sizes.sum()
print("加重平均", w, "合計点", (sizes * means).sum(), "平均の平均", round(means.mean(), 2))

# 演習5: 外れ値の追加
y = np.array([12, 15, 15, 18, 20, 21, 25])
y2 = np.append(y, 200)
print("外れ値 前 平均", round(y.mean(), 2), "中央値", np.median(y), " 後 平均", round(y2.mean(), 2), "中央値", np.median(y2))
