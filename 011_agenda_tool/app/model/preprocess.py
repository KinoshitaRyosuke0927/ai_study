"""リマインド判定モデル(TF-IDF + ロジスティック回帰)の学習・推論で共通に使うテキスト前処理。

学習済みモデル(reminder_classifier.joblib)には、この関数への参照が含まれる。
そのため、モデルの読み込み時にこのモジュールがimportできる必要がある。
関数名・モジュールの場所を変更した場合は、モデルの再学習が必要になる。
"""

from __future__ import annotations

import re

# 全員宛てのメンション(内容の性質を表すため、正規化せずそのまま残す)
BROADCAST_MENTIONS = ("channel", "here", "all")
MENTION_PATTERN = re.compile(r"@(?!(?:%s)\b)[A-Za-z0-9._\-]+" % "|".join(BROADCAST_MENTIONS))
URL_PATTERN = re.compile(r"https?://\S+")


def preprocess_text(text: str) -> str:
    """
    個人宛てメンション・URLを共通の記号に置き換え、小文字化する
    (特定の人物名やURLの文字列にモデルが依存しないようにするため。@channel/@here/@all はそのまま残す)

    Args
    -----------------
    - text: str,   前処理前の投稿テキスト

    Returns
    -----------------
    - text: str,   前処理後のテキスト

    """
    # URLを置き換える(URL中の英数字が特徴量として拾われないようにする)
    text = URL_PATTERN.sub(" URL ", text)
    # 個人宛てメンション(@yamada など)を @USER に置き換える
    text = MENTION_PATTERN.sub("@USER", text)
    # 英字の大文字・小文字の違いを無視する
    return text.lower()
