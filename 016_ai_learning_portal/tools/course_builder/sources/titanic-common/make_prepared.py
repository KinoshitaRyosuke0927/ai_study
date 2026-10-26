"""講座3・4 で使う特徴量の表(train_prepared.csv / test_prepared.csv)を作る。
講座2(titanic-features)の単元5「前処理を関数にまとめる」と同じ前処理(コードも同じ)。
使い方: train.csv / test.csv を作業ディレクトリに置いて実行し、出力された CSV を保存する。
"""
import numpy as np
import pandas as pd

train = pd.read_csv("train.csv")
test = pd.read_csv("test.csv")


def extract_title(name):
    """名前から敬称を取り出し、主な 4 つ以外を Rare にまとめる"""
    title = name.str.extract(r",\s*([^.]+)\.")[0]
    title = title.replace({"Mlle": "Miss", "Ms": "Miss", "Mme": "Mrs"})
    return title.where(title.isin(["Mr", "Mrs", "Miss", "Master"]), "Rare").rename("Title")


age_by_title = train.groupby(extract_title(train["Name"]))["Age"].median()
fare_median = train["Fare"].median()
embarked_mode = train["Embarked"].mode()[0]


def preprocess(df):
    """元のデータ df から、モデルに入れる特徴量の表を作って返す"""
    out = pd.DataFrame({"PassengerId": df["PassengerId"]})
    out["Pclass"] = df["Pclass"]
    out["SibSp"] = df["SibSp"]
    out["Parch"] = df["Parch"]
    out["Sex"] = (df["Sex"] == "female").astype(int)
    title = extract_title(df["Name"])
    out["Age"] = df["Age"].fillna(title.map(age_by_title))
    out["LogFare"] = np.log1p(df["Fare"].fillna(fare_median))
    out["HasCabin"] = df["Cabin"].notna().astype(int)
    out["FamilySize"] = df["SibSp"] + df["Parch"] + 1
    out["IsAlone"] = (out["FamilySize"] == 1).astype(int)
    embarked = pd.get_dummies(df["Embarked"].fillna(embarked_mode), prefix="Embarked", dtype=int)
    titles = pd.get_dummies(title, prefix="Title", dtype=int)
    return pd.concat([out, embarked, titles], axis=1)


train_prepared = preprocess(train)
test_prepared = preprocess(test).reindex(columns=train_prepared.columns, fill_value=0)
train_out = train_prepared.copy()
train_out["Survived"] = train["Survived"]
train_out.to_csv("train_prepared.csv", index=False)
test_prepared.to_csv("test_prepared.csv", index=False)
print(train_out.shape, test_prepared.shape)
