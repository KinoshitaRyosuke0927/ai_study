import time
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import LabelEncoder, StandardScaler
from scipy.sparse import hstack, csr_matrix

def log(msg, start=None):
    """ステップ名と経過時間を表示する"""
    elapsed = f"  ({time.time() - start:.1f}s)" if start else ""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}{elapsed}", flush=True)

# 活動期間データ読み込み
log("活動期間データ読み込み...")
active = pd.read_csv("create/active_period.csv", encoding="utf-8-sig")
active["debut_date"]    = pd.to_datetime(active["debut_date"],    format="%Y/%m/%d")
active["graduate_date"] = pd.to_datetime(active["graduate_date"], format="%Y/%m/%d", errors="coerce")
active = active.set_index("channel_name")

# 投稿日に活動中のクラスのみ True になるマスクを返す (shape: n_samples × n_classes)
def build_active_mask(dates, classes):
    debut_arr = np.array([
        active.loc[c, "debut_date"].to_datetime64() if c in active.index else np.datetime64("NaT")
        for c in classes
    ], dtype="datetime64[D]")
    grad_arr = np.array([
        active.loc[c, "graduate_date"].to_datetime64()
        if (c in active.index and not pd.isna(active.loc[c, "graduate_date"]))
        else np.datetime64("NaT")
        for c in classes
    ], dtype="datetime64[D]")

    dates_arr = dates.values.astype("datetime64[D]")
    mask = np.ones((len(dates_arr), len(classes)), dtype=bool)

    # debut_date より前は予測不可
    has_debut = ~np.isnat(debut_arr)
    mask[:, has_debut] &= dates_arr[:, None] >= debut_arr[None, has_debut]

    # graduate_date より後は予測不可
    has_grad = ~np.isnat(grad_arr)
    mask[:, has_grad] &= dates_arr[:, None] <= grad_arr[None, has_grad]

    # 投稿日が不明なサンプルは制限しない
    nat_rows = np.isnat(dates_arr)
    mask[nat_rows, :] = True

    return mask

# decision_function に活動期間マスクを適用し、活動中 VTuber の中で最スコアのクラスを返す
def domain_predict(model, X, dates, le):
    scores = model.decision_function(X)
    scores[~build_active_mask(dates, le.classes_)] = -np.inf
    return scores.argmax(axis=1)

# 投稿日に活動中の VTuber 数（train / test 両方で計算可能なドメイン特徴量）
def n_active_vtubers(dates):
    debut_arr  = active["debut_date"].values.astype("datetime64[D]")
    has_grad   = ~pd.isna(active["graduate_date"])
    grad_valid = active["graduate_date"].values[has_grad].astype("datetime64[D]")
    counts = np.zeros(len(dates), dtype=float)
    for i, d in enumerate(dates):
        if pd.isna(d):
            counts[i] = len(active)
            continue
        d64 = np.datetime64(d, "D")
        after_debut  = d64 >= debut_arr
        before_grad  = np.ones(len(active), dtype=bool)
        before_grad[has_grad.values] = d64 <= grad_valid
        counts[i] = (after_debut & before_grad).sum()
    return counts.reshape(-1, 1)

# データ読み込み
log("データ読み込み...")
t = time.time()
train = pd.read_csv("create/train_data_v2.csv",             encoding="utf-8-sig")
test  = pd.read_csv("create/test_data_channel_name_v2.csv", encoding="utf-8-sig")
log(f"完了: train={len(train)}行, test={len(test)}行", t)

# 投稿日を datetime に変換（活動期間との照合に使用）
train_dates = pd.to_datetime(train["date"], errors="coerce")
test_dates  = pd.to_datetime(test["date"],  errors="coerce")

## 特徴量エンジニアリング
# title を文字 n-gram TF-IDF でベクトル化
log("TF-IDF ベクトル化...")
t = time.time()
tfidf = TfidfVectorizer(
    analyzer="char",
    ngram_range=(2, 3),
    max_features=30000,
    sublinear_tf=True,
)
title_train = tfidf.fit_transform(train["title"].fillna(""))
title_test  = tfidf.transform(test["title"].fillna(""))
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

# 投稿日に活動中の VTuber 数を特徴量として追加
log("活動中 VTuber 数 特徴量 計算...")
t = time.time()
n_active_train = n_active_vtubers(train_dates)
n_active_test  = n_active_vtubers(test_dates)
log("完了", t)

# 数値特徴量を結合し StandardScaler でスケール統一
num_train = np.hstack([dt_train.values, log_views_train, cat_train,
                        title_len_train, duration_train, n_active_train])
num_test  = np.hstack([dt_test.values,  log_views_test,  cat_test,
                        title_len_test,  duration_test,  n_active_test])
scaler = StandardScaler()
num_train_scaled = scaler.fit_transform(num_train)
num_test_scaled  = scaler.transform(num_test)

X_train = hstack([title_train, csr_matrix(num_train_scaled)])
X_test  = hstack([title_test,  csr_matrix(num_test_scaled)])

## 目的変数
le = LabelEncoder()
y_train = le.fit_transform(train["channel_name"])

## 層化 CV で Macro F1 を評価
log("交差検証 開始 (5-Fold)...")
cv_start = time.time()
skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
cv_scores_base   = []
cv_scores_domain = []
model = LinearSVC(C=1.0, max_iter=2000, random_state=42)
for fold, (tr_idx, val_idx) in enumerate(skf.split(X_train, y_train)):
    t = time.time()
    X_tr,  X_val = X_train[tr_idx], X_train[val_idx]
    y_tr,  y_val = y_train[tr_idx], y_train[val_idx]
    val_dates     = train_dates.iloc[val_idx].reset_index(drop=True)
    model.fit(X_tr, y_tr)
    score_base   = f1_score(y_val, model.predict(X_val),                     average="macro")
    score_domain = f1_score(y_val, domain_predict(model, X_val, val_dates, le), average="macro")
    cv_scores_base.append(score_base)
    cv_scores_domain.append(score_domain)
    print(f"  Fold {fold + 1}  base={score_base:.4f}  domain={score_domain:.4f}  ({time.time() - t:.1f}s)", flush=True)

log(f"CV Macro F1 (base)         : {np.mean(cv_scores_base):.4f} ± {np.std(cv_scores_base):.4f}", cv_start)
log(f"CV Macro F1 (domain制約あり): {np.mean(cv_scores_domain):.4f} ± {np.std(cv_scores_domain):.4f}")

## 学習・予測
log("全データで再学習...")
t = time.time()
model.fit(X_train, y_train)
log("完了", t)

log("テストデータ予測 (ドメイン制約あり)...")
y_pred = le.inverse_transform(domain_predict(model, X_test, test_dates, le))

# 提出ファイル生成
submission = pd.DataFrame({"channel_name": y_pred})
submission.to_csv("submission_domain_info.csv", index=False, encoding="utf-8-sig")
log(f"予測完了: submission_domain_info.csv ({len(submission)}件)")
