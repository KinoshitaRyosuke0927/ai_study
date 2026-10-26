"""単元1(仮説検定の考え方)の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u01_regions.png : 標準正規分布の棄却域(両側 5%・右片側 5%)
- u01_pvalue.png  : 検定統計量 z = 2.0 の両側 p 値
"""
import numpy as np
from scipy import stats

x = np.linspace(-4, 4, 600)
y = stats.norm.pdf(x)


def base(ax):
    ax.plot(x, y, color=PRIMARY)
    ax.fill_between(x, y, color=PRIMARY, alpha=0.12)
    ax.set_yticks([])
    ax.set_xlabel("z")


# ---------- 棄却域 ----------
fig, axes = plt.subplots(1, 2, figsize=(12, 3.2))
base(axes[0])
for side in (-1, 1):
    m = side * x >= 1.96
    axes[0].fill_between(x[m], y[m], color=ACCENT, alpha=0.6)
    axes[0].axvline(side * 1.96, color=ACCENT, linestyle="--", linewidth=1)
    axes[0].text(side * 2.9, 0.06, "2.5%", ha="center", color=ACCENT)
axes[0].set_xticks([-1.96, 0, 1.96], ["-1.96", "0", "1.96"])
axes[0].set_title("two-sided test (5%): reject if |z| > 1.96")
base(axes[1])
m = x >= 1.645
axes[1].fill_between(x[m], y[m], color=ACCENT, alpha=0.6)
axes[1].axvline(1.645, color=ACCENT, linestyle="--", linewidth=1)
axes[1].text(2.7, 0.07, "5%", ha="center", color=ACCENT)
axes[1].set_xticks([0, 1.645], ["0", "1.645"])
axes[1].set_title("one-sided test (5%): reject if z > 1.645")
fig.tight_layout()
fig.savefig("u01_regions.png")
plt.close(fig)

# ---------- p 値(z = 2.0、両側) ----------
fig, ax = plt.subplots(figsize=(8, 3.2))
base(ax)
for side in (-1, 1):
    m = side * x >= 2.0
    ax.fill_between(x[m], y[m], color=ACCENT, alpha=0.6)
ax.axvline(2.0, color="#333333", linewidth=1.5)
ax.annotate("observed z = 2.0", xy=(2.0, 0.12), xytext=(2.4, 0.25), arrowprops=dict(arrowstyle="->", color="#333333"))
ax.text(3.0, 0.03, "0.0228", ha="center", color=ACCENT)
ax.text(-3.0, 0.03, "0.0228", ha="center", color=ACCENT)
ax.set_title("two-sided p-value = 0.0228 x 2 = 0.0455")
ax.set_xticks([-2, 0, 2])
fig.tight_layout()
fig.savefig("u01_pvalue.png")
plt.close(fig)
print("done")
