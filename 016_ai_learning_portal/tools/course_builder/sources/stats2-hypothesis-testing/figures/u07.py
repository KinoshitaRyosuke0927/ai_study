"""単元7(適合度検定)の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u07_obs_exp.png  : 血液型の観測度数と期待度数(比 4:2:3:1、200 人)
- u07_chi2_df3.png : 自由度 3 のカイ二乗分布の上側 5% 棄却域と、χ² = 2.42 の位置
- u07_ex_bars.png  : 演習「寄与の大きいカテゴリ」の観測度数と期待度数
"""
import numpy as np
from scipy import stats


def obs_exp(fname, labels, obs, exp, title):
    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(8, 3.4))
    b1 = ax.bar(x - 0.2, obs, width=0.4, color=PRIMARY, label="observed O")
    b2 = ax.bar(x + 0.2, exp, width=0.4, color=CATEGORY_COLORS[3], label="expected E")
    for bars in (b1, b2):
        for r in bars:
            ax.text(r.get_x() + r.get_width() / 2, r.get_height() + 1, f"{r.get_height():.0f}", ha="center", fontsize=9)
    ax.set_xticks(x, labels)
    ax.set_ylabel("count")
    ax.set_ylim(0, max(max(obs), max(exp)) * 1.18)
    ax.legend()
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(fname)
    plt.close(fig)


obs_exp("u07_obs_exp.png", ["A", "B", "O", "AB"], [90, 34, 56, 20], [80, 40, 60, 20], "blood type (n = 200, expected ratio 4:2:3:1)")
obs_exp("u07_ex_bars.png", ["A", "B", "C", "D"], [62, 45, 41, 52], [50, 50, 50, 50], "4 categories (n = 200)")

# ---------- 自由度 3 のカイ二乗分布 ----------
c = stats.chi2.ppf(0.95, 3)
x = np.linspace(0.01, 16, 500)
y = stats.chi2.pdf(x, 3)
fig, ax = plt.subplots(figsize=(9, 3.2))
ax.plot(x, y, color=PRIMARY)
ax.fill_between(x, y, color=PRIMARY, alpha=0.12)
ax.fill_between(x, y, where=x >= c, color=ACCENT, alpha=0.6)
ax.axvline(2.42, color="#333333", linewidth=1.5, zorder=3)
ax.annotate("chi-square = 2.42", xy=(2.42, 0.12), xytext=(4.5, 0.2), arrowprops=dict(arrowstyle="->", color="#333333"))
ax.set_xticks([0, c], ["0", f"{c:.3f}"])
ax.set_yticks([])
ax.set_xlabel("chi-square (df = 3)")
ax.set_title("goodness-of-fit test: reject if chi-square > 7.815 (upper 5%)")
fig.tight_layout()
fig.savefig("u07_chi2_df3.png")
plt.close(fig)
print("done")
