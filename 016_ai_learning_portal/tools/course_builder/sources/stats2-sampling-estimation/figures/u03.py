"""単元3(正規分布と標準正規分布表・二項分布の正規近似)の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u03_standardize.png : X ~ N(60, 10²) と標準化した Z の目盛りの対応、P(X > 75) = P(Z > 1.5)
- u03_binom_approx.png : 二項分布 B(100, 0.5) と正規近似、連続修正(59.5 から右)
"""
import numpy as np
from scipy import stats

# ---------- 標準化 ----------
x = np.linspace(20, 100, 600)
y = stats.norm.pdf(x, 60, 10)
fig, ax = plt.subplots(figsize=(10, 3.4))
ax.plot(x, y, color=PRIMARY)
ax.fill_between(x, y, color=PRIMARY, alpha=0.12)
ax.fill_between(x, y, where=x >= 75, color=ACCENT, alpha=0.6)
ax.annotate("P(X > 75) = P(Z > 1.5) = 0.0668", xy=(78, 0.004), xytext=(80, 0.025), arrowprops=dict(arrowstyle="->", color="#333333"))
ticks = [30, 40, 50, 60, 70, 75, 80, 90]
ax.set_xticks(ticks, [f"{t}\nz={(t - 60) / 10:g}" for t in ticks])
ax.set_yticks([])
ax.set_xlabel("X ~ N(60, 10^2)   (z = (x - 60) / 10)")
fig.tight_layout()
fig.savefig("u03_standardize.png")
plt.close(fig)

# ---------- 二項分布の正規近似と連続修正 ----------
k = np.arange(35, 66)
pmf = stats.binom.pmf(k, 100, 0.5)
fig, ax = plt.subplots(figsize=(10, 3.4))
colors = [ACCENT if v >= 60 else CATEGORY_COLORS[2] for v in k]
ax.bar(k, pmf, width=1.0, color=colors, edgecolor="white")
xs = np.linspace(35, 65, 400)
ax.plot(xs, stats.norm.pdf(xs, 50, 5), color=PRIMARY, linewidth=2, label="normal N(50, 5^2)")
ax.axvline(59.5, color="#333333", linestyle="--", linewidth=1.2)
ax.annotate("continuity correction:\nstart the area at 59.5", xy=(59.5, 0.04), xytext=(61, 0.06), fontsize=9,
            arrowprops=dict(arrowstyle="->", color="#333333"))
ax.set_xlabel("number of heads in 100 tosses")
ax.set_yticks([])
ax.legend(loc="upper left")
fig.tight_layout()
fig.savefig("u03_binom_approx.png")
plt.close(fig)
print("done")
