"""単元1〜3 の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u01_model.png   : 単回帰モデル(各 x での y の分布が、回帰直線を中心とする同じ形の正規分布)
- u02_t_test.png  : 回帰係数の t 検定(自由度 3 の t 分布と棄却域、5 組のデータの t = 2.12)
- u03_partial.png : 単回帰と重回帰で築年数の係数の符号が変わる例(中古マンション 40 件)
"""
import numpy as np
import pandas as pd
from scipy import stats

# ---------- 単回帰モデル ----------
rng = np.random.default_rng(3)
fig, ax = plt.subplots(figsize=(8, 4))
xs = rng.uniform(0, 10, 60)
ys = 10 + 2 * xs + rng.normal(0, 3, 60)
ax.scatter(xs, ys, s=14, color=PRIMARY, alpha=0.5)
line = np.linspace(-0.5, 10.5, 50)
ax.plot(line, 10 + 2 * line, color=PRIMARY, linewidth=2)
yy = np.linspace(-9, 9, 100)
for x0 in (2, 5, 8):
    dens = stats.norm.pdf(yy, 0, 3)
    ax.plot(x0 + dens * 6, 10 + 2 * x0 + yy, color=ACCENT, linewidth=1.5)
    ax.plot([x0, x0], [10 + 2 * x0 - 9, 10 + 2 * x0 + 9], color=ACCENT, linewidth=0.8, linestyle=":")
ax.text(8.5, 13, "y ~ N(b0 + b1 x, sigma^2)\nat each x", color=ACCENT, fontsize=9)
ax.text(0.2, 31, "E[y] = b0 + b1 x", color=PRIMARY, fontsize=10)
ax.set_xlabel("x")
ax.set_ylabel("y")
fig.tight_layout()
fig.savefig("u01_model.png")
plt.close(fig)

# ---------- 回帰係数の t 検定 ----------
fig, ax = plt.subplots(figsize=(8, 3.2))
t = np.linspace(-6, 6, 600)
d = stats.t.pdf(t, 3)
crit = stats.t.ppf(0.975, 3)
ax.plot(t, d, color=PRIMARY, linewidth=2)
ax.fill_between(t, d, where=t >= crit, color=ACCENT, alpha=0.6)
ax.fill_between(t, d, where=t <= -crit, color=ACCENT, alpha=0.6)
ax.axvline(2.121, color=PRIMARY, linestyle="--", linewidth=1.5)
ax.text(2.2, 0.3, "t = 0.6 / 0.283\n= 2.12", fontsize=9)
ax.text(crit + 0.2, 0.06, f"reject\n(t > {crit:.3f})", color=ACCENT, fontsize=9)
ax.text(-crit - 0.2, 0.06, "reject", color=ACCENT, fontsize=9, ha="right")
ax.set_title("t distribution with 3 (= n - 2) degrees of freedom")
ax.set_yticks([])
fig.tight_layout()
fig.savefig("u02_t_test.png")
plt.close(fig)

# ---------- 単回帰と重回帰 ----------
df = pd.read_csv("flats.csv")
fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True)
b1, b0 = np.polyfit(df.age, df.price, 1)
axes[0].scatter(df.age, df.price, s=18, color=PRIMARY)
line = np.linspace(0, 37, 50)
axes[0].plot(line, b0 + b1 * line, color=ACCENT, linewidth=2)
axes[0].set_title(f"simple regression: slope of age = {b1:+.1f}")
X = np.column_stack([np.ones(len(df)), df.area, df.age])
c0, c_area, c_age = np.linalg.lstsq(X, df.price, rcond=None)[0]
groups = [("area < 58", df.area < 58), ("58 to 75", (df.area >= 58) & (df.area < 75)), ("area >= 75", df.area >= 75)]
for (label, mask), color in zip(groups, SERIES_COLORS):
    sub = df[mask]
    axes[1].scatter(sub.age, sub.price, s=18, color=color, label=label)
    a_mean = sub.area.mean()
    lo, hi = sub.age.min() - 2, sub.age.max() + 2
    axes[1].plot([lo, hi], [c0 + c_area * a_mean + c_age * lo, c0 + c_area * a_mean + c_age * hi], color=color, linewidth=2)
axes[1].set_title(f"multiple regression: slope of age = {c_age:+.1f}\n(area held fixed)")
axes[1].legend(fontsize=9, loc="lower right")
for ax in axes:
    ax.set_xlabel("age (years)")
axes[0].set_ylabel("price (10k yen)")
fig.tight_layout()
fig.savefig("u03_partial.png")
plt.close(fig)
print("simple", round(b1, 2), "multiple", round(c_age, 2))
