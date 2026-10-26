"""単元2(大数の法則・中心極限定理)の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u02_lln.png    : サイコロを振り続けたときの平均の推移(大数の法則)
- u02_clt.png    : 右に裾が長い母集団からの標本平均の分布(n = 2・10・30)と正規分布
- u02_ex_clt.png : 演習「標本の大きさの判定」(A: n = 30、B: n = 1、C: n = 5)
"""
import numpy as np
from scipy import stats

# ---------- 大数の法則 ----------
rng = np.random.default_rng(4)
fig, ax = plt.subplots(figsize=(10, 3.4))
n = np.arange(1, 1001)
for i, color in enumerate([PRIMARY, SERIES_COLORS[2], SERIES_COLORS[3]]):
    rolls = rng.integers(1, 7, 1000)
    ax.plot(n, np.cumsum(rolls) / n, color=color, linewidth=1.2, label=f"trial {i + 1}")
ax.axhline(3.5, color=ACCENT, linestyle="--", linewidth=1.5, label="population mean 3.5")
ax.set_xscale("log")
ax.set_ylim(1, 6)
ax.set_xlabel("number of rolls (log scale)")
ax.set_ylabel("running mean")
ax.legend(ncol=4, loc="upper right")
fig.tight_layout()
fig.savefig("u02_lln.png")
plt.close(fig)

# ---------- 中心極限定理 ----------
rng = np.random.default_rng(2)
scale = 1.0  # 指数分布(母平均 1、母標準偏差 1)
fig, axes = plt.subplots(1, 4, figsize=(14, 3.0))
x = np.linspace(0, 4, 400)
axes[0].plot(x, stats.expon.pdf(x), color=PRIMARY)
axes[0].fill_between(x, stats.expon.pdf(x), color=PRIMARY, alpha=0.2)
axes[0].set_title("population (exponential)")
for ax, k in zip(axes[1:], (2, 10, 30)):
    means = rng.exponential(scale, (20000, k)).mean(axis=1)
    ax.hist(means, bins=np.linspace(0, 3, 60), color=PRIMARY, density=True)
    xs = np.linspace(0, 3, 300)
    ax.plot(xs, stats.norm.pdf(xs, 1, 1 / k ** 0.5), color=ACCENT, linewidth=1.5)
    ax.set_title(f"sample mean, n = {k}")
for ax in axes:
    ax.set_yticks([])
fig.tight_layout()
fig.savefig("u02_clt.png")
plt.close(fig)

# ---------- 演習: A(n = 30)・B(n = 1)・C(n = 5) ----------
rng = np.random.default_rng(8)
fig, axes = plt.subplots(1, 3, figsize=(12, 2.9), sharex=True)
for ax, (name, k) in zip(axes, [("A", 30), ("B", 1), ("C", 5)]):
    means = rng.exponential(1.0, (20000, k)).mean(axis=1)
    ax.hist(means, bins=np.linspace(0, 4, 60), color=PRIMARY, density=True)
    ax.set_title(name, fontsize=15, fontweight="bold")
    ax.set_yticks([])
    ax.set_xlabel("sample mean")
fig.tight_layout()
fig.savefig("u02_ex_clt.png")
plt.close(fig)
print("done")
