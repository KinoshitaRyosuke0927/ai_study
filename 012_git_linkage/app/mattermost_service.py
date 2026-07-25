"""Mattermost API v4 のラッパー関数群(DM投稿のみ)。"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
import requests

# 環境変数(.env)を読み込む
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

## Mattermost の接続情報を環境変数から取得
# MattermostサーバーのURL
MATTERMOST_URL = os.environ["MATTERMOST_URL"].rstrip("/")
# API呼び出し用のアクセストークン
MATTERMOST_TOKEN = os.environ["MATTERMOST_TOKEN"]
# DM送信先ユーザー名
MATTERMOST_TARGET_USERNAME = os.environ["MATTERMOST_TARGET_USERNAME"]

HEADERS = {"Authorization": f"Bearer {MATTERMOST_TOKEN}"}


def _get(path: str) -> dict:
    """
    Mattermost APIにGETリクエストを送信する

    Args
    -----------------
    - path: str,    APIパス（例: "/api/v4/users/me"）

    Returns
    -----------------
    - result: dict, レスポンスをJSONとして解析した結果

    """
    res = requests.get(f"{MATTERMOST_URL}{path}", headers=HEADERS, timeout=10)
    res.raise_for_status()
    return res.json()


def _post(path: str, json_body) -> dict:
    """
    Mattermost APIにPOSTリクエストを送信する

    Args
    -----------------
    - path: str,        APIパス（例: "/api/v4/posts"）
    - json_body: Any,   リクエストボディ

    Returns
    -----------------
    - result: dict,     レスポンスをJSONとして解析した結果

    """
    res = requests.post(f"{MATTERMOST_URL}{path}", headers=HEADERS, json=json_body, timeout=10)
    res.raise_for_status()
    return res.json()


def get_my_user_id() -> str:
    """
    自分自身（Botまたはトークン所有者）のユーザーIDを取得する
    """
    return _get("/api/v4/users/me")["id"]


def get_user_id_by_username(username: str) -> str:
    """
    ユーザー名からユーザーIDを取得する

    Args
    -----------------
    - username: str,    Mattermostのユーザー名

    Returns
    -----------------
    - user_id: str,     対象ユーザーのID

    """
    return _get(f"/api/v4/users/username/{username}")["id"]


def get_or_create_direct_channel(user_id_a: str, user_id_b: str) -> str:
    """
    2ユーザー間のDMチャンネルを取得する。存在しなければ新規作成される

    Args
    -----------------
    - user_id_a: str,   1人目のユーザーID
    - user_id_b: str,   2人目のユーザーID

    Returns
    -----------------
    - channel_id: str,  DMチャンネルのID

    """
    return _post("/api/v4/channels/direct", [user_id_a, user_id_b])["id"]


def post_message(channel_id: str, message: str) -> None:
    """
    指定チャンネルにメッセージを投稿する

    Args
    -----------------
    - channel_id: str,  投稿先チャンネルのID
    - message: str,     投稿するメッセージ本文

    """
    _post("/api/v4/posts", {"channel_id": channel_id, "message": message})


def post_dm_to_target(message: str) -> None:
    """
    DM送信先(MATTERMOST_TARGET_USERNAME)にメッセージを投稿する

    Args
    -----------------
    - message: str,     投稿するメッセージ本文

    """
    # 自分自身のIDと送信先ユーザーのIDを取得し、DMチャンネルを特定してから投稿する
    my_id = get_my_user_id()
    target_id = get_user_id_by_username(MATTERMOST_TARGET_USERNAME)
    channel_id = get_or_create_direct_channel(my_id, target_id)
    post_message(channel_id, message)
