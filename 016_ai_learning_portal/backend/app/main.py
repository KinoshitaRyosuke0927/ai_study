"""FastAPI アプリのエントリポイント。

起動(backend/ で実行): uvicorn app.main:app --reload --port 8016
本番ではフロントエンドのビルド成果物(frontend/dist)もこのアプリから配信する。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.config.settings import get_settings
from app.infra.db import get_engine
from app.routers import auth, learning


def create_app() -> FastAPI:
    """
    FastAPI アプリを生成する

    Returns
    -----------------
    - app: FastAPI,                     アプリ

    """
    # 設定を読み込む
    settings = get_settings()
    # 本番で既定の秘密鍵のまま起動しないようにする
    if not settings.is_local and settings.app_secret_key == "change-me":
        raise RuntimeError("APP_SECRET_KEY を設定してください")
    # アプリを生成
    app = FastAPI(title="AI学習ポータル", docs_url="/api/docs", openapi_url="/api/openapi.json")
    # 署名付き Cookie によるセッション(本番は HTTPS のみ送信)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.app_secret_key,
        session_cookie="ai_learning_portal_session",
        max_age=settings.app_session_max_age_days * 24 * 3600,
        same_site="lax",
        https_only=not settings.is_local,
    )
    # API ルーターを登録
    app.include_router(auth.router)
    app.include_router(learning.router)

    @app.get("/api/health")
    def health() -> dict:
        """
        死活監視用(DB への接続も確認する)

        Returns
        -----------------
        - status: dict,                     状態

        """
        # DB に簡単なクエリを投げて接続を確認
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        # 正常なら ok を返却
        return {"status": "ok"}

    # フロントエンドのビルド成果物があれば配信する
    dist = Path(settings.app_frontend_dist)
    if dist.is_dir():
        _mount_frontend(app, dist)
    # アプリを返却
    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    """
    SPA(ビルド済みフロントエンド)を配信するルートを登録する

    Args
    -----------------
    - app: FastAPI,                     アプリ
    - dist: Path,                       ビルド成果物のフォルダ

    """
    # ハッシュ付きの静的ファイル(JS/CSS)
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        """
        SPA のルーティング用に index.html を返す

        Args
        -----------------
        - path: str,                        要求されたパス

        Returns
        -----------------
        - response: FileResponse,           ファイル

        """
        # 未定義の API は 404 を返す(index.html を返さない)
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        # 実在するファイル(favicon など)はそのまま返す
        target = (dist / path).resolve()
        if path and target.is_file() and dist.resolve() in target.parents:
            return FileResponse(target)
        # それ以外は SPA の index.html を返す
        index = dist / "index.html"
        if not index.exists():
            raise HTTPException(404)
        return FileResponse(index)


app = create_app()
