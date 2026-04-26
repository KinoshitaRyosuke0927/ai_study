import os

from lightgbm import LGBMRegressor
from sklearn.model_selection import TimeSeriesSplit, ParameterSampler, cross_val_score
from scipy.stats import randint, uniform
from tqdm import tqdm

import numpy as np
import pandas as pd
from pathlib import Path

"""
https://www.kaggle.com/competitions/store-sales-time-series-forecasting/overview
エクアドルの食料品チェーン「Favorita」の店舗売上を予測する時系列回帰問題。
評価指標: RMSLE（Root Mean Squared Log Error）
  → log1p(sales) を目的変数にすることで RMSE ≈ RMSLE になる。

store_sales.py からの改善:
  改善1: 目的変数のラグ特徴量を追加（lag16/21/28/365）
         テスト期間は15日間なので lag>=16 でリーク防止
  改善2: ローリング統計量を追加（7日・28日の移動平均・標準偏差）
         shift(16) してから rolling することでリークを防ぐ

実装上の重要ポイント:
  ラグ特徴量はtrain+testを結合してから計算する。
  テストデータの直前がtrainデータであるため、
  testを単独でshift()しても過去の値が参照できない。
"""

DATA_DIR = Path(r"C:\azure_ai\education\005_kaggle\competitions\store-sales-time-series-forecasting")

## データの読み込み
train        = pd.read_csv(DATA_DIR / "train.csv",           parse_dates=["date"])
test         = pd.read_csv(DATA_DIR / "test.csv",            parse_dates=["date"])
stores       = pd.read_csv(DATA_DIR / "stores.csv")
oil          = pd.read_csv(DATA_DIR / "oil.csv",             parse_dates=["date"])
holidays     = pd.read_csv(DATA_DIR / "holidays_events.csv", parse_dates=["date"])
transactions = pd.read_csv(DATA_DIR / "transactions.csv",    parse_dates=["date"])


## 欠損値・補完処理
# 原油価格: 週末・祝日は市場休場のため時系列補間
oil_full = (
    pd.date_range(oil["date"].min(), oil["date"].max(), freq="D")
    .to_frame(name="date")
    .merge(oil, on="date", how="left")
)
oil_full["oil_price"]     = oil_full["dcoilwtico"].interpolate(method="linear")
oil_full["oil_change_7d"] = oil_full["oil_price"].diff(7)


## 特徴量エンジニアリング
# ラグ特徴量はtrain+testを結合してから計算するため、
# まず外部データ（店舗・原油・祝日）の特徴量を付与する関数を定義する

from sklearn.preprocessing import LabelEncoder

# ---- LabelEncoder をデータ全体で fit（train/test で同じカテゴリのため） ----
le_city   = LabelEncoder().fit(stores["city"])
le_state  = LabelEncoder().fit(stores["state"])
le_family = LabelEncoder().fit(pd.concat([train["family"], test["family"]]))

type_order = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}
stores["type_enc"]  = stores["type"].map(type_order)
stores["city_enc"]  = le_city.transform(stores["city"])
stores["state_enc"] = le_state.transform(stores["state"])

# 全国祝日テーブル（振替祝日を除外済み）
national_hol = (
    holidays[holidays["transferred"] == False]
    .query("locale == 'National'")[["date", "type"]]
    .drop_duplicates("date")
    .rename(columns={"type": "holiday_type"})
)
le_holiday = LabelEncoder().fit(
    pd.concat([national_hol["holiday_type"], pd.Series(["None"])])
)

# 取引件数: lag15 でシフト
trans_lag15 = transactions.copy()
trans_lag15["date"] = trans_lag15["date"] + pd.Timedelta(days=15)
trans_lag15 = trans_lag15.rename(columns={"transactions": "transactions_lag15"})


def add_base_features(df):
    """日付・店舗・商品・外部データの特徴量を付与する（ラグ以外）"""
    df = df.copy()

    # ---- 日付特徴量 ----
    df["year"]           = df["date"].dt.year
    df["month"]          = df["date"].dt.month
    df["day"]            = df["date"].dt.day
    df["dayofweek"]      = df["date"].dt.dayofweek
    df["dayofyear"]      = df["date"].dt.dayofyear
    df["weekofyear"]     = df["date"].dt.isocalendar().week.astype(int)
    df["is_weekend"]     = (df["dayofweek"] >= 5).astype(int)
    df["is_month_start"] = (df["day"] == 1).astype(int)
    df["days_in_month"]  = df["date"].dt.days_in_month
    df["is_salary_day"]  = (
        (df["day"] == 15) | (df["day"] == df["days_in_month"])
    ).astype(int)

    # ---- 店舗特徴量 ----
    df = df.merge(
        stores[["store_nbr", "type_enc", "cluster", "city_enc", "state_enc"]],
        on="store_nbr", how="left"
    )

    # ---- 商品カテゴリ特徴量 ----
    df["family_enc"] = le_family.transform(df["family"])
    df["has_promo"]  = (df["onpromotion"] > 0).astype(int)

    # ---- 原油価格 ----
    df = df.merge(oil_full[["date", "oil_price", "oil_change_7d"]], on="date", how="left")

    # ---- 祝日（全国レベルのみ） ----
    df = df.merge(national_hol, on="date", how="left")
    df["is_national_holiday"] = df["holiday_type"].notna().astype(int)
    df["holiday_type_enc"]    = le_holiday.transform(df["holiday_type"].fillna("None"))

    # ---- 取引件数（lag15） ----
    df = df.merge(
        trans_lag15[["date", "store_nbr", "transactions_lag15"]],
        on=["date", "store_nbr"], how="left"
    )

    return df


def add_lag_features(df):
    """
    改善1: 目的変数のラグ特徴量
    改善2: ローリング統計量（移動平均・標準偏差）

    前提: df は train + test を結合し (store_nbr, family, date) でソート済み。
    sales 列はtestでは NaN。
    lag >= 16 にすることでテスト最終日(+15日目)でもリークなしで使用可能。
    """
    grp = df.groupby(["store_nbr", "family"])["sales"]

    # ---- 改善1: ラグ特徴量 ----
    # lag16: 16日前の売上（テスト期間全体で安全に使用できる最小ラグ）
    # lag21: 3週間前（同曜日±1日の参照）
    # lag28: 4週間前（同じ曜日の売上が参照できる）
    # lag365: 昨年同日（年次季節性の捕捉）
    for lag in [16, 21, 28, 365]:
        df[f"sales_lag_{lag}"] = grp.shift(lag)

    # ---- 改善2: ローリング統計量 ----
    # shift(16) してから rolling → テスト日から見て16日以上前のデータのみ使用
    # これにより未来情報の混入（データリーク）を防ぐ
    sales_shifted = grp.shift(16)

    df["sales_roll7_mean"]  = sales_shifted.rolling(7,  min_periods=1).mean()
    df["sales_roll28_mean"] = sales_shifted.rolling(28, min_periods=1).mean()
    df["sales_roll7_std"]   = sales_shifted.rolling(7,  min_periods=2).std()
    df["sales_roll28_std"]  = sales_shifted.rolling(28, min_periods=2).std()

    return df


# ---- train + test を結合してラグ特徴量を計算 ----
# testの sales は NaN として結合 → ラグ計算時にtrainのsalesが参照される
combined = pd.concat([
    train[["id", "date", "store_nbr", "family", "sales", "onpromotion"]],
    test[["id",  "date", "store_nbr", "family", "onpromotion"]].assign(sales=np.nan),
], ignore_index=True).sort_values(["store_nbr", "family", "date"]).reset_index(drop=True)

combined = add_base_features(combined)
combined = add_lag_features(combined)

# train / test に分割
# 2016年以降に絞り込み: lag_365 の NaN（2013年分が100%欠損）を完全排除
train_feat = combined[(combined["sales"].notna()) & (combined["date"] >= "2014-01-01")].copy()
test_feat  = combined[combined["sales"].isna()].copy()
print(f"学習データ: {len(train_feat):,} 行  ({train_feat['date'].min().date()} ~ {train_feat['date'].max().date()})")


## 使用する特徴量の定義
NUM_FEATURES = [
    # 商品（最重要）
    "family_enc", "onpromotion", "has_promo",
    # 店舗
    "store_nbr", "type_enc", "cluster", "city_enc", "state_enc",
    # 日付
    "year", "month", "day", "dayofweek", "dayofyear",
    "weekofyear", "is_weekend", "is_month_start", "is_salary_day",
    # 原油価格
    "oil_price", "oil_change_7d",
    # 祝日（全国レベルのみ）
    "is_national_holiday", "holiday_type_enc",
    # 取引件数（15日ラグ、リーク防止済）
    "transactions_lag15",
    # 改善1: 目的変数のラグ特徴量（lag>=16 でテスト期間全体をカバー）
    # sales_lag_365 は2013年分が100%NaNのため除外（2014年以降でも0.3%残る）
    "sales_lag_16", "sales_lag_21", "sales_lag_28",
    # 改善2: ローリング統計量（shift(16)後に集計してリーク防止）
    "sales_roll7_mean", "sales_roll28_mean",
    "sales_roll7_std",  "sales_roll28_std",
]

X      = train_feat[NUM_FEATURES].copy()
X_test = test_feat[NUM_FEATURES].copy()

# 欠損値: 数値列は中央値、整数列は 0 で補完
for col in NUM_FEATURES:
    if X[col].dtype in [np.float64, np.float32]:
        median = X[col].median()
        X[col]      = X[col].fillna(median)
        X_test[col] = X_test[col].fillna(median)
    else:
        X[col]      = X[col].fillna(0)
        X_test[col] = X_test[col].fillna(0)

# 目的変数: log1p 変換（RMSLE 対応、右歪み分布の緩和）
# train_feat は2016年以降に絞り込み済みのため、train["sales"] ではなく train_feat["sales"] を使用
y = np.log1p(train_feat["sales"].values)


## LightGBM のパラメータ設定
# TUNE = True : RandomizedSearchCV で新たにパラメータを探索する（時間がかかる）
# TUNE = False: 探索済みパラメータをそのまま使用して即座に学習する
TUNE = True

# 探索済み最良パラメータ
# ラグ特徴量追加後は TUNE=True で再探索を推奨（以下は追加前の参考値）
BEST_PARAMS = {
    "colsample_bytree":  0.9596256011286259,
    "learning_rate":     0.14591262023331808,
    "max_depth":         7,
    "min_child_samples": 34,
    "n_estimators":      733,
    "num_leaves":        34,
    "reg_alpha":         0.35212131245762546,
    "reg_lambda":        0.5020265708358327,
    "subsample":         0.8498521922522961,
}

# TimeSeriesSplit: 過去データで未来を学習する時系列専用 CV
# 通常の k-fold は未来のデータで過去を学習してしまうため不適切
tscv = TimeSeriesSplit(n_splits=5)

print("学習開始")

if TUNE:
    param_dist = {
        "n_estimators":      randint(200, 1000),
        "max_depth":         randint(3, 7),       # 方向性B: 上限を10→7に下げ深い木を制限
        "learning_rate":     uniform(0.01, 0.19),
        "num_leaves":        randint(15, 63),      # 方向性B: 上限を127→63に下げ複雑さを制限
        "subsample":         uniform(0.6, 0.4),
        "colsample_bytree":  uniform(0.6, 0.4),
        "reg_alpha":         uniform(0.1, 1.9),   # 方向性B: 下限を0→0.1に上げ正則化を強化
        "reg_lambda":        uniform(1.0, 3.0),   # 方向性B: 範囲を上方シフトして正則化を強化
        "min_child_samples": randint(30, 100),    # 方向性B: 下限を10→30に上げ過学習を抑制
    }
    N_ITER = 50
    param_list   = list(ParameterSampler(param_dist, n_iter=N_ITER, random_state=1))
    results      = []
    best_score   = np.inf
    best_params_found = None

    for i, params in enumerate(tqdm(param_list, desc="チューニング中"), 1):
        model  = LGBMRegressor(**params, random_state=1, verbosity=-1, n_jobs=-1)
        scores = cross_val_score(model, X, y, cv=tscv, scoring="neg_root_mean_squared_error", n_jobs=-1)
        rmse   = -scores.mean()
        results.append({"params": params, "rmse": rmse})
        if rmse < best_score:
            best_score        = rmse
            best_params_found = params
        tqdm.write(f"  [{i:2d}/{N_ITER}] RMSE={rmse:.4f}  best={best_score:.4f}")

    print(f"\nチューニング完了  CV RMSE={best_score:.4f}")
    print(f"best_params={best_params_found}")
    best_model = LGBMRegressor(**best_params_found, random_state=1, verbosity=-1, n_jobs=-1)
    best_model.fit(X, y)
else:
    best_model = LGBMRegressor(
        **BEST_PARAMS, random_state=1, verbosity=-1, n_jobs=-1
    )
    best_model.fit(X, y)
    print("探索済みパラメータで学習完了")

## 予測・提出ファイルの出力
# 予測値を log1p 変換前のスケール（売上）に戻す
# sales >= 0 なので clip(0) で負値を排除
predictions = np.expm1(best_model.predict(X_test)).clip(0)

output = pd.DataFrame({
    "id":    test["id"],
    "sales": predictions,
})
output.to_csv(
    Path(__file__).parent / "submission.csv",
    index=False
)
print(output.head())
print("submission.csv を出力しました")
