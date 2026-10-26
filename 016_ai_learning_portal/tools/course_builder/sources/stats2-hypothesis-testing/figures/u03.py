"""単元3(母平均の検定)の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u03_t_vs_normal.png : t 分布(自由度 3・9)と標準正規分布
- u03_t_test.png      : 自由度 9 の t 分布の両側 5% 棄却域と、t = 1.581 の位置
"""
import numpy as np
from scipy import stats

x = np.linspace(-4.5, 4.5, 600)

# ---------- t 分布と標準正規分布 ----------
fig, ax = plt.subplots(figsize=(9, 3.4))
ax.plot(x, stats.norm.pdf(x), color="#333333", linewidth=2, label="standard normal")
ax.plot(x, stats.t.pdf(x, 9), color=PRIMARY, linewidth=2, label="t (df = 9)")
ax.plot(x, stats.t.pdf(x, 3), color=ACCENT, linewidth=2, linestyle="--", label="t (df = 3)")
ax.set_yticks([])
ax.legend()
ax.set_title("t distributions have heavier tails; they approach the normal as df grows")
fig.tight_layout()
fig.savefig("u03_t_vs_normal.png")
plt.close(fig)

# ---------- t 検定の棄却域(自由度 9) ----------
y = stats.t.pdf(x, 9)
c = stats.t.ppf(0.975, 9)
fig, ax = plt.subplots(figsize=(9, 3.2))
ax.plot(x, y, color=PRIMARY)
ax.fill_between(x, y, color=PRIMARY, alpha=0.12)
for side in (-1, 1):
    m = side * x >= c
    ax.fill_between(x[m], y[m], color=ACCENT, alpha=0.6)
ax.axvline(1.581, color="#333333", linewidth=1.5, zorder=3)
ax.annotate("t = 1.581\n(not in the rejection region)", xy=(1.581, 0.1), xytext=(-3.8, 0.3),
            arrowprops=dict(arrowstyle="->", color="#333333"), fontsize=9)
ax.set_xticks([-c, 0, 1.581, c], [f"-{c:.3f}", "0", "", f"{c:.3f}"])
ax.set_yticks([])
ax.set_xlabel("t (df = 9)")
ax.set_title("two-sided 5%: reject if |t| > 2.262")
fig.tight_layout()
fig.savefig("u03_t_test.png")
plt.close(fig)
print("done")
