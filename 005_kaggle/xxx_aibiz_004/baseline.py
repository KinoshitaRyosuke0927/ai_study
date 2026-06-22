import numpy as np
import pandas as pd

from sklearn.svm import LinearSVC
from scipy.sparse import hstack, csr_matrix
from sklearn.metrics import f1_score
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import StratifiedKFold
from sklearn.feature_extraction.text import TfidfVectorizer


# データ読み込み
train = pd.read_csv("create/train_data_v2.csv", encoding="utf-8-sig")
test  = pd.read_csv("create/test_data_channel_name_v2.csv", encoding="utf-8-sig")

## 特徴量エンジニアリング
# title を文字 n-gram TF-IDF でベクトル化
tfidf = TfidfVectorizer(
    analyzer="char",
    ngram_range=(2, 3),
    max_features=30000,
    sublinear_tf=True,
)
title_train = tfidf.fit_transform(train["title"].fillna(""))
title_test  = tfidf.transform(test["title"].fillna(""))

# 投稿日時から時間帯・曜日・月・年を抽出
def extract_dt(df):
    dt = pd.to_datetime(df["date"] + " " + df["time"], errors="coerce")
    return pd.DataFrame({
        "hour":      dt.dt.hour.fillna(0).astype(int),
        "dayofweek": dt.dt.dayofweek.fillna(0).astype(int),
        "month":     dt.dt.month.fillna(0).astype(int),
        "year":      dt.dt.year.fillna(0).astype(int),
    })

dt_train = extract_dt(train)
dt_test  = extract_dt(test)

# 再生数は対数変換してスケールを抑える
log_views_train = np.log1p(pd.to_numeric(train["views"], errors="coerce").fillna(0).values).reshape(-1, 1)
log_views_test  = np.log1p(pd.to_numeric(test["views"],  errors="coerce").fillna(0).values).reshape(-1, 1)

# カテゴリを数値コードに変換
cat_all    = pd.Categorical(pd.concat([train["category"], test["category"]]).fillna("unknown"))
cat_train  = cat_all[:len(train)].codes.reshape(-1, 1)
cat_test   = cat_all[len(train):].codes.reshape(-1, 1)

# TF-IDF + 数値特徴量を結合
num_train = np.hstack([dt_train.values, log_views_train, cat_train])
num_test  = np.hstack([dt_test.values,  log_views_test,  cat_test])
X_train = hstack([title_train, csr_matrix(num_train)])
X_test  = hstack([title_test,  csr_matrix(num_test)])

## 目的変数
le = LabelEncoder()
y_train = le.fit_transform(train["channel_name"])

## 層化 CV で Macro F1 を評価
skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
cv_scores = []
model = LinearSVC(C=1.0, max_iter=2000, random_state=42)
for fold, (tr_idx, val_idx) in enumerate(skf.split(X_train, y_train)):
    X_tr, X_val = X_train[tr_idx], X_train[val_idx]
    y_tr, y_val = y_train[tr_idx], y_train[val_idx]
    model.fit(X_tr, y_tr)
    score = f1_score(y_val, model.predict(X_val), average="macro")
    cv_scores.append(score)
    print(f"  Fold {fold + 1} Val Macro F1: {score:.4f}")

print(f"CV Macro F1: {np.mean(cv_scores):.4f} ± {np.std(cv_scores):.4f}")

## 学習・予測
model.fit(X_train, y_train)
y_pred = le.inverse_transform(model.predict(X_test))

# 提出ファイル生成
submission = pd.DataFrame({"channel_name": y_pred})
submission.to_csv("submission.csv", index=False, encoding="utf-8-sig")
print(f"\n予測完了: submission.csv ({len(submission)}件)")
