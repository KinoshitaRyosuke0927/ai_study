import time
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import LabelEncoder, StandardScaler
from scipy.sparse import hstack, csr_matrix

def log(msg, start=None):
    elapsed = f"  ({time.time() - start:.1f}s)" if start else ""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}{elapsed}", flush=True)

# データ読み込み
log("データ読み込み...")
t = time.time()
train = pd.read_csv("create/train_data_v2.csv", encoding="utf-8-sig")
test  = pd.read_csv("create/test_data_channel_name_v2.csv", encoding="utf-8-sig")
log(f"完了: train={len(train)}行, test={len(test)}行", t)

## 特徴量エンジニアリング

# [v4変更点1] char n-gram TF-IDF: max_features を 30K → 50K に拡大
log("TF-IDF ベクトル化 (char n-gram)...")
t = time.time()
tfidf_char = TfidfVectorizer(
    analyzer="char",
    ngram_range=(2, 3),
    max_features=50000,
    sublinear_tf=True,
)
title_char_train = tfidf_char.fit_transform(train["title"].fillna(""))
title_char_test  = tfidf_char.transform(test["title"].fillna(""))
log("完了", t)

# [v4追加] word n-gram TF-IDF: チャンネル固有の単語・フレーズを捉える
log("TF-IDF ベクトル化 (word n-gram)...")
t = time.time()
tfidf_word = TfidfVectorizer(
    analyzer="word",
    ngram_range=(1, 2),
    max_features=50000,
    sublinear_tf=True,
)
title_word_train = tfidf_word.fit_transform(train["title"].fillna(""))
title_word_test  = tfidf_word.transform(test["title"].fillna(""))
log("完了", t)

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
cat_all   = pd.Categorical(pd.concat([train["category"], test["category"]]).fillna("unknown"))
cat_train = cat_all[:len(train)].codes.reshape(-1, 1)
cat_test  = cat_all[len(train):].codes.reshape(-1, 1)

# タイトル文字数
title_len_train = train["title"].fillna("").str.len().values.reshape(-1, 1)
title_len_test  = test["title"].fillna("").str.len().values.reshape(-1, 1)

# 動画時間を秒数に変換（hh:mm:ss 形式）
def to_seconds(time_str):
    try:
        parts = [int(p) for p in str(time_str).split(":")]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        return 0
    except Exception:
        return 0

duration_train = train["time"].apply(to_seconds).values.reshape(-1, 1)
duration_test  = test["time"].apply(to_seconds).values.reshape(-1, 1)

# 数値特徴量を結合し StandardScaler でスケール統一
num_train = np.hstack([dt_train.values, log_views_train, cat_train, title_len_train, duration_train])
num_test  = np.hstack([dt_test.values,  log_views_test,  cat_test,  title_len_test,  duration_test])
scaler = StandardScaler()
num_train_scaled = scaler.fit_transform(num_train)
num_test_scaled  = scaler.transform(num_test)

# [v4変更点1] char + word TF-IDF を結合
X_train = hstack([title_char_train, title_word_train, csr_matrix(num_train_scaled)])
X_test  = hstack([title_char_test,  title_word_test,  csr_matrix(num_test_scaled)])

## 目的変数
le = LabelEncoder()
y_train = le.fit_transform(train["channel_name"])

## [v4変更点2] LinearSVC → LogisticRegression に変更
# C=5.0: LinearSVC C=1.0 より大きめの値でテキスト分類の精度が出やすい
# solver="saga": 大規模疎行列に適したソルバー
# n_jobs=-1: 並列化で高速化

# C の探索（CVループ内で比較したい場合は以下のリストを変更）
C_VALUE = 5.0

## 層化 CV で Macro F1 を評価
log(f"交差検証 開始 (5-Fold, LogisticRegression C={C_VALUE})...")
cv_start = time.time()
skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
cv_scores = []
model = LogisticRegression(C=C_VALUE, max_iter=1000, solver="saga", n_jobs=-1, random_state=42)
for fold, (tr_idx, val_idx) in enumerate(skf.split(X_train, y_train)):
    t = time.time()
    X_tr, X_val = X_train[tr_idx], X_train[val_idx]
    y_tr, y_val = y_train[tr_idx], y_train[val_idx]
    model.fit(X_tr, y_tr)
    score = f1_score(y_val, model.predict(X_val), average="macro")
    cv_scores.append(score)
    print(f"  Fold {fold + 1} Val Macro F1: {score:.4f}  ({time.time() - t:.1f}s)", flush=True)

log(f"CV Macro F1: {np.mean(cv_scores):.4f} ± {np.std(cv_scores):.4f}", cv_start)

## 学習・予測
log("全データで再学習...")
t = time.time()
model.fit(X_train, y_train)
log("完了", t)

log("テストデータ予測...")
y_pred = le.inverse_transform(model.predict(X_test))

# 提出ファイル生成
submission = pd.DataFrame({"channel_name": y_pred})
submission.to_csv("submission_feature_eng_v4.csv", index=False, encoding="utf-8-sig")
log(f"予測完了: submission_feature_eng_v4.csv ({len(submission)}件)")
