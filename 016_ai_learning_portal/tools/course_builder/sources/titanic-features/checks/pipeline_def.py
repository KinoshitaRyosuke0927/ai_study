import numpy as np
import pandas as pd
train = pd.read_csv("train.csv")
test = pd.read_csv("test.csv")
def title_of(name):
    return name.str.extract(r",\s*([^.]+)\.")[0]

for df in (train, test):
    df["Title"] = title_of(df["Name"])



TITLE_MAP = {"Mlle": "Miss", "Ms": "Miss", "Mme": "Mrs"}
MAIN = ["Mr", "Mrs", "Miss", "Master"]
def group_title(t):
    t = t.replace(TITLE_MAP)
    return t.where(t.isin(MAIN), "Rare")
for df in (train, test):
    df["Title"] = group_title(df["Title"])


# 学習用から求める値
age_by_title = train.groupby("Title")["Age"].median()
fare_median = train["Fare"].median()
emb_mode = train["Embarked"].mode()[0]




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
Xte = preprocess(test)
