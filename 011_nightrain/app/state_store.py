"""監視状態(どこまで確認したか・どの投稿を通知済みか)の永続化。

Azure Functions(Consumption)は実行間でメモリ状態を保持しないため、監視対象ごとの状態を
Azure Blob Storage(環境変数 AzureWebJobsStorage の接続文字列のストレージアカウント)に保存する。

ローカルでの動作確認時は、環境変数 STATE_STORE_DIR にフォルダを指定すると、
Blobの代わりにそのフォルダへJSONファイルとして保存する(run_local.py が設定する)。

保存する状態の形式:
    {
        "cursor": int,              # 次回の取得開始の基準にする時刻(epochミリ秒、0は未処理=初回)
        "notified": {id: int},      # 通知済み(または通知をあきらめた)投稿ID -> 投稿時刻(epochミリ秒)
        "failures": {id: int},      # リマインド作成・投稿に失敗した投稿ID -> 失敗回数
    }

これとは別に、再リマインドの予定を "followups"(形式は app/followup.py)、変更後の期日を "deadline_changes"(形式は app/dedup.py)というキーで保存する。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

STATE_CONTAINER_NAME = "nightrain-state"

# 再リマインド予定の一覧を保存するキー(監視対象ごとの状態とは別に1つだけ持つ)
FOLLOWUP_KEY = "followups"


def _empty_state() -> dict:
    """初期状態(未処理)を返す"""
    return {"cursor": 0, "notified": {}, "failures": {}}


def _local_dir() -> Path | None:
    """ローカル保存先のフォルダ(STATE_STORE_DIR)を返す。未設定ならNone(Blobを使う)"""
    raw = os.environ.get("STATE_STORE_DIR", "").strip()
    return Path(raw) if raw else None


def _get_container_client():
    """
    AzureWebJobsStorage接続文字列から、状態保存用コンテナのクライアントを取得する
    (コンテナが無ければ作成する)

    Args
    -----------------
    - なし

    Returns
    -----------------
    - container_client: ContainerClient,  状態保存用コンテナのクライアント

    """
    # ローカル保存時はazure-storage-blobを不要にするため、ここでimportする
    from azure.storage.blob import BlobServiceClient

    conn_str = os.environ["AzureWebJobsStorage"]
    service_client = BlobServiceClient.from_connection_string(conn_str)
    container_client = service_client.get_container_client(STATE_CONTAINER_NAME)
    if not container_client.exists():
        container_client.create_container()
    return container_client


def _read_json(key: str) -> dict | None:
    """
    指定キーのJSONを読み込む(未保存の場合は None)

    Args
    -----------------
    - key: str,  保存キー(ファイル名・Blob名の拡張子を除いた部分)

    Returns
    -----------------
    - data: dict | None,  保存されている内容。未保存なら None

    """
    # ローカル保存の場合はJSONファイルから読み込む
    local_dir = _local_dir()
    if local_dir is not None:
        path = local_dir / f"{key}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    # Blobから読み込む(未保存なら None)
    from azure.core.exceptions import ResourceNotFoundError

    blob_client = _get_container_client().get_blob_client(f"{key}.json")
    try:
        return json.loads(blob_client.download_blob().readall())
    except ResourceNotFoundError:
        return None


def _write_json(key: str, data: dict) -> None:
    """
    指定キーにJSONを上書き保存する

    Args
    -----------------
    - key: str,    保存キー
    - data: dict,  保存する内容

    Returns
    -----------------
    - None

    """
    body = json.dumps(data, ensure_ascii=False)

    # ローカル保存の場合はJSONファイルに書き込む
    local_dir = _local_dir()
    if local_dir is not None:
        local_dir.mkdir(parents=True, exist_ok=True)
        (local_dir / f"{key}.json").write_text(body, encoding="utf-8")
        return

    # Blobに上書き保存する
    _get_container_client().get_blob_client(f"{key}.json").upload_blob(body, overwrite=True)


def load_state(key: str) -> dict:
    """
    指定した監視対象の状態を取得する。未保存の場合は初期状態を返す

    Args
    -----------------
    - key: str,  監視対象を表すキー(例: "mattermost-<チャンネルID>", "groupsession-<フォーラムID>")

    Returns
    -----------------
    - state: dict,  {"cursor", "notified", "failures"}

    """
    # 項目が欠けていても動くよう、初期状態に上書きする形で返す
    return {**_empty_state(), **(_read_json(key) or {})}


def save_state(key: str, state: dict) -> None:
    """
    指定した監視対象の状態を上書き保存する

    Args
    -----------------
    - key: str,     監視対象を表すキー
    - state: dict,  保存する状態({"cursor", "notified", "failures"})

    Returns
    -----------------
    - None

    """
    _write_json(key, state)


def load_followups() -> dict:
    """
    再リマインド予定の一覧を取得する(未保存の場合は空)

    Args
    -----------------
    - なし

    Returns
    -----------------
    - followups: dict,  {1回目のリマインド投稿ID: 再リマインドの予定(app.followup を参照)}

    """
    return _read_json(FOLLOWUP_KEY) or {}


def save_followups(followups: dict) -> None:
    """
    再リマインド予定の一覧を上書き保存する

    Args
    -----------------
    - followups: dict,  {1回目のリマインド投稿ID: 再リマインドの予定}

    Returns
    -----------------
    - None

    """
    _write_json(FOLLOWUP_KEY, followups)


def load_json(key: str) -> dict:
    """
    任意のキーで保存した辞書を取得する(未保存の場合は空)

    Args
    -----------------
    - key: str,  保存キー(例: "deadline_changes")

    Returns
    -----------------
    - data: dict,  保存されている内容
    """
    return _read_json(key) or {}


def save_json(key: str, data: dict) -> None:
    """
    任意のキーで辞書を上書き保存する

    Args
    -----------------
    - key: str,    保存キー
    - data: dict,  保存する内容

    Returns
    -----------------
    - None
    """
    _write_json(key, data)
