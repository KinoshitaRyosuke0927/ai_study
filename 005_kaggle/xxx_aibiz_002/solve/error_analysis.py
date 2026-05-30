"""
予測誤差の詳細分析スクリプト
submission_walk_forward_v2.csv と test_eval_ans.csv を比較し、
どのようなデータで大きく予測を外しているか確認する
"""
import pandas as pd
import numpy as np
from sklearn.metrics import mean_squared_error

pred   = pd.read_csv("submission_walk_forward_v2.csv")
answer = pd.read_csv("../test_eval_ans.csv")

df = answer.merge(pred.rename(columns={"tokyo_price": "pred"}), on="id")
df["error"]     = df["pred"] - df["tokyo_price"]
df["abs_error"] = df["error"].abs()
df["date"]      = pd.to_datetime(df["date"])

rmse = np.sqrt(mean_squared_error(df["tokyo_price"], df["pred"]))
mae  = df["abs_error"].mean()
print(f"RMSE: {rmse:.4f}")
print(f"MAE : {mae:.4f}")

# ── 誤差の分布 ─────────────────────────────────────────────
print("\n--- 誤差の分布 ---")
for t in [5, 10, 15, 20]:
    n = (df["abs_error"] > t).sum()
    print(f"  abs_error > {t:2d}: {n:4d}件 ({n/len(df)*100:.1f}%)")

# ── フレーム帯別 ───────────────────────────────────────────
print("\n--- フレーム帯別 平均絶対誤差（上位10コマ）---")
frame_err = df.groupby("frame")["abs_error"].mean().sort_values(ascending=False).head(10)
print(frame_err.to_string())

# ── 曜日別 ────────────────────────────────────────────────
print("\n--- 曜日別 平均絶対誤差 ---")
df["dow"] = df["date"].dt.dayofweek
dow_map   = {0:"月", 1:"火", 2:"水", 3:"木", 4:"金", 5:"土", 6:"日"}
dow_err   = df.groupby("dow")["abs_error"].mean().rename(index=dow_map)
print(dow_err.to_string())

# ── 月別 ──────────────────────────────────────────────────
print("\n--- 月別 平均絶対誤差 ---")
df["month"] = df["date"].dt.month
month_err   = df.groupby("month")["abs_error"].mean()
print(month_err.to_string())

# ── 実績価格帯別 ───────────────────────────────────────────
print("\n--- 実績価格帯別 平均絶対誤差 ---")
bins   = [0, 5, 10, 15, 20, 30, 50]
labels = ["0-5", "5-10", "10-15", "15-20", "20-30", "30+"]
df["price_band"] = pd.cut(df["tokyo_price"], bins=bins, labels=labels)
band_err = df.groupby("price_band", observed=True)["abs_error"].agg(["mean", "count"])
print(band_err.to_string())

# ── 誤差上位20件（過大予測・過小予測） ─────────────────────
print("\n--- 誤差 Top20（過大予測: 予測 > 実績）---")
cols = ["date", "frame", "tokyo_price", "pred", "error"]
top_over = df.nlargest(20, "error")[cols]
print(top_over.to_string(index=False))

print("\n--- 誤差 Top20（過小予測: 予測 < 実績）---")
top_under = df.nsmallest(20, "error")[cols]
print(top_under.to_string(index=False))

# ── 日別の最大誤差 Top10 ───────────────────────────────────
print("\n--- 日別 最大絶対誤差 Top10 ---")
day_err = df.groupby("date")["abs_error"].agg(["max", "mean"]).sort_values("max", ascending=False).head(10)
day_err.index = day_err.index.strftime("%Y/%m/%d")
print(day_err.to_string())
