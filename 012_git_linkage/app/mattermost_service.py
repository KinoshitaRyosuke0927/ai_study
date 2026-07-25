"""Mattermost API v4 のラッパー関数群(DM投稿のみ)。"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
import requests

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

MATTERMOST_URL = os.environ["MATTERMOST_URL"].rstrip("/")
MATTERMOST_TOKEN = os.environ["MATTERMOST_TOKEN"]
MATTERMOST_TARGET_USERNAME = os.environ["MATTERMOST_TARGET_USERNAME"]

HEADERS = {"Authorization": f"Bearer {MATTERMOST_TOKEN}"}


def _get(path: str) -> dict:
    res = requests.get(f"{MATTERMOST_URL}{path}", headers=HEADERS, timeout=10)
    res.raise_for_status()
    return res.json()


def _post(path: str, json_body) -> dict:
    res = requests.post(f"{MATTERMOST_URL}{path}", headers=HEADERS, json=json_body, timeout=10)
    res.raise_for_status()
    return res.json()


def get_my_user_id() -> str:
    return _get("/api/v4/users/me")["id"]


def get_user_id_by_username(username: str) -> str:
    return _get(f"/api/v4/users/username/{username}")["id"]


def get_or_create_direct_channel(user_id_a: str, user_id_b: str) -> str:
    return _post("/api/v4/channels/direct", [user_id_a, user_id_b])["id"]


def post_message(channel_id: str, message: str) -> None:
    _post("/api/v4/posts", {"channel_id": channel_id, "message": message})


def post_dm_to_target(message: str) -> None:
    """DM送信先(MATTERMOST_TARGET_USERNAME)にメッセージを投稿する。"""
    my_id = get_my_user_id()
    target_id = get_user_id_by_username(MATTERMOST_TARGET_USERNAME)
    channel_id = get_or_create_direct_channel(my_id, target_id)
    post_message(channel_id, message)
