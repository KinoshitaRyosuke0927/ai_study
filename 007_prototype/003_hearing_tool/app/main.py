"""ヒアリング管理ツールの起動。

起動方法（003_hearing_tool フォルダで実行）：
    .venv\\Scripts\\python.exe -m uvicorn app.main:app --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import RESOURCE_ROOT
from .routers import analysis, io, sessions, tables, transcripts
from .storage import StorageError, data_dir

# 画面のファイルの場所（exe では同梱先のフォルダから探す）
STATIC_DIR = RESOURCE_ROOT / "app" / "static"

@asynccontextmanager
async def lifespan(_: FastAPI):
    """起動時にデータフォルダを用意する。

    Args:
        _: アプリ（使わない）。

    Returns:
        非同期のコンテキスト。終了時の処理はない。
    """
    data_dir()
    yield


app = FastAPI(title="ヒアリング管理ツール", lifespan=lifespan)

# API を登録する
app.include_router(tables.router)
app.include_router(sessions.router)
app.include_router(io.router)
app.include_router(transcripts.router)
app.include_router(analysis.router)

# 画面のファイルを配信する
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(StorageError)
def handle_storage_error(_: Request, exc: StorageError) -> JSONResponse:
    """CSV の読み書きの失敗を、画面に出せる形で返す。

    Args:
        _: リクエスト（使わない）。
        exc: 発生したエラー。

    Returns:
        JSONResponse: 400 と、エラーの内容。
    """
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/")
def index() -> FileResponse:
    """トップの画面を返す。

    Returns:
        FileResponse: index.html。
    """
    return FileResponse(STATIC_DIR / "index.html")
