import sys
import pandas as pd
from sklearn.metrics import f1_score, classification_report

ANS_PATH = "create/test_data_ans.csv"

# 引数で予測ファイルを指定（省略時は submission.csv）
pred_path = sys.argv[1] if len(sys.argv) > 1 else "submission.csv"

# データ読み込み
ans  = pd.read_csv(ANS_PATH, encoding="utf-8-sig")
pred = pd.read_csv(pred_path, encoding="utf-8-sig")

# 行数チェック
if len(ans) != len(pred):
    print(f"[ERROR] 行数が一致しません: 正解={len(ans)}行, 予測={len(pred)}行")
    sys.exit(1)

y_true = ans["channel_name"]
y_pred = pred["channel_name"]

# Macro F1
macro_f1 = f1_score(y_true, y_pred, average="macro")
print(f"予測ファイル : {pred_path}")
print(f"Macro F1     : {macro_f1:.4f}")

# チャンネル別の詳細
print("\n--- チャンネル別詳細 ---")
print(classification_report(y_true, y_pred, digits=4))
