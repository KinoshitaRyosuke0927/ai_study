"""単元1の図を作る(Pyodide で実行し、PNG を出力する)。

共通スタイル(backend/app/ai/figure_style.py)を適用した状態で実行する前提(make-figures.mjs が適用する)。
PRIMARY / ACCENT / CATEGORY_COLORS はスタイル側で定義済み。

- u01_hist_cum.png       : 数学の点数(120人)のヒストグラムと累積相対度数グラフ(中央値の読み取り)
- u01_binwidth.png       : 同じ年収データを、階級幅を変えて描いたヒストグラム
- u01_bar_pie.png        : 地域別の世帯数の棒グラフと円グラフ
- u01_shape_examples.png : 分布の形の例
- u01_shapes.png         : 演習「分布の形の判定」のヒストグラム A〜E
"""
import numpy as np
import pandas as pd

# ---------- 数学の点数の度数分布表 ----------
st = pd.read_csv("students.csv")
math = st["math"]
bins = np.arange(10, 100, 10)  # 10, 20, ..., 90
freq = pd.cut(math, bins=bins, right=False).value_counts().sort_index()
rel = freq / freq.sum()
print("median", math.median())

# ヒストグラムと累積相対度数グラフ
fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
axes[0].hist(math, bins=bins, color=PRIMARY)
axes[0].set_xticks(bins)
axes[0].set_xlabel("math score")
axes[0].set_ylabel("frequency")
axes[0].set_title("Histogram (class width 10)")
cum_y = np.concatenate([[0], rel.cumsum().to_numpy()])
axes[1].plot(bins, cum_y, marker="o", color=PRIMARY)
axes[1].axhline(0.5, color="gray", linestyle="--", linewidth=1)
# 累積相対度数 0.5 となる点(直線で補間)
med_x = np.interp(0.5, cum_y, bins)
axes[1].axvline(med_x, color=ACCENT, linestyle=":", linewidth=1.5)
axes[1].annotate(f"about {med_x:.0f}", xy=(med_x, 0.5), xytext=(med_x + 8, 0.25), color=ACCENT,
                 arrowprops=dict(arrowstyle="->", color=ACCENT))
axes[1].set_xticks(bins)
axes[1].set_yticks([0, 0.25, 0.5, 0.75, 1.0])
axes[1].set_xlabel("math score")
axes[1].set_ylabel("cumulative relative frequency")
axes[1].set_title("Cumulative relative frequency")
fig.tight_layout()
fig.savefig("u01_hist_cum.png")
plt.close(fig)

# ---------- 階級幅による見え方の違い(年収) ----------
hh = pd.read_csv("households.csv")
income = hh["income"]
fig, axes = plt.subplots(1, 3, figsize=(13, 3.2))
for ax, width in zip(axes, [25, 100, 800]):
    ax.hist(income, bins=np.arange(0, 2400 + width, width), color=PRIMARY, linewidth=0.5)
    ax.set_title(f"class width {width}")
    ax.set_xlabel("income (10k yen)")
    ax.set_xlim(0, 2400)
axes[0].set_ylabel("frequency")
fig.tight_layout()
fig.savefig("u01_binwidth.png")
plt.close(fig)

# ---------- 棒グラフと円グラフ(地域別の世帯数) ----------
order = ["北日本", "関東", "中部", "近畿", "西日本"]
labels = ["North", "Kanto", "Chubu", "Kinki", "West"]
counts = hh["region"].value_counts().reindex(order)
fig, axes = plt.subplots(1, 2, figsize=(10, 3.6))
axes[0].bar(labels, counts.values, color=PRIMARY)
axes[0].set_ylabel("households")
axes[0].set_title("Bar chart")
axes[1].pie(counts.values, labels=labels, autopct="%.0f%%", startangle=90, counterclock=False,
            colors=CATEGORY_COLORS, textprops={"fontsize": 10})
axes[1].set_title("Pie chart")
fig.tight_layout()
fig.savefig("u01_bar_pie.png")
plt.close(fig)

# ---------- 分布の形の例 ----------
rng = np.random.default_rng(0)
shapes = [
    ("right-skewed", rng.lognormal(0, 0.6, 3000)),
    ("left-skewed", 10 - rng.lognormal(0, 0.6, 3000)),
    ("symmetric (bell)", rng.normal(0, 1, 3000)),
    ("uniform", rng.uniform(0, 1, 3000)),
    ("bimodal", np.concatenate([rng.normal(-2, 0.7, 1500), rng.normal(2, 0.7, 1500)])),
]
fig, axes = plt.subplots(1, 5, figsize=(14, 2.6))
for ax, (name, values) in zip(axes, shapes):
    ax.hist(values, bins=30, color=PRIMARY, linewidth=0.3)
    ax.set_title(name)
    ax.set_yticks([])
    ax.set_xticks([])
fig.tight_layout()
fig.savefig("u01_shape_examples.png")
plt.close(fig)

# ---------- 演習「分布の形の判定」のヒストグラム A〜E ----------
# 10 階級の度数(A: 左に裾が長い、B: 二峰、C: 右に裾が長い、D: 一様、E: 左右対称)
exercise = {
    "A": [1, 1, 2, 3, 4, 6, 9, 15, 17, 10],
    "B": [3, 9, 14, 8, 4, 4, 8, 14, 10, 3],
    "C": [4, 11, 17, 14, 8, 6, 4, 2, 1, 1],
    "D": [12, 13, 12, 12, 13, 12, 13, 12, 12, 13],
    "E": [1, 3, 7, 12, 17, 17, 12, 7, 3, 1],
}
fig, axes = plt.subplots(1, 5, figsize=(13, 2.8), sharey=True)
for ax, (name, c) in zip(axes, exercise.items()):
    ax.bar(np.arange(10), c, width=1.0, color=PRIMARY, linewidth=1)
    ax.set_title(name, fontsize=16, fontweight="bold")
    ax.set_xticks([])
    ax.set_xlabel("value (small → large)", fontsize=9)
axes[0].set_ylabel("frequency")
fig.tight_layout()
fig.savefig("u01_shapes.png")
plt.close(fig)
print("figures saved")
