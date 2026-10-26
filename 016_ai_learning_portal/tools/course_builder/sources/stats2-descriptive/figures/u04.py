"""単元4(歪度・尖度・ジニ係数)の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u04_skew_kurt.png      : 歪度・尖度の値と分布の形(正規・右に裾・一様・裾が重い)
- u04_lorenz_example.png : ローレンツ曲線とジニ係数(5 世帯の例)
- u04_ex_skew.png        : 演習「歪度の符号」のヒストグラム A〜C
- u04_ex_lorenz.png      : 演習「ローレンツ曲線の比較」の曲線 A〜C
"""
import numpy as np
from scipy import stats

# ---------- 歪度・尖度と分布の形 ----------
rng = np.random.default_rng(0)
samples = [
    ("normal", rng.normal(0, 1, 5000)),
    ("right-skewed", rng.lognormal(0, 0.6, 5000)),
    ("uniform", rng.uniform(0, 1, 5000)),
    ("heavy-tailed", rng.standard_t(5, 5000)),
]
fig, axes = plt.subplots(1, 4, figsize=(14, 2.9))
for ax, (name, v) in zip(axes, samples):
    lo, hi = np.percentile(v, [0.5, 99.5])
    ax.hist(v[(v >= lo) & (v <= hi)], bins=35, color=PRIMARY, linewidth=0.3)
    ax.set_title(f"{name}\nskewness {stats.skew(v):.2f} / kurtosis {stats.kurtosis(v):.2f}", fontsize=11)
    ax.set_yticks([])
    ax.set_xticks([])
fig.tight_layout()
fig.savefig("u04_skew_kurt.png")
plt.close(fig)

# ---------- ローレンツ曲線の例(100, 200, 300, 400, 1000) ----------
x = np.array([100, 200, 300, 400, 1000])
L = np.concatenate([[0], np.cumsum(x) / x.sum()])
P = np.linspace(0, 1, len(x) + 1)
fig, ax = plt.subplots(figsize=(5.2, 4.6))
ax.plot([0, 1], [0, 1], color="gray", linestyle="--", label="equality line")
ax.plot(P, L, marker="o", color=PRIMARY, label="Lorenz curve")
ax.fill_between(P, L, P, color=ACCENT, alpha=0.25, label="area between (Gini = 2 x area)")
for p, l in zip(P[1:-1], L[1:-1]):
    ax.annotate(f"{l:.2f}", xy=(p, l), xytext=(p + 0.02, l - 0.07), fontsize=9, color=PRIMARY)
ax.set_xticks(P)
ax.set_xlabel("cumulative share of households")
ax.set_ylabel("cumulative share of income")
ax.legend(loc="upper left")
ax.set_aspect("equal")
fig.tight_layout()
fig.savefig("u04_lorenz_example.png")
plt.close(fig)

# ---------- 演習: 歪度の符号(A: ほぼ対称、B: 左に裾、C: 右に裾) ----------
rng = np.random.default_rng(5)
shape = [("A", rng.normal(50, 10, 2000)), ("B", 100 - rng.gamma(2, 8, 2000)), ("C", rng.gamma(2, 8, 2000))]
fig, axes = plt.subplots(1, 3, figsize=(12, 2.8))
for ax, (name, v) in zip(axes, shape):
    ax.hist(v, bins=30, color=PRIMARY, linewidth=0.3)
    ax.set_title(name, fontsize=15, fontweight="bold")
    ax.set_yticks([])
    ax.set_xlabel("value")
fig.tight_layout()
fig.savefig("u04_ex_skew.png")
plt.close(fig)

# ---------- 演習: 3 本のローレンツ曲線 ----------
groups = {
    "A": [300, 320, 340, 350, 360, 380, 400, 420, 440, 460],
    "B": [100, 150, 200, 250, 300, 350, 400, 500, 650, 900],
    "C": [20, 30, 40, 50, 60, 80, 100, 150, 300, 1500],
}
# A・B・C の位置が判別しやすいよう、曲線ごとに線の種類を変える
styles = {"A": ("-", SERIES_COLORS[0]), "B": ("--", SERIES_COLORS[1]), "C": (":", SERIES_COLORS[2])}
fig, ax = plt.subplots(figsize=(5.2, 4.6))
ax.plot([0, 1], [0, 1], color="gray", linewidth=1)
P = np.linspace(0, 1, 11)
for name, v in groups.items():
    v = np.sort(np.asarray(v, dtype=float))
    L = np.concatenate([[0], np.cumsum(v) / v.sum()])
    ls, color = styles[name]
    ax.plot(P, L, linestyle=ls, color=color, linewidth=2)
    ax.text(0.62, np.interp(0.62, P, L) + 0.02, name, fontsize=13, fontweight="bold", color=color)
ax.set_xlabel("cumulative share of households")
ax.set_ylabel("cumulative share of income")
ax.set_aspect("equal")
fig.tight_layout()
fig.savefig("u04_ex_lorenz.png")
plt.close(fig)
print("done")
