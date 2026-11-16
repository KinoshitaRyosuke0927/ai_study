"""アジェンダ作成ツールの FastAPI エントリポイント。
Mattermost投稿・GROUPSESSION記事の期間指定取得(学習済みモデルによる絞り込み)、
AIによる部会アジェンダ生成、GROWIへの公開を行う。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests

from app import agenda_service
from app import groupsession_service as gs
from app import growi_service as growi
from app import mattermost_service as mm
from app.settings_loader import load_settings

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

SETTINGS = load_settings()


class AgendaItem(BaseModel):
    message: str
    username: str
    source: str
    url: str | None = None


class AgendaRequest(BaseModel):
    items: list[AgendaItem]


class AgendaPublishRequest(BaseModel):
    agenda: str
    year: int
    month: int
    grant: str = "public"  # "public": 公開 / "only_me": 自分のみ公開


class GroupsessionLoginRequest(BaseModel):
    username: str
    password: str


app = FastAPI(title="アジェンダ作成ツール", version="1.0.0")
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


@app.get("/api/groupsession/login-status")
def get_groupsession_login_status() -> dict:
    return {"logged_in": gs.has_credentials()}


@app.post("/api/groupsession/login")
def post_groupsession_login(request: GroupsessionLoginRequest) -> dict:
    username = request.username.strip()
    password = request.password
    if not username or not password:
        raise HTTPException(status_code=400, detail="IDとパスワードを入力してください")

    try:
        gs.login(username, password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except requests.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"GROUPSESSION APIエラー: {exc}") from exc

    return {"result": "ok"}


@app.post("/api/groupsession/logout")
def post_groupsession_logout() -> dict:
    gs.logout()
    return {"result": "ok"}


@app.get("/api/settings")
def get_settings() -> dict:
    """settings.ini に設定された、履歴取得対象のチャンネル名・期間(日数)を返す"""
    return SETTINGS


@app.get("/api/channels")
def get_channels() -> list[dict]:
    try:
        return mm.list_my_channels()
    except requests.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Mattermost APIエラー: {exc}") from exc


@app.get("/api/channels/{channel_id}/posts")
def get_channel_posts(channel_id: str, start: str, end: str, threshold: float = 0.5) -> list[dict]:
    try:
        start_ts = date_str_to_epoch_ms(start, end_of_day=False)
        end_ts = date_str_to_epoch_ms(end, end_of_day=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="日付の形式が正しくありません (YYYY-MM-DD)") from exc

    if start_ts > end_ts:
        raise HTTPException(status_code=400, detail="取得開始日は取得終了日より前にしてください")

    try:
        posts = mm.get_channel_posts_in_range(channel_id, start_ts, end_ts)
    except requests.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Mattermost APIエラー: {exc}") from exc

    try:
        return agenda_service.filter_posts_by_reminder_score(posts, threshold)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"モデルによる投稿の絞り込みに失敗しました: {exc}") from exc


@app.get("/api/webpage/announcements")
def get_webpage_announcements(start: str, end: str, threshold: float = 0.5) -> list[dict]:
    if not gs.has_credentials():
        raise HTTPException(status_code=401, detail="GROUPSESSIONにログインしてください")

    forum_sids = SETTINGS.get("groupsession_forum_sids", [])
    if not forum_sids:
        raise HTTPException(status_code=400, detail="settings.iniにgroupsessionのforum_sidが設定されていません")

    try:
        since_ts_ms = date_str_to_epoch_ms(start, end_of_day=False)
        until_ts_ms = date_str_to_epoch_ms(end, end_of_day=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="日付の形式が正しくありません (YYYY-MM-DD)") from exc

    if since_ts_ms > until_ts_ms:
        raise HTTPException(status_code=400, detail="取得開始日は取得終了日より前にしてください")

    try:
        posts = [
            post
            for forum_sid in forum_sids
            for post in gs.get_recent_announcements(forum_sid, since_ts_ms, until_ts_ms)
        ]
        posts.sort(key=lambda p: p["create_at"])
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except requests.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"GROUPSESSIONへのアクセスに失敗しました: {exc}") from exc

    try:
        return agenda_service.filter_posts_by_reminder_score(posts, threshold)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"モデルによる投稿の絞り込みに失敗しました: {exc}") from exc


@app.post("/api/agenda")
def post_agenda(request: AgendaRequest) -> dict:
    if not request.items:
        raise HTTPException(status_code=400, detail="アジェンダに含める投稿・記事が選択されていません")

    try:
        agenda = agenda_service.render_agenda_document([item.model_dump() for item in request.items])
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AIによるアジェンダ生成に失敗しました: {exc}") from exc

    return {"agenda": agenda}


@app.post("/api/agenda/publish")
def publish_agenda(request: AgendaPublishRequest) -> dict:
    agenda = request.agenda.strip()
    if not agenda:
        raise HTTPException(status_code=400, detail="公開するアジェンダがありません")

    grant = growi.PAGE_GRANT_ONLY_ME if request.grant == "only_me" else growi.PAGE_GRANT_PUBLIC

    try:
        result = agenda_service.publish_agenda_document(SETTINGS, agenda, request.year, request.month, grant)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except requests.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"GROWIへの公開に失敗しました: {exc}") from exc

    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
