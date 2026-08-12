"""Mattermost 連携アプリの FastAPI エントリポイント。
チャンネル一覧の取得、過去チャットの期間指定表示、リアクション確認、DM投稿を行う。
"""

from __future__ import annotations

import configparser
import sys
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests

from app import groupsession_service as gs
from app import growi_service as growi
from app import mattermost_service as mm
from app.azure_ai_service import call_filter_reminder_posts, call_generate_agenda, call_generate_reminder

# リマインド作成時に、リアクション済みとみなす絵文字名
REMINDER_DONE_EMOJI = "sumi"

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
# settings.ini はユーザーが編集する運用のため、exe化(frozen)時はexeと同じ階層を参照する
if getattr(sys, "frozen", False):
    SETTINGS_PATH = Path(sys.executable).resolve().parent / "settings.ini"
else:
    SETTINGS_PATH = BASE_DIR.parent / "settings.ini"


def load_settings() -> dict:
    """settings.ini を読み込んで辞書で返す。ファイルがない場合は空辞書"""
    config = configparser.ConfigParser()
    if not SETTINGS_PATH.exists():
        print("[警告] settings.ini が見つかりません。画面からの手動選択が必要です。")
        return {}
    config.read(SETTINGS_PATH, encoding="utf-8")
    members_raw = config.get("channel_users", "members", fallback="")
    members = [m.strip() for m in members_raw.split(",") if m.strip()]
    remind_channels_raw = config.get("groupsession", "remind_channel", fallback="")
    remind_channels = [c.strip() for c in remind_channels_raw.split(",") if c.strip()]
    agenda_channels_raw = config.get("growi", "channel_list", fallback="")
    agenda_channels = [c.strip() for c in agenda_channels_raw.split(",") if c.strip()]
    forum_sids_raw = config.get("groupsession", "forum_sid", fallback="")
    forum_sids = [int(s.strip()) for s in forum_sids_raw.split(",") if s.strip()]
    return {
        "channel": config.get("history", "channel", fallback=""),
        "read_date": config.getint("history", "read_date", fallback=30),
        "members": members,
        "groupsession_forum_sids": forum_sids,
        "groupsession_read_date": config.getint("groupsession", "read_date", fallback=30),
        "groupsession_remind_channels": remind_channels,
        "agenda_mattermost_channels": agenda_channels,
        "growi_root_path": config.get("growi", "root_path", fallback=""),
        "mattermost_target_username": config.get("mattermost", "target_username", fallback=""),
    }


SETTINGS = load_settings()


class DmRequest(BaseModel):
    message: str
    target: str = "dm"  # "dm": DM送信先へ投稿 / "channel": 投稿元チャンネルへ返信
    channel_id: str | None = None
    post_id: str | None = None


class ReminderRequest(BaseModel):
    source: str = "mattermost"
    post_id: str | None = None
    source_url: str | None = None
    message: str
    author_username: str


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
    return {"username": SETTINGS.get("mattermost_target_username", "")}


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
def get_channel_posts(channel_id: str, start: str, end: str) -> list[dict]:
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
        target_ids = call_filter_reminder_posts(posts)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AIによる投稿の絞り込みに失敗しました: {exc}") from exc

    return [p for p in posts if p["id"] in target_ids]


@app.get("/api/webpage/announcements")
def get_webpage_announcements(start: str, end: str) -> list[dict]:
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
    except requests.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"GROUPSESSIONへのアクセスに失敗しました: {exc}") from exc

    try:
        target_ids = call_filter_reminder_posts(posts)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AIによる投稿の絞り込みに失敗しました: {exc}") from exc

    return [p for p in posts if p["id"] in target_ids]


@app.get("/api/posts/{post_id}/reactions")
def get_post_reactions(post_id: str) -> list[dict]:
    try:
        return mm.get_post_reactions(post_id)
    except requests.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Mattermost APIエラー: {exc}") from exc


@app.post("/api/reminder")
def post_reminder(request: ReminderRequest) -> dict:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="投稿内容がありません")

    try:
        reminder = call_generate_reminder(
            message, request.author_username.strip(), source_url=request.source_url
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AIによるリマインド生成に失敗しました: {exc}") from exc

    members = SETTINGS.get("members", [])
    if request.source == "mattermost" and request.post_id:
        try:
            reactions = mm.get_post_reactions(request.post_id)
        except requests.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Mattermost APIエラー: {exc}") from exc

        reacted_usernames = {
            r["username"] for r in reactions if r["emoji_name"] == REMINDER_DONE_EMOJI
        }
        mention_targets = [m for m in members if m not in reacted_usernames]
        mention_line = " ".join(f"@{m}" for m in mention_targets)
    else:
        # Web記事にはリアクションの概念がないため、メンバー全員をメンション対象とする
        mention_line = "@channel"

    reminder = reminder.replace("@channel", mention_line, 1)

    return {"reminder": reminder}


@app.post("/api/agenda")
def post_agenda(request: AgendaRequest) -> dict:
    if not request.items:
        raise HTTPException(status_code=400, detail="アジェンダに含める投稿・記事が選択されていません")

    try:
        agenda_body = call_generate_agenda([item.model_dump() for item in request.items])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AIによるアジェンダ生成に失敗しました: {exc}") from exc

    now = datetime.now()
    agenda = f"""# {now.year}年{now.month}月度アジェンダ
- 実施日時：{now.year}/{now.month}/dd 15:00-16:00

## 第一部
#### 役員会の共有

#### 全体共有事項
{agenda_body}

## 第二部
#### 進捗報告
#### 豆知識コーナー

#### その他プロジェクト等の共有事項
"""

    return {"agenda": agenda}


@app.post("/api/agenda/publish")
def publish_agenda(request: AgendaPublishRequest) -> dict:
    agenda = request.agenda.strip()
    if not agenda:
        raise HTTPException(status_code=400, detail="公開するアジェンダがありません")

    root_path = SETTINGS.get("growi_root_path", "")
    if not root_path:
        raise HTTPException(status_code=400, detail="settings.iniにgrowiのroot_pathが設定されていません")

    try:
        result = growi.publish_agenda(root_path, request.year, request.month, agenda)
    except requests.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"GROWIへの公開に失敗しました: {exc}") from exc

    return result


@app.post("/api/dm")
def post_dm(request: DmRequest) -> dict:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="メッセージは必須です")

    try:
        if request.target == "channel":
            if not request.channel_id:
                raise HTTPException(status_code=400, detail="投稿先のチャンネルが指定されていません")
            mm.post_message(request.channel_id, message, root_id=request.post_id)
        else:
            target_username = SETTINGS.get("mattermost_target_username", "")
            if not target_username:
                raise HTTPException(status_code=400, detail="settings.iniにmattermostのtarget_usernameが設定されていません")
            mm.post_dm_to_target(message, target_username)
    except requests.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Mattermost APIエラー: {exc}") from exc

    return {"result": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
