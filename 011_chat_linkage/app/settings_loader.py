"""settings.ini の読み込みロジック。

main.py(FastAPI)・slash_command_watcher.py(Azure Functions)の両方から利用するため、
FastAPI等の重い依存を持ち込まない独立したモジュールとして切り出している。
"""

from __future__ import annotations

import configparser
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
# settings.ini はユーザーが編集する運用のため、exe化(frozen)時はexeと同じ階層を参照する
if getattr(sys, "frozen", False):
    SETTINGS_PATH = Path(sys.executable).resolve().parent / "settings.ini"
else:
    SETTINGS_PATH = APP_DIR.parent / "settings.ini"


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
    watch_channels_raw = config.get("slash_watch", "watch_channels", fallback="")
    watch_channels = [c.strip() for c in watch_channels_raw.split(",") if c.strip()]
    watch_dm_users_raw = config.get("slash_watch", "watch_dm_users", fallback="")
    watch_dm_users = [u.strip() for u in watch_dm_users_raw.split(",") if u.strip()]
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
        "slash_watch_channels": watch_channels,
        "slash_watch_dm_users": watch_dm_users,
        "slash_watch_poll_overlap_minutes": config.getint("slash_watch", "poll_overlap_minutes", fallback=2),
        "slash_watch_reminder_threshold": config.getfloat("slash_watch", "reminder_threshold", fallback=0.9),
    }
