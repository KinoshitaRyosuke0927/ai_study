import os

from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.model_selection import RandomizedSearchCV, cross_val_score
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
from scipy.stats import randint, uniform

import pandas as pd

"""
https://www.kaggle.com/competitions/spaceship-titanic/overview
特徴量: Age, TotalSpend (アメニティ支出合計) の2つを使用。
EDAの結果、冷凍睡眠中の乗客はアメニティを使えないため支出0が多く、
TotalSpend と転送有無に強い関係があることが確認された。
"""

DATA_DIR = r"C:\azure_ai\education\005_kaggle\competitions\spaceship-titanic"

## データの読み込み
train_data = pd.read_csv(os.path.join(DATA_DIR, "train.csv"))
test_data  = pd.read_csv(os.path.join(DATA_DIR, "test.csv"))

## 特徴量エンジニアリング
AMENITIES = ["RoomService", "FoodCourt", "ShoppingMall", "Spa", "VRDeck"]

def add_features(df):
    df = df.copy()
    df["TotalSpend"] = df[AMENITIES].sum(axis=1)
    return df

train_feat = add_features(train_data)
test_feat  = add_features(test_data)

## 特徴量と目的変数の定義
features = ["Age", "TotalSpend"]

# 欠損値を各列の中央値で補完
medians = train_feat[features].median()
X      = train_feat[features].fillna(medians)
X_test = test_feat[features].fillna(medians)

y = train_data["Transported"].astype(int)

## 各モデルの RandomizedSearchCV 設定
model_candidates = {
    "RandomForest": (
        RandomForestClassifier(random_state=1),
        {
            "n_estimators": randint(100, 600),
            "max_depth": randint(3, 12),
            "min_samples_split": randint(2, 12),
            "min_samples_leaf": randint(1, 6),
            "max_features": uniform(0.3, 0.7),
        },
    ),
    "XGBoost": (
        XGBClassifier(random_state=1, eval_metric="logloss", verbosity=0),
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
        LGBMClassifier(random_state=1, verbosity=-1),
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
tuned_models = {}
best_model   = None
best_score   = 0.0

print("学習開始")
for name, (estimator, param_dist) in model_candidates.items():
    inner_cv = RandomizedSearchCV(
        estimator, param_dist, n_iter=100, cv=5,
        scoring="accuracy", n_jobs=-1, random_state=1,
    )
    outer_scores = cross_val_score(inner_cv, X, y, cv=5, scoring="accuracy")
    mean_score   = outer_scores.mean()
    print(f"{name}: Nested CV accuracy={mean_score:.4f} ± {outer_scores.std():.4f}")
    inner_cv.fit(X, y)
    tuned_models[name] = inner_cv.best_estimator_
    if mean_score > best_score:
        best_score = mean_score
        best_model = inner_cv.best_estimator_

## VotingClassifier（ソフト投票）: チューニング済みの3モデルをアンサンブル
voting = VotingClassifier(
    estimators=[(name, model) for name, model in tuned_models.items()],
    voting="soft",
)
voting_scores = cross_val_score(voting, X, y, cv=5, scoring="accuracy")
voting_mean   = voting_scores.mean()
print(f"VotingClassifier: Nested CV accuracy={voting_mean:.4f} ± {voting_scores.std():.4f}")
if voting_mean > best_score:
    best_score = voting_mean
    voting.fit(X, y)
    best_model = voting

print(f"\n最良モデル: {best_model.__class__.__name__}  CV accuracy={best_score:.4f}")

## 最良モデルで予測・提出ファイル出力
predictions = best_model.predict(X_test)
output = pd.DataFrame({
    "PassengerId": test_data["PassengerId"],
    "Transported": predictions.astype(bool),
})
output.to_csv(os.path.join(os.path.dirname(__file__), "submission.csv"), index=False)
print(output.head())
print("submission.csv を出力しました")
