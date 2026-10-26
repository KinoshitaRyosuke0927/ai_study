"""講座4(精度の改善と提出ファイルの作成)の数値の確認。test の正解は手本の確認用にだけ使う。"""
import time
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import GridSearchCV, StratifiedKFold, cross_val_score
from sklearn.ensemble import RandomForestClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.inspection import permutation_importance

df = pd.read_csv("train_prepared.csv"); te = pd.read_csv("test_prepared.csv")
ans = pd.read_csv("test_answers.csv")
X = df.drop(columns=["PassengerId", "Survived"]); y = df["Survived"]; Xt = te.drop(columns=["PassengerId"])
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)
def tacc(m):
    return round((m.predict(Xt) == ans.Survived.to_numpy()).mean(), 3)
s = time.time()
gs = GridSearchCV(RandomForestClassifier(n_estimators=100, random_state=0), {"max_depth": [3, 5, 7], "min_samples_leaf": [1, 3, 5]}, cv=cv)
gs.fit(X, y)
print("u1 rf grid", gs.best_params_, round(gs.best_score_, 3), f"{time.time()-s:.1f}s", "test", tacc(gs.best_estimator_))
print(pd.DataFrame(gs.cv_results_)[["param_max_depth", "param_min_samples_leaf", "mean_test_score"]].round(3).to_string())
s = time.time()
gt = GridSearchCV(DecisionTreeClassifier(random_state=0), {"max_depth": [2, 3, 4, 5, 6], "min_samples_leaf": [1, 5, 10, 20]}, cv=cv).fit(X, y)
print("u1 tree grid", gt.best_params_, round(gt.best_score_, 3), f"{time.time()-s:.1f}s")
# u2 LightGBM
for params in ({}, {"n_estimators": 100, "learning_rate": 0.05, "num_leaves": 15}, {"n_estimators": 200, "learning_rate": 0.05, "num_leaves": 15}, {"n_estimators": 100, "learning_rate": 0.1, "num_leaves": 7}, {"n_estimators": 300, "learning_rate": 0.02, "num_leaves": 7}, {"n_estimators": 100, "learning_rate": 0.05, "num_leaves": 7, "min_child_samples": 20}):
    s = time.time()
    m = lgb.LGBMClassifier(random_state=0, verbose=-1, **params)
    sc = cross_val_score(m, X, y, cv=cv)
    m.fit(X, y)
    print("u2 lgb", params, round(sc.mean(), 3), round(sc.std(), 3), f"{time.time()-s:.1f}s", "test", tacc(m))
for lr in (0.01, 0.05, 0.1, 0.3):
    sc = cross_val_score(lgb.LGBMClassifier(n_estimators=100, learning_rate=lr, num_leaves=7, random_state=0, verbose=-1), X, y, cv=cv)
    print("u2 lr", lr, round(sc.mean(), 3))
# u3 features
rf = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=0)
base = cross_val_score(rf, X, y, cv=cv).mean()
print("u3 base", round(base, 3))
for drop in (["Embarked_C", "Embarked_Q", "Embarked_S"], ["SibSp", "Parch"], ["IsAlone"], ["Age"], ["Title_Master", "Title_Miss", "Title_Mr", "Title_Mrs", "Title_Rare"]):
    print("u3 drop", drop, round(cross_val_score(rf, X.drop(columns=drop), y, cv=cv).mean(), 3))
X2 = X.copy(); X2["IsChild"] = (X2.Age < 16).astype(int)
print("u3 +IsChild", round(cross_val_score(rf, X2, y, cv=cv).mean(), 3))
X3 = X.copy(); X3["SexPclass"] = X3.Sex * X3.Pclass
print("u3 +SexPclass", round(cross_val_score(rf, X3, y, cv=cv).mean(), 3))
lr = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
print("u3 lr base", round(cross_val_score(lr, X, y, cv=cv).mean(), 3), "+SexPclass", round(cross_val_score(lr, X3, y, cv=cv).mean(), 3))
rf.fit(X, y)
pi = permutation_importance(rf, X, y, n_repeats=5, random_state=0)
print(pd.Series(pi.importances_mean, index=X.columns).round(3).sort_values(ascending=False).head(8))
# u4 pipeline
print("u4 lr nopipe", round(cross_val_score(LogisticRegression(max_iter=1000), X, y, cv=cv).mean(), 3), "pipe", round(cross_val_score(lr, X, y, cv=cv).mean(), 3))
gp = GridSearchCV(lr, {"logisticregression__C": [0.01, 0.1, 1, 10]}, cv=cv).fit(X, y)
print("u4 pipe grid", gp.best_params_, round(gp.best_score_, 3), "test", tacc(gp.best_estimator_))
for C in (0.01, 0.1, 1, 10):
    print(" C", C, round(cross_val_score(make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=1000)), X, y, cv=cv).mean(), 3))
# u5 final
fin = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=0).fit(X, y)
pred = fin.predict(Xt)
print("u5 final rf5 test", tacc(fin), "survived pred", pred.sum(), "rate", round(pred.mean(), 3))
