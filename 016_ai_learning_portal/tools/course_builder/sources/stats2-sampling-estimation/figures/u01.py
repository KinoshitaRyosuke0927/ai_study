"""単元1(母集団と標本・標本平均の分布)の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u01_sampling_means.png : 母集団の分布と、標本平均の分布(n = 4・16)。中心は同じで、幅が 1/√n になる
"""
import numpy as np

rng = np.random.default_rng(1)
pop = rng.gamma(4, 2.5, 200000)  # 母平均 10、母標準偏差 5
bins = np.arange(0, 30.5, 0.5)
fig, axes = plt.subplots(1, 3, figsize=(13, 3.0), sharex=True)
axes[0].hist(pop, bins=bins, color=CATEGORY_COLORS[2], density=True)
axes[0].set_title("population (mean 10, sd 5)")
for ax, n in zip(axes[1:], (4, 16)):
    means = rng.gamma(4, 2.5, (20000, n)).mean(axis=1)
    ax.hist(means, bins=bins, color=PRIMARY, density=True)
    ax.set_title(f"sample mean, n = {n} (sd 5/sqrt({n}) = {5 / n ** 0.5:.2f})")
for ax in axes:
    ax.axvline(10, color=ACCENT, linewidth=1.5)
    ax.set_yticks([])
    ax.set_xlabel("value")
fig.tight_layout()
fig.savefig("u01_sampling_means.png")
plt.close(fig)
print("done")
