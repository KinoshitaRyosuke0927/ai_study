"""単元5(2つの母平均の差の検定)の図を作る。共通スタイル適用済みの前提(make-figures.mjs が適用する)。

- u05_paired.png : 対応のあるデータ(5 人の前後)と、差だけを見る考え方
"""
import numpy as np

before = np.array([62, 75, 58, 81, 69])
diff = np.array([3, 5, 2, 6, 4])
after = before + diff
fig, axes = plt.subplots(1, 2, figsize=(11, 3.6), gridspec_kw={"width_ratios": [3, 2]})
for i, (b, a) in enumerate(zip(before, after)):
    axes[0].plot([0, 1], [b, a], marker="o", color=PRIMARY)
    axes[0].text(-0.06, b, f"person {i + 1}", ha="right", va="center", fontsize=9)
axes[0].set_xticks([0, 1], ["before", "after"])
axes[0].set_xlim(-0.45, 1.2)
axes[0].set_ylabel("score")
axes[0].set_title("scores differ a lot between people,\nbut every person goes up")
axes[1].bar(range(1, 6), diff, color=ACCENT)
axes[1].axhline(0, color="gray", linewidth=1)
axes[1].set_xticks(range(1, 6), [f"p{i}" for i in range(1, 6)])
axes[1].set_ylabel("after - before")
axes[1].set_title("analyze only the differences d")
fig.tight_layout()
fig.savefig("u05_paired.png")
plt.close(fig)
print("before", before.tolist(), "after", after.tolist())
