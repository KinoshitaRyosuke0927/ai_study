"""単元5(標準化)の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u05_hensachi.png : 正規分布と z 得点・偏差値の対応、±1σ・±2σ の範囲に入る割合
"""
import numpy as np
from scipy import stats

z = np.linspace(-3.5, 3.5, 500)
y = stats.norm.pdf(z)
fig, ax = plt.subplots(figsize=(10, 3.6))
ax.plot(z, y, color=PRIMARY)
ax.fill_between(z, y, where=np.abs(z) <= 1, color=PRIMARY, alpha=0.35)
ax.fill_between(z, y, where=(np.abs(z) > 1) & (np.abs(z) <= 2), color=PRIMARY, alpha=0.18)
ax.fill_between(z, y, where=np.abs(z) > 2, color=ACCENT, alpha=0.25)
for x, text in [(-0.5, "34.1%"), (0.5, "34.1%"), (-1.5, "13.6%"), (1.5, "13.6%"), (-2.45, "2.3%"), (2.45, "2.3%")]:
    ax.text(x, 0.03 if abs(x) > 1 else 0.15, text, ha="center", fontsize=10)
ax.set_xticks(range(-3, 4), [f"z = {k}\n({50 + 10 * k})" for k in range(-3, 4)])
ax.set_yticks([])
ax.set_xlabel("z score  (deviation value = 50 + 10z)")
fig.tight_layout()
fig.savefig("u05_hensachi.png")
plt.close(fig)
print("done")
