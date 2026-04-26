import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
from pathlib import Path
from lightgbm import LGBMRegressor
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.preprocessing import LabelEncoder
from matplotlib.patches import Patch

matplotlib.rcParams["font.family"] = "MS Gothic"
plt.rcParams["figure.facecolor"] = "white"

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

print(f"train: {len(train):,} 行")

# 計算時間を抑えるため直近2年（約120万行）を使用
train = train[train["date"] >= "2016-01-01"].copy()
print(f"直近2年に絞り込み: {len(train):,} 行  ({train['date'].min().date()} ~ {train['date'].max().date()})")

# ==============================================================
# ステップ1: 特徴量エンジニアリング（全候補を一括生成）
# ==============================================================
print("\n--- ステップ1: 特徴量エンジニアリング ---")

# ---- 日付特徴量 ----
train["year"]           = train["date"].dt.year
train["month"]          = train["date"].dt.month
train["day"]            = train["date"].dt.day
train["dayofweek"]      = train["date"].dt.dayofweek
train["dayofyear"]      = train["date"].dt.dayofyear
train["weekofyear"]     = train["date"].dt.isocalendar().week.astype(int)
train["is_weekend"]     = (train["dayofweek"] >= 5).astype(int)
train["is_month_start"] = (train["day"] == 1).astype(int)
train["days_in_month"]  = train["date"].dt.days_in_month
# 給料日: 15日と月末（エクアドル公務員の給与支給日）
train["is_salary_day"]  = (
    (train["day"] == 15) | (train["day"] == train["days_in_month"])
).astype(int)

# ---- 店舗特徴量（stores.csv） ----
le = LabelEncoder()
for col in ["city", "state", "type"]:
    stores[col + "_enc"] = le.fit_transform(stores[col])

train = train.merge(
    stores[["store_nbr", "type_enc", "cluster", "city_enc", "state_enc"]],
    on="store_nbr", how="left"
)

# ---- 商品カテゴリ特徴量 ----
train["family_enc"] = le.fit_transform(train["family"])

# ---- 原油価格特徴量（oil.csv） ----
# 週末・祝日は市場休場のため時系列補間
oil_full = (
    pd.date_range(oil["date"].min(), oil["date"].max(), freq="D")
    .to_frame(name="date")
    .merge(oil, on="date", how="left")
)
oil_full["oil_price"]    = oil_full["dcoilwtico"].interpolate(method="linear")
oil_full["oil_change_7d"] = oil_full["oil_price"].diff(7)

train = train.merge(oil_full[["date", "oil_price", "oil_change_7d"]], on="date", how="left")

# ---- 祝日特徴量（holidays_events.csv） ----
# 振替祝日(transferred=True)は実質平日なので除外
hol = holidays[holidays["transferred"] == False].copy()

# 全国祝日フラグ
national_hol = hol[hol["locale"] == "National"][["date", "type"]].drop_duplicates("date")
national_hol.columns = ["date", "holiday_type"]
train = train.merge(national_hol, on="date", how="left")
train["is_national_holiday"] = train["holiday_type"].notna().astype(int)
train["holiday_type_enc"]    = le.fit_transform(train["holiday_type"].fillna("None"))

# 地域・ローカル祝日: 店舗の state/city と照合
state_map = stores.set_index("store_nbr")["state"].to_dict()
city_map  = stores.set_index("store_nbr")["city"].to_dict()
train["store_state"] = train["store_nbr"].map(state_map)
train["store_city"]  = train["store_nbr"].map(city_map)

regional_hol = hol[hol["locale"] == "Regional"][["date", "locale_name"]].drop_duplicates()
local_hol    = hol[hol["locale"] == "Local"][["date", "locale_name"]].drop_duplicates()

regional_set = set(zip(regional_hol["date"], regional_hol["locale_name"]))
local_set    = set(zip(local_hol["date"],    local_hol["locale_name"]))

train["is_regional_holiday"] = [
    1 if (d, s) in regional_set else 0
    for d, s in zip(train["date"], train["store_state"])
]
train["is_local_holiday"] = [
    1 if (d, c) in local_set else 0
    for d, c in zip(train["date"], train["store_city"])
]

# ---- プロモーション特徴量 ----
train["has_promo"] = (train["onpromotion"] > 0).astype(int)

# ---- 取引件数（transactions.csv）: 7日前のラグで使用（データリーク防止）----
# transactions をそのまま使うと「その日の来客数で売上を予測」になりリークする
# 7日前の値にシフトして過去情報として使う
trans_lag = transactions.copy()
trans_lag["date"] = trans_lag["date"] + pd.Timedelta(days=7)
trans_lag = trans_lag.rename(columns={"transactions": "transactions_lag7"})
train = train.merge(trans_lag[["date", "store_nbr", "transactions_lag7"]],
                    on=["date", "store_nbr"], how="left")

print("特徴量エンジニアリング完了")

# ==============================================================
# 特徴量グループ定義
# ==============================================================
ALL_FEATURES = {
    "日付":         ["year", "month", "day", "dayofweek", "dayofyear",
                     "weekofyear", "is_weekend", "is_month_start", "is_salary_day"],
    "店舗":         ["store_nbr", "type_enc", "cluster", "city_enc", "state_enc"],
    "商品":         ["family_enc", "onpromotion", "has_promo"],
    "原油":         ["oil_price", "oil_change_7d"],
    "祝日":         ["is_national_holiday", "holiday_type_enc",
                     "is_regional_holiday", "is_local_holiday"],
    "取引件数(ラグ)": ["transactions_lag7"],
}
COLORS_MAP = {
    "日付":          "#5B9BD5",
    "店舗":          "#ED7D31",
    "商品":          "#A9D18E",
    "原油":          "#FFC000",
    "祝日":          "#9E80B8",
    "取引件数(ラグ)":  "#E74C3C",
}

ALL_FEAT_LIST = [f for feats in ALL_FEATURES.values() for f in feats]
feat_to_group = {f: g for g, feats in ALL_FEATURES.items() for f in feats}

TARGET = "sales_log"
train["sales_log"] = np.log1p(train["sales"])

for col in ALL_FEAT_LIST:
    if train[col].dtype in [np.float64, np.float32]:
        train[col] = train[col].fillna(train[col].median())
    else:
        train[col] = train[col].fillna(0)

X = train[ALL_FEAT_LIST].copy()
y = train[TARGET].copy()

print(f"\n候補特徴量数: {len(ALL_FEAT_LIST)}")
for group, feats in ALL_FEATURES.items():
    print(f"  [{group}] {feats}")

# ==============================================================
# ステップ2: 全特徴量で LightGBM + TimeSeriesSplit CV
# ==============================================================
print("\n--- ステップ2: 全特徴量で LightGBM + TimeSeriesSplit CV ---")
print("時系列CVの仕組み:")
print("  fold1: [学習] → [検証]")
print("  fold2: [学習 学習] → [検証]")
print("  fold3: [学習 学習 学習] → [検証]")
print("  → 未来のデータで過去を学習しない正しい評価方法")

tscv = TimeSeriesSplit(n_splits=5)

model_base = LGBMRegressor(
    n_estimators=300, learning_rate=0.05,
    num_leaves=31, random_state=42, verbosity=-1, n_jobs=-1,
)

scores_all = cross_val_score(
    model_base, X, y, cv=tscv,
    scoring="neg_root_mean_squared_error"
)
rmse_all = -scores_all.mean()
print(f"\n全特徴量({len(ALL_FEAT_LIST)}個) CV RMSE: {rmse_all:.4f}  (std={-scores_all.std():.4f})")

# ==============================================================
# ステップ3: Feature Importance の可視化
# ==============================================================
print("\n--- ステップ3: Feature Importance 計算・可視化 ---")

model_base.fit(X, y)
importances = pd.Series(model_base.feature_importances_, index=ALL_FEAT_LIST).sort_values(ascending=True)

bar_colors = [COLORS_MAP[feat_to_group[f]] for f in importances.index]
legend_els = [Patch(facecolor=c, label=g) for g, c in COLORS_MAP.items()]

fig, ax = plt.subplots(figsize=(10, 8))
ax.barh(importances.index, importances.values, color=bar_colors)
ax.set_title(f"Feature Importance（全{len(ALL_FEAT_LIST)}特徴量）\nCV RMSE={rmse_all:.4f}", fontsize=13)
ax.set_xlabel("Importance（ツリーの分岐への寄与回数）")
ax.legend(handles=legend_els, loc="lower right", fontsize=9)
plt.tight_layout()
plt.savefig(OUT_DIR / "fs_01_feature_importance_all.png", dpi=100)
plt.show()

print("\n重要度ランキング（降順）:")
for f, v in importances.sort_values(ascending=False).items():
    print(f"  [{feat_to_group[f]:12s}] {f:25s}: {v}")

# ==============================================================
# ステップ4: 重要度の低い特徴量を段階的に除外してCV RMSE を比較
# ==============================================================
print("\n--- ステップ4: 段階的な特徴量除外とCVスコア比較 ---")

sorted_feats  = importances.sort_values(ascending=False).index.tolist()
removal_rates = [0, 20, 40, 60, 80]
results       = []

for rate in removal_rates:
    n_keep = max(1, int(len(sorted_feats) * (1 - rate / 100)))
    kept   = sorted_feats[:n_keep]
    scores = cross_val_score(
        LGBMRegressor(n_estimators=300, learning_rate=0.05,
                      num_leaves=31, random_state=42, verbosity=-1, n_jobs=-1),
        X[kept], y, cv=tscv, scoring="neg_root_mean_squared_error"
    )
    rmse = -scores.mean()
    std  = -scores.std()
    results.append({"除外率": f"{rate}%", "残特徴量数": n_keep,
                    "残特徴量": kept, "CV RMSE": rmse, "std": std})
    mark = " ← ベースライン" if rate == 0 else ""
    print(f"  除外率 {rate:2d}%（残 {n_keep:2d}特徴量）: CV RMSE={rmse:.4f} (±{std:.4f}){mark}")

result_df = pd.DataFrame(results)

fig, axes = plt.subplots(1, 2, figsize=(13, 5))
fig.suptitle("ステップ4: 特徴量の段階的除外による CV RMSE の変化", fontsize=13)

xs = range(len(result_df))
axes[0].plot(xs, result_df["CV RMSE"], marker="o", markersize=8,
             color="#5B9BD5", linewidth=2)
axes[0].fill_between(xs,
    result_df["CV RMSE"] - result_df["std"],
    result_df["CV RMSE"] + result_df["std"],
    alpha=0.2, color="#5B9BD5")
axes[0].set_title("除外率 vs CV RMSE（低いほど良い）")
axes[0].set_xlabel("除外率")
axes[0].set_ylabel("CV RMSE")
axes[0].set_xticks(xs)
axes[0].set_xticklabels(result_df["除外率"])
for i, row in result_df.iterrows():
    axes[0].annotate(f"{row['CV RMSE']:.4f}", (i, row["CV RMSE"]),
                     textcoords="offset points", xytext=(0, 10), ha="center", fontsize=9)

axes[1].bar(result_df["除外率"], result_df["残特徴量数"], color="#ED7D31")
axes[1].set_title("除外率 vs 残特徴量数")
axes[1].set_xlabel("除外率")
axes[1].set_ylabel("残特徴量数")
for i, row in result_df.iterrows():
    axes[1].text(i, row["残特徴量数"] + 0.1, str(row["残特徴量数"]),
                 ha="center", fontweight="bold")

plt.tight_layout()
plt.savefig(OUT_DIR / "fs_02_removal_comparison.png", dpi=100)
plt.show()

# ==============================================================
# ステップ5: 最適な特徴量セットの決定と最終出力
# ==============================================================
print("\n--- ステップ5: 最適な特徴量セットの決定 ---")

best_result = result_df.loc[result_df["CV RMSE"].idxmin()]
best_feats  = best_result["残特徴量"]
best_rmse   = best_result["CV RMSE"]
best_rate   = best_result["除外率"]

model_best = LGBMRegressor(
    n_estimators=300, learning_rate=0.05,
    num_leaves=31, random_state=42, verbosity=-1, n_jobs=-1,
)
model_best.fit(X[best_feats], y)
imp_best       = pd.Series(model_best.feature_importances_, index=best_feats).sort_values(ascending=True)
bc_best        = [COLORS_MAP[feat_to_group[f]] for f in imp_best.index]
legend_els_best = [Patch(facecolor=c, label=g) for g, c in COLORS_MAP.items()
                   if g in {feat_to_group[f] for f in best_feats}]

fig, ax = plt.subplots(figsize=(10, max(5, len(best_feats) * 0.45)))
ax.barh(imp_best.index, imp_best.values, color=bc_best)
ax.set_title(f"Feature Importance（採用特徴量 {len(best_feats)}個）\nCV RMSE={best_rmse:.4f}", fontsize=13)
ax.set_xlabel("Importance（ツリーの分岐への寄与回数）")
ax.legend(handles=legend_els_best, loc="lower right", fontsize=9)
plt.tight_layout()
plt.savefig(OUT_DIR / "fs_03_feature_importance_final.png", dpi=100)
plt.show()

# ==============================================================
# サマリー
# ==============================================================
print("\n" + "=" * 60)
print("特徴量選択サマリー")
print("=" * 60)
print(f"\n候補特徴量数:      {len(ALL_FEAT_LIST)}")
print(f"採用特徴量数:      {len(best_feats)}")
print(f"全特徴量 CV RMSE: {rmse_all:.4f}")
print(f"最良    CV RMSE: {best_rmse:.4f}  （除外率 {best_rate}）")
print(f"改善量:           {rmse_all - best_rmse:.4f}")
print()
print("--- 段階的除外の結果 ---")
print(result_df[["除外率", "残特徴量数", "CV RMSE"]].to_string(index=False))
print()
print("--- 採用特徴量（重要度順） ---")
for f in imp_best.sort_values(ascending=False).index:
    print(f"  [{feat_to_group[f]:12s}] {f}")
print()
print("グラフ保存先:")
print("  fs_01_feature_importance_all.png   全特徴量のImportance")
print("  fs_02_removal_comparison.png       段階的除外のRMSE比較")
print("  fs_03_feature_importance_final.png 採用特徴量のImportance")
