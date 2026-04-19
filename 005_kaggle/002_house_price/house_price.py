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
"""

DATA_DIR = r"C:\azure_ai\education\005_kaggle\competitions\house-prices-advanced-regression-techniques"

## データの読み込み
train_data = pd.read_csv(os.path.join(DATA_DIR, "train.csv"))
test_data  = pd.read_csv(os.path.join(DATA_DIR, "test.csv"))

## 特徴量エンジニアリング（LotArea・YearRemodAdd の加工のみ）
def add_features(df):
    df = df.copy()
    # リフォームからの経過年数（売却年の中央値 2007 年基準）
    df["YearsSinceRemod"] = 2007 - df["YearRemodAdd"]
    # 敷地面積の対数変換（外れ値の影響を緩和）
    df["LotArea_log"] = np.log1p(df["LotArea"])
    # 面積 × リフォーム年の交互作用（広くて新しいほど高価格）
    df["Area_x_RemodYear"] = df["LotArea"] * df["YearRemodAdd"]
    return df

train_feat = add_features(train_data)
test_feat  = add_features(test_data)

features = ["LotArea", "YearRemodAdd", "YearsSinceRemod", "LotArea_log", "Area_x_RemodYear"]
# SalePrice : 販売価格($) — 右歪み分布のため対数変換して学習する
y = np.log1p(train_data["SalePrice"])
X      = train_feat[features]
X_test = test_feat[features]

## 各モデルの RandomizedSearchCV 設定
param_dists = {
    "RandomForest": (
        RandomForestRegressor(random_state=1),
        {
            "n_estimators": randint(100, 600),
            "max_depth": randint(3, 20),
            "min_samples_split": randint(2, 12),
            "min_samples_leaf": randint(1, 6),
            "max_features": uniform(0.3, 0.7),
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

## 各モデルを RandomizedSearchCV でチューニングし CV スコアで比較
# neg_root_mean_squared_error: 大きいほど良い（-RMSE のため符号を反転して表示）
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

# 最良モデルが VotingRegressor 以外の場合は全データで再学習済みのため予測のみ
if not isinstance(best_model, VotingRegressor):
    best_model.fit(X, y)
# 予測値を対数変換前のスケール（ドル）に戻す
predictions = np.expm1(best_model.predict(X_test))

## 提出ファイルの出力
output = pd.DataFrame({"Id": test_data["Id"], "SalePrice": predictions})
output.to_csv(os.path.join(os.path.dirname(__file__), "submission.csv"), index=False)
print(output.head())
print("submission.csv を出力しました")
