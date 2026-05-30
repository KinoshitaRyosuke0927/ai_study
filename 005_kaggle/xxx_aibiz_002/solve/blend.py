"""
v9（一括予測）とウォークフォワード予測のブレンドスクリプト
複数のブレンド比率を評価し、最良のRMSEとなる比率で提出ファイルを生成する

使い方:
    python blend.py
"""
import pandas as pd
import numpy as np
from sklearn.metrics import mean_squared_error

# ── 予測ファイルと正解ファイルの読み込み ──────────────────
pred_v9 = pd.read_csv("submission_feature_eng_v9.csv")
pred_wf = pd.read_csv("submission_walk_forward.csv")
answer  = pd.read_csv("../test_eval_ans.csv")[["id", "tokyo_price"]]

# id をキーに結合
merged = (
    answer
    .merge(pred_v9[["id", "tokyo_price"]].rename(columns={"tokyo_price": "pred_v9"}), on="id")
    .merge(pred_wf[["id", "tokyo_price"]].rename(columns={"tokyo_price": "pred_wf"}), on="id")
)

print(f"{'モデル':<30} RMSE")
print("-" * 45)

# ── 単体スコアの確認 ───────────────────────────────────────
rmse_v9 = np.sqrt(mean_squared_error(merged["tokyo_price"], merged["pred_v9"]))
rmse_wf = np.sqrt(mean_squared_error(merged["tokyo_price"], merged["pred_wf"]))
print(f"{'v9（一括予測）':<30} {rmse_v9:.4f}")
print(f"{'walk_forward':<30} {rmse_wf:.4f}")
print("-" * 45)

# ── 各ブレンド比率を評価 ───────────────────────────────────
# weight = v9 の重み（1 - weight = walk_forward の重み）
results = []
for weight in np.arange(0.0, 1.01, 0.05):
    blended = merged["pred_v9"] * weight + merged["pred_wf"] * (1 - weight)
    rmse = np.sqrt(mean_squared_error(merged["tokyo_price"], blended))
    results.append({"weight_v9": round(weight, 2), "weight_wf": round(1 - weight, 2), "rmse": rmse})
    print(f"  v9:{weight:.2f} / walk_forward:{1-weight:.2f}  RMSE: {rmse:.4f}")

# ── 最良のブレンド比率を特定 ──────────────────────────────
best = min(results, key=lambda x: x["rmse"])
print(f"\n最良ブレンド: v9={best['weight_v9']} / walk_forward={best['weight_wf']}")
print(f"Best RMSE  : {best['rmse']:.4f}")

# ── 最良比率で提出ファイルを生成 ──────────────────────────
final_pred = (
    pred_v9.set_index("id")["tokyo_price"] * best["weight_v9"]
    + pred_wf.set_index("id")["tokyo_price"] * best["weight_wf"]
).round(2).reset_index()
final_pred.columns = ["id", "tokyo_price"]
final_pred.to_csv("submission_blend.csv", index=False)
print(f"\n出力完了: submission_blend.csv ({len(final_pred)}件)")
