"""
all_power_usage_summary.csv の TIME列（1時間刻み）を FRAME列（30分刻み、1〜48）に変換するスクリプト
各時間行を2行に展開し、他の列は同じ値を引き継ぐ
  例: 0:00 → FRAME=1, FRAME=2
      1:00 → FRAME=3, FRAME=4
      ...
     23:00 → FRAME=47, FRAME=48
"""
import pandas as pd

# ── データ読み込み ─────────────────────────────────────────
df = pd.read_csv("all_power_usage_summary.csv", encoding="utf-8-sig")

# ── TIME列をフレーム番号（1〜48）に展開 ────────────────────
# TIME列から時間を抽出し、フレーム番号を計算
# 時間 h → FRAME h*2+1（:00）と h*2+2（:30）の2行を生成
df["hour"] = df["TIME"].str.split(":").str[0].astype(int)

rows = []
value_cols = [c for c in df.columns if c not in ("DATE", "TIME", "hour")]

for _, row in df.iterrows():
    base_frame = row["hour"] * 2 + 1
    for frame in [base_frame, base_frame + 1]:
        new_row = {"DATE": row["DATE"], "FRAME": frame}
        for col in value_cols:
            new_row[col] = row[col]
        rows.append(new_row)

# ── 結果を DATE・FRAME 順に並べて出力 ─────────────────────
result = pd.DataFrame(rows, columns=["DATE", "FRAME"] + value_cols)
result = result.sort_values(["DATE", "FRAME"]).reset_index(drop=True)

result.to_csv("all_power_usage_frame.csv", index=False, encoding="utf-8-sig")
print(f"変換完了: all_power_usage_frame.csv")
print(f"行数: {len(result)} 行（元データ {len(df)} 行 × 2）")
print(f"FRAMEの範囲: {result['FRAME'].min()} 〜 {result['FRAME'].max()}")
print(result.head(6).to_string(index=False))
