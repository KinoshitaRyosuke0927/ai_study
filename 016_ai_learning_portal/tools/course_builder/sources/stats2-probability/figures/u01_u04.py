"""単元1〜4 の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u01_sampling_methods.png : 単純無作為・系統・層化・集落(クラスター)抽出のイメージ(母集団 100)
- u02_designs.png          : 完全無作為化法と乱塊法(ブロック)の区画配置
- u03_venn.png             : 事象 A・B のベン図(和事象・積事象)
- u04_tree.png             : 検査の例を 10000 人で考えた樹形図
"""
import numpy as np
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle

GRAY = "#d9dde0"

# ---------- 抽出法 ----------
rng = np.random.default_rng(5)
xs, ys = np.meshgrid(np.arange(10), np.arange(10))
xs, ys = xs.ravel(), ys.ravel()[::-1]
fig, axes = plt.subplots(1, 4, figsize=(14, 3.8))
sel_random = rng.choice(100, 10, replace=False)
sel_system = np.arange(3, 100, 10)
strata = np.repeat([0, 1, 2], [50, 30, 20])  # 上 5 行・次の 3 行・下 2 行
sel_strata = np.concatenate([rng.choice(np.where(strata == k)[0], m, replace=False) for k, m in [(0, 5), (1, 3), (2, 2)]])
clusters = (xs // 5) + 2 * (ys // 2)  # 5 x 2 のブロックが 10 個
sel_cluster = np.where(np.isin(clusters, [1, 6]))[0]
titles = ["simple random", "systematic (every 10th)", "stratified (3 strata)", "cluster (2 blocks)"]
for ax, title, sel in zip(axes, titles, [sel_random, sel_system, sel_strata, sel_cluster]):
    base = [CATEGORY_COLORS[[3, 2, 4][s]] for s in strata] if "stratified" in title else [GRAY] * 100
    ax.scatter(xs, ys, s=70, c=base, edgecolors="white")
    ax.scatter(xs[sel], ys[sel], s=70, color=ACCENT, edgecolors="white", zorder=3)
    if "cluster" in title:
        for cx in range(2):
            for cy in range(5):
                ax.add_patch(Rectangle((cx * 5 - 0.5, cy * 2 - 0.5), 5, 2, fill=False, edgecolor="gray", linewidth=0.8))
    ax.set_title(title, fontsize=11)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_aspect("equal")
fig.tight_layout()
fig.savefig("u01_sampling_methods.png")
plt.close(fig)

# ---------- 完全無作為化法と乱塊法 ----------
rng = np.random.default_rng(3)
fig, axes = plt.subplots(1, 2, figsize=(12, 3.6))
colors = {"A": CATEGORY_COLORS[0], "B": CATEGORY_COLORS[2], "C": CATEGORY_COLORS[4]}
layouts = [rng.permutation(list("AAAABBBBCCCC")).reshape(4, 3),
           np.array([rng.permutation(list("ABC")) for _ in range(4)])]
for ax, title, lay in zip(axes, ["completely randomized design", "randomized block design (rows = blocks)"], layouts):
    for r in range(4):
        for c in range(3):
            t = lay[r, c]
            ax.add_patch(Rectangle((c, 3 - r), 0.95, 0.9, color=colors[t]))
            ax.text(c + 0.47, 3 - r + 0.45, t, ha="center", va="center", fontsize=13, color="white" if t == "A" else "#333333")
    if "block" in title:
        for r in range(4):
            ax.add_patch(Rectangle((-0.05, 3 - r - 0.03), 3.0, 0.96, fill=False, edgecolor="#333333", linewidth=1.5))
            ax.text(3.1, 3 - r + 0.45, f"block {r + 1}", va="center", fontsize=9)
    ax.annotate("", xy=(-0.35, 0), xytext=(-0.35, 4), arrowprops=dict(arrowstyle="->", color="gray"))
    ax.text(-0.45, 2, "soil fertility", rotation=90, ha="right", va="center", fontsize=9, color="gray")
    ax.set_xlim(-0.7, 3.9)
    ax.set_ylim(-0.1, 4.1)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(title, fontsize=11)
fig.tight_layout()
fig.savefig("u02_designs.png")
plt.close(fig)

# ---------- ベン図 ----------
fig, ax = plt.subplots(figsize=(6, 3.4))
ax.add_patch(Rectangle((0, 0), 10, 6, fill=False, edgecolor="#333333"))
ax.add_patch(Circle((3.8, 3), 2.2, color=PRIMARY, alpha=0.35))
ax.add_patch(Circle((6.2, 3), 2.2, color=ACCENT, alpha=0.35))
ax.text(2.6, 3, "A", fontsize=16, ha="center", va="center")
ax.text(7.4, 3, "B", fontsize=16, ha="center", va="center")
ax.text(5, 3, "A and B", fontsize=9, ha="center", va="center")
ax.text(0.3, 5.5, "sample space", fontsize=9)
ax.set_xlim(-0.2, 10.2)
ax.set_ylim(-0.2, 6.2)
ax.set_aspect("equal")
ax.axis("off")
fig.tight_layout()
fig.savefig("u03_venn.png")
plt.close(fig)

# ---------- 樹形図(10000 人) ----------
fig, ax = plt.subplots(figsize=(10, 4.2))
nodes = {
    "all": (0.5, 2.0, "10000 people"),
    "D": (3.5, 3.2, "disease\n100 (1%)"),
    "H": (3.5, 0.8, "healthy\n9900 (99%)"),
    "DP": (7.0, 3.7, "positive\n99"),
    "DN": (7.0, 2.7, "negative\n1"),
    "HP": (7.0, 1.3, "positive\n495"),
    "HN": (7.0, 0.3, "negative\n9405"),
}
edges = [("all", "D", ""), ("all", "H", ""), ("D", "DP", "99%"), ("D", "DN", "1%"), ("H", "HP", "5%"), ("H", "HN", "95%")]
for a, b, label in edges:
    (x1, y1, _), (x2, y2, _) = nodes[a], nodes[b]
    ax.plot([x1 + 0.9, x2 - 0.9], [y1, y2], color="gray", linewidth=1)
    if label:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 0.12, label, fontsize=9, color="gray", ha="center")
for key, (x, y, text) in nodes.items():
    color = ACCENT if key in ("DP", "HP") else CATEGORY_COLORS[3]
    ax.add_patch(FancyBboxPatch((x - 0.85, y - 0.35), 1.7, 0.7, boxstyle="round,pad=0.05", color=color, alpha=0.8))
    ax.text(x, y, text, ha="center", va="center", fontsize=9)
ax.text(8.2, 2.5, "positive in total:\n99 + 495 = 594\n\nP(disease | positive)\n= 99 / 594 = 0.167", fontsize=10, va="center")
ax.set_xlim(-0.5, 10.5)
ax.set_ylim(-0.3, 4.3)
ax.axis("off")
fig.tight_layout()
fig.savefig("u04_tree.png")
plt.close(fig)
print("done")
