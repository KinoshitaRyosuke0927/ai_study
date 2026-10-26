"""単元8(2つの母集団の区間推定)の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u08_ci_test.png : 平均の差の 95% 信頼区間が 0 を含むかどうかと、両側 5% の検定の結論の対応
- u08_ex_ci.png   : 演習「信頼区間から検定の結論を読む」(A〜D)
"""


def ci_plot(fname, items, title, xlabel, xlim, highlight=True):
    """信頼区間を横棒で描く。highlight が真なら、0 を含まない区間を強調色にする(演習の図では答えが分からないよう使わない)。"""
    fig, ax = plt.subplots(figsize=(9, 0.6 * len(items) + 1.2))
    for i, (name, lo, hi) in enumerate(items):
        color = ACCENT if highlight and not (lo <= 0 <= hi) else PRIMARY
        ax.plot([lo, hi], [i, i], color=color, linewidth=4)
        ax.plot((lo + hi) / 2, i, "o", color=color, markersize=6)
    ax.axvline(0, color="#333333", linestyle="--", linewidth=1.2)
    ax.set_yticks(range(len(items)), [it[0] for it in items])
    ax.set_ylim(-0.7, len(items) - 0.3)
    ax.invert_yaxis()
    ax.set_xlim(*xlim)
    ax.set_xlabel(xlabel)
    if title:
        ax.set_title(title, fontsize=11)
    fig.tight_layout()
    fig.savefig(fname)
    plt.close(fig)


ci_plot(
    "u08_ci_test.png",
    [("teaching methods: [-0.52, 10.52]", -0.52, 10.52), ("another study: [1.30, 8.70]", 1.30, 8.70)],
    "contains 0 -> not rejected (two-sided 5%) / excludes 0 -> rejected",
    "difference of means (group 1 - group 2)",
    (-4, 13),
)
# 演習: A・C は 0 を含まない(有意差あり)、B・D は 0 を含む(有意差なし)
ci_plot(
    "u08_ex_ci.png",
    [("A", 1.2, 6.8), ("B", -2.1, 3.5), ("C", -7.4, -0.6), ("D", -0.3, 9.8)],
    None,
    "95% confidence interval for mu1 - mu2",
    (-10, 12),
    highlight=False,
)
print("done")
