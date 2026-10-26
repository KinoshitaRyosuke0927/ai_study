"""単元3(散らばり・箱ひげ図)の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u03_boxplot_parts.png  : 箱ひげ図の各部の名前(解説の例 2,4,5,7,8,10,12,13,15,30)
- u03_box_hist.png       : ヒストグラムと箱ひげ図の対応(右に裾・対称・左に裾)
- u03_spread_compare.png : 平均が同じで散らばりが違う2つの分布
- u03_ex_match.png       : 演習「ヒストグラムと箱ひげ図の対応」
- u03_ex_class_box.png   : 演習「クラス別の箱ひげ図の読み取り」
"""
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle

DARK = "#333333"

# ---------- 箱ひげ図の各部の名前(四分位数は下半分・上半分の中央値:Q1=5, 中央値=9, Q3=13) ----------
fig, ax = plt.subplots(figsize=(11, 2.8))
q1, med, q3, lo, hi, out, fence = 5, 9, 13, 2, 15, 30, 25
y0, h = 0.4, 0.4
ax.add_patch(Rectangle((q1, y0), q3 - q1, h, facecolor=PRIMARY, alpha=0.25, edgecolor=PRIMARY, linewidth=2))
ax.plot([med, med], [y0, y0 + h], color=PRIMARY, linewidth=3)
ax.plot([lo, q1], [y0 + h / 2] * 2, color=PRIMARY, linewidth=2)
ax.plot([q3, hi], [y0 + h / 2] * 2, color=PRIMARY, linewidth=2)
ax.plot([lo, lo], [y0 + 0.1, y0 + h - 0.1], color=PRIMARY, linewidth=2)
ax.plot([hi, hi], [y0 + 0.1, y0 + h - 0.1], color=PRIMARY, linewidth=2)
ax.plot(out, y0 + h / 2, "o", color=ACCENT, markersize=9)
ax.axvline(fence, color=ACCENT, linestyle="--", linewidth=1)
labels = [
    (lo, "min (within fence)\n= 2"), (q1, "Q1 = 5"), (med, "median = 9"), (q3, "Q3 = 13"),
    (hi, "max (within fence)\n= 15"), (fence, "Q3 + 1.5 IQR\n= 25"), (out, "outlier\n= 30"),
]
for x, text in labels:
    ax.annotate(text, xy=(x, y0 + h + 0.02), xytext=(x, 1.25), ha="center", fontsize=9,
                arrowprops=dict(arrowstyle="-", color="gray", linewidth=0.8))
ax.annotate("", xy=(q1, 0.3), xytext=(q3, 0.3), arrowprops=dict(arrowstyle="<->", color=DARK))
ax.text((q1 + q3) / 2, 0.12, "IQR = Q3 - Q1 = 8", ha="center", fontsize=9)
ax.set_xlim(0, 32)
ax.set_ylim(0, 1.6)
ax.set_yticks([])
ax.set_xticks(range(0, 33, 2))
for side in ("left", "top", "right"):
    ax.spines[side].set_visible(False)
fig.tight_layout()
fig.savefig("u03_boxplot_parts.png")
plt.close(fig)

# ---------- ヒストグラムと箱ひげ図の対応 ----------
rng = np.random.default_rng(3)
right = rng.gamma(2.0, 1.5, 600)
sym = rng.normal(6, 1.6, 600)
left = 12 - rng.gamma(2.0, 1.5, 600)
fig, axes = plt.subplots(2, 3, figsize=(13, 4.2), sharex="col", gridspec_kw={"height_ratios": [3, 1]})
for col, (name, data) in enumerate([("right-skewed", right), ("symmetric", sym), ("left-skewed", left)]):
    axes[0, col].hist(data, bins=24, color=PRIMARY)
    axes[0, col].set_title(name)
    axes[0, col].set_yticks([])
    axes[1, col].boxplot(data, orientation="horizontal", widths=0.6, patch_artist=True,
                         boxprops=dict(facecolor=PRIMARY, alpha=0.3), medianprops=dict(color=DARK, linewidth=2),
                         flierprops=dict(marker="o", markersize=3, markerfacecolor=ACCENT, markeredgecolor=ACCENT))
    axes[1, col].set_yticks([])
fig.tight_layout()
fig.savefig("u03_box_hist.png")
plt.close(fig)

# ---------- 平均が同じで散らばりが違う2つの分布 ----------
rng = np.random.default_rng(1)
a = rng.normal(60, 5, 300)
b = rng.normal(60, 15, 300)
fig, axes = plt.subplots(2, 1, figsize=(9, 3.8), sharex=True)
axes[0].hist(a, bins=30, color=PRIMARY)
axes[0].set_title(f"A: mean {a.mean():.1f}, sd {a.std(ddof=1):.1f}")
axes[1].hist(b, bins=30, color=PRIMARY)
axes[1].set_title(f"B: mean {b.mean():.1f}, sd {b.std(ddof=1):.1f}")
axes[1].set_xlabel("score")
fig.tight_layout()
fig.savefig("u03_spread_compare.png")
plt.close(fig)

# ---------- 演習: ヒストグラム 1〜3 と箱ひげ図 A〜C の対応 ----------
# ヒストグラム 1: 右に裾 → 箱ひげ図 C / 2: 左に裾 → A / 3: 対称で散らばりが小さい → B
rng = np.random.default_rng(11)
h1 = rng.gamma(1.8, 8, 500) + 20
h2 = 100 - rng.gamma(1.8, 8, 500)
h3 = rng.normal(60, 6, 500)
fig = plt.figure(figsize=(13, 4.6))
for i, (name, data) in enumerate([("1", h1), ("2", h2), ("3", h3)]):
    ax = fig.add_subplot(2, 3, i + 1)
    ax.hist(data, bins=np.arange(0, 125, 5), color=PRIMARY)
    ax.set_xlim(0, 120)
    ax.set_yticks([])
    ax.set_title(f"histogram {name}", fontweight="bold")
ax = fig.add_subplot(2, 1, 2)
# 下から C(=1)・B(=3)・A(=2) の順に並べる
ax.boxplot([h1, h3, h2], orientation="horizontal", widths=0.55, patch_artist=True,
                 boxprops=dict(facecolor=PRIMARY, alpha=0.3), medianprops=dict(color=DARK, linewidth=2),
                 flierprops=dict(marker="o", markersize=3, markerfacecolor=ACCENT, markeredgecolor=ACCENT))
ax.set_yticks([1, 2, 3], ["C", "B", "A"], fontsize=13, fontweight="bold")
ax.set_xlim(0, 120)
ax.set_xlabel("value")
ax.set_title("box plots A, B, C")
fig.tight_layout()
fig.savefig("u03_ex_match.png")
plt.close(fig)

# ---------- 演習: クラス別の箱ひげ図(students.csv の数学) ----------
st = pd.read_csv("students.csv")
groups = [st.loc[st["class"] == c, "math"] for c in ["A", "B", "C"]]
fig, ax = plt.subplots(figsize=(8, 4))
ax.boxplot(groups, widths=0.5, patch_artist=True,
           boxprops=dict(facecolor=PRIMARY, alpha=0.3), medianprops=dict(color=DARK, linewidth=2),
           flierprops=dict(marker="o", markersize=5, markerfacecolor=ACCENT, markeredgecolor=ACCENT))
ax.set_xticks([1, 2, 3], ["class A", "class B", "class C"])
ax.set_yticks(range(10, 101, 10))
ax.set_ylim(10, 90)
ax.grid(axis="y", color="#dddddd", linewidth=0.8)
ax.set_axisbelow(True)
ax.set_ylabel("math score")
fig.tight_layout()
fig.savefig("u03_ex_class_box.png")
plt.close(fig)
print("done")
