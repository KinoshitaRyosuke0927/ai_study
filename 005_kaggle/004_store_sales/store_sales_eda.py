import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
from pathlib import Path

matplotlib.rcParams['font.family'] = 'MS Gothic'
plt.rcParams['figure.facecolor'] = 'white'

DATA_DIR = Path(r"C:\azure_ai\education\005_kaggle\competitions\store-sales-time-series-forecasting")
OUT_DIR  = DATA_DIR

# ==============================================================
# データ読み込み
# ==============================================================
train        = pd.read_csv(DATA_DIR / "train.csv",           parse_dates=["date"])
stores       = pd.read_csv(DATA_DIR / "stores.csv")
oil          = pd.read_csv(DATA_DIR / "oil.csv",             parse_dates=["date"])
holidays     = pd.read_csv(DATA_DIR / "holidays_events.csv", parse_dates=["date"])
transactions = pd.read_csv(DATA_DIR / "transactions.csv",    parse_dates=["date"])

train["sales_log"] = np.log1p(train["sales"])
train["year"]      = train["date"].dt.year
train["month"]     = train["date"].dt.month
train["dayofweek"] = train["date"].dt.dayofweek
train["day"]       = train["date"].dt.day

print("=== データ読み込み完了 ===")
print(f"train: {len(train):,} 行  期間: {train['date'].min().date()} ~ {train['date'].max().date()}")

# ==============================================================
# 1. 売上の全体分布
# ==============================================================
fig, axes = plt.subplots(1, 2, figsize=(13, 5))
fig.suptitle("1. 売上の全体分布", fontsize=13)

axes[0].hist(train["sales"], bins=100, color="#5B9BD5", edgecolor="none")
axes[0].set_title("元スケール")
axes[0].set_xlabel("sales")
axes[0].set_ylabel("件数")

axes[1].hist(train["sales_log"], bins=100, color="#ED7D31", edgecolor="none")
axes[1].set_title("log1p 変換後")
axes[1].set_xlabel("log1p(sales)")
axes[1].set_ylabel("件数")

plt.tight_layout()
plt.savefig(OUT_DIR / "eda_01_sales_dist.png", dpi=100)
plt.show()

zero_pct = (train["sales"] == 0).mean() * 100
print(f"\n[1] 売上=0 の割合: {zero_pct:.1f}%")

# ==============================================================
# 2. 時系列トレンド（全店舗合計）
# ==============================================================
daily   = train.groupby("date")["sales"].sum().reset_index()
monthly = daily.set_index("date").resample("ME")["sales"].mean()

fig, axes = plt.subplots(2, 1, figsize=(15, 8))
fig.suptitle("2. 全店舗合計の日次売上トレンド", fontsize=13)

axes[0].plot(daily["date"], daily["sales"], linewidth=0.6, color="#5B9BD5")
axes[0].set_title("日次売上（全期間）")
axes[0].set_ylabel("合計売上")

axes[1].plot(monthly.index, monthly.values, marker="o", markersize=4, color="#ED7D31")
axes[1].set_title("月次平均売上（トレンド確認）")
axes[1].set_ylabel("月次平均売上")

plt.tight_layout()
plt.savefig(OUT_DIR / "eda_02_trend.png", dpi=100)
plt.show()

print("\n[2] 年次平均売上:")
print(train.groupby("year")["sales"].mean().round(2).to_string())

# ==============================================================
# 3. 季節性（曜日・月）
# ==============================================================
dow_sales = train.groupby("dayofweek")["sales"].mean()
mon_sales = train.groupby("month")["sales"].mean()

fig, axes = plt.subplots(1, 2, figsize=(13, 5))
fig.suptitle("3. 季節性（曜日・月別の平均売上）", fontsize=13)

dow_labels = ["月", "火", "水", "木", "金", "土", "日"]
axes[0].bar(dow_labels, dow_sales.values, color="#5B9BD5")
axes[0].set_title("曜日別平均売上")
axes[0].set_ylabel("平均売上")

axes[1].bar(range(1, 13), mon_sales.values, color="#ED7D31")
axes[1].set_title("月別平均売上")
axes[1].set_xlabel("月")
axes[1].set_ylabel("平均売上")
axes[1].set_xticks(range(1, 13))

plt.tight_layout()
plt.savefig(OUT_DIR / "eda_03_seasonality.png", dpi=100)
plt.show()

print("\n[3] 曜日別平均売上（0=月曜）:")
print(dow_sales.round(2).to_string())

# ==============================================================
# 4. 商品カテゴリ（family）別の売上
# ==============================================================
family_stats = (
    train.groupby("family")["sales"]
    .agg(["mean", "std"])
    .sort_values("mean", ascending=True)
)

fig, axes = plt.subplots(1, 2, figsize=(14, 9))
fig.suptitle("4. 商品カテゴリ（family）別の売上", fontsize=13)

axes[0].barh(family_stats.index, family_stats["mean"], color="#5B9BD5")
axes[0].set_title("カテゴリ別平均売上")
axes[0].set_xlabel("平均売上")

axes[1].barh(family_stats.index, family_stats["std"], color="#ED7D31")
axes[1].set_title("カテゴリ別売上の標準偏差（ばらつき）")
axes[1].set_xlabel("標準偏差")

plt.tight_layout()
plt.savefig(OUT_DIR / "eda_04_family.png", dpi=100)
plt.show()

print("\n[4] 商品カテゴリ別平均売上（上位10）:")
print(family_stats["mean"].sort_values(ascending=False).head(10).round(2).to_string())

# ==============================================================
# 5. 店舗タイプ・クラスター別の売上
# ==============================================================
train_stores  = train.merge(stores, on="store_nbr")
type_sales    = train_stores.groupby("type")["sales"].mean().sort_values(ascending=False)
cluster_sales = train_stores.groupby("cluster")["sales"].mean().sort_values(ascending=False)

fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle("5. 店舗タイプ・クラスター別の平均売上", fontsize=13)

bars = axes[0].bar(type_sales.index, type_sales.values, color="#5B9BD5")
axes[0].set_title("店舗タイプ別（A〜E）")
axes[0].set_ylabel("平均売上")
axes[0].axhline(train["sales"].mean(), color="red", linestyle="--", linewidth=1, label="全体平均")
axes[0].legend()
for bar, v in zip(bars, type_sales.values):
    axes[0].text(bar.get_x() + bar.get_width()/2, v + 1, f"{v:.1f}", ha="center", fontsize=9)

axes[1].bar(cluster_sales.index.astype(str), cluster_sales.values, color="#ED7D31")
axes[1].set_title("クラスター別（1〜17）")
axes[1].set_ylabel("平均売上")
axes[1].set_xlabel("cluster")
axes[1].axhline(train["sales"].mean(), color="red", linestyle="--", linewidth=1, label="全体平均")
axes[1].legend()

plt.tight_layout()
plt.savefig(OUT_DIR / "eda_05_store_type.png", dpi=100)
plt.show()

print("\n[5] 店舗タイプ別平均売上:")
print(type_sales.round(2).to_string())

# ==============================================================
# 6. プロモーション（onpromotion）と売上の関係
# ==============================================================
train["has_promo"] = (train["onpromotion"] > 0).astype(int)
promo_effect = train.groupby("has_promo")["sales"].mean()
sample = train[train["sales"] > 0].sample(5000, random_state=42)

fig, axes = plt.subplots(1, 2, figsize=(13, 5))
fig.suptitle("6. プロモーション（onpromotion）と売上の関係", fontsize=13)

axes[0].bar(["プロモなし", "プロモあり"], promo_effect.values, color=["#5B9BD5", "#ED7D31"])
axes[0].set_title("プロモーション有無別の平均売上")
axes[0].set_ylabel("平均売上")
for i, v in enumerate(promo_effect.values):
    axes[0].text(i, v + 1, f"{v:.1f}", ha="center", fontweight="bold")

axes[1].scatter(sample["onpromotion"], sample["sales_log"],
                alpha=0.3, s=5, color="#5B9BD5")
axes[1].set_title("プロモーション数 vs log1p(sales)（5,000件サンプル）")
axes[1].set_xlabel("onpromotion")
axes[1].set_ylabel("log1p(sales)")

plt.tight_layout()
plt.savefig(OUT_DIR / "eda_06_promotion.png", dpi=100)
plt.show()

promo_lift = (promo_effect[1] / promo_effect[0] - 1) * 100
print(f"\n[6] プロモーション効果（リフト）: +{promo_lift:.1f}%")

# ==============================================================
# 7. 原油価格（oil）と売上の関係
# ==============================================================
oil_filled = oil.set_index("date")["dcoilwtico"].interpolate(method="time").reset_index()
oil_filled.columns = ["date", "oil_price"]
daily_with_oil = daily.merge(oil_filled, on="date", how="left")

fig, axes = plt.subplots(2, 1, figsize=(15, 8))
fig.suptitle("7. 原油価格と全店舗合計売上の推移", fontsize=13)

ax1 = axes[0]
ax2 = ax1.twinx()
ax1.plot(daily_with_oil["date"], daily_with_oil["sales"],
         linewidth=0.6, color="#5B9BD5", label="売上（左軸）")
ax2.plot(daily_with_oil["date"], daily_with_oil["oil_price"],
         linewidth=1, color="#ED7D31", label="原油価格（右軸）", alpha=0.8)
ax1.set_ylabel("合計売上", color="#5B9BD5")
ax2.set_ylabel("原油価格（USD）", color="#ED7D31")
ax1.set_title("売上と原油価格の重ね合わせ")
lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

corr_df = daily_with_oil.dropna()
axes[1].scatter(corr_df["oil_price"], corr_df["sales"], alpha=0.3, s=8, color="#5B9BD5")
axes[1].set_title("原油価格 vs 合計売上（散布図）")
axes[1].set_xlabel("原油価格（USD）")
axes[1].set_ylabel("合計売上")

plt.tight_layout()
plt.savefig(OUT_DIR / "eda_07_oil.png", dpi=100)
plt.show()

oil_corr = corr_df[["oil_price", "sales"]].corr().iloc[0, 1]
print(f"\n[7] 原油価格と合計売上の相関係数: {oil_corr:.3f}")

# ==============================================================
# 8. 祝日・イベントと売上の関係
# ==============================================================
national_holidays = holidays[
    (holidays["locale"] == "National") &
    (holidays["transferred"] == False) &
    (holidays["type"].isin(["Holiday", "Event", "Additional"]))
][["date", "type"]].copy()

daily["is_holiday"] = daily["date"].isin(national_holidays["date"]).astype(int)
holiday_effect = daily.groupby("is_holiday")["sales"].mean()

type_merged = daily.merge(
    national_holidays.drop_duplicates("date"), on="date", how="left"
)
type_merged["type"] = type_merged["type"].fillna("通常日")
type_mean = type_merged.groupby("type")["sales"].mean().sort_values(ascending=False)

fig, axes = plt.subplots(1, 2, figsize=(13, 5))
fig.suptitle("8. 祝日・イベントと売上の関係（全国レベル）", fontsize=13)

axes[0].bar(["通常日", "祝日・イベント"], holiday_effect.values, color=["#5B9BD5", "#ED7D31"])
axes[0].set_title("祝日有無別の日次合計売上平均")
axes[0].set_ylabel("日次合計売上の平均")
for i, v in enumerate(holiday_effect.values):
    axes[0].text(i, v + 1000, f"{v:,.0f}", ha="center", fontweight="bold")

axes[1].bar(type_mean.index, type_mean.values, color="#5B9BD5")
axes[1].set_title("祝日タイプ別の日次合計売上平均")
axes[1].set_ylabel("日次合計売上の平均")
axes[1].axhline(daily["sales"].mean(), color="red", linestyle="--", linewidth=1, label="全体平均")
axes[1].legend()

plt.tight_layout()
plt.savefig(OUT_DIR / "eda_08_holiday.png", dpi=100)
plt.show()

holiday_lift = (holiday_effect[1] / holiday_effect[0] - 1) * 100
print(f"\n[8] 祝日効果（リフト）: {holiday_lift:+.1f}%")

# ==============================================================
# 9. 取引件数（transactions）と売上の関係
# ==============================================================
daily_trans  = transactions.groupby("date")["transactions"].sum().reset_index()
daily_merged = daily.merge(daily_trans, on="date", how="left")

store_corr = (
    train.merge(transactions, on=["date", "store_nbr"])
    .groupby("store_nbr")[["sales", "transactions"]]
    .corr().unstack()["sales"]["transactions"]
    .sort_values(ascending=True)
)

fig, axes = plt.subplots(1, 2, figsize=(13, 5))
fig.suptitle("9. 取引件数（transactions）と売上の関係", fontsize=13)

trans_corr = daily_merged[["transactions", "sales"]].corr().iloc[0, 1]
axes[0].scatter(daily_merged["transactions"], daily_merged["sales"],
                alpha=0.4, s=8, color="#5B9BD5")
axes[0].set_title("日次取引件数 vs 日次合計売上")
axes[0].set_xlabel("transactions（取引件数）")
axes[0].set_ylabel("sales（合計売上）")
axes[0].text(0.05, 0.92, f"相関係数: {trans_corr:.3f}",
             transform=axes[0].transAxes, fontsize=11,
             bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

axes[1].barh(store_corr.index.astype(str), store_corr.values, color="#ED7D31")
axes[1].set_title("店舗別：取引件数と売上の相関係数")
axes[1].set_xlabel("相関係数")
axes[1].set_ylabel("store_nbr")
axes[1].axvline(0.5, color="red", linestyle="--", linewidth=1)

plt.tight_layout()
plt.savefig(OUT_DIR / "eda_09_transactions.png", dpi=100)
plt.show()

print(f"\n[9] 取引件数と合計売上の相関係数: {trans_corr:.3f}")
print(f"    店舗別相関の中央値: {store_corr.median():.3f}")

# ==============================================================
# 10. 給料日（15日・月末）の売上への影響
# ==============================================================
train["days_in_month"] = train["date"].dt.days_in_month
train["is_salary_day"] = (
    (train["day"] == 15) | (train["day"] == train["days_in_month"])
).astype(int)

daily_sal     = train.groupby(["date", "is_salary_day"])["sales"].sum().reset_index()
salary_effect = daily_sal.groupby("is_salary_day")["sales"].mean()

fig, ax = plt.subplots(figsize=(8, 5))
ax.bar(["通常日", "給料日（15日・月末）"], salary_effect.values, color=["#5B9BD5", "#ED7D31"])
ax.set_title("10. 給料日（15日・月末）と売上の関係\nエクアドル公務員は15日・月末に給与支給", fontsize=12)
ax.set_ylabel("日次合計売上の平均")
for i, v in enumerate(salary_effect.values):
    ax.text(i, v + 1000, f"{v:,.0f}", ha="center", fontweight="bold")
ax.axhline(daily["sales"].mean(), color="red", linestyle="--", linewidth=1, label="全体平均")
ax.legend()

plt.tight_layout()
plt.savefig(OUT_DIR / "eda_10_payday.png", dpi=100)
plt.show()

salary_lift = (salary_effect[1] / salary_effect[0] - 1) * 100
print(f"\n[10] 給料日効果（リフト）: {salary_lift:+.1f}%")

# ==============================================================
# EDA サマリー
# ==============================================================
print("\n" + "=" * 60)
print("EDA サマリー：特徴量として使えそうな要素")
print("=" * 60)
print(f"売上=0 の割合:         {zero_pct:.1f}%  -> log1p 変換が有効")
print(f"プロモーション効果:     +{promo_lift:.1f}%  -> onpromotion は重要な特徴量")
print(f"原油価格との相関:       {oil_corr:.3f}       -> 補助特徴量として有効")
print(f"祝日効果:              {holiday_lift:+.1f}%  -> 祝日フラグは売上に影響")
print(f"取引件数との相関:       {trans_corr:.3f}       -> 強い正の相関（leak防止に注意）")
print(f"給料日効果:            {salary_lift:+.1f}%  -> 給料日フラグは有効")
