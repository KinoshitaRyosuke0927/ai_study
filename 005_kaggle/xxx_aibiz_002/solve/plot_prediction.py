"""
実際の価格 vs 最良予測（v3）の可視化
"""
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from sklearn.metrics import mean_squared_error

# ── データ読み込み ─────────────────────────────────────────
ans = pd.read_csv("../test_eval_ans.csv")
sub = pd.read_csv("submission_v3.csv")
test = pd.read_csv("../test_eval.csv")

test["date"] = pd.to_datetime(test["date"])
merged = test[["id", "date", "frame"]].merge(ans[["id", "tokyo_price"]], on="id")
merged = merged.merge(sub[["id", "tokyo_price"]], on="id", suffixes=("_actual", "_pred"))
merged = merged.sort_values(["date", "frame"]).reset_index(drop=True)

# 日次集計
daily = merged.groupby("date").agg(
    actual=("tokyo_price_actual", "mean"),
    pred=("tokyo_price_pred", "mean"),
    actual_max=("tokyo_price_actual", "max"),
    actual_min=("tokyo_price_actual", "min"),
).reset_index()
daily["error"] = daily["pred"] - daily["actual"]

# 誤差
merged["abs_error"] = (merged["tokyo_price_pred"] - merged["tokyo_price_actual"]).abs()
rmse = np.sqrt(mean_squared_error(merged["tokyo_price_actual"], merged["tokyo_price_pred"]))

# ── 日本語フォント設定 ─────────────────────────────────────
plt.rcParams["font.family"] = "MS Gothic"
plt.rcParams["axes.unicode_minus"] = False

fig = plt.figure(figsize=(16, 14))
fig.suptitle(f"JEPX 東京エリア電力スポット価格予測 — v3 (RMSE: {rmse:.4f})", fontsize=14, fontweight="bold", y=0.98)

# ── グラフ1: 日次平均の時系列比較 ────────────────────────
ax1 = fig.add_subplot(3, 2, (1, 2))
ax1.fill_between(daily["date"], daily["actual_min"], daily["actual_max"],
                 alpha=0.15, color="steelblue", label="実績値レンジ（日内最小〜最大）")
ax1.plot(daily["date"], daily["actual"], color="steelblue", linewidth=1.8, label="実績値（日次平均）")
ax1.plot(daily["date"], daily["pred"],   color="crimson",   linewidth=1.5,
         linestyle="--", label="予測値（日次平均）", alpha=0.85)
ax1.set_title("日次平均価格の推移（2026/1〜3月）", fontsize=11)
ax1.set_ylabel("価格（円/kWh）")
ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
ax1.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0))
ax1.legend(fontsize=9)
ax1.grid(axis="y", alpha=0.4)
plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha="right")

# ── グラフ2: 誤差（日次平均）の時系列 ──────────────────
ax2 = fig.add_subplot(3, 2, (3, 4))
colors = ["crimson" if e > 0 else "steelblue" for e in daily["error"]]
ax2.bar(daily["date"], daily["error"], color=colors, alpha=0.7, width=0.8)
ax2.axhline(0, color="black", linewidth=0.8)
ax2.set_title("日次平均誤差（予測 − 実績）", fontsize=11)
ax2.set_ylabel("誤差（円/kWh）")
ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
ax2.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0))
ax2.grid(axis="y", alpha=0.4)
plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha="right")

# ── グラフ3: 散布図（実績 vs 予測） ───────────────────
ax3 = fig.add_subplot(3, 2, 5)
sc = ax3.scatter(merged["tokyo_price_actual"], merged["tokyo_price_pred"],
                 alpha=0.3, s=5, c=merged["abs_error"], cmap="YlOrRd", vmax=10)
lim_max = max(merged["tokyo_price_actual"].max(), merged["tokyo_price_pred"].max()) + 1
ax3.plot([0, lim_max], [0, lim_max], "k--", linewidth=0.8, alpha=0.6)
ax3.set_xlabel("実績値（円/kWh）")
ax3.set_ylabel("予測値（円/kWh）")
ax3.set_title("散布図（実績 vs 予測）", fontsize=11)
ax3.set_xlim(0, lim_max)
ax3.set_ylim(0, lim_max)
plt.colorbar(sc, ax=ax3, label="絶対誤差（円）")
ax3.grid(alpha=0.3)

# ── グラフ4: 絶対誤差のヒストグラム ──────────────────
ax4 = fig.add_subplot(3, 2, 6)
ax4.hist(merged["abs_error"], bins=50, color="steelblue", edgecolor="white", linewidth=0.4)
for thr, col in [(1, "green"), (2, "orange"), (5, "red")]:
    pct = (merged["abs_error"] <= thr).mean() * 100
    ax4.axvline(thr, color=col, linewidth=1.2, linestyle="--",
                label=f"±{thr}円: {pct:.1f}%")
ax4.set_xlabel("絶対誤差（円/kWh）")
ax4.set_ylabel("コマ数")
ax4.set_title("絶対誤差の分布", fontsize=11)
ax4.legend(fontsize=9)
ax4.grid(axis="y", alpha=0.4)

plt.tight_layout(rect=[0, 0, 1, 0.97])
plt.savefig("prediction_analysis_v3.png", dpi=150, bbox_inches="tight")
print("保存完了: prediction_analysis_v3.png")
