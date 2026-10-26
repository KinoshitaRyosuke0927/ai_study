"""タイタニック講座のデータファイル(train.csv / test.csv)を作る。

元データ: titanic3.csv(https://hbiostat.org/data/repo/titanic3.csv)
  Data obtained from http://hbiostat.org/data courtesy of the Vanderbilt University Department of Biostatistics.
  Thomas Cason(University of Virginia)が Encyclopedia Titanica をもとに作成(1999年8月2日時点)。

Kaggle のタイタニックと同じ形にそろえる:
- 1309 人を乱数で並べ替え、891 人を train.csv(正解 Survived あり)、418 人を test.csv(正解なし)にする
- 列名は Kaggle と同じ(PassengerId, Survived, Pclass, Name, Sex, Age, SibSp, Parch, Ticket, Fare, Cabin, Embarked)
- titanic3 にしかない列(Boat, Body, HomeDest)は train.csv だけに残す。
  Boat・Body は事故の後に決まる情報(リーク)で、予測の時点では手に入らないため test.csv には含めない
使い方: node tools/course_builder/run-py.mjs tools/course_builder/sources/titanic-common/make_data.py --save-csv
(titanic3.csv はこのスクリプトと同じフォルダに置き、作業ディレクトリに読み込ませるため data/ にも置く)
"""
import numpy as np
import pandas as pd

raw = pd.read_csv("titanic3.csv")
df = raw.rename(columns={
    "pclass": "Pclass", "survived": "Survived", "name": "Name", "sex": "Sex", "age": "Age",
    "sibsp": "SibSp", "parch": "Parch", "ticket": "Ticket", "fare": "Fare", "cabin": "Cabin",
    "embarked": "Embarked", "boat": "Boat", "body": "Body", "home.dest": "HomeDest",
})
# 乱数で並べ替えて train / test に分け、PassengerId を振る(train が 1〜891、test が 892〜1309)
order = np.random.default_rng(2026).permutation(len(df))
df = df.iloc[order].reset_index(drop=True)
df.insert(0, "PassengerId", np.arange(1, len(df) + 1))
cols = ["PassengerId", "Survived", "Pclass", "Name", "Sex", "Age", "SibSp", "Parch", "Ticket", "Fare", "Cabin", "Embarked"]
train = df.iloc[:891][cols + ["Boat", "Body", "HomeDest"]]
test = df.iloc[891:][[c for c in cols if c != "Survived"]]
train.to_csv("train.csv", index=False)
test.to_csv("test.csv", index=False)
# 正解(講座には含めない。手本の確認用)
df.iloc[891:][["PassengerId", "Survived"]].to_csv("test_answers.csv", index=False)
print("train", train.shape, "生存率", round(train.Survived.mean(), 4))
print("test", test.shape, "生存率(確認用)", round(df.iloc[891:].Survived.mean(), 4))
print(train.isna().sum().to_dict())
