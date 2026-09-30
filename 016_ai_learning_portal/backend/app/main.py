"""FastAPI アプリのエントリポイント。

起動(backend/ で実行): uvicorn app.main:app --reload --port 8000
本番ではフロントエンドのビルド成果物(frontend/dist)もこのアプリから配信する。
"""

from __future__ import annotations

from pathlib import Path

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import InterfaceError, OperationalError
from starlette.middleware.sessions import SessionMiddleware

from app.config.settings import get_settings
from app.infra.db import get_engine
from app.infra.db_power import DbPowerError, ensure_starting
from app.routers import admin, auth, learning
from app.services.activity_service import record_activity
from app.services.ai_course_service import mark_interrupted_jobs

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    起動・終了時の処理(起動時に、前回の実行中に止まった AI の下書き生成ジョブを「中断」にする)

    Args
    -----------------
    - app: FastAPI,                     アプリ

    """
    # DB が停止中などで失敗しても起動は続ける(最初のアクセスで DB を起動する)
    try:
        count = await run_in_threadpool(mark_interrupted_jobs)
        if count:
            logger.info("中断された AI の下書き生成ジョブ: %d 件", count)
    except Exception as e:
        logger.warning("起動時のジョブ確認をスキップしました: %s", e)
    yield


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
    app = FastAPI(title="AI学習ポータル", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)
    # 署名付き Cookie によるセッション(本番は HTTPS のみ送信)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.app_secret_key,
        session_cookie="ai_learning_portal_session",
        max_age=settings.app_session_max_age_days * 24 * 3600,
        same_site="lax",
        https_only=not settings.is_local,
    )
    @app.exception_handler(OperationalError)
    @app.exception_handler(InterfaceError)
    async def db_unavailable(request: Request, exc: Exception) -> JSONResponse:
        """
        DB に接続できないときの応答(自動起動が有効なら、停止中の DB を起動する)

        Args
        -----------------
        - request: Request,                 リクエスト
        - exc: Exception,                   発生した例外

        Returns
        -----------------
        - response: JSONResponse,           503 応答(code: db_starting / db_unavailable)

        """
        logger.warning("DB に接続できません: %s", exc)
        # 自動起動が無効(ローカルなど)なら、接続できないことだけを返す
        if not get_settings().db_autostart_enabled:
            return JSONResponse({"detail": "データベースに接続できません", "code": "db_unavailable"}, status_code=503)
        # 停止中なら起動を要求して、起動中であることを返す(画面は数分待って再接続する)
        try:
            state = await run_in_threadpool(ensure_starting)
        except DbPowerError as e:
            logger.error("DB の自動起動に失敗しました: %s", e)
            return JSONResponse({"detail": "データベースに接続できません", "code": "db_unavailable"}, status_code=503)
        return JSONResponse(
            {"detail": "データベースを起動しています。数分お待ちください。", "code": "db_starting", "db_state": state},
            status_code=503,
            headers={"Retry-After": "30"},
        )

    @app.middleware("http")
    async def track_activity(request: Request, call_next):
        """
        API へのアクセスがあれば最終アクセス日時を記録する(DB の自動停止の判断に使う)

        Args
        -----------------
        - request: Request,                 リクエスト
        - call_next: Callable,              次の処理

        Returns
        -----------------
        - response: Response,               応答

        """
        # リクエストを処理
        response = await call_next(request)
        # 正常に処理できた API 呼び出しだけを記録する(死活監視は除く)
        path = request.url.path
        if path.startswith("/api/") and path != "/api/health" and response.status_code < 500:
            try:
                await run_in_threadpool(record_activity)
            except Exception as e:  # 記録の失敗で応答を失敗させない
                logger.warning("最終アクセス日時を記録できませんでした: %s", e)
        return response

    # API ルーターを登録
    app.include_router(auth.router)
    app.include_router(learning.router)
    app.include_router(admin.router)

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
