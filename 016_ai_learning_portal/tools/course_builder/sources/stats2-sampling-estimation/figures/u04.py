"""単元4(t 分布・カイ二乗分布・F 分布)の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u04_three_dists.png : t 分布と標準正規分布、カイ二乗分布(自由度 5・10)、F 分布((5, 10)・(10, 5))
"""
import numpy as np
from scipy import stats

fig, axes = plt.subplots(1, 3, figsize=(14, 3.2))
x = np.linspace(-4, 4, 400)
axes[0].plot(x, stats.norm.pdf(x), color="#333333", linewidth=2, label="standard normal")
axes[0].plot(x, stats.t.pdf(x, 5), color=PRIMARY, linewidth=2, linestyle="--", label="t (df = 5)")
axes[0].set_title("t distribution")
x = np.linspace(0.01, 30, 400)
for df, color in [(5, PRIMARY), (10, ACCENT)]:
    axes[1].plot(x, stats.chi2.pdf(x, df), color=color, linewidth=2, label=f"df = {df} (mean {df})")
axes[1].set_title("chi-square distribution")
x = np.linspace(0.01, 5, 400)
for (d1, d2), color in [((5, 10), PRIMARY), ((10, 5), ACCENT)]:
    axes[2].plot(x, stats.f.pdf(x, d1, d2), color=color, linewidth=2, label=f"df = ({d1}, {d2})")
axes[2].set_title("F distribution")
for ax in axes:
    ax.set_yticks([])
    ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig("u04_three_dists.png")
plt.close(fig)
print("done")
