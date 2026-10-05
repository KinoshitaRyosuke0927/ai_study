"""ポーリング監視の状態(最終処理済み投稿時刻)をAzure Blob Storageに永続化する。

Azure Functions(Consumption)は実行間でメモリ状態を保持しないため、
「どの投稿まで処理済みか」をチャンネル単位でBlobに保存し、次回実行時に読み出す。
保存先には、Azure Functionsが元々必要とするStorage Account
(環境変数 AzureWebJobsStorage の接続文字列)を流用する。
"""

from __future__ import annotations

import json
import os

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient, ContainerClient

STATE_CONTAINER_NAME = "slash-command-watcher-state"


def _get_container_client() -> ContainerClient:
    """AzureWebJobsStorage接続文字列から、状態保存用コンテナのクライアントを取得する
    (コンテナが無ければ作成する)"""
    conn_str = os.environ["AzureWebJobsStorage"]
    service_client = BlobServiceClient.from_connection_string(conn_str)
    container_client = service_client.get_container_client(STATE_CONTAINER_NAME)
    if not container_client.exists():
        container_client.create_container()
    return container_client


def load_channel_state(channel_id: str) -> dict:
    """
    指定チャンネルの監視状態を取得する。未保存の場合は初期状態を返す

    Args
    -----------------
    - channel_id: str,   Mattermostのチャンネル(またはDMチャンネル)ID

    Returns
    -----------------
    - state: dict,   {"last_processed_at": int(epoch ms), "last_processed_post_ids": list[str]}
                      last_processed_at=0 は「未処理(初回)」を表す

    """
    container_client = _get_container_client()
    blob_client = container_client.get_blob_client(f"{channel_id}.json")
    try:
        data = blob_client.download_blob().readall()
    except ResourceNotFoundError:
        return {"last_processed_at": 0, "last_processed_post_ids": []}
    return json.loads(data)


def save_channel_state(channel_id: str, last_processed_at: int, last_processed_post_ids: list[str]) -> None:
    """
    指定チャンネルの監視状態を上書き保存する

    Args
    -----------------
    - channel_id: str,                     Mattermostのチャンネル(またはDMチャンネル)ID
    - last_processed_at: int,              今回のポーリングで処理済みとする最新のcreate_at(epoch ms)
    - last_processed_post_ids: list[str],  last_processed_atと同時刻(ミリ秒同値)の投稿IDの一覧
                                            (同一ミリ秒に複数投稿があった場合の重複処理防止用)

    Returns
    -----------------
    - None

    """
    container_client = _get_container_client()
    blob_client = container_client.get_blob_client(f"{channel_id}.json")
    body = json.dumps(
        {"last_processed_at": last_processed_at, "last_processed_post_ids": last_processed_post_ids},
        ensure_ascii=False,
    )
    blob_client.upload_blob(body, overwrite=True)
