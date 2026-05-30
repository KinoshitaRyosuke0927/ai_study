"""
data_20240401_20260531.csv の weather 列を気象庁天気コードから英語名称に変換するスクリプト
変換後は weather 列の値が数値コードから英語名称に置き換わる
"""
import pandas as pd

# ── 気象庁 天気コード → 英語名称マッピング ─────────────────
WEATHER_CODE_MAP = {
    1:  "clear",
    2:  "sunny",
    3:  "slightly_cloudy",
    4:  "cloudy",
    5:  "haze",
    6:  "dust_storm",
    7:  "drifting_snow",
    8:  "fog",
    9:  "drizzle",
    10: "rain",
    11: "sleet",
    12: "snow",
    13: "graupel",
    14: "hail",
    15: "thunder",
}

# ── データ読み込み ─────────────────────────────────────────
df = pd.read_csv("data_20240401_20260531.csv")

# ── weather 列を英語名称に変換 ──────────────────────────────
# コードが整数として読み込まれるため Int64 に変換してからマッピング
df["weather"] = df["weather"].astype("Int64").map(WEATHER_CODE_MAP)

# ── 変換結果の確認 ─────────────────────────────────────────
print("変換後の weather 列のユニーク値:")
print(df["weather"].value_counts(dropna=False).to_string())

# ── 出力 ──────────────────────────────────────────────────
df.to_csv("data_20240401_20260531.csv", index=False)
print(f"\n変換完了: data_20240401_20260531.csv ({len(df)} 行)")
