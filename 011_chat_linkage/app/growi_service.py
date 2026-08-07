"""GROWI(社内wiki)へアジェンダページを公開するためのラッパー関数群。

GROWI REST API v3 でページの取得・新規作成を行い、既存ページの更新のみ
レガシーAPI(/_api/pages.update)を利用する(v3にはページ更新用の
エンドポイントが存在しないため)。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
import requests

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

GROWI_BASE_URL = os.environ["GROWI_BASE_URL"].rstrip("/")
GROWI_API_TOKEN = os.environ["GROWI_API_TOKEN"]

# 新規作成ページの公開範囲(1 = 公開)
PAGE_GRANT_PUBLIC = 1


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


def _create_page(path: str, body: str) -> dict:
    """新規ページを作成する。中間階層(親ページ)が無い場合は自動生成される"""
    response = requests.post(
        f"{GROWI_BASE_URL}/_api/v3/pages",
        params={"access_token": GROWI_API_TOKEN},
        json={"path": path, "body": body, "grant": PAGE_GRANT_PUBLIC},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["page"]


def _update_page(page_id: str, revision_id: str, body: str) -> dict:
    """既存ページの内容を上書き更新する"""
    response = requests.post(
        f"{GROWI_BASE_URL}/_api/pages.update",
        params={"access_token": GROWI_API_TOKEN},
        data={"page_id": page_id, "revision_id": revision_id, "body": body},
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok", True):
        raise requests.HTTPError(data.get("error", "GROWIページの更新に失敗しました"))
    return data["page"]


def publish_agenda(root_path: str, year: int, month: int, body: str) -> dict:
    """
    root_path 配下に "/{year}/{month:02d}" のページを作成(無ければ新規作成、
    既にあれば上書き更新)し、公開先のパスとURLを返す。
    """
    path = f"{root_path.rstrip('/')}/{year}/{month:02d}"

    existing = _get_page(path)
    if existing is None:
        page = _create_page(path, body)
    else:
        page = _update_page(existing["_id"], existing["revision"]["_id"], body)

    return {"path": path, "url": f"{GROWI_BASE_URL}/{page['_id']}"}
