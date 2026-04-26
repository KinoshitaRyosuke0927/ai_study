"""
https://www.kaggle.com/competitions/digit-recognizer/overview
手書き数字画像（0〜9）の多クラス分類問題。
評価指標: Accuracy（正解率）

EDA の目的:
  1. クラス分布の確認 → データの偏りがないか
  2. 画像の可視化   → どんな手書きパターンがあるか
  3. ピクセル分布   → 値の偏り・正規化の必要性
  4. クラス平均画像 → クラスごとの典型的な形状を把握
  5. 混同しやすいクラスの確認 → 予測が難しいペアを事前に把握
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path

DATA_DIR = Path(r"C:\azure_ai\education\005_kaggle\competitions\digit-recognizer")
OUT_DIR  = DATA_DIR

train = pd.read_csv(DATA_DIR / "train.csv")
test  = pd.read_csv(DATA_DIR / "test.csv")

print("=" * 55)
print("基本情報")
print("=" * 55)
print(f"train: {train.shape[0]:,} 行 × {train.shape[1]:,} 列")
print(f"test : {test.shape[0]:,} 行 × {test.shape[1]:,} 列")
print(f"ピクセル数: {train.shape[1] - 1} = 28×28")
print(f"欠損値(train): {train.isnull().sum().sum()}")
print(f"欠損値(test) : {test.isnull().sum().sum()}")
print(f"クラス数: {train['label'].nunique()} （{sorted(train['label'].unique())}）")


# ================================================================
# EDA 1: クラス分布
# ================================================================
print("\n" + "=" * 55)
print("EDA 1: クラス分布")
print("=" * 55)

counts = train["label"].value_counts().sort_index()
for label, cnt in counts.items():
    bar = "█" * (cnt // 100)
    print(f"  {label}: {cnt:>5,}枚  {bar}")

fig, ax = plt.subplots(figsize=(8, 4))
ax.bar(counts.index, counts.values, color="steelblue", edgecolor="white")
ax.set_xlabel("数字ラベル")
ax.set_ylabel("枚数")
ax.set_title("EDA 1: クラス分布（各数字の学習データ枚数）")
ax.set_xticks(range(10))
for i, v in enumerate(counts.values):
    ax.text(i, v + 30, str(v), ha="center", fontsize=9)
plt.tight_layout()
plt.savefig(OUT_DIR / "eda_01_class_distribution.png", dpi=120)
plt.close()
print("→ eda_01_class_distribution.png を保存しました")


# ================================================================
# EDA 2: 各クラスのサンプル画像
# ================================================================
print("\n" + "=" * 55)
print("EDA 2: 各クラスのサンプル画像（5枚ずつ）")
print("=" * 55)

N_SAMPLES = 5
fig, axes = plt.subplots(10, N_SAMPLES, figsize=(N_SAMPLES * 1.5, 10 * 1.5))
fig.suptitle("EDA 2: 各クラスのサンプル画像", fontsize=13)

for digit in range(10):
    samples = train[train["label"] == digit].head(N_SAMPLES)
    for j, (_, row) in enumerate(samples.iterrows()):
        img = row[1:].values.reshape(28, 28)
        axes[digit, j].imshow(img, cmap="gray")
        axes[digit, j].axis("off")
        if j == 0:
            axes[digit, j].set_title(f"{digit}", fontsize=11, loc="left", pad=2)

plt.tight_layout()
plt.savefig(OUT_DIR / "eda_02_sample_images.png", dpi=120)
plt.close()
print("→ eda_02_sample_images.png を保存しました")


# ================================================================
# EDA 3: ピクセル値の分布
# ================================================================
print("\n" + "=" * 55)
print("EDA 3: ピクセル値の分布")
print("=" * 55)

pixel_values = train.iloc[:, 1:].values.flatten()
zero_ratio   = (pixel_values == 0).mean() * 100
nonzero      = pixel_values[pixel_values > 0]

print(f"  ピクセル値の範囲: {pixel_values.min()} 〜 {pixel_values.max()}")
print(f"  ゼロ値（白背景）の割合: {zero_ratio:.1f}%")
print(f"  非ゼロの平均値: {nonzero.mean():.1f}")
print(f"  非ゼロの中央値: {np.median(nonzero):.1f}")

fig, axes = plt.subplots(1, 2, figsize=(12, 4))
fig.suptitle("EDA 3: ピクセル値の分布", fontsize=13)

# 全ピクセルのヒストグラム
axes[0].hist(pixel_values, bins=50, color="steelblue", edgecolor="white", log=True)
axes[0].set_xlabel("ピクセル値 (0=白, 255=黒)")
axes[0].set_ylabel("頻度（対数スケール）")
axes[0].set_title(f"全ピクセルの分布（ゼロ={zero_ratio:.1f}%）")

# 非ゼロのピクセルのヒストグラム
axes[1].hist(nonzero, bins=50, color="coral", edgecolor="white")
axes[1].set_xlabel("ピクセル値")
axes[1].set_ylabel("頻度")
axes[1].set_title("非ゼロピクセルの分布")

plt.tight_layout()
plt.savefig(OUT_DIR / "eda_03_pixel_distribution.png", dpi=120)
plt.close()
print("→ eda_03_pixel_distribution.png を保存しました")


# ================================================================
# EDA 4: クラス別の平均画像
# ================================================================
print("\n" + "=" * 55)
print("EDA 4: クラス別の平均画像（各数字の典型的な形状）")
print("=" * 55)

fig, axes = plt.subplots(2, 5, figsize=(12, 5))
fig.suptitle("EDA 4: クラス別の平均画像（各数字の典型的な形状）", fontsize=13)

for digit in range(10):
    ax  = axes[digit // 5, digit % 5]
    avg = train[train["label"] == digit].iloc[:, 1:].mean().values.reshape(28, 28)
    im  = ax.imshow(avg, cmap="hot")
    ax.set_title(f"数字: {digit}", fontsize=11)
    ax.axis("off")

plt.colorbar(im, ax=axes, shrink=0.6, label="平均ピクセル値")
plt.savefig(OUT_DIR / "eda_04_average_images.png", dpi=120)
plt.close()
print("→ eda_04_average_images.png を保存しました")


# ================================================================
# EDA 5: クラス別のピクセル使用領域（どこに筆跡が集中するか）
# ================================================================
print("\n" + "=" * 55)
print("EDA 5: 全クラス共通の筆跡頻度マップ")
print("=" * 55)

pixel_cols  = train.columns[1:]
active_freq = (train[pixel_cols] > 0).mean().values.reshape(28, 28)

fig, ax = plt.subplots(figsize=(6, 6))
im = ax.imshow(active_freq, cmap="YlOrRd")
ax.set_title("EDA 5: 筆跡頻度マップ\n（各ピクセルで値>0になる確率）", fontsize=12)
ax.set_xlabel("列 (0〜27)")
ax.set_ylabel("行 (0〜27)")
plt.colorbar(im, ax=ax, label="非ゼロ確率")
plt.tight_layout()
plt.savefig(OUT_DIR / "eda_05_active_pixel_map.png", dpi=120)
plt.close()
print("→ eda_05_active_pixel_map.png を保存しました")


# ================================================================
# EDA 6: 紛らわしい数字のペア確認（4 vs 9, 3 vs 8 など）
# ================================================================
print("\n" + "=" * 55)
print("EDA 6: 混同しやすい数字ペアの比較")
print("=" * 55)

CONFUSABLE_PAIRS = [(4, 9), (3, 8), (1, 7), (5, 6)]
fig, axes = plt.subplots(len(CONFUSABLE_PAIRS), 10, figsize=(15, 7))
fig.suptitle("EDA 6: 混同しやすい数字ペアのサンプル比較", fontsize=13)

for row_idx, (d1, d2) in enumerate(CONFUSABLE_PAIRS):
    for col_idx, digit in enumerate([d1] * 5 + [d2] * 5):
        sample_idx = col_idx if col_idx < 5 else col_idx - 5
        sample = train[train["label"] == digit].iloc[sample_idx, 1:].values.reshape(28, 28)
        axes[row_idx, col_idx].imshow(sample, cmap="gray")
        axes[row_idx, col_idx].axis("off")

    axes[row_idx, 0].set_title(f"← {d1}", fontsize=10, loc="left")
    axes[row_idx, 5].set_title(f"← {d2}", fontsize=10, loc="left")

plt.tight_layout()
plt.savefig(OUT_DIR / "eda_06_confusable_pairs.png", dpi=120)
plt.close()
print("→ eda_06_confusable_pairs.png を保存しました")


# ================================================================
# EDA 7: ピクセル値の統計サマリー
# ================================================================
print("\n" + "=" * 55)
print("EDA 7: クラス別ピクセル統計サマリー")
print("=" * 55)

summary = []
for digit in range(10):
    vals = train[train["label"] == digit].iloc[:, 1:].values.flatten()
    summary.append({
        "数字":       digit,
        "枚数":       counts[digit],
        "平均輝度":   f"{vals.mean():.1f}",
        "非ゼロ率(%)": f"{(vals > 0).mean() * 100:.1f}",
        "最大値":     int(vals.max()),
    })

summary_df = pd.DataFrame(summary).set_index("数字")
print(summary_df.to_string())


print("\n" + "=" * 55)
print("EDA 完了  —  保存されたグラフ一覧")
print("=" * 55)
for fname in [
    "eda_01_class_distribution.png",
    "eda_02_sample_images.png",
    "eda_03_pixel_distribution.png",
    "eda_04_average_images.png",
    "eda_05_active_pixel_map.png",
    "eda_06_confusable_pairs.png",
]:
    print(f"  {fname}")
