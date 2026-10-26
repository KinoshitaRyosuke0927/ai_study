"""単元6〜7 の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u06_oneway.png        : 一元配置の例(3 群 × 4 個)と、群間・群内のばらつき
- u07_interaction.png   : 交互作用のない場合とある場合の平均値のグラフ
- u07_ex_interaction.png : 演習用の平均値のグラフ A〜C
"""
import numpy as np

# ---------- 一元配置 ----------
groups = {"A": [5, 7, 6, 6], "B": [9, 11, 10, 10], "C": [7, 8, 9, 8]}
fig, ax = plt.subplots(figsize=(7.5, 3.8))
for i, (name, vals) in enumerate(groups.items()):
    vals = np.array(vals)
    offs = np.array([-0.12, -0.04, 0.04, 0.12])
    ax.scatter(i + offs, vals, s=30, color=PRIMARY, zorder=3)
    m = vals.mean()
    ax.plot([i - 0.25, i + 0.25], [m, m], color=PRIMARY, linewidth=2.5)
    for o, v in zip(offs, vals):
        ax.plot([i + o, i + o], [m, v], color=PRIMARY, linewidth=0.8, alpha=0.6)
    if m != 8:
        ax.annotate("", xy=(i + 0.32, m), xytext=(i + 0.32, 8), arrowprops=dict(arrowstyle="->", color=ACCENT))
        ax.text(i + 0.36, (m + 8) / 2, f"{m - 8:+.0f}", color=ACCENT, fontsize=9, va="center")
ax.axhline(8, color=ACCENT, linestyle="--", linewidth=1.2)
ax.text(-0.45, 8.15, "grand mean 8", color=ACCENT, fontsize=9)
ax.set_xticks(range(3), ["A (mean 6)", "B (mean 10)", "C (mean 8)"])
ax.set_xlim(-0.5, 2.6)
ax.set_ylabel("y")
ax.set_title("between groups: group mean - grand mean / within groups: value - group mean", fontsize=10)
fig.tight_layout()
fig.savefig("u06_oneway.png")
plt.close(fig)


# ---------- 交互作用 ----------
def means_plot(ax, rows, title):
    for (label, vals), color, marker in zip(rows, SERIES_COLORS, ("o", "s")):
        ax.plot(range(1, len(vals) + 1), vals, marker=marker, color=color, linewidth=2, label=label)
    ax.set_xticks(range(1, len(rows[0][1]) + 1), [f"B{j}" for j in range(1, len(rows[0][1]) + 1)])
    ax.set_title(title, fontsize=10)
    ax.set_ylim(0, 12)
    ax.legend(fontsize=8, loc="upper left")


fig, axes = plt.subplots(1, 2, figsize=(11, 3.6), sharey=True)
means_plot(axes[0], [("A1", [4, 6, 7]), ("A2", [6, 8, 9])], "no interaction: lines are parallel")
means_plot(axes[1], [("A1", [4, 6, 8]), ("A2", [8, 6, 4])], "interaction: effect of A depends on B")
axes[0].set_ylabel("mean of y")
fig.tight_layout()
fig.savefig("u07_interaction.png")
plt.close(fig)

fig, axes = plt.subplots(1, 3, figsize=(13, 3.4), sharey=True)
means_plot(axes[0], [("A1", [3, 5, 9]), ("A2", [7, 7, 5])], "A")
means_plot(axes[1], [("A1", [5, 5, 5]), ("A2", [8, 8, 8])], "B")
means_plot(axes[2], [("A1", [3, 5, 6]), ("A2", [5, 7, 8])], "C")
axes[0].set_ylabel("mean of y")
fig.tight_layout()
fig.savefig("u07_ex_interaction.png")
plt.close(fig)
