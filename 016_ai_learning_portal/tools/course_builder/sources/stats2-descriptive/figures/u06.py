"""単元6(散布図と相関)の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u06_scatter_examples.png : 相関係数の値と散布図の見え方
- u06_quadrants.png        : 平均で4つに分けた散布図と、偏差の積の符号
- u06_limits.png           : 相関係数の限界(曲線的な関係・外れ値)
- u06_kids.png             : 見かけの相関(学年で色分けした散布図)
- u06_ex_scatter.png       : 演習「散布図と相関係数の対応」の散布図 A〜D
"""
import numpy as np
import pandas as pd


def with_r(rng, n, r):
    """相関係数がちょうど r になる (x, y) を作る。"""
    x = rng.normal(0, 1, n)
    e = rng.normal(0, 1, n)
    zx = (x - x.mean()) / x.std()
    e = e - e.mean()
    e = e - (e @ zx) / (zx @ zx) * zx  # x と無相関にする
    ze = e / e.std()
    return zx, r * zx + np.sqrt(1 - r ** 2) * ze


def scatter_row(fname, items, label_fmt):
    fig, axes = plt.subplots(1, len(items), figsize=(3.2 * len(items), 3.2))
    for ax, (label, x, y) in zip(axes, items):
        ax.scatter(x, y, s=12, color=PRIMARY)
        ax.set_title(label_fmt(label), fontsize=13, fontweight="bold")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_xlabel("x")
        ax.set_ylabel("y")
    fig.tight_layout()
    fig.savefig(fname)
    plt.close(fig)


# ---------- 相関係数の値と散布図 ----------
rng = np.random.default_rng(7)
items = [(f"r = {r}", *with_r(rng, 80, r)) for r in (0.95, 0.6, 0.0, -0.8)]
scatter_row("u06_scatter_examples.png", items, lambda s: s)

# ---------- 平均で4つに分けた散布図 ----------
st = pd.read_csv("students.csv")
x, y = st["study_hours"], st["math"]
fig, ax = plt.subplots(figsize=(6, 4.2))
pos = (x - x.mean()) * (y - y.mean()) > 0
ax.scatter(x[pos], y[pos], s=14, color=PRIMARY, label="(x - mean)(y - mean) > 0")
ax.scatter(x[~pos], y[~pos], s=14, color=ACCENT, label="(x - mean)(y - mean) < 0")
ax.axvline(x.mean(), color="gray", linestyle="--", linewidth=1)
ax.axhline(y.mean(), color="gray", linestyle="--", linewidth=1)
# 平均の線で分けた4つの領域の中ほどに、偏差の積の符号を書く
xl, xh, yl, yh = x.min(), x.max(), y.min(), y.max()
for tx, ty, s, c in [
    ((x.mean() + xh) / 2, (y.mean() + yh) / 2, "+", PRIMARY), ((xl + x.mean()) / 2, (yl + y.mean()) / 2, "+", PRIMARY),
    ((xl + x.mean()) / 2, (y.mean() + yh) / 2, "\u2212", ACCENT), ((x.mean() + xh) / 2, (yl + y.mean()) / 2, "\u2212", ACCENT),
]:
    ax.text(tx, ty, s, fontsize=26, fontweight="bold", ha="center", va="center", color=c, alpha=0.8,
            bbox=dict(boxstyle="circle", facecolor="white", edgecolor=c, alpha=0.9))
ax.set_xlabel("study hours / week")
ax.set_ylabel("math score")
ax.legend(loc="lower right", fontsize=8)
fig.tight_layout()
fig.savefig("u06_quadrants.png")
plt.close(fig)

# ---------- 相関係数の限界 ----------
rng = np.random.default_rng(3)
xu = rng.uniform(-3, 3, 100)
yu = xu ** 2 + rng.normal(0, 0.5, 100)
x2, y2 = rng.normal(0, 1, 30), rng.normal(0, 1, 30)
x3, y3 = np.append(x2, 8), np.append(y2, 8)
fig, axes = plt.subplots(1, 3, figsize=(11, 3.2))
for ax, (title, xa, ya) in zip(axes, [
    (f"curved relation: r = {np.corrcoef(xu, yu)[0, 1]:.2f}", xu, yu),
    (f"no outlier: r = {np.corrcoef(x2, y2)[0, 1]:.2f}", x2, y2),
    (f"one outlier added: r = {np.corrcoef(x3, y3)[0, 1]:.2f}", x3, y3),
]):
    ax.scatter(xa, ya, s=12, color=PRIMARY)
    ax.set_title(title, fontsize=11)
    ax.set_xticks([])
    ax.set_yticks([])
axes[2].scatter([8], [8], s=40, color=ACCENT, zorder=3)
fig.tight_layout()
fig.savefig("u06_limits.png")
plt.close(fig)

# ---------- 見かけの相関(学年で色分け) ----------
kids = pd.read_csv("kids.csv")
fig, ax = plt.subplots(figsize=(6.5, 4.2))
colors = ["#c9dfe0", "#9cc4c6", "#6aa3a8", "#3b7f86", "#2a5d62", "#173a3d"]
for (g, part), c in zip(kids.groupby("grade"), colors):
    ax.scatter(part["foot_cm"], part["vocab"], s=16, color=c, label=f"grade {g}")
ax.set_xlabel("foot size (cm)")
ax.set_ylabel("vocabulary")
ax.set_title(f"all grades: r = {kids['foot_cm'].corr(kids['vocab']):.2f}")
ax.legend(fontsize=8, ncol=2)
fig.tight_layout()
fig.savefig("u06_kids.png")
plt.close(fig)

# ---------- 演習: 散布図 A〜D(相関係数 0.9 / 0.0 / -0.7 / 0.5) ----------
rng = np.random.default_rng(21)
items = [(k, *with_r(rng, 80, r)) for k, r in [("A", 0.9), ("B", 0.0), ("C", -0.7), ("D", 0.5)]]
for k, xa, ya in items:
    print("演習", k, round(np.corrcoef(xa, ya)[0, 1], 3))
scatter_row("u06_ex_scatter.png", items, lambda s: s)
print("done")
