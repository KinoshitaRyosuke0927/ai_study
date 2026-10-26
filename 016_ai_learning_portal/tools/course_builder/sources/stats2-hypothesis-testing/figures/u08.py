"""単元8(独立性の検定)の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u08_band.png     : 性別ごとの購入の有無の構成比(観測)と、独立なときに予想される構成比
- u08_chi2_df1.png : 自由度 1 のカイ二乗分布の上側 5% 棄却域と、χ² = 2.27 の位置
"""
import numpy as np
from scipy import stats

# ---------- 構成比の比較(観測と、独立なときの予想) ----------
labels = ["male (observed)", "female (observed)", "if independent"]
rows = np.array([[30.0, 70.0], [45.0, 55.0], [39.0, 61.0]])
fig, ax = plt.subplots(figsize=(9, 2.8))
left = np.zeros(3)
for j, (name, color) in enumerate(zip(["purchased", "not purchased"], [CATEGORY_COLORS[0], CATEGORY_COLORS[3]])):
    ax.barh(labels, rows[:, j], left=left, color=color, label=name)
    for i, v in enumerate(rows[:, j]):
        ax.text(left[i] + v / 2, i, f"{v:.0f}%", ha="center", va="center", color="white" if j == 0 else "#333333")
    left += rows[:, j]
ax.set_xlim(0, 100)
ax.invert_yaxis()
ax.set_xlabel("share (%)")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.3), ncol=2, frameon=False)
fig.tight_layout()
fig.savefig("u08_band.png")
plt.close(fig)

# ---------- 自由度 1 のカイ二乗分布 ----------
c = stats.chi2.ppf(0.95, 1)
x = np.linspace(0.05, 8, 500)
y = stats.chi2.pdf(x, 1)
fig, ax = plt.subplots(figsize=(9, 3.0))
ax.plot(x, y, color=PRIMARY)
ax.fill_between(x, y, color=PRIMARY, alpha=0.12)
ax.fill_between(x, y, where=x >= c, color=ACCENT, alpha=0.6)
ax.axvline(2.27, color="#333333", linewidth=1.5, zorder=3)
ax.annotate("chi-square = 2.27", xy=(2.27, 0.1), xytext=(4.6, 0.4), arrowprops=dict(arrowstyle="->", color="#333333"))
ax.set_ylim(0, 1.0)
ax.set_xticks([0, c], ["0", f"{c:.3f}"])
ax.set_yticks([])
ax.set_xlabel("chi-square (df = 1)")
ax.set_title("test of independence (2 x 2): reject if chi-square > 3.841")
fig.tight_layout()
fig.savefig("u08_chi2_df1.png")
plt.close(fig)
print("done")
