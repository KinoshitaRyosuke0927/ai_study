"""講座3・4 の構成を決めるための、モデルの精度の確認(test の正解は手本の確認用にだけ使う)。"""
import time
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold, GridSearchCV
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import accuracy_score, roc_auc_score
import lightgbm as lgb

exec(open("pipeline_def.py").read())
X = Xtr.drop(columns=["PassengerId"]); y = train["Survived"]
Xt = Xte.drop(columns=["PassengerId"])
ans = pd.read_csv("test_answers.csv")["Survived"].to_numpy()
Xa, Xv, ya, yv = train_test_split(X, y, test_size=0.25, random_state=0, stratify=y)
cv = StratifiedKFold(5, shuffle=True, random_state=0)
models = {
    "logreg": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)),
    "tree3": DecisionTreeClassifier(max_depth=3, random_state=0),
    "tree_full": DecisionTreeClassifier(random_state=0),
    "rf": RandomForestClassifier(n_estimators=200, random_state=0),
    "rf_d6": RandomForestClassifier(n_estimators=200, max_depth=6, random_state=0),
    "gb": GradientBoostingClassifier(random_state=0),
    "lgb": lgb.LGBMClassifier(n_estimators=200, learning_rate=0.05, num_leaves=15, verbose=-1, random_state=0),
}
for name, m in models.items():
    t = time.time()
    m.fit(Xa, ya)
    tr_acc = accuracy_score(ya, m.predict(Xa)); va = accuracy_score(yv, m.predict(Xv))
    cvs = cross_val_score(m, X, y, cv=cv).mean()
    m.fit(X, y); te = accuracy_score(ans, m.predict(Xt))
    print(f"{name:10s} train {tr_acc:.3f} valid {va:.3f} cv {cvs:.3f} test {te:.3f} ({time.time()-t:.1f}s)")
print("baseline valid", round((yv == 0).mean(), 3), "test", round((ans == 0).mean(), 3))
