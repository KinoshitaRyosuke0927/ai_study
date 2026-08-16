"""GROWI(社内wiki)へアジェンダページを公開するためのラッパー関数群。

GROWI REST API v3 でページの取得・新規作成を行い、既存ページの更新のみ
レガシーAPI(/_api/pages.update)を利用する(v3にはページ更新用の
エンドポイントが存在しないため)。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import requests

# 環境変数(.env)を読み込む
if getattr(sys, "frozen", False):
    _env_path = Path(sys.executable).resolve().parent / ".env"
else:
    _env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(_env_path)

GROWI_BASE_URL = os.environ["GROWI_BASE_URL"].rstrip("/")
GROWI_API_TOKEN = os.environ["GROWI_API_TOKEN"]

# ページの公開範囲
PAGE_GRANT_PUBLIC = 1
PAGE_GRANT_ONLY_ME = 4


def _get_page(path: str) -> dict | None:
    """指定パスのページ情報を取得する。存在しない場合は None を返す"""
    response = requests.get(
        f"{GROWI_BASE_URL}/_api/v3/page",
        params={"path": path, "access_token": GROWI_API_TOKEN},
        timeout=10,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()["page"]


def _create_page(path: str, body: str, grant: int) -> dict:
    """新規ページを作成する。中間階層(親ページ)が無い場合は自動生成される。
    grant=PAGE_GRANT_ONLY_ME の場合、GROWI側がAPIトークンの持ち主を
    自動的にアクセス許可ユーザーとして設定する。"""
    response = requests.post(
        f"{GROWI_BASE_URL}/_api/v3/pages",
        params={"access_token": GROWI_API_TOKEN},
        json={"path": path, "body": body, "grant": grant},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["page"]


def _update_page(page_id: str, revision_id: str, body: str, grant: int | None = None) -> dict:
    """既存ページの内容を上書き更新する。

    grant を指定する場合は PAGE_GRANT_ONLY_ME 以外を渡すこと。レガシーAPI
    (/_api/pages.update) は grant=PAGE_GRANT_ONLY_ME 変更時にアクセス許可
    ユーザーを正しく設定できず、投稿者自身も含めて誰もアクセスできない
    ページになってしまうため、その変更には _delete_page + _create_page を使う。
    """
    data = {"page_id": page_id, "revision_id": revision_id, "body": body}
    if grant is not None:
        data["grant"] = grant
    response = requests.post(
        f"{GROWI_BASE_URL}/_api/pages.update",
        params={"access_token": GROWI_API_TOKEN},
        data=data,
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok", True):
        raise requests.HTTPError(data.get("error", "GROWIページの更新に失敗しました"))
    return data["page"]


def _delete_page(page_id: str) -> None:
    """ページを完全削除する"""
    response = requests.post(
        f"{GROWI_BASE_URL}/_api/v3/pages/delete",
        params={"access_token": GROWI_API_TOKEN},
        json={"pageIdToRevisionIdMap": {page_id: None}, "isCompletely": True},
        timeout=10,
    )
    response.raise_for_status()


def publish_agenda(root_path: str, year: int, month: int, body: str, grant: int) -> dict:
    """
    root_path 配下に "/{year}/{month:02d}" のページを、指定した公開範囲(grant)で
    作成(無ければ新規作成、既にあれば上書き更新)し、公開先のパス・URL・
    ページを新規作成し直したか(recreated)を返す。

    既存ページの公開範囲を PAGE_GRANT_ONLY_ME に変更する場合のみ、
    (レガシー更新APIの制約により)ページを削除して同じパスに新規作成し直す。
    この場合ページのURLが変わるため、呼び出し元に recreated=True を伝える。
    """
    path = f"{root_path.rstrip('/')}/{year}/{month:02d}"

    existing = _get_page(path)
    recreated = False
    if existing is None:
        page = _create_page(path, body, grant)
    elif existing["grant"] == grant:
        page = _update_page(existing["_id"], existing["revision"]["_id"], body)
    elif grant == PAGE_GRANT_ONLY_ME:
        _delete_page(existing["_id"])
        page = _create_page(path, body, grant)
        recreated = True
    else:
        page = _update_page(existing["_id"], existing["revision"]["_id"], body, grant=grant)

    return {"path": path, "url": f"{GROWI_BASE_URL}/{page['_id']}", "recreated": recreated}
