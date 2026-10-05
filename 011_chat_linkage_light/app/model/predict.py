"""train_model.py で学習したモデル(TF-IDF + ロジスティック回帰)を使い、投稿テキストの
「リマインドが必要そうか」を0~1のスコアで判定する。

動作確認用の実行方法: 011_chat_linkage_light ディレクトリで
    python -m app.model.predict "@channel 明日までに経費精算をお願いします"
"""

from __future__ import annotations

import sys
from pathlib import Path

import joblib

# 学習済みモデル(joblib形式)は、読み込み時に初めて以下のクラス・関数を参照する。
# コード上で直接使わないため、明示的にimportしておかないとPyInstallerの静的解析で検出されず、
# exeに同梱されない(読み込み時にModuleNotFoundErrorになる)。そのため、ここで明示的にimportしておく。
import sklearn.feature_extraction.text  # noqa: F401  (TfidfVectorizer)
import sklearn.linear_model  # noqa: F401  (LogisticRegression)
import sklearn.pipeline  # noqa: F401  (Pipeline)

from app.model import preprocess  # noqa: F401  (preprocess_text)

# exe化(PyInstaller)時、__file__ は "app/model/" のパッケージ階層を保持したまま
# _internal 配下に展開されるため、通常のimportモジュールと同じ扱いでは
# --add-data で配置した "_internal/model/reminder_classifier.joblib" と場所がずれる。
# そのため他のモジュール(mattermost_service.pyの.envパス等)と同様に、
# frozen時は sys.executable(exeの場所)を基準にパスを組み立てる。
#
# 学習済みモデルは数百KBと小さいため、Azure Functions運用時もデプロイパッケージに
# そのまま同梱する(BERT版のようなBlob Storageからのダウンロード・キャッシュは不要)。
MODEL_FILENAME = "reminder_classifier.joblib"
if getattr(sys, "frozen", False):
    MODEL_PATH = Path(sys.executable).resolve().parent / "_internal" / "model" / MODEL_FILENAME
else:
    MODEL_PATH = Path(__file__).resolve().parent / MODEL_FILENAME

_model = None


def _load_model() -> None:
    """
    MODEL_PATH から学習済みモデルを読み込み、モジュール内にキャッシュする
    (2回目以降の呼び出しでは何もしない)
    """
    global _model
    # すでに読み込み済みの場合は何もしない
    if _model is not None:
        return
    # 学習済みモデル(Pipeline)と学習条件の情報をまとめて保存した辞書から、モデル本体を取り出す
    _model = joblib.load(MODEL_PATH)["model"]


def predict_reminder_score(text: str) -> float:
    """
    投稿テキスト1件のリマインド必要度をスコアリングする

    Args
    -----------------
    - text: str,       スコアリング対象の投稿本文

    Returns
    -----------------
    - score: float,    リマインドが必要そうな度合い(0~1)

    """
    return predict_reminder_scores([text])[0]


def predict_reminder_scores(texts: list[str]) -> list[float]:
    """
    複数の投稿テキストをまとめてスコアリングする

    Args
    -----------------
    - texts: list[str],    スコアリング対象の投稿本文のリスト

    Returns
    -----------------
    - scores: list[float], 各投稿に対応する、リマインドが必要そうな度合い(0~1)のリスト

    """
    # 空リストの場合はモデルを読み込まずに返す
    if not texts:
        return []
    # モデルが未読み込みの場合は読み込む
    _load_model()
    # 前処理・TF-IDF変換・ロジスティック回帰をまとめて適用し、"1(要リマインド)"クラスの確率を得る
    probs = _model.predict_proba(texts)
    # 各テキストに対応する"1(要リマインド)"クラスの確率をリストで返す
    return probs[:, 1].tolist()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('使い方: python -m app.model.predict "投稿テキスト"')
        raise SystemExit(1)
    score = predict_reminder_score(sys.argv[1])
    print(f"リマインド必要度スコア: {score:.4f}")
