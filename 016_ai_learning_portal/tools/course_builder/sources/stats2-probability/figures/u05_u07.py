"""単元5〜7 の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u05_dice_sum.png       : サイコロ2個の目の和の確率分布(期待値 7)
- u06_discrete_shapes.png : 二項・ポアソン・幾何・超幾何分布の確率関数
- u07_continuous.png     : 一様分布・指数分布の密度と、確率 = 面積
- u07_bivariate.png      : 2変量正規分布の散布図(相関係数 0・0.6・−0.8)
"""
import numpy as np
from scipy import stats

# ---------- サイコロ2個の和 ----------
s = np.arange(2, 13)
p = np.array([6 - abs(7 - v) for v in s]) / 36
fig, ax = plt.subplots(figsize=(8, 3.2))
ax.bar(s, p, color=PRIMARY, width=0.7)
for v, q in zip(s, p):
    ax.text(v, q + 0.004, f"{round(q * 36)}/36", ha="center", fontsize=8)
ax.axvline(7, color=ACCENT, linestyle="--", linewidth=1.5)
ax.text(7.15, 0.17, "E[X] = 7", color=ACCENT)
ax.set_xticks(s)
ax.set_xlabel("sum of two dice")
ax.set_ylabel("probability")
ax.set_ylim(0, 0.19)
fig.tight_layout()
fig.savefig("u05_dice_sum.png")
plt.close(fig)

# ---------- 離散型の分布 ----------
fig, axes = plt.subplots(1, 4, figsize=(14, 3.0))
k = np.arange(0, 11)
items = [
    ("binomial B(10, 0.3)", k, stats.binom.pmf(k, 10, 0.3)),
    ("Poisson (lambda = 3)", k, stats.poisson.pmf(k, 3)),
    ("geometric (p = 1/6)", np.arange(1, 16), stats.geom.pmf(np.arange(1, 16), 1 / 6)),
    ("hypergeometric (N=20, M=5, n=4)", np.arange(0, 5), stats.hypergeom.pmf(np.arange(0, 5), 20, 5, 4)),
]
for ax, (title, x, y) in zip(axes, items):
    ax.bar(x, y, color=PRIMARY, width=0.7)
    ax.set_title(title, fontsize=10)
    ax.set_yticks([])
fig.tight_layout()
fig.savefig("u06_discrete_shapes.png")
plt.close(fig)

# ---------- 連続型の分布 ----------
fig, axes = plt.subplots(1, 2, figsize=(12, 3.2))
x = np.linspace(-1, 11, 500)
y = np.where((x >= 0) & (x <= 10), 0.1, 0)
axes[0].plot(x, y, color=PRIMARY, linewidth=2)
axes[0].fill_between(x, y, where=(x >= 2) & (x <= 5), color=ACCENT, alpha=0.6)
axes[0].text(3.5, 0.04, "P(2 < X < 5)\n= 3 x 0.1 = 0.3", ha="center", fontsize=9)
axes[0].set_ylim(0, 0.15)
axes[0].set_title("uniform U(0, 10): density 1/10")
x = np.linspace(0, 25, 500)
y = stats.expon.pdf(x, scale=5)
axes[1].plot(x, y, color=PRIMARY, linewidth=2)
axes[1].fill_between(x, y, where=x >= 10, color=ACCENT, alpha=0.6)
axes[1].text(14, 0.05, "P(X > 10) = e^(-2)\n= 0.135", fontsize=9)
axes[1].set_title("exponential, mean 5 (lambda = 0.2)")
for ax in axes:
    ax.set_xlabel("x")
fig.tight_layout()
fig.savefig("u07_continuous.png")
plt.close(fig)

# ---------- 2変量正規分布 ----------
rng = np.random.default_rng(10)
fig, axes = plt.subplots(1, 3, figsize=(12, 3.6))
for ax, rho in zip(axes, (0.0, 0.6, -0.8)):
    xy = rng.multivariate_normal([0, 0], [[1, rho], [rho, 1]], 600)
    ax.scatter(xy[:, 0], xy[:, 1], s=6, color=PRIMARY, alpha=0.6)
    ax.set_title(f"rho = {rho}")
    ax.set_xlim(-3.5, 3.5)
    ax.set_ylim(-3.5, 3.5)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
fig.tight_layout()
fig.savefig("u07_bivariate.png")
plt.close(fig)
print("done")
