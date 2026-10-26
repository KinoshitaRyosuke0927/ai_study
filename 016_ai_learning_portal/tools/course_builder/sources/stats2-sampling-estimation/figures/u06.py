"""単元6(母平均の区間推定)の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u06_ci_sim.png : 同じ母集団(μ = 50、σ = 10)から 20 回標本をとって作った 95% 信頼区間(n = 25)
"""
import numpy as np

rng = np.random.default_rng(15)
mu, sigma, n = 50, 10, 25
se = sigma / n ** 0.5
fig, ax = plt.subplots(figsize=(10, 4))
misses = 0
for i in range(20):
    m = rng.normal(mu, sigma, n).mean()
    lo, hi = m - 1.96 * se, m + 1.96 * se
    hit = lo <= mu <= hi
    misses += not hit
    color = PRIMARY if hit else ACCENT
    ax.plot([lo, hi], [i, i], color=color, linewidth=2.5)
    ax.plot(m, i, "o", color=color, markersize=4)
ax.axvline(mu, color="#333333", linestyle="--", linewidth=1.2)
ax.text(mu, 20.2, "true mean 50", ha="center", fontsize=9)
ax.set_yticks([])
ax.set_ylim(-1, 21)
ax.set_xlabel("95% confidence interval of each sample")
ax.set_title(f"{20 - misses} of 20 intervals contain the true mean (red: misses)")
fig.tight_layout()
fig.savefig("u06_ci_sim.png")
plt.close(fig)
print("misses", misses)
