"""講座1 単元4〜6 の数値の確認。"""
import pandas as pd
tr = pd.read_csv("train.csv")
print(pd.crosstab(tr.Embarked, tr.Pclass, normalize="index").round(3))
print(pd.crosstab(tr.Sex, tr.Survived, normalize="index").round(3))
print(tr.pivot_table(index="Sex", columns="Pclass", values="Survived", aggfunc="mean").round(3))
print(tr.pivot_table(index="Embarked", columns="Pclass", values="Survived", aggfunc="mean").round(3))
print(tr.groupby("Embarked").Survived.agg(["mean", "count"]).round(3))
print(tr.groupby("Survived").Age.describe().round(2))
print(tr.groupby(pd.cut(tr.Age, [0, 10, 20, 40, 60, 80]), observed=True).Survived.agg(["mean", "count"]).round(3))
print(tr.groupby(pd.cut(tr.Age, [0, 16, 32, 48, 64, 80]), observed=True).Survived.agg(["mean", "count"]).round(3))
print(tr.groupby(pd.qcut(tr.Fare, 5), observed=True).Survived.agg(["mean", "count"]).round(3))
tr["Child"] = tr.Age < 16
print(tr.pivot_table(index="Child", columns="Sex", values="Survived", aggfunc="mean").round(3))
print(tr.groupby(["Sex", tr.Age < 16]).Survived.agg(["mean","count"]).round(3))
fam = tr.SibSp + tr.Parch + 1
tr["FamilySize"] = fam
tr["FamilyGroup"] = pd.cut(fam, [0, 1, 4, 11], labels=["alone", "small", "large"])
print(tr.groupby("FamilyGroup", observed=True).Survived.agg(["mean","count"]).round(3))
print(tr.groupby("Parch").Survived.agg(["mean","count"]).round(3))
print(tr.groupby("SibSp").Survived.agg(["mean","count"]).round(3))
t = tr.Name.str.extract(r",\s*([^.]+)\.")[0]
print(tr.groupby(t).Survived.agg(["mean","count"]).sort_values("count", ascending=False).head(6).round(3))
print(tr[["Survived","Pclass","Age","SibSp","Parch","Fare"]].corr()["Survived"].round(3))
print("Boat あり", tr.Boat.notna().mean().round(3), tr.groupby(tr.Boat.notna()).Survived.mean().round(3).to_dict())
