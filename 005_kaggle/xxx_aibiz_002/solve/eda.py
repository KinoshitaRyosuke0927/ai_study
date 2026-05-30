"""
JEPX 東京エリア電力スポット価格予測 - 探索的データ分析（EDA）
学習データ（pre_eval.csv）の基本統計・分布・相関を確認する
"""
import pandas as pd
import numpy as np

# ── データ読み込み ─────────────────────────────────────────
df = pd.read_csv("../pre_eval.csv")
df["date"] = pd.to_datetime(df["date"])

print("=" * 60)
print("【基本情報】")
print(f"行数: {len(df)}, 列数: {len(df.columns)}")
print(f"期間: {df['date'].min().date()} 〜 {df['date'].max().date()}")
print(f"列: {list(df.columns)}")

# ── 欠損値確認 ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("【欠損値】")
missing = df.isnull().sum()
missing_pct = (missing / len(df) * 100).round(2)
missing_df = pd.DataFrame({"欠損数": missing, "欠損率(%)": missing_pct})
print(missing_df[missing_df["欠損数"] > 0].to_string())
print("欠損なし" if missing_df["欠損数"].sum() == 0 else "")

# ── 目的変数の分布 ─────────────────────────────────────────
print("\n" + "=" * 60)
print("【目的変数 tokyo_price（円/kWh）の分布】")
p = df["tokyo_price"]
print(f"  min={p.min():.2f}, max={p.max():.2f}")
print(f"  mean={p.mean():.2f}, median={p.median():.2f}, std={p.std():.2f}")
print(f"  25%={p.quantile(0.25):.2f}, 75%={p.quantile(0.75):.2f}")
print(f"  0円以下の行数: {(p <= 0).sum()}")
print(f"  30円超の行数: {(p > 30).sum()} ({(p > 30).mean()*100:.1f}%)")

# ── 数値特徴量の基本統計量 ─────────────────────────────────
print("\n" + "=" * 60)
print("【数値特徴量の基本統計量】")
num_cols = ["temp", "power_result", "power_prediction",
            "usage_rate", "power_supply",
            "sell_amount", "buy_amount", "contracted_amount"]
print(df[num_cols].describe().T.round(2).to_string())

# ── 目的変数との相関 ───────────────────────────────────────
print("\n" + "=" * 60)
print("【各特徴量と tokyo_price の相関係数（数値列）】")
corr_cols = num_cols + ["frame", "dayofweek", "is_holiday"]
corr = df[corr_cols + ["tokyo_price"]].corr()["tokyo_price"].drop("tokyo_price")
print(corr.sort_values(ascending=False).round(4).to_string())

# ── 時間帯（frame）別の平均価格 ───────────────────────────
print("\n" + "=" * 60)
print("【フレーム帯別 平均 tokyo_price（上位・下位5コマ）】")
frame_mean = df.groupby("frame")["tokyo_price"].mean().round(2)
print("  価格が高いコマ TOP5:")
print(frame_mean.nlargest(5).to_string())
print("  価格が低いコマ TOP5:")
print(frame_mean.nsmallest(5).to_string())

# ── 曜日別の平均価格 ───────────────────────────────────────
print("\n" + "=" * 60)
print("【曜日別 平均 tokyo_price（0=月〜6=日）】")
dow_map = {0:"月", 1:"火", 2:"水", 3:"木", 4:"金", 5:"土", 6:"日"}
dow_mean = df.groupby("dayofweek")["tokyo_price"].mean().round(2)
dow_mean.index = dow_mean.index.map(dow_map)
print(dow_mean.to_string())

# ── 祝日フラグ別の平均価格 ────────────────────────────────
print("\n" + "=" * 60)
print("【祝日フラグ別 平均 tokyo_price】")
holiday_mean = df.groupby("is_holiday")["tokyo_price"].agg(["mean", "count"]).round(2)
holiday_mean.index = ["平日", "祝日"]
print(holiday_mean.to_string())

# ── 月別の平均価格 ─────────────────────────────────────────
print("\n" + "=" * 60)
print("【月別 平均 tokyo_price】")
df["month"] = df["date"].dt.to_period("M")
month_mean = df.groupby("month")["tokyo_price"].mean().round(2)
print(month_mean.to_string())

# ── 天気別の平均価格 ───────────────────────────────────────
print("\n" + "=" * 60)
print("【天気別 平均 tokyo_price】")
weather_mean = (
    df.groupby("weather")["tokyo_price"]
    .agg(["mean", "count"])
    .sort_values("mean", ascending=False)
    .round(2)
)
print(weather_mean.to_string())
