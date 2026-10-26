"""単元4〜5 の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u04_adj_r2.png      : 無関係な変数を加えていったときの決定係数と自由度調整済み決定係数(中古マンション 40 件)
- u05_collinearity.png : 広さと築年数の散布図(相関係数 0.92)
- u05_dummy.png       : ダミー変数を入れた回帰(立地ごとに平行な直線)
"""
import numpy as np
import pandas as pd

df = pd.read_csv("flats.csv")
n = len(df)

# ---------- 決定係数と自由度調整済み決定係数 ----------
rng = np.random.default_rng(13)
noise = rng.normal(size=(n, 6))
cols = [np.ones(n), df.area.to_numpy(), df.age.to_numpy()]
st = ((df.price - df.price.mean()) ** 2).sum()
ks, r2s, adjs = [], [], []
for k in range(1, 9):
    X = np.column_stack(cols[: k + 1] if k <= 2 else cols + [noise[:, j] for j in range(k - 2)])
    resid = df.price - X @ np.linalg.lstsq(X, df.price, rcond=None)[0]
    se = (resid ** 2).sum()
    ks.append(k)
    r2s.append(1 - se / st)
    adjs.append(1 - (se / (n - k - 1)) / (st / (n - 1)))
fig, ax = plt.subplots(figsize=(8, 3.4))
ax.plot(ks, r2s, marker="o", color=PRIMARY, label="R-squared")
ax.plot(ks, adjs, marker="s", color=ACCENT, label="adjusted R-squared")
ax.axvspan(2.5, 8.5, color="gray", alpha=0.1)
ax.text(5.5, 0.6, "added variables are\nunrelated random noise", ha="center", fontsize=9)
ax.set_xticks(ks, ["area", "+age"] + [f"+noise{j}" for j in range(1, 7)], fontsize=8)
ax.set_xlabel("explanatory variables in the model")
ax.set_ylim(0.5, 0.8)
ax.legend(loc="lower right", fontsize=9)
fig.tight_layout()
fig.savefig("u04_adj_r2.png")
plt.close(fig)
print("R2", np.round(r2s, 4).tolist())
print("adj", np.round(adjs, 4).tolist())

# ---------- 多重共線性 ----------
fig, ax = plt.subplots(figsize=(5.5, 4))
ax.scatter(df.age, df.area, s=18, color=PRIMARY)
ax.set_xlabel("age (years)")
ax.set_ylabel("area (m2)")
ax.set_title(f"r = {df.area.corr(df.age):.2f}")
fig.tight_layout()
fig.savefig("u05_collinearity.png")
plt.close(fig)

# ---------- ダミー変数 ----------
fig, ax = plt.subplots(figsize=(7.5, 4))
x = np.linspace(10, 60, 50)
for (label, shift), color in zip((("station (D1 = 1)", 40), ("mall (D2 = 1)", 15), ("suburb (base)", 0)), SERIES_COLORS):
    ax.plot(x, 150 + 2.0 * x + shift, color=color, linewidth=2, label=label)
ax.annotate("", xy=(50, 290), xytext=(50, 250), arrowprops=dict(arrowstyle="<->", color="gray"))
ax.text(51, 268, "+40", fontsize=10)
ax.annotate("", xy=(35, 235), xytext=(35, 220), arrowprops=dict(arrowstyle="<->", color="gray"))
ax.text(36, 223, "+15", fontsize=10)
ax.set_xlabel("floor area x")
ax.set_ylabel("predicted sales")
ax.set_title("y = 150 + 2.0 x + 40 D1 + 15 D2")
ax.legend(fontsize=9, loc="upper left")
fig.tight_layout()
fig.savefig("u05_dummy.png")
plt.close(fig)
