import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
from sklearn.metrics import f1_score, classification_report, confusion_matrix

matplotlib.rcParams["font.family"] = "MS Gothic"

ANS_PATH  = "create/test_data_ans.csv"
PRED_BASE = "submission_feature_eng_v3_v1.csv"
PRED_V3   = "submission_feature_eng_v3_v2.csv"
OUT_DIR   = "output"
os.makedirs(OUT_DIR, exist_ok=True)

# データ読み込み
ans  = pd.read_csv(ANS_PATH,  encoding="utf-8-sig")
base = pd.read_csv(PRED_BASE, encoding="utf-8-sig")
v3   = pd.read_csv(PRED_V3,   encoding="utf-8-sig")

y_true      = ans["channel_name"]
y_pred_base = base["channel_name"]
y_pred_v3   = v3["channel_name"]
labels      = sorted(y_true.unique())

# ── 図1: チャンネル別 F1 比較棒グラフ ──────────────────────────────
report_base = classification_report(y_true, y_pred_base, labels=labels, output_dict=True)
report_v3   = classification_report(y_true, y_pred_v3,   labels=labels, output_dict=True)

f1_base = [report_base[ch]["f1-score"] for ch in labels]
f1_v3   = [report_v3[ch]["f1-score"]   for ch in labels]
diff    = [v - b for v, b in zip(f1_v3, f1_base)]

x = np.arange(len(labels))
w = 0.35

fig, ax = plt.subplots(figsize=(16, 8))
bars_b = ax.bar(x - w / 2, f1_base, w, label="baseline", color="steelblue", alpha=0.8)
bars_v = ax.bar(x + w / 2, f1_v3,   w, label="v3",       color="tomato",    alpha=0.8)

# 差分をバーの上に表示
for i, (xpos, d) in enumerate(zip(x, diff)):
    color = "green" if d >= 0 else "red"
    ax.text(xpos, max(f1_base[i], f1_v3[i]) + 0.005, f"{d:+.3f}",
            ha="center", va="bottom", fontsize=7, color=color)

ax.set_xticks(x)
ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=9)
ax.set_ylim(0, 1.08)
ax.set_ylabel("F1 スコア")
ax.set_title("チャンネル別 F1 スコア比較（baseline vs v3）")
ax.legend()
ax.axhline(y=np.mean(f1_base), color="steelblue", linestyle="--", linewidth=0.8, alpha=0.6, label=f"baseline avg")
ax.axhline(y=np.mean(f1_v3),   color="tomato",    linestyle="--", linewidth=0.8, alpha=0.6, label=f"v3 avg")
plt.tight_layout()
plt.savefig(f"{OUT_DIR}/01_f1_comparison.png", dpi=150)
plt.close()
print("保存: 01_f1_comparison.png")

# ── 図2・3: 混同行列 ────────────────────────────────────────────────
def plot_confusion(y_true, y_pred, labels, title, path):
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    # 行ごとに正規化（再現率ベース）
    cm_norm = cm.astype(float) / cm.sum(axis=1, keepdims=True)

    fig, ax = plt.subplots(figsize=(16, 14))
    im = ax.imshow(cm_norm, cmap="Blues", vmin=0, vmax=1)
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("予測ラベル")
    ax.set_ylabel("正解ラベル")
    ax.set_title(title)

    # セルに件数を表示（件数が多いセルのみ）
    for i in range(len(labels)):
        for j in range(len(labels)):
            if cm[i, j] > 0:
                color = "white" if cm_norm[i, j] > 0.6 else "black"
                ax.text(j, i, str(cm[i, j]), ha="center", va="center",
                        fontsize=6, color=color)

    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()

plot_confusion(y_true, y_pred_base, labels,
               "混同行列 - baseline（行方向正規化）",
               f"{OUT_DIR}/02_confusion_baseline.png")
print("保存: 02_confusion_baseline.png")

plot_confusion(y_true, y_pred_v3, labels,
               "混同行列 - v3（行方向正規化）",
               f"{OUT_DIR}/03_confusion_v3.png")
print("保存: 03_confusion_v3.png")

# ── サマリ表示 ───────────────────────────────────────────────────────
macro_base = f1_score(y_true, y_pred_base, average="macro")
macro_v3   = f1_score(y_true, y_pred_v3,   average="macro")
print(f"\nMacro F1  baseline: {macro_base:.4f}")
print(f"Macro F1  v3      : {macro_v3:.4f}  ({macro_v3 - macro_base:+.4f})")
print(f"\n出力先: {os.path.abspath(OUT_DIR)}/")
