"""ダッシュボード HTML の配信とヘルスチェック。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import FileResponse

from infra.db import ping
from config.settings import get_settings

router = APIRouter()

STATIC_DIR = "static"


@router.get("/")
def index() -> FileResponse:
    """ダッシュボード HTML を配信する。"""
    return FileResponse(f"{STATIC_DIR}/index.html")


@router.get("/api/health")
def health() -> dict[str, Any]:
    """DB 接続と実行モードを返す。"""
    settings = get_settings()
    return {
        "status": "ok" if ping(settings) else "db_error",
        "run_mode": settings.app_run_mode,
        "ai_enabled": settings.ai_enabled,
    }
