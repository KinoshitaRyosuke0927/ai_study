import time

from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.model_selection import RandomizedSearchCV, cross_val_score
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
from scipy.stats import randint, uniform

import pandas as pd

"""
https://www.kaggle.com/competitions/titanic/overview
"""


## データの読み込み
train_data = pd.read_csv(r"C:\azure_ai\education\005_kaggle\competitions\titanic\train.csv")
test_data  = pd.read_csv(r"C:\azure_ai\education\005_kaggle\competitions\titanic\test.csv")

## 特徴量を4つに固定
features = ["Pclass", "Sex", "SibSp", "Parch"]
y      = train_data["Survived"]
X      = pd.get_dummies(train_data[features])
X_test = pd.get_dummies(test_data[features])
X_test = X_test.reindex(columns=X.columns, fill_value=0)

## モデルごとの RandomizedSearchCV 設定
model_candidates = {
    "RandomForest": (
        # ランダムフォレストによるクラス分類
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

## 各モデルを Nested CV で評価し、全データで最終チューニング
# 内側CV(RandomizedSearchCV, n_iter=100): 広いパラメータ空間を効率探索
# 外側CV(cross_val_score): モデル選択バイアスのない汎化性能の推定
tuned_models = {}
best_model   = None
best_score   = 0.0

print("学習開始")
_start = time.time()

for name, (estimator, param_dist) in model_candidates.items():
    inner_cv = RandomizedSearchCV(
        estimator, param_dist, n_iter=100, cv=5,
        scoring="accuracy", n_jobs=-1, random_state=1
    )
    outer_scores = cross_val_score(inner_cv, X, y, cv=5, scoring="accuracy")
    mean_score   = outer_scores.mean()
    print(f"{name}: Nested CV accuracy={mean_score:.4f} ± {outer_scores.std():.4f}")
    # 全データで改めてチューニングし、最終モデルを確定
    inner_cv.fit(X, y)
    tuned_models[name] = inner_cv.best_estimator_
    if mean_score > best_score:
        best_score = mean_score
        best_model = inner_cv.best_estimator_

## VotingClassifier（ソフト投票）: チューニング済みの3モデルをアンサンブル
# ソフト投票は各モデルの予測確率を平均し、最も確率が高いクラスを選択する
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

print(f"\n学習完了(s): {time.time() - _start:.1f}")
print(f"最良モデル: {best_model.__class__.__name__}  CV accuracy={best_score:.4f}")

## 最良モデルで予測・提出ファイル出力
predictions = best_model.predict(X_test)
output = pd.DataFrame({"PassengerId": test_data.PassengerId, "Survived": predictions})
output.to_csv("submission.csv", index=False)
print("Your submission was successfully saved!")
