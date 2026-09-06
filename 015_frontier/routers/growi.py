"""wiki(GROWI)情報取得(画面表示用。DB へは保存しない)。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config.runtime import load_runtime_config
from config.settings import get_settings

router = APIRouter()


class GrowiFetchBody(BaseModel):
    """/api/growi/fetch のリクエストボディ。"""

    page_id: str


@router.get("/api/growi/pages")
def api_growi_pages() -> dict[str, Any]:
    """設定の「参照する Wiki のページ」配下のページ一覧(プルダウン用)。"""
    from viewers import growi as growi_view

    settings = get_settings()
    rc = load_runtime_config()
    try:
        return growi_view.list_pages(settings, rc.growi_page_path)
    except growi_view.GrowiViewError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/api/growi/fetch")
def api_growi_fetch(body: GrowiFetchBody) -> dict[str, Any]:
    """選択ページの記事内容・更新履歴・コメントを返す。"""
    from viewers import growi as growi_view

    settings = get_settings()
    try:
        return growi_view.fetch_page(settings, body.page_id.strip())
    except growi_view.GrowiViewError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
