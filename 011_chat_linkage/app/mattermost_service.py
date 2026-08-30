"""Mattermost API v4 のラッパー関数群。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import requests

# 環境変数(.env)を読み込む
if getattr(sys, "frozen", False):
    _env_path = Path(sys.executable).resolve().parent / ".env"
else:
    _env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(_env_path)

MATTERMOST_URL = os.environ["MATTERMOST_URL"].rstrip("/")
MATTERMOST_TOKEN = os.environ["MATTERMOST_TOKEN"]

HEADERS = {"Authorization": f"Bearer {MATTERMOST_TOKEN}"}

# 通常のチャンネルのみを一覧対象とする（D=DM, G=グループDM は除外）
CHANNEL_TYPES_FOR_LIST = ("O", "P")

# 履歴取得時のページネーション設定
POSTS_PER_PAGE = 200
MAX_PAGES = 50


def _get(path: str, params: dict | None = None) -> dict:
    res = requests.get(f"{MATTERMOST_URL}{path}", headers=HEADERS, params=params, timeout=10)
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


def post_message(channel_id: str, message: str, root_id: str | None = None) -> None:
    body = {"channel_id": channel_id, "message": message}
    if root_id:
        body["root_id"] = root_id
    _post("/api/v4/posts", body)


def get_direct_channel_id_by_username(username: str) -> str:
    """
    自分と指定ユーザーとのDMチャンネルIDを取得する(未作成の場合はMattermost側が自動作成する)

    Args
    -----------------
    - username: str,   DM相手のユーザー名

    Returns
    -----------------
    - channel_id: str, DMチャンネルのID

    """
    my_id = get_my_user_id()
    target_id = get_user_id_by_username(username)
    return get_or_create_direct_channel(my_id, target_id)


def post_dm_to_target(message: str, target_username: str) -> None:
    """DM送信先(target_username)にメッセージを投稿する。"""
    channel_id = get_direct_channel_id_by_username(target_username)
    post_message(channel_id, message)


def get_channel(channel_id: str) -> dict:
    return _get(f"/api/v4/channels/{channel_id}")


def get_team(team_id: str) -> dict:
    return _get(f"/api/v4/teams/{team_id}")


def build_post_permalink(team_name: str, post_id: str) -> str:
    """投稿の恒久リンク(パーマリンク)を組み立てる"""
    return f"{MATTERMOST_URL}/{team_name}/pl/{post_id}"


def get_my_teams() -> list[dict]:
    return _get("/api/v4/users/me/teams")


def get_my_channels_in_team(team_id: str) -> list[dict]:
    return _get(f"/api/v4/users/me/teams/{team_id}/channels")


def list_my_channels() -> list[dict]:
    """参加しているチーム横断で、通常チャンネルの一覧を返す。"""
    channels = []
    for team in get_my_teams():
        for channel in get_my_channels_in_team(team["id"]):
            if channel.get("type") not in CHANNEL_TYPES_FOR_LIST:
                continue
            channels.append({
                "id": channel["id"],
                "name": channel["display_name"] or channel["name"],
                "team_name": team["display_name"] or team["name"],
            })
    channels.sort(key=lambda c: (c["team_name"], c["name"]))
    return channels


def get_usernames_by_ids(user_ids: list[str]) -> dict:
    if not user_ids:
        return {}
    users = _post("/api/v4/users/ids", list(set(user_ids)))
    return {u["id"]: u["username"] for u in users}


def get_channel_posts_in_range(channel_id: str, start_ts_ms: int, end_ts_ms: int) -> list[dict]:
    """指定チャンネルの、指定期間内(create_atがstart~end)の投稿を古い順で返す。"""
    collected = []
    page = 0

    while page < MAX_PAGES:
        data = _get(
            f"/api/v4/channels/{channel_id}/posts",
            params={"page": page, "per_page": POSTS_PER_PAGE},
        )
        order = data["order"]
        if not order:
            break

        posts_by_id = data["posts"]
        oldest_create_at = None
        for post_id in order:
            post = posts_by_id[post_id]
            create_at = post["create_at"]
            oldest_create_at = create_at if oldest_create_at is None else min(oldest_create_at, create_at)

            # 通常メッセージのみ対象（system_join_channel などの通知は除外）
            if post.get("type") or post.get("delete_at"):
                continue
            if start_ts_ms <= create_at <= end_ts_ms:
                collected.append(post)

        if oldest_create_at is not None and oldest_create_at < start_ts_ms:
            break
        if len(order) < POSTS_PER_PAGE:
            break
        page += 1

    collected.sort(key=lambda p: p["create_at"])

    usernames = get_usernames_by_ids([p["user_id"] for p in collected])

    channel = get_channel(channel_id)
    # DM・グループDMチャンネルは team_id が空文字になり get_team() が404になるため、
    # パーマリンク構築用に自分が参加している(どれか1つの)チームの名前で代用する
    if channel.get("team_id"):
        team_name = get_team(channel["team_id"])["name"]
    else:
        my_teams = get_my_teams()
        team_name = my_teams[0]["name"] if my_teams else ""

    return [
        {
            "id": p["id"],
            "channel_id": channel_id,
            "username": usernames.get(p["user_id"], p["user_id"]),
            "message": p["message"],
            "create_at": p["create_at"],
            "url": build_post_permalink(team_name, p["id"]),
        }
        for p in collected
    ]


def get_post_reactions(post_id: str) -> list[dict]:
    """指定投稿に対するリアクション(誰がどの絵文字を押したか)を返す。"""
    reactions = _get(f"/api/v4/posts/{post_id}/reactions") or []
    usernames = get_usernames_by_ids([r["user_id"] for r in reactions])
    return [
        {
            "username": usernames.get(r["user_id"], r["user_id"]),
            "emoji_name": r["emoji_name"],
        }
        for r in reactions
    ]
