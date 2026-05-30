"""
power_usage.csv / spot_summary.csv / weather_data.csv を
date・frame をキーに INNER JOIN で結合し、時間・曜日・祝日フラグを付与するスクリプト

事前インストール: pip install jpholiday
"""
import pandas as pd
import jpholiday

# ── データ読み込み ─────────────────────────────────────────
power   = pd.read_csv("power_usage.csv")
spot    = pd.read_csv("spot_summary.csv")
weather = pd.read_csv("weather_data.csv")

# ── date 列のフォーマットを統一（YYYY/MM/DD） ──────────────
# 各ファイルで表記揺れ（2024/4/1 と 2024/04/01）があるため正規化
for df in [power, spot, weather]:
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y/%m/%d")

# ── INNER JOIN で結合 ──────────────────────────────────────
merged = (
    spot
    .merge(power,   on=["date", "frame"], how="inner")
    .merge(weather, on=["date", "frame"], how="inner")
)

# ── 時間帯・曜日・祝日フラグを付与 ────────────────────────
dt = pd.to_datetime(merged["date"])

# 曜日: 0=月曜 〜 6=日曜
merged["dayofweek"]  = dt.dt.dayofweek

# 祝日フラグ: 祝日=1, 平日=0
merged["is_holiday"] = dt.apply(lambda d: 1 if jpholiday.is_holiday(d) else 0)

# ── 列の並び替え（tokyo_price を最右列に） ─────────────────
col_order = [
    # キー・時間情報
    "date", "frame", "dayofweek", "is_holiday",
    # 気象
    "temp", "weather",
    # 電力需給
    "power_result", "power_prediction", "usage_rate", "power_supply",
    # 市場（目的変数を最右）
    "sell_amount", "buy_amount", "contracted_amount", "tokyo_price",
]
merged = merged[col_order]

# ── 結果確認・出力 ─────────────────────────────────────────
print(f"spot     : {len(spot)} 行")
print(f"power    : {len(power)} 行")
print(f"weather  : {len(weather)} 行")
print(f"結合後   : {len(merged)} 行")
print(f"期間     : {merged['date'].min()} 〜 {merged['date'].max()}")
print(f"列       : {list(merged.columns)}")

merged.to_csv("merged_dataset.csv", index=False)
print("\n出力完了: merged_dataset.csv")
