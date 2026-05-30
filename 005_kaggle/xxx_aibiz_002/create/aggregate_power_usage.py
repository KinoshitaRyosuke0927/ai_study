"""
東京電力パワーグリッド「でんき予報」の日別CSVを全期間分まとめて集計するスクリプト
対象フォルダ: yyyymm_power_usage の命名規則に従うすべてのフォルダ
対象列: DATE, TIME, 当日実績(万kW), 予測値(万kW), 使用率(%), 供給力(万kW)
"""
import os
import re
import glob
import pandas as pd
from io import StringIO

# ── パス設定 ─────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(BASE_DIR, "all_power_usage_summary.csv")

# ── yyyymm_power_usage フォルダを昇順で列挙 ───────────────
pattern = re.compile(r"^\d{6}_power_usage$")
target_dirs = sorted([
    os.path.join(BASE_DIR, d)
    for d in os.listdir(BASE_DIR)
    if os.path.isdir(os.path.join(BASE_DIR, d)) and pattern.match(d)
])
print(f"対象フォルダ数: {len(target_dirs)}")

# ── 全フォルダ・全日別ファイルの読み込み・抽出 ────────────
all_dfs = []

for dir_path in target_dirs:
    dir_name = os.path.basename(dir_path)
    csv_files = sorted(glob.glob(os.path.join(dir_path, "*.csv")))

    if not csv_files:
        print(f"[WARN] CSVファイルが見つかりません: {dir_name}")
        continue

    month_dfs = []
    for filepath in csv_files:
        with open(filepath, encoding="cp932") as f:
            lines = f.readlines()

        # 1時間間隔データのヘッダー行を探す
        # 「DATE,TIME,」で始まり「5分間隔値」を含まない行が対象セクション
        header_idx = None
        for i, line in enumerate(lines):
            if line.startswith("DATE,TIME,") and "5分間隔値" not in line:
                header_idx = i
                break

        if header_idx is None:
            print(f"  [WARN] データセクションが見つかりません: {os.path.basename(filepath)}")
            continue

        # ヘッダー行から空行までを抽出
        data_lines = [lines[header_idx]]
        for line in lines[header_idx + 1:]:
            if line.strip() == "":
                break
            data_lines.append(line)

        df = pd.read_csv(StringIO("".join(data_lines)))
        month_dfs.append(df)

    if month_dfs:
        month_result = pd.concat(month_dfs, ignore_index=True)
        all_dfs.append(month_result)
        print(f"  {dir_name}: {len(month_dfs)}日分 / {len(month_result)}行")

# ── 全期間データへ結合・出力 ───────────────────────────────
result = pd.concat(all_dfs, ignore_index=True)
result.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
print(f"\n集計完了: {OUTPUT_FILE}")
print(f"合計: {len(result)} 行")
print(f"期間: {result['DATE'].min()} 〜 {result['DATE'].max()}")
print(f"列: {list(result.columns)}")
