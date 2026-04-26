import os

from lightgbm import LGBMRegressor
from sklearn.model_selection import RandomizedSearchCV, TimeSeriesSplit
from scipy.stats import randint, uniform

import numpy as np
import pandas as pd
from pathlib import Path

"""
https://www.kaggle.com/competitions/store-sales-time-series-forecasting/overview
エクアドルの食料品チェーン「Favorita」の店舗売上を予測する時系列回帰問題。
評価指標: RMSLE（Root Mean Squared Log Error）
  → log1p(sales) を目的変数にすることで RMSE ≈ RMSLE になる。
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

# 取引件数: lag15 でシフト（テスト期間15日間すべてで安全に使用できる最小ラグ）
trans_lag15 = transactions.copy()
trans_lag15["date"] = trans_lag15["date"] + pd.Timedelta(days=15)
trans_lag15 = trans_lag15.rename(columns={"transactions": "transactions_lag15"})


def add_base_features(df):
    """日付・店舗・商品・外部データの特徴量を付与する"""
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


train_feat = add_base_features(train)
test_feat  = add_base_features(test)


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
y = np.log1p(train["sales"])


## LightGBM のパラメータ設定
# TUNE = True : RandomizedSearchCV で新たにパラメータを探索する（時間がかかる）
# TUNE = False: 探索済みパラメータをそのまま使用して即座に学習する
TUNE = False

# 探索済み最良パラメータ
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
tscv = TimeSeriesSplit(n_splits=5)

print("学習開始")

if TUNE:
    param_dist = {
        "n_estimators":      randint(200, 1000),
        "max_depth":         randint(3, 10),
        "learning_rate":     uniform(0.01, 0.19),
        "num_leaves":        randint(15, 127),
        "subsample":         uniform(0.6, 0.4),
        "colsample_bytree":  uniform(0.6, 0.4),
        "reg_alpha":         uniform(0, 1),
        "reg_lambda":        uniform(0.5, 2),
        "min_child_samples": randint(10, 50),
    }
    gs = RandomizedSearchCV(
        LGBMRegressor(random_state=1, verbosity=-1, n_jobs=-1),
        param_dist,
        n_iter=50,
        cv=tscv,
        scoring="neg_root_mean_squared_error",
        n_jobs=-1,
        random_state=1,
        verbose=1,
    )
    gs.fit(X, y)
    print(f"CV RMSE={-gs.best_score_:.4f}")
    print(f"best_params={gs.best_params_}")
    best_model = gs.best_estimator_
else:
    best_model = LGBMRegressor(
        **BEST_PARAMS, random_state=1, verbosity=-1, n_jobs=-1
    )
    best_model.fit(X, y)
    print("探索済みパラメータで学習完了")


## 予測・提出ファイルの出力
predictions = np.expm1(best_model.predict(X_test)).clip(0)

output = pd.DataFrame({
    "id":    test["id"],
    "sales": predictions,
})
output.to_csv(
    Path(__file__).parent / "submission_1st.csv",
    index=False
)
print(output.head())
print("submission_1st.csv を出力しました")
