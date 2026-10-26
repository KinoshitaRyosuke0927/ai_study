"""単元7(クロス集計)の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u07_band.png    : 地域別の住居の構成比(帯グラフ)
- u07_ex_band.png : 演習「帯グラフの読み取り」(店舗別の満足度の構成比)
"""
import numpy as np
import pandas as pd


def band(fname, labels, rows, legend, title=None, height=3.0):
    """100% 積み上げ横棒グラフ(帯グラフ)を描く。rows は行ごとの割合(%)。"""
    rows = np.asarray(rows, dtype=float)
    fig, ax = plt.subplots(figsize=(9, height))
    left = np.zeros(len(labels))
    colors = [CATEGORY_COLORS[0], CATEGORY_COLORS[2], CATEGORY_COLORS[4]][: rows.shape[1]]
    for j, (name, color) in enumerate(zip(legend, colors)):
        ax.barh(labels, rows[:, j], left=left, color=color, edgecolor="white", label=name)
        for i, v in enumerate(rows[:, j]):
            ax.text(left[i] + v / 2, i, f"{v:.0f}%", ha="center", va="center", fontsize=10,
                    color="white" if j == 0 else "#333333")
        left += rows[:, j]
    ax.set_xlim(0, 100)
    ax.set_xlabel("share (%)")
    ax.invert_yaxis()
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.25), ncol=len(legend), frameon=False)
    if title:
        ax.set_title(title)
    fig.tight_layout()
    fig.savefig(fname)
    plt.close(fig)


# ---------- 地域別の住居の構成比 ----------
hh = pd.read_csv("households.csv")
order = ["北日本", "関東", "中部", "近畿", "西日本"]
rate = pd.crosstab(hh["region"], hh["housing"], normalize="index").reindex(order) * 100
band("u07_band.png", ["North", "Kanto", "Chubu", "Kinki", "West"], rate[["持ち家", "賃貸"]].to_numpy(),
     ["owner", "rent"], height=3.2)

# ---------- 演習: 店舗別の満足度 ----------
band("u07_ex_band.png", ["store P (n=200)", "store Q (n=50)", "store R (n=100)"],
     [[50, 30, 20], [30, 40, 30], [60, 25, 15]], ["satisfied", "neutral", "dissatisfied"], height=2.8)
print("done")
