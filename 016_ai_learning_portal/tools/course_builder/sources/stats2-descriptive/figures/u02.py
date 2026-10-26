"""単元2(代表値)の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u02_income_lines.png : 年収のヒストグラムと平均値・中央値・最頻値の位置
- u02_shapes_mmm.png   : 分布の形と3つの代表値の位置関係(右に裾・対称・左に裾)
- u02_ex_lines.png     : 演習「グラフ上の代表値」の図(a・b・c の線)
"""
import numpy as np
import pandas as pd
from scipy import stats

# ---------- 年収のヒストグラムと3つの代表値 ----------
inc = pd.read_csv("households.csv")["income"]
bins = np.arange(0, 2200, 100)
fig, ax = plt.subplots(figsize=(10, 3.6))
ax.hist(inc, bins=bins, color=PRIMARY)
ax.axvline(450, color="gray", linestyle=":", linewidth=2.5, zorder=3, label="mode = 450 (class value)")
ax.axvline(inc.median(), color="#333333", linestyle="--", linewidth=2.5, zorder=3, label=f"median = {inc.median():.0f}")
ax.axvline(inc.mean(), color=ACCENT, linewidth=2.5, zorder=3, label=f"mean = {inc.mean():.1f}")
ax.set_xlabel("income (10k yen)")
ax.set_ylabel("households")
ax.set_xticks(np.arange(0, 2200, 200))
ax.legend()
fig.tight_layout()
fig.savefig("u02_income_lines.png")
plt.close(fig)

# ---------- 分布の形と3つの代表値 ----------
fig, axes = plt.subplots(1, 3, figsize=(13, 3.2))
xs = np.linspace(0.01, 4, 400)
right = stats.lognorm(s=0.5)
panels = [
    ("right-skewed", xs, right.pdf(xs), np.exp(-0.25), right.median(), right.mean()),
    ("symmetric", xs - 2, stats.norm(0, 0.6).pdf(xs - 2), 0, 0, 0),
    ("left-skewed", 4 - xs, right.pdf(xs), 4 - np.exp(-0.25), 4 - right.median(), 4 - right.mean()),
]
for ax, (name, x, y, mode, med, mean) in zip(axes, panels):
    ax.plot(x, y, color=PRIMARY)
    ax.fill_between(x, y, color=PRIMARY, alpha=0.15)
    top = y.max() * 1.05
    ax.vlines(mode, 0, top, color="gray", linestyle=":", linewidth=2, label="mode")
    ax.vlines(med, 0, top, color=PRIMARY, linestyle="--", linewidth=2, label="median")
    ax.vlines(mean, 0, top, color=ACCENT, linewidth=2, label="mean")
    ax.set_title(name)
    ax.set_yticks([])
    ax.set_xticks([])
axes[0].legend(loc="upper right")
fig.tight_layout()
fig.savefig("u02_shapes_mmm.png")
plt.close(fig)

# ---------- 演習: グラフ上の代表値(ガンマ分布 k=2: 最頻値 1、中央値 約1.68、平均 2) ----------
g = stats.gamma(a=2)
xs = np.linspace(0, 8, 400)
ys = g.pdf(xs)
fig, ax = plt.subplots(figsize=(8, 3.2))
ax.plot(xs, ys, color=PRIMARY)
ax.fill_between(xs, ys, color=PRIMARY, alpha=0.15)
top = ys.max() * 1.12
for label, pos in [("a", g.mean()), ("b", 1.0), ("c", g.median())]:
    ax.vlines(pos, 0, top, color=ACCENT, linewidth=1.5)
    ax.text(pos, top * 1.02, label, ha="center", va="bottom", fontsize=13, fontweight="bold", color=ACCENT)
ax.set_ylim(0, top * 1.15)
ax.set_yticks([])
ax.set_xlabel("value")
fig.tight_layout()
fig.savefig("u02_ex_lines.png")
plt.close(fig)
print("median of gamma(2)", round(g.median(), 3))
