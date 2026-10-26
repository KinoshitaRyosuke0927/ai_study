"""講座2〜4 で共通に使う前処理(特徴量の定義)の試作と、数値の確認。"""
import numpy as np
import pandas as pd

train = pd.read_csv("train.csv")
test = pd.read_csv("test.csv")

def title_of(name):
    return name.str.extract(r",\s*([^.]+)\.")[0]

for df in (train, test):
    df["Title"] = title_of(df["Name"])
print("train titles", train.Title.value_counts().to_dict())
print("test titles", test.Title.value_counts().to_dict())

TITLE_MAP = {"Mlle": "Miss", "Ms": "Miss", "Mme": "Mrs"}
MAIN = ["Mr", "Mrs", "Miss", "Master"]
def group_title(t):
    t = t.replace(TITLE_MAP)
    return t.where(t.isin(MAIN), "Rare")
for df in (train, test):
    df["Title"] = group_title(df["Title"])
print("grouped", train.Title.value_counts().to_dict(), test.Title.value_counts().to_dict())

# 学習用から求める値
age_by_title = train.groupby("Title")["Age"].median()
fare_median = train["Fare"].median()
emb_mode = train["Embarked"].mode()[0]
print("age by title", age_by_title.to_dict(), "fare median", fare_median, "embarked mode", emb_mode)
print("age overall median", train.Age.median(), "mean", round(train.Age.mean(), 2))
print("train Embarked missing", train.Embarked.isna().sum(), "test", test.Embarked.isna().sum(), "Fare missing", train.Fare.isna().sum(), test.Fare.isna().sum())

def preprocess(df):
    out = pd.DataFrame({"PassengerId": df["PassengerId"]})
    out["Pclass"] = df["Pclass"]
    out["Sex"] = (df["Sex"] == "female").astype(int)
    out["Age"] = df["Age"].fillna(df["Title"].map(age_by_title))
    out["SibSp"] = df["SibSp"]
    out["Parch"] = df["Parch"]
    out["LogFare"] = np.log1p(df["Fare"].fillna(fare_median))
    out["HasCabin"] = df["Cabin"].notna().astype(int)
    out["FamilySize"] = df["SibSp"] + df["Parch"] + 1
    out["IsAlone"] = (out["FamilySize"] == 1).astype(int)
    emb = pd.get_dummies(df["Embarked"].fillna(emb_mode), prefix="Embarked", dtype=int)
    tit = pd.get_dummies(df["Title"], prefix="Title", dtype=int)
    out = pd.concat([out, emb, tit], axis=1)
    return out

Xtr = preprocess(train); Xte = preprocess(test)
print(Xtr.shape, Xte.shape, list(Xtr.columns))
print("same cols", list(Xtr.columns) == list(Xte.columns), "nan", Xtr.isna().sum().sum(), Xte.isna().sum().sum())
print(Xtr.head(3).to_string())
print(Xtr.describe().round(2).T)
Xtr["Survived"] = train["Survived"]
print(Xtr.drop(columns="PassengerId").corr()["Survived"].round(3).sort_values())
print(Xtr.groupby("IsAlone").Survived.mean().round(3), Xtr.groupby("HasCabin").Survived.mean().round(3))
print(Xtr.groupby(train.Title).Survived.agg(["mean","count"]).round(3))
