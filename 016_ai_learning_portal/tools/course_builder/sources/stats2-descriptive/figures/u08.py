"""単元8(単回帰)の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u08_fit_residuals.png      : 回帰直線と残差(5 組の例)
- u08_residual_patterns.png  : 残差プロットの典型的なパターン(解説用、名前つき)
- u08_log_transform.png      : 対数変換で指数的な増加が直線になる様子
- u08_ex_residuals.png       : 演習「残差プロットの読み取り」(A〜C、名前なし)
"""
import numpy as np

DARK = "#333333"

# ---------- 回帰直線と残差 ----------
x = np.array([1, 2, 3, 4, 5], dtype=float)
y = np.array([2, 4, 5, 4, 5], dtype=float)
a, b = 2.2, 0.6
fig, ax = plt.subplots(figsize=(6, 4))
xs = np.linspace(0.5, 5.5, 2)
ax.plot(xs, a + b * xs, color=ACCENT, label="y = 2.2 + 0.6x")
for xi, yi in zip(x, y):
    ax.plot([xi, xi], [yi, a + b * xi], color="gray", linestyle=":", linewidth=1.5)
ax.scatter(x, y, s=40, color=PRIMARY, zorder=3, label="data")
ax.plot(3, 4, marker="x", color=DARK, markersize=9, zorder=4)
ax.annotate("(mean x, mean y) = (3, 4)", xy=(3, 4), xytext=(3.2, 2.6), fontsize=9,
            arrowprops=dict(arrowstyle="->", color=DARK))
ax.annotate("residual", xy=(3, 4.5), xytext=(1.6, 5.2), fontsize=9, color="gray",
            arrowprops=dict(arrowstyle="->", color="gray"))
ax.set_xlabel("x")
ax.set_ylabel("y")
ax.legend(loc="lower right")
fig.tight_layout()
fig.savefig("u08_fit_residuals.png")
plt.close(fig)


def residual_panel(ax, kind, rng, title=None):
    """残差プロットの典型パターン(random / curved / funnel)を描く。"""
    f = np.sort(rng.uniform(10, 50, 80))
    if kind == "random":
        r = rng.normal(0, 3, 80)
    elif kind == "curved":
        r = 0.02 * (f - 30) ** 2 - 2.6 + rng.normal(0, 1, 80)
    else:
        r = rng.normal(0, 1, 80) * (f - 8) * 0.15
    ax.scatter(f, r, s=12, color=PRIMARY)
    ax.axhline(0, color="gray", linewidth=1)
    ax.set_xlabel("fitted value")
    ax.set_ylabel("residual")
    ax.set_yticks([])
    if title:
        ax.set_title(title, fontsize=12 if len(title) > 1 else 15, fontweight="normal" if len(title) > 1 else "bold")


# ---------- 残差プロットのパターン(解説) ----------
rng = np.random.default_rng(4)
fig, axes = plt.subplots(1, 3, figsize=(12, 3.2))
for ax, (kind, title) in zip(axes, [("random", "good fit (random)"), ("curved", "curved pattern"), ("funnel", "spread grows (funnel)")]):
    residual_panel(ax, kind, rng, title)
fig.tight_layout()
fig.savefig("u08_residual_patterns.png")
plt.close(fig)

# ---------- 対数変換 ----------
t = np.arange(1, 13)
mem = np.array([1020, 1105, 1230, 1310, 1450, 1590, 1710, 1880, 2050, 2240, 2410, 2650])
fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
b1, a1 = np.polyfit(t, mem, 1)
axes[0].scatter(t, mem, color=PRIMARY, zorder=3)
axes[0].plot(t, a1 + b1 * t, color=ACCENT)
axes[0].set_title(f"y = a + bt   (R2 = {np.corrcoef(t, mem)[0, 1] ** 2:.4f})")
axes[0].set_xlabel("month t")
axes[0].set_ylabel("members y")
b2, a2 = np.polyfit(t, np.log(mem), 1)
axes[1].scatter(t, np.log(mem), color=PRIMARY, zorder=3)
axes[1].plot(t, a2 + b2 * t, color=ACCENT)
axes[1].set_title(f"log y = a + bt   (R2 = {np.corrcoef(t, np.log(mem))[0, 1] ** 2:.4f})")
axes[1].set_xlabel("month t")
axes[1].set_ylabel("log(members)")
fig.tight_layout()
fig.savefig("u08_log_transform.png")
plt.close(fig)

# ---------- 演習: 残差プロット A(ばらつきが広がる)・B(ランダム)・C(曲線) ----------
rng = np.random.default_rng(12)
fig, axes = plt.subplots(1, 3, figsize=(12, 3.2))
for ax, (kind, title) in zip(axes, [("funnel", "A"), ("random", "B"), ("curved", "C")]):
    residual_panel(ax, kind, rng, title)
fig.tight_layout()
fig.savefig("u08_ex_residuals.png")
plt.close(fig)
print("done")
