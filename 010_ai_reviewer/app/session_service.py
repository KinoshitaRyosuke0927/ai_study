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

# 保存先のBlob接続文字列。共有機能と同じストレージアカウントを流用する（コンテナだけ分ける）
SESSION_STORAGE_CONNECTION_STRING = (
    os.getenv("SESSION_STORAGE_CONNECTION_STRING")
    or os.getenv("SHARE_STORAGE_CONNECTION_STRING", "")
)
SESSION_CONTAINER_NAME = "sessions"
SESSION_EXPIRES_DAYS = 30

# 接続文字列が無い場合は、ローカルのファイルシステムに保存するフォールバックを使う（開発・動作確認用）
_USE_BLOB = bool(SESSION_STORAGE_CONNECTION_STRING)
_LOCAL_SESSION_DIR = _base_dir / "_sessions"


def _get_container_client():
    """
    作業状況の保存用のBlobコンテナクライアントを取得する
    """
    client = BlobServiceClient.from_connection_string(SESSION_STORAGE_CONNECTION_STRING)
    return client.get_container_client(SESSION_CONTAINER_NAME)


def _local_path(session_id: str) -> Path:
    """
    ローカルフォールバック時の保存ファイルパスを返す
    """
    return _LOCAL_SESSION_DIR / f"{session_id}.json"


def _write_record(session_id: str, record: dict[str, Any]) -> None:
    """
    保存レコードをBlob（またはローカルファイル）に書き込む（上書き）
    """
    data = json.dumps(record, ensure_ascii=False)
    if _USE_BLOB:
        # Blob Storageへ保存（同じ名前で上書き）。上書き時はライフサイクル削除の起点もリセットされる
        _get_container_client().upload_blob(
            name=f"{session_id}.json",
            data=data,
            overwrite=True,
            content_type="application/json",
        )
    else:
        # ローカルファイルへ保存
        _LOCAL_SESSION_DIR.mkdir(parents=True, exist_ok=True)
        _local_path(session_id).write_text(data, encoding="utf-8")


def _read_record(session_id: str) -> dict[str, Any] | None:
    """
    保存レコードをBlob（またはローカルファイル）から読み込む。存在しなければ None
    """
    if _USE_BLOB:
        try:
            raw = _get_container_client().download_blob(f"{session_id}.json").readall()
        except ResourceNotFoundError:
            return None
        return json.loads(raw)

    path = _local_path(session_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _is_expired(record: dict[str, Any]) -> bool:
    """
    有効期限切れかどうかを判定する
    """
    expires_at = datetime.fromisoformat(record["expires_at"])
    return datetime.now(timezone.utc) >= expires_at


def create_session(payload: dict[str, Any]) -> dict[str, Any]:
    """
    作業状況のスナップショットを新規保存し、保存用メタデータを返す

    Args
    -----------------
    - payload: dict[str, Any],   ブラウザから送られてきた作業状況一式（スライド画像・レビュー結果・修正イメージ・伝えたいことなど）

    Returns
    -----------------
    - meta: dict[str, Any],      session_id / created_at / updated_at / expires_at を含む辞書

    """
    # 一意な保存IDを発行し、この後URLに使う
    session_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=SESSION_EXPIRES_DAYS)

    # 受け取った作業状況にメタ情報を付与してレコードを組み立てる
    record = {
        **payload,
        "session_id": session_id,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }

    # 保存先へ書き込む
    _write_record(session_id, record)

    return {
        "session_id": session_id,
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "expires_at": record["expires_at"],
    }


def update_session(session_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """
    既存の保存IDに対して作業状況を上書き保存する。IDが存在しない／期限切れの場合は None を返す（URLは変わらない）

    Args
    -----------------
    - session_id: str,           上書き対象の保存ID
    - payload: dict[str, Any],   新しい作業状況一式

    Returns
    -----------------
    - meta: dict[str, Any] | None,   session_id / created_at / updated_at / expires_at を含む辞書（不在・期限切れは None）

    """
    # 既存レコードを読み込む（作成日時を引き継ぐため）
    existing = _read_record(session_id)
    if existing is None or _is_expired(existing):
        return None

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=SESSION_EXPIRES_DAYS)

    # 作成日時は維持し、内容・更新日時・有効期限を更新する
    record = {
        **payload,
        "session_id": session_id,
        "created_at": existing.get("created_at", now.isoformat()),
        "updated_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }

    # 同じ名前で上書き保存する
    _write_record(session_id, record)

    return {
        "session_id": session_id,
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "expires_at": record["expires_at"],
    }


def get_session(session_id: str) -> dict[str, Any] | None:
    """
    保存IDに対応する作業状況のスナップショットを取得する。有効期限切れ、または存在しない場合は None を返す

    Args
    -----------------
    - session_id: str,   保存ID

    Returns
    -----------------
    - record: dict[str, Any] | None,   保存されている作業状況一式（期限切れ/不在の場合は None）

    """
    record = _read_record(session_id)
    if record is None:
        return None

    # 有効期限切れの場合は、物理削除（ライフサイクル管理）を待たずに「見つからない」扱いにする
    if _is_expired(record):
        return None

    return record
