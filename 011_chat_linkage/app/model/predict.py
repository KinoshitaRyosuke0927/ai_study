"""train_model.py で学習したモデルを使い、投稿テキストの
「リマインドが必要そうか」を0~1のスコアで判定する。

動作確認用の実行方法: 011_chat_linkage ディレクトリで
    python -m app.model.predict "@channel 明日までに経費精算をお願いします"
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# exe化(PyInstaller)時、__file__ は "app/model/" のパッケージ階層を保持したまま
# _internal 配下に展開されるため、通常のimportモジュールと同じ扱いでは
# --add-data で配置した "_internal/model/reminder_classifier" と場所がずれる。
# そのため他のモジュール(mattermost_service.pyの.envパス等)と同様に、
# frozen時は sys.executable(exeの場所)を基準にパスを組み立てる。
#
# Azure Functions運用時は、学習済みモデル(数百MB)をデプロイパッケージに含めると
# デプロイに失敗するため、パッケージには含めずBlob Storageから初回起動時のみ
# ダウンロードしてMODEL_CACHE_DIR環境変数の指すローカル領域にキャッシュする。
MODEL_CACHE_DIR_ENV = "MODEL_CACHE_DIR"
MODEL_BLOB_CONTAINER_ENV = "MODEL_BLOB_CONTAINER"
MODEL_FILES = ["config.json", "model.safetensors", "tokenizer_config.json", "training_args.bin", "vocab.txt"]

if getattr(sys, "frozen", False):
    MODEL_DIR = Path(sys.executable).resolve().parent / "_internal" / "model" / "reminder_classifier"
elif os.environ.get(MODEL_CACHE_DIR_ENV):
    MODEL_DIR = Path(os.environ[MODEL_CACHE_DIR_ENV])
else:
    MODEL_DIR = Path(__file__).resolve().parent / "reminder_classifier"
MAX_LENGTH = 256

_tokenizer = None
_model = None


def _ensure_model_cached() -> None:
    """
    MODEL_CACHE_DIR環境変数が設定されている場合(Azure Functions運用時)、
    モデルファイルがまだローカルにキャッシュされていなければBlob Storageから
    ダウンロードする。ローカル実行・exe配布時はMODEL_CACHE_DIRを設定しないため
    何もしない(既存のパッケージ同梱モデルをそのまま使う)。
    """
    if not os.environ.get(MODEL_CACHE_DIR_ENV):
        return
    # 代表として1ファイルの有無だけを見て、キャッシュ済みかどうかを判定する
    if (MODEL_DIR / MODEL_FILES[0]).exists():
        return

    from azure.storage.blob import BlobServiceClient

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    conn_str = os.environ["AzureWebJobsStorage"]
    container_name = os.environ.get(MODEL_BLOB_CONTAINER_ENV, "models")
    service_client = BlobServiceClient.from_connection_string(conn_str)
    container_client = service_client.get_container_client(container_name)
    for filename in MODEL_FILES:
        blob_client = container_client.get_blob_client(f"reminder_classifier/{filename}")
        (MODEL_DIR / filename).write_bytes(blob_client.download_blob().readall())


def _load_model() -> None:
    """
    MODEL_DIR から学習済みモデル・トークナイザーを読み込み、モジュール内にキャッシュする
    (2回目以降の呼び出しでは何もしない)
    """
    global _tokenizer, _model
    # すでに読み込み済みの場合は何もしない
    if _model is not None:
        return
    # Azure Functions運用時は、ローカルに未キャッシュならBlob Storageから取得する
    _ensure_model_cached()
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
