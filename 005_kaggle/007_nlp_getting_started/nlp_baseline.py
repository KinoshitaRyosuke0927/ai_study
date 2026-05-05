import re
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import f1_score
from sklearn.pipeline import Pipeline


"""
https://www.kaggle.com/competitions/nlp-getting-started/overview
"""

# ── パス設定 ──────────────────────────────────────────────
DATA_DIR   = Path(__file__).parent.parent / "competitions" / "nlp-getting-started"
OUTPUT_DIR = Path(__file__).parent
OUTPUT_DIR.mkdir(exist_ok=True)

# ── データ読み込み ─────────────────────────────────────────
train = pd.read_csv(DATA_DIR / "train.csv")
test  = pd.read_csv(DATA_DIR / "test.csv")

TARGET = "target"
ID_COL = "id"

print(f"Train: {len(train)}件  Test: {len(test)}件")
print(f"Target 分布:\n{train[TARGET].value_counts().to_string()}\n")

# ── テキスト前処理 ─────────────────────────────────────────
URL_RE      = re.compile(r"https?://\S+")
MENTION_RE  = re.compile(r"@\w+")
HASHTAG_RE  = re.compile(r"#(\w+)")   # # を除いて単語だけ残す
NONALPHA_RE = re.compile(r"[^a-zA-Z\s]")

def clean_text(text: str) -> str:
    text = URL_RE.sub("", text)          # URL を除去
    text = MENTION_RE.sub("", text)      # @メンション を除去
    text = HASHTAG_RE.sub(r"\1", text)   # #hashtag → hashtag
    text = NONALPHA_RE.sub(" ", text)    # 記号・数字を空白に
    text = text.lower().strip()          # 小文字化・前後空白除去
    return text

train["clean_text"] = train["text"].apply(clean_text)
test["clean_text"]  = test["text"].apply(clean_text)

print("前処理サンプル:")
for _, row in train.head(3).iterrows():
    print(f"  元: {row['text'][:80]}")
    print(f"  後: {row['clean_text'][:80]}")
    print()

# ── Pipeline の構築 ───────────────────────────────────────
# Pipeline を使うと「TF-IDF 変換 → モデル学習」を1つのオブジェクトとして扱える
# CV 時にデータリーク（検証データの情報が学習に混入）を自動で防いでくれる
pipeline = Pipeline([
    ("tfidf", TfidfVectorizer(
        max_features=20000,    # 辞書サイズ（頻度上位 20,000単語を使用）
        ngram_range=(1, 2),    # 単語単体(1-gram)と2単語の組(2-gram)を使う
        min_df=2,              # 2件以上のツイートに登場した単語のみ使用
        sublinear_tf=True,     # TF を log スケールに変換（大きな値を抑制）
    )),
    ("clf", LogisticRegression(
        C=1.0,                 # 正則化の強さ（小さいほど過学習を抑制）
        max_iter=1000,
        solver="lbfgs",
        random_state=42,
    )),
])

# ── 5-Fold CV で F1 を評価 ─────────────────────────────────
X = train["clean_text"]
y = train[TARGET]

skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

cv_scores = cross_val_score(
    pipeline, X, y,
    cv=skf,
    scoring="f1",   # Kaggle の評価指標に合わせる
    n_jobs=-1,
)

print("=== 5-Fold CV F1 Score ===")
for i, s in enumerate(cv_scores, 1):
    print(f"  Fold {i}: {s:.4f}")
print(f"  Mean : {cv_scores.mean():.4f}  ±{cv_scores.std():.4f}")

# ── 全データで再学習して予測 ───────────────────────────────
pipeline.fit(X, y)

# 学習データへの適合確認
train_pred = pipeline.predict(X)
train_f1   = f1_score(y, train_pred)
print(f"\nTrain F1 : {train_f1:.4f}")
print(f"CV F1    : {cv_scores.mean():.4f}")
print(f"差分     : {train_f1 - cv_scores.mean():.4f}  (過学習の目安)")

# ── TF-IDF の重要単語 Top20 ───────────────────────────────
vectorizer    = pipeline.named_steps["tfidf"]
clf           = pipeline.named_steps["clf"]
feature_names = vectorizer.get_feature_names_out()
coef          = clf.coef_[0]

top_disaster     = pd.Series(coef, index=feature_names).nlargest(20)
top_not_disaster = pd.Series(coef, index=feature_names).nsmallest(20)

print("\n=== 災害ツイートに寄与する単語 Top20（係数が大きい） ===")
print(top_disaster.to_string())

print("\n=== 非災害ツイートに寄与する単語 Top20（係数が小さい） ===")
print(top_not_disaster.to_string())

# ── 提出ファイル生成 ───────────────────────────────────────
test_pred = pipeline.predict(test["clean_text"])

submission = pd.DataFrame({
    ID_COL: test[ID_COL],
    TARGET: test_pred,
})
out_path = OUTPUT_DIR / "submission_baseline.csv"
submission.to_csv(out_path, index=False)
print(f"\nSubmission saved → {out_path}")
print(submission[TARGET].value_counts().to_string())
