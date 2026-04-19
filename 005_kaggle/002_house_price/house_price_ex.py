import os

from sklearn.ensemble import RandomForestRegressor, VotingRegressor
from sklearn.model_selection import RandomizedSearchCV, cross_val_score
from xgboost import XGBRegressor
from lightgbm import LGBMRegressor
from scipy.stats import randint, uniform

import numpy as np
import pandas as pd

"""
https://www.kaggle.com/competitions/house-prices-advanced-regression-techniques/overview
house_price.py（LotArea・YearRemodAdd の2特徴量モデル）の拡張版。
多くの特徴量と特徴量エンジニアリングを追加し、より高精度なモデルを構築する。
"""

DATA_DIR = r"C:\azure_ai\education\005_kaggle\competitions\house-prices-advanced-regression-techniques"

## データの読み込み
train_data = pd.read_csv(os.path.join(DATA_DIR, "train.csv"))
test_data  = pd.read_csv(os.path.join(DATA_DIR, "test.csv"))


## 欠損値処理
# ガレージ・地下室等の NA は「設備なし（0）」を意味する列
ZERO_FILL_COLS = [
    "GarageArea", "GarageCars", "GarageYrBlt",
    "BsmtFinSF1", "BsmtFinSF2", "BsmtUnfSF", "TotalBsmtSF",
    "BsmtFullBath", "BsmtHalfBath",
    "MasVnrArea",
]

def fill_missing(df, num_medians=None, cat_modes=None):
    df = df.copy()
    # 「設備なし」を意味する列は 0 で補完
    for col in ZERO_FILL_COLS:
        if col in df.columns:
            df[col] = df[col].fillna(0)
    # 数値列: train の中央値で補完（リーク防止のため train の値を再利用）
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if num_medians is None:
        num_medians = df[num_cols].median()
    df[num_cols] = df[num_cols].fillna(num_medians)
    # カテゴリ列: train の最頻値で補完
    cat_cols = df.select_dtypes(include=["object"]).columns.tolist()
    if cat_modes is None:
        cat_modes = df[cat_cols].mode().iloc[0]
    for col in cat_cols:
        df[col] = df[col].fillna(cat_modes[col])
    return df, num_medians, cat_modes

train_data, num_medians, cat_modes = fill_missing(train_data)
test_data,  _,           _         = fill_missing(test_data, num_medians, cat_modes)


## 特徴量エンジニアリング
def add_features(df):
    df = df.copy()
    # 総床面積（地下室 + 1階 + 2階）: 住宅の大きさを総合的に表す
    df["TotalSF"] = df["TotalBsmtSF"] + df["1stFlrSF"] + df["2ndFlrSF"]
    # バスルームの合計（フル=1、ハーフ=0.5 で換算）
    df["TotalBath"] = (df["FullBath"] + 0.5 * df["HalfBath"]
                       + df["BsmtFullBath"] + 0.5 * df["BsmtHalfBath"])
    # 建築からの経過年数（古いほど価値が下がる傾向）
    df["HouseAge"] = df["YrSold"] - df["YearBuilt"]
    # リフォームからの経過年数（最近リフォームほど高価格）
    df["YearsSinceRemod"] = df["YrSold"] - df["YearRemodAdd"]
    # 各設備の有無フラグ
    df["HasGarage"]   = (df["GarageArea"]  > 0).astype(int)
    df["HasBasement"] = (df["TotalBsmtSF"] > 0).astype(int)
    df["Has2ndFlr"]   = (df["2ndFlrSF"]    > 0).astype(int)
    df["HasFireplace"] = (df["Fireplaces"]  > 0).astype(int)
    # 屋外スペースの合計面積
    df["TotalPorchSF"] = (df["OpenPorchSF"] + df["EnclosedPorch"]
                          + df["3SsnPorch"] + df["ScreenPorch"] + df["WoodDeckSF"])
    # 品質 × 居住面積の交互作用（広くて品質が高いほど高価格）
    df["QualArea"] = df["OverallQual"] * df["GrLivArea"]
    return df

train_feat = add_features(train_data)
test_feat  = add_features(test_data)


## 使用する特徴量の定義
# 数値特徴量
NUM_FEATURES = [
    # 面積系
    "LotArea", "GrLivArea", "TotalBsmtSF", "1stFlrSF", "2ndFlrSF",
    "GarageArea", "WoodDeckSF", "OpenPorchSF", "MasVnrArea",
    # 派生面積
    "TotalSF", "TotalPorchSF",
    # 品質・状態
    "OverallQual", "OverallCond",
    # 年・築年数
    "YearBuilt", "YearRemodAdd", "HouseAge", "YearsSinceRemod",
    # 部屋数・設備数
    "TotRmsAbvGrd", "BedroomAbvGr", "Fireplaces", "GarageCars",
    "FullBath", "HalfBath", "BsmtFullBath",
    # 派生特徴量
    "TotalBath", "QualArea",
    # フラグ
    "HasGarage", "HasBasement", "Has2ndFlr", "HasFireplace",
]

# カテゴリ特徴量（One-Hot エンコードする）
CAT_FEATURES = [
    "Neighborhood",   # 地区（価格帯に最も影響）
    "MSZoning",       # 用途地域
    "BldgType",       # 建物種別
    "HouseStyle",     # 住宅スタイル
    "ExterQual",      # 外壁品質
    "KitchenQual",    # キッチン品質
    "BsmtQual",       # 地下室品質
    "GarageType",     # ガレージ種別
    "Foundation",     # 基礎の種類
    "SaleCondition",  # 売買状況
]

# One-Hot エンコード（train+test を結合してダミー変数化し、列を統一）
all_feat   = pd.concat([train_feat[NUM_FEATURES + CAT_FEATURES],
                         test_feat[NUM_FEATURES + CAT_FEATURES]], ignore_index=True)
all_feat   = pd.get_dummies(all_feat, columns=CAT_FEATURES)
n_train    = len(train_feat)
X          = all_feat.iloc[:n_train].copy()
X_test     = all_feat.iloc[n_train:].copy()

# 目的変数: SalePrice を対数変換（右歪み分布の緩和）
y = np.log1p(train_data["SalePrice"])


## 各モデルの RandomizedSearchCV 設定
param_dists = {
    "RandomForest": (
        RandomForestRegressor(random_state=1),
        {
            "n_estimators": randint(100, 600),
            "max_depth": randint(5, 25),
            "min_samples_split": randint(2, 12),
            "min_samples_leaf": randint(1, 6),
            "max_features": uniform(0.2, 0.6),
        },
    ),
    "XGBoost": (
        XGBRegressor(random_state=1, verbosity=0),
        {
            "n_estimators": randint(100, 600),
            "max_depth": randint(2, 9),
            "learning_rate": uniform(0.01, 0.29),
            "subsample": uniform(0.5, 0.5),
            "colsample_bytree": uniform(0.5, 0.5),
            "reg_alpha": uniform(0, 1),
            "reg_lambda": uniform(0.5, 2),
        },
    ),
    "LightGBM": (
        LGBMRegressor(random_state=1, verbosity=-1),
        {
            "n_estimators": randint(100, 600),
            "max_depth": randint(2, 9),
            "learning_rate": uniform(0.01, 0.29),
            "num_leaves": randint(15, 63),
            "subsample": uniform(0.5, 0.5),
            "reg_alpha": uniform(0, 1),
            "reg_lambda": uniform(0.5, 2),
        },
    ),
}

## 各モデルを RandomizedSearchCV でチューニングし CV RMSE で比較
tuned_models = {}
best_model   = None
best_score   = -np.inf

for name, (estimator, param_dist) in param_dists.items():
    gs = RandomizedSearchCV(
        estimator, param_dist, n_iter=50, cv=5,
        scoring="neg_root_mean_squared_error", n_jobs=-1, random_state=1
    )
    gs.fit(X, y)
    mean_score = gs.best_score_
    print(f"{name}: CV RMSE={-mean_score:.4f}  best_params={gs.best_params_}")
    tuned_models[name] = gs.best_estimator_
    if mean_score > best_score:
        best_score = mean_score
        best_model = gs.best_estimator_

## チューニング済みの3モデルで VotingRegressor を構成し比較
voting = VotingRegressor(
    estimators=[(name, m) for name, m in tuned_models.items()]
)
voting_scores = cross_val_score(voting, X, y, cv=5, scoring="neg_root_mean_squared_error")
voting_mean   = voting_scores.mean()
print(f"VotingRegressor: CV RMSE={-voting_mean:.4f}")
if voting_mean > best_score:
    best_score = voting_mean
    voting.fit(X, y)
    best_model = voting

print(f"\n最良モデル: {best_model.__class__.__name__}  CV RMSE={-best_score:.4f}")

## 最良モデルで予測
if not isinstance(best_model, VotingRegressor):
    best_model.fit(X, y)
predictions = np.expm1(best_model.predict(X_test))

## 提出ファイルの出力
output = pd.DataFrame({"Id": test_data["Id"], "SalePrice": predictions})
output.to_csv(os.path.join(os.path.dirname(__file__), "submission.csv"), index=False)
print(output.head())
print("submission.csv を出力しました")
