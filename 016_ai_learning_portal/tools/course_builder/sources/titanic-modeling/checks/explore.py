"""講座3(モデルの学習と評価)の解説・演習に使う数値の確認。"""
import time
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, precision_score, recall_score, f1_score, roc_auc_score

df = pd.read_csv("train_prepared.csv")
X = df.drop(columns=["PassengerId", "Survived"]); y = df["Survived"]
X_tr, X_va, y_tr, y_va = train_test_split(X, y, test_size=0.25, random_state=0, stratify=y)
print("split", X_tr.shape, X_va.shape, "valid 生存率", round(y_va.mean(), 3), "baseline", round((y_va == 0).mean(), 3))
# 単元1
m = LogisticRegression(max_iter=1000).fit(X_tr, y_tr)
print("u1 LR all", round(accuracy_score(y_va, m.predict(X_va)), 3), "train", round(m.score(X_tr, y_tr), 3))
for cols in (["Sex"], ["Sex", "Pclass"], ["Pclass"]):
    m = LogisticRegression(max_iter=1000).fit(X_tr[cols], y_tr)
    print("u1 LR", cols, round(m.score(X_va[cols], y_va), 3))
# 単元2
sc = StandardScaler().fit(X_tr)
m = LogisticRegression(max_iter=1000).fit(sc.transform(X_tr), y_tr)
print("u2 LR scaled", round(m.score(sc.transform(X_va), y_va), 3))
print(pd.Series(m.coef_[0], index=X.columns).round(3).sort_values())
p = m.predict_proba(sc.transform(X_va))[:, 1]
print("u2 proba head", np.round(p[:5], 3), list(y_va[:5]))
for th in (0.3, 0.5, 0.7):
    pred = (p >= th).astype(int)
    print("th", th, "acc", round(accuracy_score(y_va, pred), 3), "pos", pred.sum(), "prec", round(precision_score(y_va, pred), 3), "rec", round(recall_score(y_va, pred), 3))
# 単元3
for d in range(1, 11):
    t = DecisionTreeClassifier(max_depth=d, random_state=0).fit(X_tr, y_tr)
    print("u3 depth", d, round(t.score(X_tr, y_tr), 3), round(t.score(X_va, y_va), 3))
t = DecisionTreeClassifier(random_state=0).fit(X_tr, y_tr)
print("u3 full", round(t.score(X_tr, y_tr), 3), round(t.score(X_va, y_va), 3), "depth", t.get_depth(), "leaves", t.get_n_leaves())
for leaf in (1, 5, 10, 20):
    t = DecisionTreeClassifier(min_samples_leaf=leaf, random_state=0).fit(X_tr, y_tr)
    print("u3 leaf", leaf, round(t.score(X_tr, y_tr), 3), round(t.score(X_va, y_va), 3))
# 単元4
for params in ({"n_estimators": 100}, {"n_estimators": 100, "max_depth": 5}, {"n_estimators": 100, "max_depth": 7}, {"n_estimators": 100, "min_samples_leaf": 5}):
    s = time.time()
    rf = RandomForestClassifier(random_state=0, **params).fit(X_tr, y_tr)
    print("u4 rf", params, round(rf.score(X_tr, y_tr), 3), round(rf.score(X_va, y_va), 3), f"{time.time()-s:.1f}s")
rf = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=0).fit(X_tr, y_tr)
print(pd.Series(rf.feature_importances_, index=X.columns).round(3).sort_values(ascending=False))
# 単元5
t3 = DecisionTreeClassifier(max_depth=3, random_state=0).fit(X_tr, y_tr)
for name, mdl, Xv in (("LR", m, sc.transform(X_va)), ("tree3", t3, X_va), ("rf5", rf, X_va)):
    pred = mdl.predict(Xv); prob = mdl.predict_proba(Xv)[:, 1]
    print("u5", name, confusion_matrix(y_va, pred).tolist(), "acc", round(accuracy_score(y_va, pred), 3), "prec", round(precision_score(y_va, pred), 3), "rec", round(recall_score(y_va, pred), 3), "f1", round(f1_score(y_va, pred), 3), "auc", round(roc_auc_score(y_va, prob), 3))
# 単元6
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)
for name, mdl in (("LR", LogisticRegression(max_iter=1000)), ("tree3", DecisionTreeClassifier(max_depth=3, random_state=0)), ("tree_full", DecisionTreeClassifier(random_state=0)), ("rf5", RandomForestClassifier(n_estimators=100, max_depth=5, random_state=0))):
    s = cross_val_score(mdl, X, y, cv=cv)
    print("u6", name, np.round(s, 3), round(s.mean(), 3), round(s.std(), 3))
