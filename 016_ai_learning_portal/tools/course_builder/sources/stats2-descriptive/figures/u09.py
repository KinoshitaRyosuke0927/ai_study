"""単元9(時系列)の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u09_series.png          : 月次売上と 12 か月中心化移動平均(トレンド)
- u09_correlogram.png     : 月次売上のコレログラム(元の系列・前月差)
- u09_ex_correlograms.png : 演習「コレログラムの読み取り」(A: 季節変動、B: トレンド、C: ランダム)
"""
import numpy as np
import pandas as pd


def acf(x, nlags):
    """自己相関係数(分母は系列全体の偏差平方和)をラグ 0〜nlags について求める。"""
    d = np.asarray(x, dtype=float) - np.mean(x)
    den = (d ** 2).sum()
    return np.array([1.0] + [(d[:-k] * d[k:]).sum() / den for k in range(1, nlags + 1)])


def correlogram(ax, r, title):
    ax.bar(range(len(r)), r, width=0.6, color=PRIMARY)
    ax.axhline(0, color="gray", linewidth=0.8)
    ax.set_ylim(-1, 1.05)
    ax.set_xlabel("lag")
    ax.set_title(title)


# ---------- 月次売上と移動平均 ----------
df = pd.read_csv("monthly_sales.csv")
s = df["sales"]
t = pd.PeriodIndex(df["month"], freq="M").to_timestamp()
ma12 = s.rolling(12).mean().rolling(2).mean().shift(-6)
fig, ax = plt.subplots(figsize=(11, 3.6))
ax.plot(t, s, color=PRIMARY, alpha=0.6, label="monthly sales")
ax.plot(t, ma12, color=ACCENT, linewidth=2.5, label="12-month centered moving average (trend)")
ax.set_ylabel("sales (million yen)")
ax.legend(loc="upper left")
fig.tight_layout()
fig.savefig("u09_series.png")
plt.close(fig)

# ---------- コレログラム(元の系列・前月差) ----------
fig, axes = plt.subplots(1, 2, figsize=(11, 3.2))
correlogram(axes[0], acf(s, 36), "original series")
correlogram(axes[1], acf(s.diff().dropna(), 36), "month-over-month difference")
for ax in axes:
    ax.set_xticks(range(0, 37, 6))
fig.tight_layout()
fig.savefig("u09_correlogram.png")
plt.close(fig)

# ---------- 演習: コレログラム A(季節変動)・B(トレンド)・C(ランダム) ----------
rng = np.random.default_rng(9)
n = 120
k = np.arange(n)
seasonal = 10 * np.sin(2 * np.pi * k / 12) + rng.normal(0, 3, n)
trend = 0.5 * k + rng.normal(0, 4, n)
noise = rng.normal(0, 1, n)
fig, axes = plt.subplots(1, 3, figsize=(13, 3.0))
for ax, (name, x) in zip(axes, [("A", seasonal), ("B", trend), ("C", noise)]):
    correlogram(ax, acf(x, 30), name)
    ax.title.set_fontsize(15)
    ax.title.set_fontweight("bold")
    ax.set_xticks(range(0, 31, 6))
fig.tight_layout()
fig.savefig("u09_ex_correlograms.png")
plt.close(fig)
print("done")
