"""
data_20240401_20260531.csv を1時間間隔から30分間隔（FRAME列）に変換するスクリプト
- date列: 年月日のみに変更
- frame列: 0:00→1, 0:30→2, ..., 23:00→47, 23:30→48
- temp列: :30コマは直前の:00コマの値を引き継ぐ
- weather列: :30コマは空欄
"""
import pandas as pd

# ── データ読み込み ─────────────────────────────────────────
df = pd.read_csv("data_20240401_20260531.csv", index_col=False, usecols=["date", "temp", "weather"])
df["date"] = pd.to_datetime(df["date"], format="%Y/%m/%d %H:%M")

# ── 1時間間隔 → 30分間隔に展開 ────────────────────────────
rows = []
for _, row in df.iterrows():
    hour = row["date"].hour
    date_only = row["date"].strftime("%Y/%m/%d")
    base_frame = hour * 2 + 1

    # :00コマ（奇数フレーム）: temp・weather ともに元データを使用
    rows.append({
        "date":    date_only,
        "frame":   base_frame,
        "temp":    row["temp"],
        "weather": row["weather"],
    })

    # :30コマ（偶数フレーム）: temp は前行を引き継ぎ、weather は空欄
    rows.append({
        "date":    date_only,
        "frame":   base_frame + 1,
        "temp":    row["temp"],
        "weather": None,
    })

# ── 結果を date・frame 順に並べて出力 ─────────────────────
result = pd.DataFrame(rows, columns=["date", "frame", "temp", "weather"])
result = result.sort_values(["date", "frame"]).reset_index(drop=True)

result.to_csv("data_20240401_20260531.csv", index=False)
print(f"変換完了: data_20240401_20260531.csv")
print(f"行数: {len(result)} 行（元データ {len(df)} 行 × 2）")
print(f"期間: {result['date'].min()} 〜 {result['date'].max()}")
print(result.head(6).to_string(index=False))
