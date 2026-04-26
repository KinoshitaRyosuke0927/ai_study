"""
ラグ特徴量追加後の精度悪化原因調査
NaN率・年別分布・ラグ有無でのCV RMSE比較
"""
import numpy as np
import pandas as pd
from pathlib import Path
from lightgbm import LGBMRegressor
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.preprocessing import LabelEncoder

DATA_DIR = Path(r"C:\azure_ai\education\005_kaggle\competitions\store-sales-time-series-forecasting")

train        = pd.read_csv(DATA_DIR / "train.csv",           parse_dates=["date"])
test         = pd.read_csv(DATA_DIR / "test.csv",            parse_dates=["date"])
stores       = pd.read_csv(DATA_DIR / "stores.csv")
oil          = pd.read_csv(DATA_DIR / "oil.csv",             parse_dates=["date"])
holidays     = pd.read_csv(DATA_DIR / "holidays_events.csv", parse_dates=["date"])
transactions = pd.read_csv(DATA_DIR / "transactions.csv",    parse_dates=["date"])

print(f"train期間: {train['date'].min().date()} ~ {train['date'].max().date()}")
print(f"train行数: {len(train):,}")

# ---- 前処理（store_sales.py と同じ） ----
oil_full = (
    pd.date_range(oil["date"].min(), oil["date"].max(), freq="D")
    .to_frame(name="date")
    .merge(oil, on="date", how="left")
)
oil_full["oil_price"]     = oil_full["dcoilwtico"].interpolate(method="linear")
oil_full["oil_change_7d"] = oil_full["oil_price"].diff(7)

le_city   = LabelEncoder().fit(stores["city"])
le_state  = LabelEncoder().fit(stores["state"])
le_family = LabelEncoder().fit(pd.concat([train["family"], test["family"]]))

type_order = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}
stores["type_enc"]  = stores["type"].map(type_order)
stores["city_enc"]  = le_city.transform(stores["city"])
stores["state_enc"] = le_state.transform(stores["state"])

national_hol = (
    holidays[holidays["transferred"] == False]
    .query("locale == 'National'")[["date", "type"]]
    .drop_duplicates("date")
    .rename(columns={"type": "holiday_type"})
)
le_holiday = LabelEncoder().fit(
    pd.concat([national_hol["holiday_type"], pd.Series(["None"])])
)

trans_lag15 = transactions.copy()
trans_lag15["date"] = trans_lag15["date"] + pd.Timedelta(days=15)
trans_lag15 = trans_lag15.rename(columns={"transactions": "transactions_lag15"})

def add_base_features(df):
    df = df.copy()
    df["year"]           = df["date"].dt.year
    df["month"]          = df["date"].dt.month
    df["day"]            = df["date"].dt.day
    df["dayofweek"]      = df["date"].dt.dayofweek
    df["dayofyear"]      = df["date"].dt.dayofyear
    df["weekofyear"]     = df["date"].dt.isocalendar().week.astype(int)
    df["is_weekend"]     = (df["dayofweek"] >= 5).astype(int)
    df["is_month_start"] = (df["day"] == 1).astype(int)
    df["days_in_month"]  = df["date"].dt.days_in_month
    df["is_salary_day"]  = ((df["day"] == 15) | (df["day"] == df["days_in_month"])).astype(int)
    df = df.merge(stores[["store_nbr", "type_enc", "cluster", "city_enc", "state_enc"]], on="store_nbr", how="left")
    df["family_enc"] = le_family.transform(df["family"])
    df["has_promo"]  = (df["onpromotion"] > 0).astype(int)
    df = df.merge(oil_full[["date", "oil_price", "oil_change_7d"]], on="date", how="left")
    df = df.merge(national_hol, on="date", how="left")
    df["is_national_holiday"] = df["holiday_type"].notna().astype(int)
    df["holiday_type_enc"]    = le_holiday.transform(df["holiday_type"].fillna("None"))
    df = df.merge(trans_lag15[["date", "store_nbr", "transactions_lag15"]], on=["date", "store_nbr"], how="left")
    return df

def add_lag_features(df):
    grp = df.groupby(["store_nbr", "family"])["sales"]
    for lag in [16, 21, 28, 365]:
        df[f"sales_lag_{lag}"] = grp.shift(lag)
    sales_shifted = grp.shift(16)
    df["sales_roll7_mean"]  = sales_shifted.rolling(7,  min_periods=1).mean()
    df["sales_roll28_mean"] = sales_shifted.rolling(28, min_periods=1).mean()
    df["sales_roll7_std"]   = sales_shifted.rolling(7,  min_periods=2).std()
    df["sales_roll28_std"]  = sales_shifted.rolling(28, min_periods=2).std()
    return df

combined = pd.concat([
    train[["id", "date", "store_nbr", "family", "sales", "onpromotion"]],
    test[["id",  "date", "store_nbr", "family", "onpromotion"]].assign(sales=np.nan),
], ignore_index=True).sort_values(["store_nbr", "family", "date"]).reset_index(drop=True)

combined = add_base_features(combined)
combined = add_lag_features(combined)

train_feat = combined[combined["sales"].notna()].copy()

LAG_COLS = [
    "sales_lag_16", "sales_lag_21", "sales_lag_28", "sales_lag_365",
    "sales_roll7_mean", "sales_roll28_mean", "sales_roll7_std", "sales_roll28_std",
]

# ================================================================
# 調査1: ラグ特徴量のNaN率
# ================================================================
print("\n" + "="*60)
print("調査1: ラグ特徴量のNaN率")
print("="*60)
for col in LAG_COLS:
    nan_n   = train_feat[col].isna().sum()
    nan_pct = nan_n / len(train_feat) * 100
    print(f"  {col:<22}: {nan_pct:5.1f}%  ({nan_n:>8,} / {len(train_feat):,} 行)")

# ================================================================
# 調査2: 年別のlag_365 NaN率
# ================================================================
print("\n" + "="*60)
print("調査2: 年別の sales_lag_365 NaN率")
print("="*60)
for yr, grp in train_feat.groupby(train_feat["date"].dt.year):
    nan_pct = grp["sales_lag_365"].isna().mean() * 100
    print(f"  {yr}年: {nan_pct:5.1f}% NaN  ({len(grp):>8,} 行)")

# ================================================================
# 調査3: ラグ特徴量あり/なし/直近2年 の CV RMSE 比較
# ================================================================
print("\n" + "="*60)
print("調査3: CV RMSE 比較（5-fold TimeSeriesSplit）")
print("="*60)

BASE_FEATURES = [
    "family_enc", "onpromotion", "has_promo",
    "store_nbr", "type_enc", "cluster", "city_enc", "state_enc",
    "year", "month", "day", "dayofweek", "dayofyear",
    "weekofyear", "is_weekend", "is_month_start", "is_salary_day",
    "oil_price", "oil_change_7d",
    "is_national_holiday", "holiday_type_enc",
    "transactions_lag15",
]
ALL_FEATURES = BASE_FEATURES + LAG_COLS

tscv   = TimeSeriesSplit(n_splits=5)
model  = LGBMRegressor(n_estimators=300, random_state=1, verbosity=-1, n_jobs=-1)

def eval_features(df, feature_cols, label):
    X = df[feature_cols].copy()
    y = np.log1p(df["sales"])
    for col in feature_cols:
        if X[col].dtype in [np.float64, np.float32]:
            X[col] = X[col].fillna(X[col].median())
        else:
            X[col] = X[col].fillna(0)
    scores = cross_val_score(model, X, y, cv=tscv,
                             scoring="neg_root_mean_squared_error", n_jobs=-1)
    rmse = -scores.mean()
    print(f"  {label:<30}: CV RMSE = {rmse:.4f}")
    return rmse

print("  評価中...")
rmse_base    = eval_features(train_feat,                                          BASE_FEATURES, "ベース特徴量のみ（ラグなし）")
rmse_all     = eval_features(train_feat,                                          ALL_FEATURES,  "ベース + ラグ全部（全期間）")

# 直近2年
train_2y     = train_feat[train_feat["date"] >= "2016-01-01"].copy()
rmse_all_2y  = eval_features(train_2y,                                            ALL_FEATURES,  "ベース + ラグ全部（直近2年）")

# lag_365 を除外
no365_cols   = BASE_FEATURES + [c for c in LAG_COLS if c != "sales_lag_365"]
rmse_no365   = eval_features(train_feat,                                          no365_cols,    "ベース + ラグ（lag_365除外）")

# ================================================================
# 調査4: NaN補完方法の比較（lag_365: 中央値 vs 0 vs 除外）
# ================================================================
print("\n" + "="*60)
print("調査4: lag_365 のNaN補完方法 比較")
print("="*60)

def eval_with_lag365_fill(fill_method, label):
    X = train_feat[ALL_FEATURES].copy()
    y = np.log1p(train_feat["sales"])
    for col in ALL_FEATURES:
        if col == "sales_lag_365":
            if fill_method == "median":
                X[col] = X[col].fillna(X[col].median())
            elif fill_method == "zero":
                X[col] = X[col].fillna(0)
            elif fill_method == "mean_by_family":
                X[col] = X.groupby(train_feat["family_enc"])[col].transform(
                    lambda s: s.fillna(s.median())
                )
        elif X[col].dtype in [np.float64, np.float32]:
            X[col] = X[col].fillna(X[col].median())
        else:
            X[col] = X[col].fillna(0)
    scores = cross_val_score(model, X, y, cv=tscv,
                             scoring="neg_root_mean_squared_error", n_jobs=-1)
    rmse = -scores.mean()
    print(f"  {label:<35}: CV RMSE = {rmse:.4f}")

eval_with_lag365_fill("median",        "lag_365 NaN → 中央値補完（現状）")
eval_with_lag365_fill("zero",          "lag_365 NaN → 0補完")
eval_with_lag365_fill("mean_by_family","lag_365 NaN → familyごと中央値")

print("\n" + "="*60)
print("調査完了")
print("="*60)
