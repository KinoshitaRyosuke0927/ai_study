"""train_model.py で学習したモデルを使い、投稿テキストの
「リマインドが必要そうか」を0~1のスコアで判定する。

動作確認用の実行方法: 011_chat_linkage ディレクトリで
    python -m app.model.predict "@channel 明日までに経費精算をお願いします"
"""

from __future__ import annotations

import sys
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

MODEL_DIR = Path(__file__).resolve().parent / "reminder_classifier"
MAX_LENGTH = 256

_tokenizer = None
_model = None


def _load_model() -> None:
    """
    MODEL_DIR から学習済みモデル・トークナイザーを読み込み、モジュール内にキャッシュする
    (2回目以降の呼び出しでは何もしない)
    """
    global _tokenizer, _model
    # すでに読み込み済みの場合は何もしない
    if _model is not None:
        return
    # 学習済みモデル・トークナイザーを読み込む
    _tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))
    _model = AutoModelForSequenceClassification.from_pretrained(str(MODEL_DIR))
    # 推論モードに切り替える(Dropoutなどを無効化)
    _model.eval()


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
    # モデル・トークナイザーが未読み込みの場合は読み込む
    _load_model()
    # テキストをトークナイズ
    inputs = _tokenizer(
        text, truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt"
    )
    # 勾配計算をせずに推論を実行
    with torch.no_grad():
        logits = _model(**inputs).logits
    # ロジットを確率(0~1)に変換
    probs = torch.softmax(logits, dim=1)
    # "1(要リマインド)"クラスの確率を返す
    return probs[0][1].item()


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
    # モデル・トークナイザーが未読み込みの場合は読み込む
    _load_model()
    # 複数テキストをまとめてトークナイズ(バッチ処理)
    inputs = _tokenizer(
        texts, truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt"
    )
    # 勾配計算をせずに推論を実行
    with torch.no_grad():
        logits = _model(**inputs).logits
    # ロジットを確率(0~1)に変換
    probs = torch.softmax(logits, dim=1)
    # 各テキストに対応する"1(要リマインド)"クラスの確率をリストで返す
    return probs[:, 1].tolist()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('使い方: python -m app.model.predict "投稿テキスト"')
        raise SystemExit(1)
    score = predict_reminder_score(sys.argv[1])
    print(f"リマインド必要度スコア: {score:.4f}")
