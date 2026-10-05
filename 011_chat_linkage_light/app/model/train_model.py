"""ラベル付けした投稿データ(pickup_flag,user,text 形式のCSV)を用いて、
TF-IDF(文字n-gram)+ ロジスティック回帰のモデルを学習し、投稿ごとに
「リマインドが必要か」を0~1のスコアで判定するモデルを作成するスクリプト。

実行方法: 011_chat_linkage_light ディレクトリで
    python -m app.model.train_model
学習済みモデルは app/model/reminder_classifier.joblib に保存される(既存のモデルは上書き)。
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_fscore_support
from sklearn.model_selection import GridSearchCV, StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline

from app.model.preprocess import preprocess_text

DATA_DIR = Path(__file__).resolve().parent / "train_data"
# ラベル付け済みCSV(同じ pickup_flag,user,text 形式であれば複数まとめて学習に使う)
TRAIN_DATA_FILES = [DATA_DIR / "train_data.csv", DATA_DIR / "collected_posts.csv"]
OUTPUT_PATH = Path(__file__).resolve().parent / "reminder_classifier.joblib"
N_SPLITS = 5
RANDOM_SEED = 42
# 学習結果の表示に使うしきい値(settings.ini [slash_watch] reminder_threshold・画面UIの既定値と同じ)
DEFAULT_THRESHOLD = 0.5
# 正則化の強さCの候補(小さいほど正則化が強い)。交差検証でPR-AUCが最良のものを選ぶ
C_CANDIDATES = [1, 3, 10, 30]


def load_labeled_posts() -> tuple[list[str], list[int]]:
    """
    TRAIN_DATA_FILES に列挙したラベル付けCSVを読み込み、テキストとラベルのリストを返す

    Returns
    -----------------
    - texts: list[str],    投稿本文のリスト
    - labels: list[int],   各投稿に対応するラベル(0または1)のリスト

    """
    # 入れ物用意
    texts: list[str] = []
    labels: list[int] = []
    # 指定された全CSVファイルについて処理
    for path in TRAIN_DATA_FILES:
        # ファイルが存在しない場合はスキップ
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            # 1行(1投稿)ずつ処理
            for row in csv.DictReader(f):
                flag = row["pickup_flag"].strip()
                text = row["text"].strip()
                # ラベルが0/1以外、またはテキストが空の行は学習対象外として除外
                if flag not in ("0", "1") or not text:
                    continue
                # テキストとラベルをそれぞれ追加
                texts.append(text)
                labels.append(int(flag))
    return texts, labels


def build_pipeline() -> Pipeline:
    """
    前処理 → TF-IDF(文字1〜3gram)→ ロジスティック回帰 のPipelineを作成する

    Returns
    -----------------
    - pipeline: Pipeline,   未学習のPipeline

    """
    return Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    # 個人宛てメンション・URLの正規化と小文字化(推論時にも同じ処理が自動で適用される)
                    preprocessor=preprocess_text,
                    # 連続する1〜3文字を1単位とする(形態素解析は不要)
                    analyzer="char",
                    ngram_range=(1, 3),
                    # 3件以上の投稿に出現する文字列のみを使う(偶然の出現に引っ張られないようにする)
                    min_df=3,
                    # 出現回数の多さを対数で緩和する
                    sublinear_tf=True,
                ),
            ),
            # 少数派の「1(要リマインド)」を軽視しないよう、件数に反比例したクラス重みを付ける
            ("clf", LogisticRegression(class_weight="balanced", max_iter=5000)),
        ]
    )


def main() -> None:
    """
    ラベル付けCSVを読み込み、交差検証で正則化の強さを選んだうえで全データで学習し、
    学習済みモデルを OUTPUT_PATH に保存する
    """
    # ラベル付けCSVから学習データを読み込む
    texts, labels = load_labeled_posts()
    y = np.array(labels)
    print(f"学習データ: {len(texts)}件 (1(要リマインド)={y.sum()}件, 0={len(y) - y.sum()}件)")

    # 交差検証(層化5分割)で、PR-AUCが最良になる正則化の強さCを選ぶ
    cv = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_SEED)
    search = GridSearchCV(
        build_pipeline(), {"clf__C": C_CANDIDATES}, scoring="average_precision", cv=cv, n_jobs=-1
    )
    search.fit(texts, y)
    best_c = search.best_params_["clf__C"]
    print(f"選ばれた正則化の強さ: C={best_c} (交差検証PR-AUC={search.best_score_:.3f})")

    # 選んだCでの交差検証の予測から、既定しきい値での精度を確認する
    # (Cの選択にも同じ分割を使っているため、未知データでの精度よりわずかに高めに出る点に注意)
    best_pipeline = build_pipeline().set_params(clf__C=best_c)
    proba = cross_val_predict(best_pipeline, texts, y, cv=cv, method="predict_proba", n_jobs=-1)[:, 1]
    pred = (proba >= DEFAULT_THRESHOLD).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(y, pred, average="binary", zero_division=0)
    print(
        f"交差検証での精度: PR-AUC={average_precision_score(y, proba):.3f} / "
        f"しきい値{DEFAULT_THRESHOLD}: precision={precision:.3f}, recall={recall:.3f}, f1={f1:.3f}"
    )

    # 全データで学習し直す
    model = best_pipeline.fit(texts, y)

    # 学習済みモデルを、学習条件の情報と一緒に保存する
    # (scikit-learnのバージョンが学習時と推論時で異なると読み込めない場合があるため、確認用に記録する)
    joblib.dump(
        {
            "model": model,
            "sklearn_version": sklearn.__version__,
            "trained_at": datetime.now().isoformat(timespec="seconds"),
            "n_samples": len(texts),
            "params": {"C": best_c},
        },
        OUTPUT_PATH,
        compress=3,
    )
    print(f"学習済みモデルを {OUTPUT_PATH} に保存しました。({OUTPUT_PATH.stat().st_size / 1024:.0f}KB)")


if __name__ == "__main__":
    main()
