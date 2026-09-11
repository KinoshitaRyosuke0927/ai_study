from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient

# 環境変数(.env)を読み込む
if getattr(sys, "frozen", False):
    _env_path = Path(sys.executable).resolve().parent / ".env"
    _base_dir = Path(sys.executable).resolve().parent
else:
    _env_path = Path(__file__).resolve().parents[2] / ".env"
    _base_dir = Path(__file__).resolve().parents[1]  # 010_ai_reviewer
load_dotenv(_env_path)

SHARE_STORAGE_CONNECTION_STRING = os.getenv("SHARE_STORAGE_CONNECTION_STRING", "")
SHARE_CONTAINER_NAME = "shares"
SHARE_EXPIRES_DAYS = 30

# 接続文字列が無い場合は、ローカルのファイルシステムに保存するフォールバックを使う（開発・動作確認用）
_USE_BLOB = bool(SHARE_STORAGE_CONNECTION_STRING)
_LOCAL_SHARE_DIR = _base_dir / "_shares"


def _get_container_client():
    """
    共有データ保存用のBlobコンテナクライアントを取得する
    """
    client = BlobServiceClient.from_connection_string(SHARE_STORAGE_CONNECTION_STRING)
    return client.get_container_client(SHARE_CONTAINER_NAME)


def _local_path(share_id: str) -> Path:
    """
    ローカルフォールバック時の保存ファイルパスを返す
    """
    return _LOCAL_SHARE_DIR / f"{share_id}.json"


def _write_record(share_id: str, record: dict[str, Any]) -> None:
    """
    共有レコードをBlob（またはローカルファイル）へ書き込む
    """
    data = json.dumps(record, ensure_ascii=False)
    if _USE_BLOB:
        # Blob Storageへ保存
        _get_container_client().upload_blob(
            name=f"{share_id}.json",
            data=data,
            overwrite=True,
            content_type="application/json",
        )
    else:
        # ローカルファイルへ保存
        _LOCAL_SHARE_DIR.mkdir(parents=True, exist_ok=True)
        _local_path(share_id).write_text(data, encoding="utf-8")


def _read_record(share_id: str) -> dict[str, Any] | None:
    """
    共有レコードをBlob（またはローカルファイル）から読み込む。存在しなければ None
    """
    if _USE_BLOB:
        try:
            raw = _get_container_client().download_blob(f"{share_id}.json").readall()
        except ResourceNotFoundError:
            return None
        return json.loads(raw)

    path = _local_path(share_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def create_share(payload: dict[str, Any]) -> dict[str, Any]:
    """
    レビュー結果のスナップショットをBlob Storageに保存し、共有用メタデータを返す

    Args
    -----------------
    - payload: dict[str, Any],   ブラウザから送られてきたレビュー結果一式（ファイル名・スライド・レビュー結果など）

    Returns
    -----------------
    - meta: dict[str, Any],      share_id / expires_at を含む辞書

    """
    share_id = uuid.uuid4().hex
    created_at = datetime.now(timezone.utc)
    expires_at = created_at + timedelta(days=SHARE_EXPIRES_DAYS)

    record = {
        **payload,
        "share_id": share_id,
        "created_at": created_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }

    # 保存先（Blob or ローカルファイル）へ書き込む
    _write_record(share_id, record)

    return {"share_id": share_id, "expires_at": expires_at.isoformat()}


def get_share(share_id: str) -> dict[str, Any] | None:
    """
    共有IDに対応するレビュー結果のスナップショットを取得する
    有効期限切れ、または存在しない場合は None を返す

    Args
    -----------------
    - share_id: str,   共有ID

    Returns
    -----------------
    - record: dict[str, Any] | None,   保存されているレビュー結果一式（期限切れ/不在の場合はNone）

    """
    record = _read_record(share_id)
    if record is None:
        return None

    # 有効期限切れの場合は、物理削除（ライフサイクル管理）を待たずに「見つからない」扱いにする
    expires_at = datetime.fromisoformat(record["expires_at"])
    if datetime.now(timezone.utc) >= expires_at:
        return None

    return record
