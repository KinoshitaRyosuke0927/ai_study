"""
https://www.kaggle.com/competitions/rossmann-store-sales/overview
Rossmann Store Sales - v2
baseline からの変更点:
  1. 店舗別統計量の追加（Store × DoW / Month / Promo の平均 Sales）
       - 特徴量重要度で Store が split 1 位 → 暗黙的に学習していた店舗差を明示的な特徴量として渡す
       - 時系列リークを防ぐため、バリデーション用統計は学習折のデータのみから計算する
  2. num_boost_round を 3000 → 8000（best_iteration=2998 で上限到達していたため）
"""
import pandas as pd
import numpy as np
from pathlib import Path
import lightgbm as lgb

DATA_DIR   = Path(__file__).parent.parent / "competitions" / "rossmann-store-sales"
OUTPUT_DIR = Path(__file__).parent
OUTPUT_DIR.mkdir(exist_ok=True)

# ── 評価指標 ────────────────────────────────────────────────────
def rmspe(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    mask = y_true != 0
    return np.sqrt(np.mean(((y_true[mask] - y_pred[mask]) / y_true[mask]) ** 2))

def rmspe_lgbm(preds: np.ndarray, train_data: lgb.Dataset):
    y_true = np.expm1(train_data.get_label())
    y_pred = np.expm1(preds)
    return "RMSPE", rmspe(y_true, y_pred), False

# ── データ読み込み ───────────────────────────────────────────────
print("=" * 60)
print("データ読み込み & 前処理")
print("=" * 60)

train = pd.read_csv(DATA_DIR / "train.csv", low_memory=False, parse_dates=["Date"])
test  = pd.read_csv(DATA_DIR / "test.csv",  low_memory=False, parse_dates=["Date"])
store = pd.read_csv(DATA_DIR / "store.csv")

train = train.merge(store, on="Store", how="left")
test  = test.merge(store,  on="Store", how="left")

test["Open"] = test["Open"].fillna(1).astype(int)
train["StateHoliday"] = train["StateHoliday"].astype(str).replace({"0": "none"})
test["StateHoliday"]  = test["StateHoliday"].astype(str).replace({"0": "none"})

print(f"train: {train.shape}  test: {test.shape}")

# ── 特徴量エンジニアリング（ベースラインと同一） ─────────────────
MONTH_MAP = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May",  6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Year"]         = df["Date"].dt.year
    df["Month"]        = df["Date"].dt.month
    df["Day"]          = df["Date"].dt.day
    df["WeekOfYear"]   = df["Date"].dt.isocalendar().week.astype(int)
    df["IsWeekend"]    = (df["DayOfWeek"] >= 6).astype(int)
    df["IsMonthStart"] = (df["Day"] <= 5).astype(int)
    df["IsMonthEnd"]   = (df["Day"] >= 25).astype(int)

    comp_since_year  = df["CompetitionOpenSinceYear"].fillna(1900)
    comp_since_month = df["CompetitionOpenSinceMonth"].fillna(1)
    df["CompetitionOpen"] = (
        12 * (df["Year"] - comp_since_year) + (df["Month"] - comp_since_month)
    ).clip(lower=0)

    df["CompetitionDistance"]    = df["CompetitionDistance"].fillna(200_000)
    df["LogCompetitionDistance"] = np.log1p(df["CompetitionDistance"])

    df["MonthStr"]     = df["Month"].map(MONTH_MAP)
    df["Promo2Active"] = 0
    promo2_mask = df["Promo2"] == 1
    df.loc[promo2_mask, "Promo2Active"] = [
        1 if isinstance(interval, str) and month_str in interval else 0
        for interval, month_str in zip(
            df.loc[promo2_mask, "PromoInterval"],
            df.loc[promo2_mask, "MonthStr"],
        )
    ]

    p2_year = df["Promo2SinceYear"].fillna(df["Year"])
    p2_week = df["Promo2SinceWeek"].fillna(0)
    df["Promo2OpenWeeks"] = (
        52 * (df["Year"] - p2_year) + (df["WeekOfYear"] - p2_week)
    ).clip(lower=0)

    return df

print("特徴量エンジニアリング（ベース）中...")
train = build_features(train)
test  = build_features(test)

# ── 学習データの準備 ─────────────────────────────────────────────
train_open = train[train["Open"] == 1].copy()
train_open = train_open[train_open["Sales"] > 0].copy()
train_open["LogSales"] = np.log1p(train_open["Sales"])

VAL_START = pd.Timestamp("2015-06-20")
tr_fold   = train_open[train_open["Date"] <  VAL_START].copy()
val_fold  = train_open[train_open["Date"] >= VAL_START].copy()

print(f"\n=== 時系列 Hold-out CV ===")
print(f"  学習: {tr_fold['Date'].min().date()} ~ {tr_fold['Date'].max().date()}  ({len(tr_fold):,} 行)")
print(f"  検証: {val_fold['Date'].min().date()} ~ {val_fold['Date'].max().date()}  ({len(val_fold):,} 行)")

# ── 店舗別統計量（リークなし） ───────────────────────────────────
def add_store_stats(target: pd.DataFrame, ref: pd.DataFrame) -> pd.DataFrame:
    """
    ref（学習折）から統計量を計算して target にマッピングする。
    統計量を計算するデータを ref に限定することでバリデーション/テストへの
    情報リークを防いでいる。
    """
    target = target.copy()

    # Store 単体: 平均・中央値・標準偏差
    store_agg = ref.groupby("Store")["Sales"].agg(
        store_mean="mean", store_median="median", store_std="std"
    ).reset_index()
    target = target.merge(store_agg, on="Store", how="left")

    # Store × DayOfWeek: 曜日ごとの店舗平均（週パターンの個性）
    dow_mean = (
        ref.groupby(["Store", "DayOfWeek"])["Sales"].mean()
        .reset_index().rename(columns={"Sales": "store_dow_mean"})
    )
    target = target.merge(dow_mean, on=["Store", "DayOfWeek"], how="left")

    # Store × Month: 月ごとの店舗平均（季節パターンの個性）
    month_mean = (
        ref.groupby(["Store", "Month"])["Sales"].mean()
        .reset_index().rename(columns={"Sales": "store_month_mean"})
    )
    target = target.merge(month_mean, on=["Store", "Month"], how="left")

    # Store × Promo: プロモ有無別の店舗平均（プロモ感応度の個性）
    promo_mean = (
        ref.groupby(["Store", "Promo"])["Sales"].mean()
        .reset_index().rename(columns={"Sales": "store_promo_mean"})
    )
    target = target.merge(promo_mean, on=["Store", "Promo"], how="left")

    # 欠損補完: 組み合わせが存在しない場合は店舗全体平均で補完
    for col in ["store_dow_mean", "store_month_mean", "store_promo_mean"]:
        null_mask = target[col].isnull()
        if null_mask.any():
            target.loc[null_mask, col] = target.loc[null_mask, "store_mean"]

    return target

print("\n店舗別統計量を計算・追加中...")

# バリデーション用: tr_fold から統計を計算（リークなし）
tr_fold  = add_store_stats(tr_fold,  ref=tr_fold)
val_fold = add_store_stats(val_fold, ref=tr_fold)

# テスト用: train_open 全体から統計を計算
train_open = add_store_stats(train_open, ref=train_open)
test_with_stats = add_store_stats(test, ref=train_open)

# 統計量の概要をログ出力
print("\n=== 追加した店舗別統計量の概要（train_open 基準） ===")
store_agg_full = train_open.groupby("Store")["Sales"].agg(["mean","std"]).describe()
print(f"  Store 平均 Sales の分布:\n{store_agg_full.round(0).to_string()}")

STAT_COLS = ["store_mean", "store_median", "store_std",
             "store_dow_mean", "store_month_mean", "store_promo_mean"]
print(f"\n  追加した統計特徴量: {STAT_COLS}")

# ── 特徴量リスト ─────────────────────────────────────────────────
FEATURES = [
    # 店舗属性
    "Store", "StoreType", "Assortment",
    # 日付
    "DayOfWeek", "Year", "Month", "Day", "WeekOfYear",
    "IsWeekend", "IsMonthStart", "IsMonthEnd",
    # プロモーション
    "Promo", "Promo2", "Promo2Active", "Promo2OpenWeeks",
    # 祝日・休暇
    "StateHoliday", "SchoolHoliday",
    # 競合
    "LogCompetitionDistance", "CompetitionOpen",
    # 【新規】店舗別統計量
    "store_mean", "store_median", "store_std",
    "store_dow_mean", "store_month_mean", "store_promo_mean",
]

CAT_COLS = ["StoreType", "Assortment", "StateHoliday"]
TARGET   = "LogSales"

for col in CAT_COLS:
    for df in [tr_fold, val_fold, train_open, test_with_stats]:
        df[col] = df[col].astype("category")

print(f"\n使用特徴量: {len(FEATURES)} 個（ベース 19 → v2 {len(FEATURES)}）")
print(f"  うち新規統計量: {len(STAT_COLS)} 個")

# ── LightGBM 学習 ────────────────────────────────────────────────
LGBM_PARAMS = {
    "objective":         "regression",
    "metric":            "rmse",
    "verbose":           -1,
    "seed":              42,
    "learning_rate":     0.05,
    "num_leaves":        127,
    "min_child_samples": 20,
    "feature_fraction":  0.8,
    "bagging_fraction":  0.8,
    "bagging_freq":      5,
    "lambda_l1":         0.1,
    "lambda_l2":         0.1,
}

NUM_BOOST_ROUND = 8000  # 3000 → 8000: best_iteration=2998 で上限到達していたため拡張

dtrain = lgb.Dataset(tr_fold[FEATURES],  label=tr_fold[TARGET],  categorical_feature=CAT_COLS)
dval   = lgb.Dataset(val_fold[FEATURES], label=val_fold[TARGET], categorical_feature=CAT_COLS,
                     reference=dtrain)

print(f"\nLightGBM 学習中（num_boost_round={NUM_BOOST_ROUND}）...")
model = lgb.train(
    LGBM_PARAMS,
    dtrain,
    num_boost_round=NUM_BOOST_ROUND,
    valid_sets=[dtrain, dval],
    valid_names=["train", "valid"],
    feval=rmspe_lgbm,
    callbacks=[
        lgb.early_stopping(stopping_rounds=200, verbose=False),
        lgb.log_evaluation(period=500),
    ],
)

# ── バリデーションスコア ─────────────────────────────────────────
val_pred  = np.expm1(model.predict(val_fold[FEATURES]))
val_true  = np.expm1(val_fold[TARGET].values)
val_rmspe = rmspe(val_true, val_pred)

tr_pred   = np.expm1(model.predict(tr_fold[FEATURES]))
tr_true   = np.expm1(tr_fold[TARGET].values)
tr_rmspe  = rmspe(tr_true, tr_pred)

print(f"\n=== バリデーション結果 ===")
print(f"  best_iteration      : {model.best_iteration}")
print(f"  RMSPE (train)       : {tr_rmspe:.5f}  (baseline: 0.11180)")
print(f"  RMSPE (valid)       : {val_rmspe:.5f}  (baseline: 0.13670)")
print(f"  差分 (過学習度)     : {val_rmspe - tr_rmspe:+.5f}")
print(f"  改善幅 (vs baseline): {val_rmspe - 0.13670:+.5f}")

# ── 特徴量重要度 ─────────────────────────────────────────────────
print(f"\n=== 特徴量重要度 TOP {len(FEATURES)}（gain） ===")
imp = pd.Series(
    model.feature_importance(importance_type="gain"),
    index=FEATURES,
).sort_values(ascending=False)
max_val = imp.max()
for feat, val in imp.items():
    bar = "█" * max(1, int(val / max_val * 30))
    print(f"  {feat:35s}: {val:12.0f}  {bar}")

print(f"\n=== 新規統計量の重要度確認 ===")
for col in STAT_COLS:
    gain  = imp.get(col, 0)
    print(f"  {col:35s}: gain={gain:10.0f}")

# ── 全データで再学習 ─────────────────────────────────────────────
print(f"\n全データで再学習中（num_boost_round={model.best_iteration}）...")
dtrain_full = lgb.Dataset(
    train_open[FEATURES], label=train_open[TARGET],
    categorical_feature=CAT_COLS,
)
model_full = lgb.train(
    LGBM_PARAMS,
    dtrain_full,
    num_boost_round=model.best_iteration,
)

# ── テスト予測 ───────────────────────────────────────────────────
test_pred = np.expm1(model_full.predict(test_with_stats[FEATURES]))
test_pred = np.clip(test_pred, 0, None)
test_pred[test["Open"] == 0] = 0

# ── 提出ファイル ─────────────────────────────────────────────────
submission = pd.DataFrame({"Id": test["Id"], "Sales": test_pred})
out_path   = OUTPUT_DIR / "submission_v2.csv"
submission.to_csv(out_path, index=False)

print(f"\n=== 提出ファイル ===")
print(f"  保存先: {out_path}")
print(f"  行数  : {len(submission):,}")

print(f"\n=== 予測値の統計（Open=1 のみ） ===")
pred_open = test_pred[test["Open"] == 1]
print(f"  mean   : {pred_open.mean():,.1f}")
print(f"  median : {np.median(pred_open):,.1f}")
print(f"  std    : {pred_open.std():,.1f}")
print(f"  min    : {pred_open.min():,.1f}")
print(f"  max    : {pred_open.max():,.1f}")

print(f"\n=== スコアまとめ ===")
print(f"  v1 baseline RMSPE (valid): 0.13670  Kaggle LB: 0.12846")
print(f"  v2 今回    RMSPE (valid): {val_rmspe:.5f}  改善幅: {val_rmspe - 0.13670:+.5f}")
print(f"  ※ Kaggle LB はこの後提出して確認")
