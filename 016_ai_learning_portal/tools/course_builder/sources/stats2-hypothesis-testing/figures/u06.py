"""単元6(母分散の比・母比率の差の検定)の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u06_f_test.png : 自由度 (10, 15) の F 分布の両側 5% 棄却域と、F = 2.4 の位置
"""
import numpy as np
from scipy import stats

lo, hi = stats.f.ppf(0.025, 10, 15), stats.f.ppf(0.975, 10, 15)
x = np.linspace(0.01, 5, 600)
y = stats.f.pdf(x, 10, 15)
fig, ax = plt.subplots(figsize=(9, 3.2))
ax.plot(x, y, color=PRIMARY)
ax.fill_between(x, y, color=PRIMARY, alpha=0.12)
ax.fill_between(x, y, where=x <= lo, color=ACCENT, alpha=0.6)
ax.fill_between(x, y, where=x >= hi, color=ACCENT, alpha=0.6)
ax.axvline(2.4, color="#333333", linewidth=1.5, zorder=3)
ax.annotate("F = 2.4", xy=(2.4, 0.2), xytext=(3.4, 0.45), arrowprops=dict(arrowstyle="->", color="#333333"))
ax.set_xticks([lo, 1, hi], [f"{lo:.3f}", "1", f"{hi:.3f}"])
ax.set_yticks([])
ax.set_xlabel("F (df = 10, 15)")
ax.set_title("two-sided 5%: reject if F < 0.284 or F > 3.060")
fig.tight_layout()
fig.savefig("u06_f_test.png")
plt.close(fig)
print("done")
