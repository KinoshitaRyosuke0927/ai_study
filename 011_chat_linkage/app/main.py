"""Mattermost 連携アプリの FastAPI エントリポイント。
チャンネル一覧の取得、過去チャットの期間指定表示、リアクション確認、DM投稿を行う。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests

from app import mattermost_service as mm

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


class DmRequest(BaseModel):
    message: str


app = FastAPI(title="Mattermost チャット連携", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def date_str_to_epoch_ms(date_str: str, end_of_day: bool = False) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    if end_of_day:
        dt = dt + timedelta(days=1) - timedelta(milliseconds=1)
    return int(dt.timestamp() * 1000)


@app.get("/")
def index() -> FileResponse:
    """トップページを返す"""
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/target-username")
def get_target_username() -> dict:
    return {"username": mm.MATTERMOST_TARGET_USERNAME}


@app.get("/api/channels")
def get_channels() -> list[dict]:
    try:
        return mm.list_my_channels()
    except requests.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Mattermost APIエラー: {exc}") from exc


@app.get("/api/channels/{channel_id}/posts")
def get_channel_posts(channel_id: str, start: str, end: str) -> list[dict]:
    try:
        start_ts = date_str_to_epoch_ms(start, end_of_day=False)
        end_ts = date_str_to_epoch_ms(end, end_of_day=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="日付の形式が正しくありません (YYYY-MM-DD)") from exc

    if start_ts > end_ts:
        raise HTTPException(status_code=400, detail="取得開始日は取得終了日より前にしてください")

    try:
        return mm.get_channel_posts_in_range(channel_id, start_ts, end_ts)
    except requests.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Mattermost APIエラー: {exc}") from exc


@app.get("/api/posts/{post_id}/reactions")
def get_post_reactions(post_id: str) -> list[dict]:
    try:
        return mm.get_post_reactions(post_id)
    except requests.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Mattermost APIエラー: {exc}") from exc


@app.post("/api/dm")
def post_dm(request: DmRequest) -> dict:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="メッセージは必須です")

    try:
        mm.post_dm_to_target(message)
    except requests.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Mattermost APIエラー: {exc}") from exc

    return {"result": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
