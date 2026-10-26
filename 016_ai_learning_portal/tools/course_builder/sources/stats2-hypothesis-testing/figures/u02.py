"""単元2(2種類の過誤と検出力)の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u02_alpha_beta.png  : H0 と H1 の分布と、α・β・検出力の領域(n = 16)
- u02_sample_size.png : 標本の大きさによる β の違い(n = 16 と n = 64)
- u02_ex_regions.png  : 演習「領域の読み取り」(A・B・C、名前なし)
"""
import numpy as np
from scipy import stats

H1C = SERIES_COLORS[2]


def draw(ax, mu0, mu1, se, c, names=True, labels=None):
    """H0(平均 mu0)と H1(平均 mu1)の標本平均の分布と、境界 c で分けた領域を描く。"""
    x = np.linspace(mu0 - 4 * se, mu1 + 4 * se, 600)
    f0 = stats.norm.pdf(x, mu0, se)
    f1 = stats.norm.pdf(x, mu1, se)
    ax.plot(x, f0, color=PRIMARY, label="distribution under H0" if names else None)
    ax.plot(x, f1, color=H1C, label="distribution under H1 (true)" if names else None)
    ax.fill_between(x, f0, where=x >= c, color=ACCENT, alpha=0.6)
    ax.fill_between(x, f1, where=x < c, color=H1C, alpha=0.25)
    ax.fill_between(x, f1, where=x >= c, color=H1C, alpha=0.08, hatch="///", edgecolor=H1C, linewidth=0)
    ax.axvline(c, color="#333333", linestyle="--", linewidth=1)
    ax.set_yticks([])
    top = f0.max()
    if labels:
        for (text, px, py) in labels:
            ax.text(px, py * top, text, ha="center", fontsize=12 if len(text) < 3 else 10, fontweight="bold" if len(text) < 3 else "normal")
    return top


# ---------- α・β・検出力(n = 16) ----------
fig, ax = plt.subplots(figsize=(10, 3.6))
top = draw(ax, 50, 53, 1.5, 52.4675, labels=[
    ("alpha = 0.05", 54.2, 0.1), ("beta = 0.36", 51.2, 0.12), ("power = 0.64", 55.3, 0.45),
])
ax.set_xticks([50, 53], ["50 (H0)", "53 (true)"])
ax.text(52.4675 - 0.1, top * 1.02, "critical value c = 52.47", ha="right", fontsize=9, color="#333333")
ax.set_ylim(0, top * 1.12)
ax.set_xlabel("sample mean")
ax.legend(loc="upper left")
fig.tight_layout()
fig.savefig("u02_alpha_beta.png")
plt.close(fig)

# ---------- 標本の大きさによる違い ----------
fig, axes = plt.subplots(1, 2, figsize=(12, 3.2), sharex=True)
draw(axes[0], 50, 53, 1.5, 52.4675)
axes[0].set_title("n = 16: beta = 0.36, power = 0.64")
draw(axes[1], 50, 53, 0.75, 51.2338)
axes[1].set_title("n = 64: beta = 0.01, power = 0.99")
for ax in axes:
    ax.set_xlim(45, 58)
    ax.set_xlabel("sample mean")
fig.tight_layout()
fig.savefig("u02_sample_size.png")
plt.close(fig)

# ---------- 演習: 領域 A・B・C ----------
fig, ax = plt.subplots(figsize=(10, 3.4))
draw(ax, 100, 105, 2.0, 103.29, names=False, labels=[("A", 104.6, 0.06), ("B", 102.1, 0.18), ("C", 106.0, 0.45)])
ax.text(100, 1.07 * stats.norm.pdf(0, 0, 2.0), "H0", ha="center", color=PRIMARY, fontsize=12)
ax.text(105, 1.07 * stats.norm.pdf(0, 0, 2.0), "H1 (true)", ha="center", color=H1C, fontsize=12)
ax.set_ylim(0, 1.2 * stats.norm.pdf(0, 0, 2.0))
ax.set_xticks([100, 103.29, 105], ["100", "c", "105"])
ax.set_xlabel("sample mean")
fig.tight_layout()
fig.savefig("u02_ex_regions.png")
plt.close(fig)
print("done")
