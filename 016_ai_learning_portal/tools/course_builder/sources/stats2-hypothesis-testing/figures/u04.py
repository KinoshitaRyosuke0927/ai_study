"""単元4(母比率・母分散の検定)の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u04_chi2_shapes.png : カイ二乗分布の形(自由度 3・9・15)
- u04_var_test.png    : 自由度 9 のカイ二乗分布の両側 5% 棄却域と、χ² = 13.5 の位置
"""
import numpy as np
from scipy import stats

# ---------- カイ二乗分布の形 ----------
x = np.linspace(0.01, 35, 600)
fig, ax = plt.subplots(figsize=(9, 3.2))
for df, color, ls in [(3, ACCENT, "-"), (9, PRIMARY, "-"), (15, SERIES_COLORS[2], "--")]:
    ax.plot(x, stats.chi2.pdf(x, df), color=color, linestyle=ls, linewidth=2, label=f"df = {df}")
ax.set_yticks([])
ax.set_xlabel("chi-square")
ax.legend()
ax.set_title("chi-square distribution: positive values, right-skewed, mean = df")
fig.tight_layout()
fig.savefig("u04_chi2_shapes.png")
plt.close(fig)

# ---------- 母分散の検定の棄却域(自由度 9、両側 5%) ----------
lo, hi = stats.chi2.ppf(0.025, 9), stats.chi2.ppf(0.975, 9)
x = np.linspace(0.01, 30, 600)
y = stats.chi2.pdf(x, 9)
fig, ax = plt.subplots(figsize=(9, 3.2))
ax.plot(x, y, color=PRIMARY)
ax.fill_between(x, y, color=PRIMARY, alpha=0.12)
ax.fill_between(x, y, where=x <= lo, color=ACCENT, alpha=0.6)
ax.fill_between(x, y, where=x >= hi, color=ACCENT, alpha=0.6)
ax.axvline(13.5, color="#333333", linewidth=1.5, zorder=3)
ax.annotate("chi-square = 13.5", xy=(13.5, 0.05), xytext=(17, 0.08), arrowprops=dict(arrowstyle="->", color="#333333"))
ax.set_xticks([lo, 9, hi], [f"{lo:.2f}", "9", f"{hi:.2f}"])
ax.set_yticks([])
ax.set_xlabel("chi-square (df = 9)")
ax.set_title("two-sided 5%: reject if chi-square < 2.70 or > 19.02")
fig.tight_layout()
fig.savefig("u04_var_test.png")
plt.close(fig)
print("done")
