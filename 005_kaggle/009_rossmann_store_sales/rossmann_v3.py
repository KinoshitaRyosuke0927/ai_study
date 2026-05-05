"""
https://www.kaggle.com/competitions/rossmann-store-sales/overview
Rossmann Store Sales - v3
v2 からの変更点:
  ラグ特徴量の追加（前年同週・前年同日の Sales）

  特徴量重要度で store_promo_mean / store_dow_mean が上位を占めているが、
  これらは「長期平均」であり「去年の同じ時期に実際いくら売れたか」を捉えられない。
  lag_364（52週前の実測値）を追加することで：
    ・週次の季節性（クリスマス前は高い・年明けは低いなど）
    ・店舗ごとの同時期の個性
  を直接モデルに渡せる。

  リーク防止の設計:
    CV バリデーション用 → train[Date < VAL_START] を参照（val_fold の情報は使わない）
    最終モデル・テスト用 → train 全体 (2013-01-01〜2015-07-31) を参照
    test 期間（2015-08-01〜09-17）の lag_364 は 2014-08-01〜09-17 → 全て training 内 ✓
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

# ── 特徴量エンジニアリング（v2 と同一） ─────────────────────────
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

print("特徴量エンジニアリング中...")
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

# ── 店舗別統計量（v2 と同一、リークなし） ──────────────────────
def add_store_stats(target: pd.DataFrame, ref: pd.DataFrame) -> pd.DataFrame:
    target = target.copy()
    store_agg = ref.groupby("Store")["Sales"].agg(
        store_mean="mean", store_median="median", store_std="std"
    ).reset_index()
    target = target.merge(store_agg, on="Store", how="left")
    dow_mean = (
        ref.groupby(["Store", "DayOfWeek"])["Sales"].mean()
        .reset_index().rename(columns={"Sales": "store_dow_mean"})
    )
    target = target.merge(dow_mean, on=["Store", "DayOfWeek"], how="left")
    month_mean = (
        ref.groupby(["Store", "Month"])["Sales"].mean()
        .reset_index().rename(columns={"Sales": "store_month_mean"})
    )
    target = target.merge(month_mean, on=["Store", "Month"], how="left")
    promo_mean = (
        ref.groupby(["Store", "Promo"])["Sales"].mean()
        .reset_index().rename(columns={"Sales": "store_promo_mean"})
    )
    target = target.merge(promo_mean, on=["Store", "Promo"], how="left")
    for col in ["store_dow_mean", "store_month_mean", "store_promo_mean"]:
        null_mask = target[col].isnull()
        if null_mask.any():
            target.loc[null_mask, col] = target.loc[null_mask, "store_mean"]
    return target

print("\n店舗別統計量を計算・追加中...")
tr_fold     = add_store_stats(tr_fold,  ref=tr_fold)
val_fold    = add_store_stats(val_fold, ref=tr_fold)
train_open  = add_store_stats(train_open, ref=train_open)
test        = add_store_stats(test, ref=train_open)

# ── ラグ特徴量（v3 新規） ────────────────────────────────────────
# 参照テーブルの作成
# Open=0（閉店日）の Sales=0 も時系列の正当な観測値として含める。
# 例: 364日前が閉店日（Sales=0）であることもモデルへの情報となる。
def make_lag_table(ref_df: pd.DataFrame) -> pd.DataFrame:
    """
    ref_df の (Store, Date, Sales) を 364日・365日シフトしたルックアップテーブルを返す。
    シフト後の Date = 「この Sales が参照される予測日」を意味する。
    例: ref_df の 2014-08-01 の Sales が lag_364 として 2015-08-01 にマッピングされる。
    """
    ref = ref_df[["Store", "Date", "Sales"]].copy()

    lag364 = ref.copy()
    lag364["Date"] = lag364["Date"] + pd.Timedelta(days=364)
    lag364 = lag364.rename(columns={"Sales": "lag_364"})

    lag365 = ref.copy()
    lag365["Date"] = lag365["Date"] + pd.Timedelta(days=365)
    lag365 = lag365.rename(columns={"Sales": "lag_365"})

    lag_table = lag364.merge(
        lag365[["Store", "Date", "lag_365"]], on=["Store", "Date"], how="outer"
    )
    return lag_table

def apply_lag_features(target: pd.DataFrame, lag_table: pd.DataFrame) -> pd.DataFrame:
    """
    lag_table を target にマージしてラグ特徴量を付与する。
    欠損（参照先に対応するデータがない年初など）は store_mean で補完。
    """
    target = target.merge(lag_table, on=["Store", "Date"], how="left")
    for col in ["lag_364", "lag_365"]:
        null_mask = target[col].isnull()
        n_null = null_mask.sum()
        if n_null > 0:
            target.loc[null_mask, col] = target.loc[null_mask, "store_mean"]
            print(f"    {col} 欠損補完: {n_null:,} 件 → store_mean で補完")
        else:
            print(f"    {col} 欠損: 0 件（全行で参照先データあり）")
    return target

print("\nラグ特徴量を計算・追加中...")

# CV 用: VAL_START より前のデータのみを参照（val_fold の Sales は一切使わない）
train_before_val = train[train["Date"] < VAL_START]  # Open=0 含む全行
lag_table_cv = make_lag_table(train_before_val)

print(f"  CV 用ラグテーブル: {len(lag_table_cv):,} 行")
print(f"  lag_364 カバー期間: {lag_table_cv['Date'].min().date()} ~ {lag_table_cv['Date'].max().date()}")

print("  tr_fold にラグ特徴量を追加...")
tr_fold  = apply_lag_features(tr_fold,  lag_table_cv)
print("  val_fold にラグ特徴量を追加...")
val_fold = apply_lag_features(val_fold, lag_table_cv)

# 最終モデル & テスト用: train 全体（2013-01-01〜2015-07-31）を参照
lag_table_full = make_lag_table(train)  # Open=0 含む全行

print(f"\n  最終用ラグテーブル: {len(lag_table_full):,} 行")
print(f"  lag_364 カバー期間: {lag_table_full['Date'].min().date()} ~ {lag_table_full['Date'].max().date()}")

print("  train_open にラグ特徴量を追加...")
train_open = apply_lag_features(train_open, lag_table_full)
print("  test にラグ特徴量を追加...")
test       = apply_lag_features(test, lag_table_full)

# ラグ特徴量のカバー率をログ出力
print("\n=== ラグ特徴量カバー率（補完前の有効データ割合） ===")
for fold_name, fold_df in [("tr_fold", tr_fold), ("val_fold", val_fold),
                            ("train_open", train_open), ("test", test)]:
    n = len(fold_df)
    cov364 = fold_df["lag_364"].apply(lambda x: True).sum()   # 補完後は全行有効
    # 補完前の有効率を確認するため lag テーブルとの merge 前に確認できないが
    # 代わりに lag が store_mean と一致する行の割合で近似
    same_as_mean = (fold_df["lag_364"] == fold_df["store_mean"]).sum()
    print(f"  {fold_name:12s}: {n:7,} 行  (lag_364 が store_mean と一致=NaN補完された可能性: {same_as_mean:,} 件 / {same_as_mean/n*100:.1f}%)")

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
    # 【v3 新規】前年同週・前年同日のラグ
    "lag_364", "lag_365",
]

CAT_COLS = ["StoreType", "Assortment", "StateHoliday"]
TARGET   = "LogSales"

for col in CAT_COLS:
    for df in [tr_fold, val_fold, train_open, test]:
        df[col] = df[col].astype("category")

print(f"\n使用特徴量: {len(FEATURES)} 個（v2: 25 → v3: {len(FEATURES)}）")
print(f"  新規追加: lag_364, lag_365")

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

NUM_BOOST_ROUND = 8000

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

tr_pred  = np.expm1(model.predict(tr_fold[FEATURES]))
tr_true  = np.expm1(tr_fold[TARGET].values)
tr_rmspe = rmspe(tr_true, tr_pred)

print(f"\n=== バリデーション結果 ===")
print(f"  best_iteration      : {model.best_iteration}")
print(f"  RMSPE (train)       : {tr_rmspe:.5f}  (v2: 0.10520)")
print(f"  RMSPE (valid)       : {val_rmspe:.5f}  (v2: 0.13310)")
print(f"  差分 (過学習度)     : {val_rmspe - tr_rmspe:+.5f}")
print(f"  改善幅 (vs v2)      : {val_rmspe - 0.13310:+.5f}")

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

print(f"\n=== 新規ラグ特徴量の重要度 ===")
for col in ["lag_364", "lag_365"]:
    print(f"  {col:35s}: gain={imp.get(col, 0):10.0f}")

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
test_pred = np.expm1(model_full.predict(test[FEATURES]))
test_pred = np.clip(test_pred, 0, None)
test_pred[test["Open"] == 0] = 0

# ── 提出ファイル ─────────────────────────────────────────────────
submission = pd.DataFrame({"Id": test["Id"], "Sales": test_pred})
out_path   = OUTPUT_DIR / "submission_v3.csv"
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
print(f"  v2 店舗統計量   RMSPE (valid): 0.13310  Kaggle LB: 0.12274")
print(f"  v3 ラグ特徴量   RMSPE (valid): {val_rmspe:.5f}  改善幅 (vs v2): {val_rmspe - 0.13310:+.5f}")
print(f"  ※ Kaggle LB はこの後提出して確認")
