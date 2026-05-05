"""
https://www.kaggle.com/competitions/rossmann-store-sales/overview
Rossmann Store Sales - v5
v4(Optuna最適パラメータ) からの変更点:
  ① num_boost_round を 5000 → 10000 に増加
       v4 の best_iteration=4960 が上限 5000 にほぼ到達 → 学習途中で強制停止していた
       上限を広げて Early Stopping に委ねる

  ② Store × WeekOfYear 統計量を追加（2特徴量）
       v3 のラグ特徴量（lag_364）は NaN が 41.9% で失敗した
       週番号ごとの店舗別平均 Sales を使うことで「毎年この週は高い/低い」を
       NaN なしで安定的にキャプチャできる
         store_week_mean      : Store × WeekOfYear の平均 Sales
         store_week_promo_mean: Store × WeekOfYear × Promo の平均 Sales
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

# ── Optuna で見つけた最適パラメータ（v4 / Trial 31） ─────────────
BEST_PARAMS = {
    "objective":         "regression",
    "metric":            "rmse",
    "verbose":           -1,
    "seed":              42,
    "learning_rate":     0.025712018491695496,
    "num_leaves":        359,
    "min_child_samples": 146,
    "feature_fraction":  0.5623737166333678,
    "bagging_fraction":  0.9012873662882596,
    "bagging_freq":      5,
    "lambda_l1":         0.038529774921381765,
    "lambda_l2":         5.269302870224163,
    "min_split_gain":    0.0019331115902168428,
    "max_depth":         10,
}

NUM_BOOST_ROUND = 10000  # ① 5000 → 10000: best_iteration=4960 で上限到達していたため

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

# ── 特徴量エンジニアリング（v2/v4 と同一） ──────────────────────
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
    comp_since_year    = df["CompetitionOpenSinceYear"].fillna(1900)
    comp_since_month   = df["CompetitionOpenSinceMonth"].fillna(1)
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

# ── 店舗別統計量（v2 と同一） ────────────────────────────────────
def add_store_stats(target: pd.DataFrame, ref: pd.DataFrame) -> pd.DataFrame:
    target = target.copy()
    store_agg = ref.groupby("Store")["Sales"].agg(
        store_mean="mean", store_median="median", store_std="std"
    ).reset_index()
    target = target.merge(store_agg, on="Store", how="left")
    for key_cols, col_name in [
        (["Store", "DayOfWeek"], "store_dow_mean"),
        (["Store", "Month"],     "store_month_mean"),
        (["Store", "Promo"],     "store_promo_mean"),
    ]:
        grp = (
            ref.groupby(key_cols)["Sales"].mean()
            .reset_index().rename(columns={"Sales": col_name})
        )
        target = target.merge(grp, on=key_cols, how="left")
        null_mask = target[col_name].isnull()
        if null_mask.any():
            target.loc[null_mask, col_name] = target.loc[null_mask, "store_mean"]
    return target

# ── 【②新規】週別統計量 ──────────────────────────────────────────
def add_week_stats(target: pd.DataFrame, ref: pd.DataFrame) -> pd.DataFrame:
    """
    ref から Store × WeekOfYear の統計量を計算して target に付与する。
    ラグ特徴量（lag_364）の代替: NaN が発生しない安定した特徴量。

    store_week_mean      : 店舗 × 週番号の平均 Sales（毎年この週の傾向）
    store_week_promo_mean: 店舗 × 週番号 × Promo の平均 Sales（週 × プロモの組み合わせ）
    """
    target = target.copy()

    # Store × WeekOfYear 平均
    week_mean = (
        ref.groupby(["Store", "WeekOfYear"])["Sales"].mean()
        .reset_index().rename(columns={"Sales": "store_week_mean"})
    )
    target = target.merge(week_mean, on=["Store", "WeekOfYear"], how="left")

    # Store × WeekOfYear × Promo 平均（プロモの週別感応度）
    week_promo_mean = (
        ref.groupby(["Store", "WeekOfYear", "Promo"])["Sales"].mean()
        .reset_index().rename(columns={"Sales": "store_week_promo_mean"})
    )
    target = target.merge(week_promo_mean, on=["Store", "WeekOfYear", "Promo"], how="left")

    # 欠損補完: store_week_promo_mean → store_week_mean → store_mean の順
    null_wpm = target["store_week_promo_mean"].isnull()
    if null_wpm.any():
        target.loc[null_wpm, "store_week_promo_mean"] = target.loc[null_wpm, "store_week_mean"]
    null_wm = target["store_week_mean"].isnull()
    if null_wm.any():
        target.loc[null_wm, "store_week_mean"] = target.loc[null_wm, "store_mean"]

    return target

# ── データ前処理の実行 ───────────────────────────────────────────
print("特徴量エンジニアリング中...")
train = build_features(train)
test  = build_features(test)

train_open = train[train["Open"] == 1].copy()
train_open = train_open[train_open["Sales"] > 0].copy()
train_open["LogSales"] = np.log1p(train_open["Sales"])

VAL_START = pd.Timestamp("2015-06-20")
tr_fold   = train_open[train_open["Date"] <  VAL_START].copy()
val_fold  = train_open[train_open["Date"] >= VAL_START].copy()

print(f"\n=== 時系列 Hold-out CV ===")
print(f"  学習: {tr_fold['Date'].min().date()} ~ {tr_fold['Date'].max().date()}  ({len(tr_fold):,} 行)")
print(f"  検証: {val_fold['Date'].min().date()} ~ {val_fold['Date'].max().date()}  ({len(val_fold):,} 行)")

# 店舗別統計量（CV-safe）
print("\n店舗別統計量を計算中...")
tr_fold    = add_store_stats(tr_fold,    ref=tr_fold)
val_fold   = add_store_stats(val_fold,   ref=tr_fold)
train_open = add_store_stats(train_open, ref=train_open)
test       = add_store_stats(test,       ref=train_open)

# 週別統計量（② 新規、CV-safe）
print("週別統計量を計算中（② Store × WeekOfYear）...")
tr_fold    = add_week_stats(tr_fold,    ref=tr_fold)
val_fold   = add_week_stats(val_fold,   ref=tr_fold)
train_open = add_week_stats(train_open, ref=train_open)
test       = add_week_stats(test,       ref=train_open)

# 週別統計量の概要をログ出力
print("\n=== 週別統計量の概要（train_open 基準）===")
week_cov = train_open.groupby(["Store", "WeekOfYear"]).size()
print(f"  Store × WeekOfYear の組み合わせ数: {len(week_cov):,}")
print(f"  1組み合わせあたりの平均サンプル数: {week_cov.mean():.1f}")
print(f"  store_week_mean の NaN（補完前）: {train_open['store_week_mean'].isnull().sum()}")
print(f"  store_week_promo_mean の NaN（補完前）: {train_open['store_week_promo_mean'].isnull().sum()}")

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
    # 店舗別統計量（v2）
    "store_mean", "store_median", "store_std",
    "store_dow_mean", "store_month_mean", "store_promo_mean",
    # 【② 新規】週別統計量
    "store_week_mean", "store_week_promo_mean",
]

CAT_COLS = ["StoreType", "Assortment", "StateHoliday"]
TARGET   = "LogSales"

for col in CAT_COLS:
    for df in [tr_fold, val_fold, train_open, test]:
        df[col] = df[col].astype("category")

print(f"\n使用特徴量: {len(FEATURES)} 個（v4: 25 → v5: {len(FEATURES)}）")
print(f"  新規追加: store_week_mean, store_week_promo_mean")
print(f"  num_boost_round: {NUM_BOOST_ROUND}（v4: 5000 → v5: {NUM_BOOST_ROUND}）")

# ── LightGBM 学習 ────────────────────────────────────────────────
dtrain = lgb.Dataset(tr_fold[FEATURES],  label=tr_fold[TARGET],  categorical_feature=CAT_COLS)
dval   = lgb.Dataset(val_fold[FEATURES], label=val_fold[TARGET], categorical_feature=CAT_COLS,
                     reference=dtrain)

print(f"\nLightGBM 学習中（Optuna 最適パラメータ + num_boost_round={NUM_BOOST_ROUND}）...")
model = lgb.train(
    BEST_PARAMS,
    dtrain,
    num_boost_round=NUM_BOOST_ROUND,
    valid_sets=[dtrain, dval],
    valid_names=["train", "valid"],
    feval=rmspe_lgbm,
    callbacks=[
        lgb.early_stopping(stopping_rounds=300, verbose=False),  # 上限を広げたので余裕を持たせる
        lgb.log_evaluation(period=1000),
    ],
)

# ── バリデーションスコア ─────────────────────────────────────────
val_pred  = np.expm1(model.predict(val_fold[FEATURES]))
val_true  = np.expm1(val_fold[TARGET].values)
val_rmspe = rmspe(val_true, val_pred)

tr_pred  = np.expm1(model.predict(tr_fold[FEATURES]))
tr_true  = np.expm1(tr_fold[TARGET].values)
tr_rmspe = rmspe(tr_true, tr_pred)

print(f"\n=== バリデーション結果 ===")
print(f"  best_iteration      : {model.best_iteration}")
print(f"  RMSPE (train)       : {tr_rmspe:.5f}  (v4: 0.12508)")
print(f"  RMSPE (valid)       : {val_rmspe:.5f}  (v4: 0.12674)")
print(f"  差分 (過学習度)     : {val_rmspe - tr_rmspe:+.5f}")
print(f"  改善幅 ① (num_boost_round増加の効果): {'上限に到達' if model.best_iteration >= NUM_BOOST_ROUND - 10 else f'best_iter={model.best_iteration} < {NUM_BOOST_ROUND} → Early Stopping 正常動作'}")
print(f"  改善幅 ② vs v4     : {val_rmspe - 0.12674:+.5f}")

# ── 特徴量重要度 ─────────────────────────────────────────────────
print(f"\n=== 特徴量重要度（gain）===")
imp = pd.Series(
    model.feature_importance(importance_type="gain"),
    index=FEATURES,
).sort_values(ascending=False)
max_val = imp.max()
for feat, val in imp.items():
    bar = "█" * max(1, int(val / max_val * 30))
    print(f"  {feat:35s}: {val:12.0f}  {bar}")

print(f"\n=== ② 新規週別統計量の重要度 ===")
for col in ["store_week_mean", "store_week_promo_mean"]:
    rank = list(imp.index).index(col) + 1
    print(f"  {col:35s}: gain={imp[col]:10.0f}  (重要度 {rank} 位 / {len(FEATURES)} 特徴量中)")

# ── 全データで再学習 ─────────────────────────────────────────────
print(f"\n全データで再学習中（num_boost_round={model.best_iteration}）...")
dtrain_full = lgb.Dataset(
    train_open[FEATURES], label=train_open[TARGET],
    categorical_feature=CAT_COLS,
)
model_full = lgb.train(
    BEST_PARAMS,
    dtrain_full,
    num_boost_round=model.best_iteration,
)

# ── テスト予測 ───────────────────────────────────────────────────
test_pred = np.expm1(model_full.predict(test[FEATURES]))
test_pred = np.clip(test_pred, 0, None)
test_pred[test["Open"] == 0] = 0

# ── 提出ファイル ─────────────────────────────────────────────────
submission = pd.DataFrame({"Id": test["Id"], "Sales": test_pred})
out_path   = OUTPUT_DIR / "submission_v5.csv"
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
print(f"  v1 baseline  RMSPE (valid): 0.13670  Kaggle LB: 0.12846")
print(f"  v2 店舗統計量 RMSPE (valid): 0.13310  Kaggle LB: 0.12274")
print(f"  v3 ラグ特徴量 RMSPE (valid): 0.13155  Kaggle LB: 0.12514  ← 悪化")
print(f"  v4 Optuna    RMSPE (valid): 0.12674  Kaggle LB: 0.12172")
print(f"  v5 今回      RMSPE (valid): {val_rmspe:.5f}  改善幅 (vs v4): {val_rmspe - 0.12674:+.5f}")
print(f"  ※ Kaggle LB はこの後提出して確認")
