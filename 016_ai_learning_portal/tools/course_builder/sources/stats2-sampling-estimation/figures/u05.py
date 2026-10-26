"""単元5(点推定と推定量の性質)の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u05_bias_variance.png : 推定量のかたより(バイアス)とばらつきのイメージ(2 × 2)
- u05_unbiased_var.png  : n − 1 で割る分散と n で割る分散の分布(σ² = 4、n = 5)
"""
import numpy as np

# ---------- かたよりとばらつきのイメージ ----------
rng = np.random.default_rng(6)
fig, axes = plt.subplots(1, 4, figsize=(13, 3.2))
cases = [
    ("unbiased, small variance", 0.0, 0.25),
    ("unbiased, large variance", 0.0, 0.8),
    ("biased, small variance", 1.0, 0.25),
    ("biased, large variance", 1.0, 0.8),
]
for ax, (title, bias, sd) in zip(axes, cases):
    pts = rng.normal(0, sd, (40, 2)) + np.array([bias, 0.4 * bias])
    for r in (0.5, 1.0, 1.5):
        ax.add_patch(plt.Circle((0, 0), r, fill=False, color="gray", linewidth=0.8))
    ax.scatter(pts[:, 0], pts[:, 1], s=12, color=PRIMARY, zorder=3)
    ax.plot(0, 0, "+", color=ACCENT, markersize=14, markeredgewidth=2, zorder=4)
    ax.set_xlim(-2, 2)
    ax.set_ylim(-2, 2)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(title, fontsize=10)
fig.tight_layout()
fig.savefig("u05_bias_variance.png")
plt.close(fig)

# ---------- 不偏分散と n で割る分散 ----------
rng = np.random.default_rng(3)
x = rng.normal(0, 2, (100000, 5))
v1 = x.var(axis=1, ddof=1)
v0 = x.var(axis=1, ddof=0)
fig, axes = plt.subplots(1, 2, figsize=(11, 3.2), sharex=True, sharey=True)
for ax, (title, v) in zip(axes, [("divide by n - 1 (unbiased)", v1), ("divide by n", v0)]):
    ax.hist(v, bins=np.linspace(0, 16, 60), color=PRIMARY, density=True)
    ax.axvline(4, color="#333333", linewidth=1.5, label="true variance 4")
    ax.axvline(v.mean(), color=ACCENT, linestyle="--", linewidth=2, label=f"average of estimates {v.mean():.2f}")
    ax.set_title(title)
    ax.set_yticks([])
    ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig("u05_unbiased_var.png")
plt.close(fig)
print("done")
