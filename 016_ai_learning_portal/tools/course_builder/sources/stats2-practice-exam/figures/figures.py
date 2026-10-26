"""練習問題・模擬試験の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。
問題の図なので、答えがわかる色分けはしない(単色)。

- u1_hist_box.png : ヒストグラム A〜C と箱ひげ図 X〜Z(A=右に裾、B=左右対称、C=左に裾。X=左に裾、Y=右に裾、Z=左右対称)
- u5_residual.png : 予測値が大きいほど残差のばらつきが大きい残差プロット
- q_scatter.png  : 散布図 P〜S(相関係数 約 0.9 / 約 0.0(U 字型)/ 約 −0.5 / 約 0.5)
"""
import numpy as np

rng = np.random.default_rng(21)

# ---------- ヒストグラムと箱ひげ図 ----------
right = rng.gamma(2.0, 8, 300) + 10
sym = rng.normal(40, 8, 300)
left = 80 - (rng.gamma(2.0, 8, 300) + 10)
fig, axes = plt.subplots(2, 3, figsize=(12, 6))
for ax, (label, data) in zip(axes[0], (("A", right), ("B", sym), ("C", left))):
    ax.hist(data, bins=16, color=PRIMARY, edgecolor="white")
    ax.set_title(label)
    ax.set_yticks([])
for ax, (label, data) in zip(axes[1], (("X", left), ("Y", right), ("Z", sym))):
    ax.boxplot(data, vert=False, widths=0.5, patch_artist=True,
               boxprops=dict(facecolor=CATEGORY_COLORS[2], color=PRIMARY), medianprops=dict(color=PRIMARY, linewidth=2),
               whiskerprops=dict(color=PRIMARY), capprops=dict(color=PRIMARY), flierprops=dict(markeredgecolor=PRIMARY, markersize=4))
    ax.set_title(label)
    ax.set_yticks([])
fig.tight_layout()
fig.savefig("u1_hist_box.png")
plt.close(fig)

# ---------- 残差プロット ----------
fitted = rng.uniform(10, 50, 80)
resid = rng.normal(0, 1, 80) * fitted * 0.12
fig, ax = plt.subplots(figsize=(6.5, 3.6))
ax.scatter(fitted, resid, s=16, color=PRIMARY)
ax.axhline(0, color="gray", linewidth=1)
ax.set_xlabel("fitted value")
ax.set_ylabel("residual")
fig.tight_layout()
fig.savefig("u5_residual.png")
plt.close(fig)

# ---------- 散布図と相関係数 ----------
def corr_data(rho, n=80):
    xy = rng.multivariate_normal([0, 0], [[1, rho], [rho, 1]], n)
    return xy[:, 0], xy[:, 1]

xs = np.linspace(-2, 2, 80)
panels = [("P", corr_data(0.9)), ("Q", (xs, xs ** 2 + rng.normal(0, 0.3, 80))), ("R", corr_data(-0.6)), ("S", corr_data(0.4))]
fig, axes = plt.subplots(1, 4, figsize=(14, 3.4))
for ax, (label, (a, b)) in zip(axes, panels):
    ax.scatter(a, b, s=12, color=PRIMARY)
    ax.set_title(label)
    ax.set_xticks([])
    ax.set_yticks([])
    print(label, "r =", round(np.corrcoef(a, b)[0, 1], 3))
fig.tight_layout()
fig.savefig("q_scatter.png")
plt.close(fig)
