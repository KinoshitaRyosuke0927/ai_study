"""日本語BERT(reminder_classifier)の代替候補として、scikit-learnベースの
軽量テキスト分類モデル(TF-IDF + ナイーブベイズ / ロジスティック回帰 / 線形SVM)の
精度・動作面を比較評価するスクリプト。

評価は2通り行う。
1. 層化5分割交差検証(軽量モデルのみ): 全データを使ったブレの少ない比較。
   以下の3条件で比較し、前処理・パラメータ調整の効果を確認する。
     - raw/default : 前処理なし・固定パラメータ
     - norm/default: メンション・URL正規化あり・固定パラメータ
     - norm/tuned  : メンション・URL正規化あり・パラメータ調整あり
                     (外側5分割の各学習データ内で、内側3分割のグリッドサーチを行う
                      入れ子交差検証。評価用データをパラメータ選択に使わない)
2. ホールドアウト評価(軽量モデル(norm/tuned) + 既存BERT): train_model.py と同じ分割
   (VAL_RATIO=0.15, RANDOM_SEED=42)の検証データで、既存BERTと同条件で比較

実行方法: 011_chat_linkage ディレクトリで
    python -m app.model.compare_light_models
結果は app/model/compare_results/ にCSVで保存される。
"""

from __future__ import annotations

import io
import os
import re
import tempfile
import time
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_recall_curve,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.model_selection import GridSearchCV, StratifiedKFold, cross_val_predict, train_test_split
from sklearn.naive_bayes import ComplementNB, MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

from app.model.train_model import RANDOM_SEED, VAL_RATIO, load_labeled_posts

RESULT_DIR = Path(__file__).resolve().parent / "compare_results"
BERT_DIR = Path(__file__).resolve().parent / "reminder_classifier"
N_SPLITS = 5
INNER_SPLITS = 3
# 運用中の既定しきい値(settings.ini [slash_watch] reminder_threshold / 画面UIの既定値)
PROD_THRESHOLD = 0.9
# 「この適合率を保ったときに再現率がどこまで出るか」を見るための適合率の基準
TARGET_PRECISION = 0.8
# 推論時間計測に使う件数
TIMING_BATCH_SIZE = 100
# ブートストラップ法(BERTとの差の信頼区間算出)の繰り返し回数
N_BOOTSTRAP = 2000

# 全員宛てのメンション(内容の性質を表すため、正規化せずそのまま残す)
BROADCAST_MENTIONS = ("channel", "here", "all")
MENTION_PATTERN = re.compile(r"@(?!(?:%s)\b)[A-Za-z0-9._\-]+" % "|".join(BROADCAST_MENTIONS))
URL_PATTERN = re.compile(r"https?://\S+")



def normalize_text(text: str) -> str:
    """
    個人宛てメンション・URLを共通の記号に置き換え、特定の人物名やURLの文字列に
    モデルが依存しないようにする(@channel/@here/@all はそのまま残す)

    Args
    -----------------
    - text: str,   正規化前のテキスト

    Returns
    -----------------
    - text: str,   正規化後のテキスト

    """
    # URLを置き換える(URL中の英数字が特徴量として拾われないようにする)
    text = URL_PATTERN.sub(" URL ", text)
    # 個人宛てメンション(@yano など)を @USER に置き換える
    return MENTION_PATTERN.sub("@USER", text)


class JapaneseTokenizer:
    """
    fugashi(MeCab + unidic-lite)で日本語テキストを単語(表層形)に分割する、
    TfidfVectorizerの tokenizer に渡す呼び出し可能オブジェクト。

    fugashiのTaggerはpickle化できないため、並列処理での受け渡しやjoblibでの
    モデル保存時にはTaggerを持たない状態で保存し、使用時に再生成する。
    """

    def __init__(self):
        self._tagger = None

    def __call__(self, text: str) -> list[str]:
        """
        Args
        -----------------
        - text: str,   分割対象のテキスト

        Returns
        -----------------
        - tokens: list[str],   単語(表層形)のリスト

        """
        # Taggerは生成コストが高いため、初回のみ生成して保持する
        if self._tagger is None:
            import fugashi

            self._tagger = fugashi.Tagger()
        return [word.surface for word in self._tagger(text)]

    def __getstate__(self) -> dict:
        # pickle化の際はTaggerを含めない
        return {}

    def __setstate__(self, state: dict) -> None:
        # 復元時はTagger未生成の状態に戻す(初回呼び出し時に生成される)
        self._tagger = None


def build_vectorizers() -> dict[str, TfidfVectorizer]:
    """
    比較対象とする特徴量(TF-IDFベクトル化)の設定を返す

    Returns
    -----------------
    - vectorizers: dict[str, TfidfVectorizer],   特徴量名 → 未学習のVectorizer

    """
    return {
        # 文字2〜3gram: 形態素解析不要。表記ゆれ・未知語にも比較的強い
        "char": TfidfVectorizer(analyzer="char", ngram_range=(2, 3), min_df=2, sublinear_tf=True),
        # 単語1〜2gram: fugashiで分割した単語単位
        "word": TfidfVectorizer(
            tokenizer=JapaneseTokenizer(),
            token_pattern=None,
            lowercase=False,
            ngram_range=(1, 2),
            min_df=2,
            sublinear_tf=True,
        ),
    }


def build_classifiers() -> dict[str, object]:
    """
    比較対象とする分類器の設定(固定パラメータ時の既定値)を返す

    Returns
    -----------------
    - classifiers: dict[str, object],   分類器名 → 未学習の分類器

    """
    return {
        "MultinomialNB": MultinomialNB(alpha=0.1),
        "ComplementNB": ComplementNB(alpha=0.3),
        # BERT学習時の WeightedTrainer と同様に、少数派クラスの重みを大きくする
        "LogReg": LogisticRegression(C=10.0, class_weight="balanced", max_iter=5000),
        # LinearSVCは確率を出力しないため、シグモイドで確率に校正する
        "LinearSVM": CalibratedClassifierCV(
            LinearSVC(C=0.5, class_weight="balanced"), method="sigmoid", cv=5
        ),
    }


def build_param_grid(vec_name: str, clf_name: str) -> dict[str, list]:
    """
    パラメータ調整(グリッドサーチ)で探索する候補値を返す

    Args
    -----------------
    - vec_name: str,   特徴量名("char" / "word")
    - clf_name: str,   分類器名

    Returns
    -----------------
    - grid: dict[str, list],   Pipelineのパラメータ名 → 候補値のリスト

    """
    # 特徴量側: n-gramの範囲と、出現文書数の下限
    if vec_name == "char":
        grid: dict[str, list] = {"tfidf__ngram_range": [(1, 3), (2, 3), (2, 4)]}
    else:
        grid = {"tfidf__ngram_range": [(1, 1), (1, 2), (1, 3)]}
    grid["tfidf__min_df"] = [1, 2, 3]

    # 分類器側: 平滑化(alpha)または正則化の強さ(C。小さいほど正則化が強い)
    if clf_name in ("MultinomialNB", "ComplementNB"):
        grid["clf__alpha"] = [0.01, 0.03, 0.1, 0.3, 1.0]
    elif clf_name == "LogReg":
        grid["clf__C"] = [0.3, 1, 3, 10, 30, 100]
    elif clf_name == "LinearSVM":
        grid["clf__estimator__C"] = [0.03, 0.1, 0.3, 1, 3]
    return grid


def build_pipelines() -> dict[tuple[str, str], Pipeline]:
    """
    特徴量 × 分類器 の全組み合わせのPipelineを作成する

    Returns
    -----------------
    - pipelines: dict[tuple[str, str], Pipeline],   (特徴量名, 分類器名) → 未学習のPipeline

    """
    pipelines: dict[tuple[str, str], Pipeline] = {}
    # 全ての特徴量・分類器の組み合わせについてPipelineを組み立てる
    for vec_name, vectorizer in build_vectorizers().items():
        for clf_name, classifier in build_classifiers().items():
            pipelines[(vec_name, clf_name)] = Pipeline(
                [("tfidf", clone(vectorizer)), ("clf", clone(classifier))]
            )
    return pipelines


def build_tuned_model(vec_name: str, clf_name: str, pipeline: Pipeline) -> GridSearchCV:
    """
    PipelineをPR-AUC最大化のグリッドサーチでラップする(fit時に内側の交差検証で
    パラメータを選び、最良パラメータで学習データ全体を再学習する)

    Args
    -----------------
    - vec_name: str,         特徴量名
    - clf_name: str,         分類器名
    - pipeline: Pipeline,    未学習のPipeline

    Returns
    -----------------
    - search: GridSearchCV,   未学習のグリッドサーチ

    """
    return GridSearchCV(
        clone(pipeline),
        build_param_grid(vec_name, clf_name),
        scoring="average_precision",
        cv=StratifiedKFold(n_splits=INNER_SPLITS, shuffle=True, random_state=RANDOM_SEED),
        n_jobs=-1,
    )


def compute_scores(y_true: np.ndarray, proba: np.ndarray) -> dict:
    """
    正解ラベルと予測確率から、比較用の各種評価指標を算出する

    Args
    -----------------
    - y_true: np.ndarray,   正解ラベル(0/1)
    - proba: np.ndarray,    クラス1(リマインド必要)の予測確率

    Returns
    -----------------
    - scores: dict,   評価指標名 → 値

    """
    scores: dict = {}
    # しきい値に依存しない順位付けの良さ(PR-AUCは不均衡データで特に重視する)
    scores["PR-AUC"] = average_precision_score(y_true, proba)
    scores["ROC-AUC"] = roc_auc_score(y_true, proba)
    # 確率の当てはまり(小さいほど確率値が実態に近い)
    scores["Brier"] = brier_score_loss(y_true, proba)

    # 固定しきい値(0.5 / 運用値0.9)でのprecision・recall・F1
    for threshold in (0.5, PROD_THRESHOLD):
        pred = (proba >= threshold).astype(int)
        p, r, f, _ = precision_recall_fscore_support(y_true, pred, average="binary", zero_division=0)
        scores[f"P@{threshold}"] = p
        scores[f"R@{threshold}"] = r
        scores[f"F1@{threshold}"] = f

    # しきい値を動かしたときのF1最大値と、そのときのしきい値
    precision, recall, thresholds = precision_recall_curve(y_true, proba)
    f1 = 2 * precision * recall / np.clip(precision + recall, 1e-12, None)
    best_idx = int(np.argmax(f1[:-1]))
    scores["bestF1"] = f1[best_idx]
    scores["bestF1_th"] = thresholds[best_idx]

    # 適合率TARGET_PRECISION以上を保てるしきい値のうち、最大の再現率
    ok = precision[:-1] >= TARGET_PRECISION
    scores[f"R@P>={TARGET_PRECISION}"] = recall[:-1][ok].max() if ok.any() else 0.0
    return scores


def bootstrap_diff_ci(y_true: np.ndarray, proba_a: np.ndarray, proba_b: np.ndarray) -> tuple[float, float]:
    """
    ブートストラップ法で、2モデル間のPR-AUCの差(a - b)の95%信頼区間を求める

    Args
    -----------------
    - y_true: np.ndarray,    正解ラベル(0/1)
    - proba_a: np.ndarray,   モデルaの予測確率
    - proba_b: np.ndarray,   モデルbの予測確率

    Returns
    -----------------
    - low: float,    信頼区間の下限
    - high: float,   信頼区間の上限

    """
    rng = np.random.default_rng(RANDOM_SEED)
    diffs = []
    # 検証データを重複ありで再抽出し、両モデルのPR-AUCの差を繰り返し計算する
    for _ in range(N_BOOTSTRAP):
        idx = rng.integers(0, len(y_true), len(y_true))
        # 陽性が1件も含まれない抽出結果ではPR-AUCが定義できないためスキップ
        if y_true[idx].sum() == 0:
            continue
        diffs.append(
            average_precision_score(y_true[idx], proba_a[idx]) - average_precision_score(y_true[idx], proba_b[idx])
        )
    low, high = np.percentile(diffs, [2.5, 97.5])
    return float(low), float(high)


def measure_runtime(model, sample_texts: list[str]) -> dict:
    """
    学習済みモデルの保存サイズ・読み込み時間・推論時間を計測する

    Args
    -----------------
    - model: Pipeline,             学習済みのPipeline
    - sample_texts: list[str],     推論時間計測用のテキスト

    Returns
    -----------------
    - runtime: dict,   計測項目名 → 値

    """
    runtime: dict = {}
    # joblibで保存したときのファイルサイズと、読み込み時間を計測
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "model.joblib"
        joblib.dump(model, path, compress=3)
        runtime["size_MB"] = path.stat().st_size / 1024**2
        start = time.perf_counter()
        loaded = joblib.load(path)
        runtime["load_sec"] = time.perf_counter() - start

    # まとめて推論(実運用の predict_reminder_scores 相当)した時間を計測
    start = time.perf_counter()
    loaded.predict_proba(sample_texts)
    runtime[f"infer_{len(sample_texts)}_ms"] = (time.perf_counter() - start) * 1000
    # 1件ずつ推論した場合の平均時間を計測
    start = time.perf_counter()
    for text in sample_texts[:20]:
        loaded.predict_proba([text])
    runtime["infer_1_ms"] = (time.perf_counter() - start) * 1000 / 20
    return runtime


def format_params(params: dict) -> str:
    """
    グリッドサーチで選ばれたパラメータを、表示用の短い文字列にする

    Args
    -----------------
    - params: dict,   パラメータ名 → 値

    Returns
    -----------------
    - text: str,   "ngram=(1, 2) min_df=2 C=10" のような文字列

    """
    # Pipeline内の階層を表す接頭辞を取り除き、短い名前で並べる
    short = {
        "tfidf__ngram_range": "ngram",
        "tfidf__min_df": "min_df",
        "clf__alpha": "alpha",
        "clf__C": "C",
        "clf__estimator__C": "C",
    }
    return " ".join(f"{short.get(k, k)}={v}" for k, v in params.items())


def run_cross_validation(texts: list[str], labels: list[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    軽量モデル全パターンを、3条件(raw/default, norm/default, norm/tuned)で
    層化K分割交差検証により評価する(out-of-fold予測で指標を算出)

    Args
    -----------------
    - texts: list[str],    全テキスト(正規化前)
    - labels: list[int],   全ラベル

    Returns
    -----------------
    - result: pd.DataFrame,        (モデル, 条件)ごとの評価指標の表
    - chosen_params: pd.DataFrame,  norm/tuned で外側の各分割において選ばれたパラメータ

    """
    y = np.array(labels)
    texts_arr = np.array(texts, dtype=object)
    norm_arr = np.array([normalize_text(t) for t in texts], dtype=object)
    skf = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_SEED)
    rows = []
    param_rows = []

    # モデルごとに、全データについて「自分を学習に含まないモデル」の予測確率を得て評価
    for (vec_name, clf_name), pipeline in build_pipelines().items():
        name = f"{vec_name} + {clf_name}"

        # 固定パラメータ: 正規化なし / ありの2条件
        for cond, x in (("raw/default", texts_arr), ("norm/default", norm_arr)):
            proba = cross_val_predict(pipeline, x, y, cv=skf, method="predict_proba", n_jobs=N_SPLITS)[:, 1]
            rows.append({"model": name, "condition": cond, **compute_scores(y, proba)})

        # パラメータ調整あり: 外側の各分割の学習データだけでグリッドサーチ → 評価用データを予測
        proba = np.zeros(len(y))
        for fold, (train_idx, test_idx) in enumerate(skf.split(norm_arr, y)):
            search = build_tuned_model(vec_name, clf_name, pipeline)
            search.fit(norm_arr[train_idx], y[train_idx])
            proba[test_idx] = search.predict_proba(norm_arr[test_idx])[:, 1]
            param_rows.append({"model": name, "fold": fold, "params": format_params(search.best_params_)})
        rows.append({"model": name, "condition": "norm/tuned", **compute_scores(y, proba)})
        print(f"  [CV] {name} 完了")

    return pd.DataFrame(rows).set_index(["model", "condition"]), pd.DataFrame(param_rows)


def predict_bert(texts: list[str]) -> tuple[np.ndarray, dict]:
    """
    既存の学習済みBERT(reminder_classifier)でスコアを算出し、動作面も計測する

    Args
    -----------------
    - texts: list[str],   推論対象のテキスト

    Returns
    -----------------
    - proba: np.ndarray,   クラス1の予測確率
    - runtime: dict,       計測項目名 → 値

    """
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    from app.model.predict import MAX_LENGTH

    runtime: dict = {}
    # モデルフォルダの合計サイズ
    runtime["size_MB"] = sum(f.stat().st_size for f in BERT_DIR.iterdir() if f.is_file()) / 1024**2

    # モデル・トークナイザーの読み込み時間を計測
    start = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(str(BERT_DIR))
    model = AutoModelForSequenceClassification.from_pretrained(str(BERT_DIR))
    model.eval()
    runtime["load_sec"] = time.perf_counter() - start

    def _score(batch: list[str]) -> np.ndarray:
        # predict.py と同条件(MAX_LENGTH)でトークナイズし、softmaxでクラス1の確率を得る
        enc = tokenizer(batch, truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt")
        with torch.no_grad():
            logits = model(**enc).logits
        return torch.softmax(logits, dim=-1)[:, 1].numpy()

    # 評価対象全件を推論(メモリ節約のため16件ずつ)
    proba = np.concatenate([_score(texts[i : i + 16]) for i in range(0, len(texts), 16)])

    # 軽量モデルと同条件で推論時間を計測
    sample = texts[:TIMING_BATCH_SIZE]
    start = time.perf_counter()
    _score(sample)
    runtime[f"infer_{len(sample)}_ms"] = (time.perf_counter() - start) * 1000
    start = time.perf_counter()
    for text in sample[:20]:
        _score([text])
    runtime["infer_1_ms"] = (time.perf_counter() - start) * 1000 / 20
    return proba, runtime


def run_holdout(texts: list[str], labels: list[int]) -> tuple[pd.DataFrame, dict[str, Pipeline]]:
    """
    train_model.py と同じ分割の検証データで、軽量モデル(正規化+パラメータ調整あり)と
    既存BERTを同条件で評価する

    Args
    -----------------
    - texts: list[str],    全テキスト(正規化前)
    - labels: list[int],   全ラベル

    Returns
    -----------------
    - result: pd.DataFrame,              モデルごとの評価指標・動作面の計測値の表
    - best_models: dict[str, Pipeline],  モデル名 → 学習用データで調整・学習済みのPipeline

    """
    # train_model.py と同じ条件で学習用・検証用に分割(BERTには正規化前のテキストを渡す)
    train_texts, val_texts, train_labels, val_labels = train_test_split(
        texts, labels, test_size=VAL_RATIO, random_state=RANDOM_SEED, stratify=labels
    )
    train_norm = [normalize_text(t) for t in train_texts]
    val_norm = [normalize_text(t) for t in val_texts]
    y_val = np.array(val_labels)
    rows = []
    probas: dict[str, np.ndarray] = {}
    best_models: dict[str, Pipeline] = {}

    # 軽量モデル: 学習用データ内でパラメータ調整・学習 → 検証データで評価 + 動作面の計測
    for (vec_name, clf_name), pipeline in build_pipelines().items():
        name = f"{vec_name} + {clf_name}"
        search = build_tuned_model(vec_name, clf_name, pipeline)
        search.fit(train_norm, train_labels)
        # 最良パラメータでの再学習1回分の時間を計測(グリッドサーチ全体の時間は含めない)
        best = clone(search.best_estimator_)
        start = time.perf_counter()
        best.fit(train_norm, train_labels)
        fit_sec = time.perf_counter() - start
        probas[name] = best.predict_proba(val_norm)[:, 1]
        best_models[name] = best
        rows.append(
            {
                "model": name,
                **compute_scores(y_val, probas[name]),
                "fit_sec": fit_sec,
                **measure_runtime(best, val_norm[:TIMING_BATCH_SIZE]),
                "params": format_params(search.best_params_),
            }
        )
        print(f"  [holdout] {name} 完了")

    # 既存BERT: 学習済みモデルをそのまま使って検証データを評価
    if BERT_DIR.exists():
        bert_proba, runtime = predict_bert(val_texts)
        rows.append({"model": "BERT (既存)", **compute_scores(y_val, bert_proba), **runtime})
        # 各軽量モデルについて、BERTとのPR-AUC差の95%信頼区間を算出
        for row in rows[:-1]:
            low, high = bootstrap_diff_ci(y_val, probas[row["model"]], bert_proba)
            row["dPR-AUC_vs_BERT_CI"] = f"[{low:+.3f}, {high:+.3f}]"
        print("  [holdout] BERT (既存) 完了")
    return pd.DataFrame(rows).set_index("model"), best_models


def show_top_features(best_models: dict[str, Pipeline], top_n: int = 25) -> str:
    """
    ロジスティック回帰の係数から、判定に効いている特徴量を一覧化する

    Args
    -----------------
    - best_models: dict[str, Pipeline],   モデル名 → 学習済みのPipeline
    - top_n: int,                         表示する件数

    Returns
    -----------------
    - report: str,   特徴量の一覧(テキスト)

    """
    buf = io.StringIO()
    # 単語・文字それぞれのロジスティック回帰について係数上位を取り出す
    for name in ("word + LogReg", "char + LogReg"):
        model = best_models[name]
        vocab = model.named_steps["tfidf"].get_feature_names_out()
        coef = model.named_steps["clf"].coef_[0]
        order = np.argsort(coef)
        buf.write(f"\n### {name}\n")
        buf.write("リマインド必要側: " + " / ".join(repr(vocab[i]) for i in order[::-1][:top_n]) + "\n")
        buf.write("リマインド不要側: " + " / ".join(repr(vocab[i]) for i in order[:top_n]) + "\n")
    return buf.getvalue()


def main() -> None:
    """
    交差検証・ホールドアウト評価・特徴量分析を順に実行し、結果を表示・保存する
    """
    # ラベル付けCSVから全データを読み込む
    texts, labels = load_labeled_posts()
    print(f"データ: {len(texts)}件 (1={sum(labels)}件, 0={len(labels) - sum(labels)}件)")
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 300)
    pd.set_option("display.max_columns", 40)
    pd.set_option("display.max_colwidth", 60)
    pd.set_option("display.float_format", "{:.3f}".format)

    # 1. 軽量モデルの層化5分割交差検証(3条件)
    print(f"\n=== 層化{N_SPLITS}分割交差検証(軽量モデル × 3条件) ===")
    cv_result, chosen_params = run_cross_validation(texts, labels)
    print(cv_result[["PR-AUC", "ROC-AUC", "Brier", "bestF1", "bestF1_th", f"R@P>={TARGET_PRECISION}", "F1@0.5", "R@0.9"]])
    cv_result.to_csv(RESULT_DIR / "cv_results.csv", encoding="utf-8-sig")
    chosen_params.to_csv(RESULT_DIR / "cv_chosen_params.csv", encoding="utf-8-sig", index=False)
    # 外側の各分割で選ばれたパラメータの傾向(分割によって選ばれ方がぶれていないか)
    print("\n--- norm/tuned で選ばれたパラメータ(外側5分割での出現回数) ---")
    for model_name, group in chosen_params.groupby("model", sort=False):
        print(f"  {model_name}: {dict(Counter(group['params']))}")

    # 2. 既存BERTを含めたホールドアウト評価
    print(f"\n=== ホールドアウト評価(検証{VAL_RATIO:.0%}、軽量モデルは norm/tuned、BERT含む) ===")
    holdout_result, best_models = run_holdout(texts, labels)
    holdout_result = holdout_result.sort_values("PR-AUC", ascending=False)
    print(holdout_result.drop(columns=["params"]))
    print(holdout_result["params"].dropna())
    holdout_result.to_csv(RESULT_DIR / "holdout_results.csv", encoding="utf-8-sig")

    # 3. ロジスティック回帰で判定に効いている特徴量を確認
    print("\n=== 判定に効いている特徴量(ロジスティック回帰の係数、正規化後) ===")
    report = show_top_features(best_models)
    print(report)
    (RESULT_DIR / "top_features.txt").write_text(report, encoding="utf-8")
    print(f"\n結果を {RESULT_DIR} に保存しました。")


if __name__ == "__main__":
    # joblibの並列実行時にトークナイザー関連の警告が出るのを抑止
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    main()
