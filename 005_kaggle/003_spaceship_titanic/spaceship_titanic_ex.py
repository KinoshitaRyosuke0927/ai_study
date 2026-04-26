import os

from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.model_selection import RandomizedSearchCV, cross_val_score
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
from scipy.stats import randint, uniform

import numpy as np
import pandas as pd

"""
https://www.kaggle.com/competitions/spaceship-titanic/overview
spaceship_titanic_ex.py の改善版。
改善1: 年齢層・交互作用・グループ同一Cabin等の特徴量を追加
改善2: グループ内の他メンバーの値で欠損を補完（家族なら同じ惑星・Cabinのはず）
"""

DATA_DIR = r"C:\azure_ai\education\005_kaggle\competitions\spaceship-titanic"
AMENITIES = ["RoomService", "FoodCourt", "ShoppingMall", "Spa", "VRDeck"]

## データの読み込み
train_data = pd.read_csv(os.path.join(DATA_DIR, "train.csv"))
test_data  = pd.read_csv(os.path.join(DATA_DIR, "test.csv"))

## 改善2: グループ内補完 → 全体統計補完の2段階欠損値処理
def group_fill(df, col):
    """同グループ内の既知の値で欠損を前後補完する"""
    df[col] = df.groupby("Group")[col].transform(lambda x: x.ffill().bfill())
    return df

def fill_missing(df, num_medians=None, cat_modes=None):
    df = df.copy()

    # グループIDを先に作成（グループ補完に使う）
    df["Group"] = df["PassengerId"].str.split("_").str[0]

    # --- 改善2: グループ内補完 ---
    # 同グループの乗客は家族が多く、同じ惑星・目的地・Cabinを共有する傾向がある
    for col in ["HomePlanet", "Destination", "Cabin", "CryoSleep"]:
        group_fill(df, col)

    # CryoSleep=True の乗客はアメニティを利用できないため支出は 0
    cryo_true = df["CryoSleep"] == True
    for col in AMENITIES:
        df.loc[cryo_true, col] = df.loc[cryo_true, col].fillna(0)

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

    # Cabin を Deck / CabinNum / Side に分割
    cabin_split = df["Cabin"].str.split("/", expand=True)
    df["Deck"]     = cabin_split[0]
    df["CabinNum"] = pd.to_numeric(cabin_split[1], errors="coerce")
    df["Side"]     = cabin_split[2]

    # グループ情報
    if "Group" not in df.columns:
        df["Group"] = df["PassengerId"].str.split("_").str[0]
    df["GroupSize"] = df.groupby("Group")["Group"].transform("count")
    df["IsAlone"]   = (df["GroupSize"] == 1).astype(int)

    # --- 改善1: グループ内で同じCabinに乗っているか ---
    # 家族グループが同じ客室ブロックにいるか（行動パターンの類似性）
    df["FamilyInSameCabin"] = (
        df.groupby("Group")["Cabin"].transform("nunique") == 1
    ).astype(int)

    # --- 改善1: 年齢層（子供・ティーン・成人・高齢者） ---
    # 年代によって冷凍睡眠の選択やアメニティ利用パターンが異なる
    df["AgeGroup"] = pd.cut(
        df["Age"],
        bins=[-1, 12, 17, 64, 200],
        labels=["Child", "Teen", "Adult", "Senior"],
    )

    # アメニティ支出合計
    df["TotalSpend"] = df[AMENITIES].sum(axis=1)

    # 支出が 0 かどうかのフラグ
    df["NoSpend"] = (df["TotalSpend"] == 0).astype(int)

    # --- 改善1: CryoSleep × HomePlanet の交互作用 ---
    # EDAより CryoSleep と HomePlanet は共に転送率に強く影響するため
    # 組み合わせることで「Europa かつ CryoSleep=True」などの細かいパターンを捉える
    df["Cryo_x_Planet"] = df["CryoSleep"].astype(str) + "_" + df["HomePlanet"].astype(str)

    return df

train_feat = add_features(train_data)
test_feat  = add_features(test_data)

## 使用する特徴量の定義
NUM_FEATURES = [
    "Age",
    "TotalSpend",
    "RoomService", "FoodCourt", "ShoppingMall", "Spa", "VRDeck",
    "GroupSize",
    "IsAlone",
    "NoSpend",
    "CabinNum",
    "FamilyInSameCabin",
]

CAT_FEATURES = [
    "CryoSleep",
    "HomePlanet",
    "Destination",
    "Deck",
    "Side",
    "VIP",
    "AgeGroup",
    "Cryo_x_Planet",
]

# One-Hot エンコード（train+test を結合してダミー変数化し、列を統一）
all_feat = pd.concat(
    [train_feat[NUM_FEATURES + CAT_FEATURES],
     test_feat[NUM_FEATURES + CAT_FEATURES]],
    ignore_index=True,
)
all_feat = pd.get_dummies(all_feat, columns=CAT_FEATURES)
n_train  = len(train_feat)
X        = all_feat.iloc[:n_train].copy()
X_test   = all_feat.iloc[n_train:].copy()

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

## 各モデルを Nested CV で評価し、全データで最終チューニング
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
    print(f"{name}: Nested CV accuracy={mean_score:.4f} +/- {outer_scores.std():.4f}")
    inner_cv.fit(X, y)
    tuned_models[name] = inner_cv.best_estimator_
    if mean_score > best_score:
        best_score = mean_score
        best_model = inner_cv.best_estimator_

## VotingClassifier（ソフト投票）
voting = VotingClassifier(
    estimators=[(name, model) for name, model in tuned_models.items()],
    voting="soft",
)
voting_scores = cross_val_score(voting, X, y, cv=5, scoring="accuracy")
voting_mean   = voting_scores.mean()
print(f"VotingClassifier: Nested CV accuracy={voting_mean:.4f} +/- {voting_scores.std():.4f}")
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
