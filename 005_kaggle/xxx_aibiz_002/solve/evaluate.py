"""
提出ファイルのRMSEスコアを正解ファイルと比較して算出するスクリプト

使い方:
    python evaluate.py <提出ファイルのパス>

例:
    python evaluate.py submission_baseline.csv
"""
import sys
import pandas as pd
import numpy as np
from sklearn.metrics import mean_squared_error

# ── 引数チェック ───────────────────────────────────────────
if len(sys.argv) < 2:
    print("使い方: python evaluate.py <提出ファイルのパス>")
    print("例:     python evaluate.py submission_baseline.csv")
    sys.exit(1)

submission_path = sys.argv[1]

# ── ファイル読み込み ───────────────────────────────────────
try:
    submission = pd.read_csv(submission_path)
except FileNotFoundError:
    print(f"[ERROR] ファイルが見つかりません: {submission_path}")
    sys.exit(1)

answer = pd.read_csv("../test_eval_ans.csv")[["id", "tokyo_price"]]

# ── バリデーション ─────────────────────────────────────────
if "id" not in submission.columns or "tokyo_price" not in submission.columns:
    print(f"[ERROR] 提出ファイルに 'id' または 'tokyo_price' 列がありません")
    print(f"  検出された列: {list(submission.columns)}")
    sys.exit(1)

if len(submission) != len(answer):
    print(f"[ERROR] 行数が一致しません: 提出={len(submission)}, 正解={len(answer)}")
    sys.exit(1)

# ── id をキーに結合してスコア算出 ──────────────────────────
merged = answer.merge(submission[["id", "tokyo_price"]], on="id", suffixes=("_ans", "_pred"))

if merged.isnull().any().any():
    print(f"[WARN] 予測値に欠損があります: {merged.isnull().sum().to_dict()}")

rmse = np.sqrt(mean_squared_error(merged["tokyo_price_ans"], merged["tokyo_price_pred"]))
mae  = (merged["tokyo_price_ans"] - merged["tokyo_price_pred"]).abs().mean()

# ── 結果表示 ───────────────────────────────────────────────
print(f"提出ファイル : {submission_path}")
print(f"評価件数     : {len(merged)} 件")
print(f"RMSE         : {rmse:.4f}")
print(f"MAE          : {mae:.4f}  （参考）")
