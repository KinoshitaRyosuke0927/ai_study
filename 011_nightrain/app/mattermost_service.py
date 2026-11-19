"""Mattermost API v4 のラッパー関数群。

接続情報(MATTERMOST_URL / MATTERMOST_TOKEN)は、Azure Functionsのアプリケーション設定
(環境変数)から読み込む。
"""

from __future__ import annotations

import requests

from app import config

# 通常のチャンネルのみを一覧対象とする（D=DM, G=グループDM は除外）
CHANNEL_TYPES_FOR_LIST = ("O", "P")

# 履歴取得時のページネーション設定
POSTS_PER_PAGE = 200
MAX_PAGES = 50


def _base_url() -> str:
    """末尾のスラッシュを除いたMattermostのURLを返す"""
    return config.get_required("MATTERMOST_URL").rstrip("/")


def _headers() -> dict:
    """認証ヘッダ(パーソナルアクセストークン)を返す"""
    return {"Authorization": f"Bearer {config.get_required('MATTERMOST_TOKEN')}"}


def _get(path: str, params: dict | None = None) -> dict:
    """
    Mattermost APIへGETリクエストを送り、JSONを返す

    Args
    -----------------
    - path: str,            "/api/v4/..." 形式のパス
    - params: dict | None,  クエリパラメータ

    Returns
    -----------------
    - data: dict,  レスポンスのJSON

    """
    res = requests.get(f"{_base_url()}{path}", headers=_headers(), params=params, timeout=10)
    res.raise_for_status()
    return res.json()


def _post(path: str, json_body) -> dict:
    """
    Mattermost APIへPOSTリクエストを送り、JSONを返す

    Args
    -----------------
    - path: str,      "/api/v4/..." 形式のパス
    - json_body: any, リクエストボディ(JSONに変換して送る)

    Returns
    -----------------
    - data: dict,  レスポンスのJSON

    """
    res = requests.post(f"{_base_url()}{path}", headers=_headers(), json=json_body, timeout=10)
    res.raise_for_status()
    return res.json()


def get_my_user_id() -> str:
    """トークンの持ち主(自分)のユーザーIDを返す"""
    return _get("/api/v4/users/me")["id"]


def get_user_id_by_username(username: str) -> str:
    """ユーザー名からユーザーIDを返す"""
    return _get(f"/api/v4/users/username/{username}")["id"]


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
    return _post("/api/v4/channels/direct", [my_id, target_id])["id"]


def post_message(channel_id: str, message: str, props: dict | None = None, root_id: str | None = None) -> str:
    """
    指定チャンネルにメッセージを投稿する

    Args
    -----------------
    - channel_id: str,       投稿先チャンネルのID
    - message: str,          投稿本文
    - props: dict | None,    投稿に付与する独自プロパティ(このサービスの投稿であることの目印に使う)
    - root_id: str | None,   スレッドへの返信にする場合、返信先(スレッドの親)の投稿ID

    Returns
    -----------------
    - post_id: str,  作成された投稿のID

    """
    # 投稿内容を組み立てる(返信の場合は親投稿のIDを付ける)
    body = {"channel_id": channel_id, "message": message}
    if props:
        body["props"] = props
    if root_id:
        body["root_id"] = root_id
    return _post("/api/v4/posts", body)["id"]


def get_post(post_id: str) -> dict:
    """投稿の情報を返す"""
    return _get(f"/api/v4/posts/{post_id}")


def get_reaction_user_ids(post_id: str, emoji_name: str) -> set[str]:
    """
    投稿に指定のスタンプ(リアクション)を押したユーザーのIDを返す

    Args
    -----------------
    - post_id: str,     対象の投稿ID
    - emoji_name: str,  スタンプ名(コロンなし。例: "sumi")

    Returns
    -----------------
    - user_ids: set[str],  スタンプを押したユーザーIDの集合

    """
    # リアクションが1件も無い場合、APIは null を返すことがあるため空リストとして扱う
    reactions = _get(f"/api/v4/posts/{post_id}/reactions") or []
    return {r["user_id"] for r in reactions if r.get("emoji_name") == emoji_name}


def get_channel_member_ids(channel_id: str) -> list[str]:
    """
    チャンネルに所属しているユーザーのIDを返す

    Args
    -----------------
    - channel_id: str,  対象チャンネルのID

    Returns
    -----------------
    - user_ids: list[str],  所属ユーザーIDの一覧

    """
    user_ids = []
    page = 0

    # ページングしながら所属メンバーをすべて取得する
    while page < MAX_PAGES:
        members = _get(f"/api/v4/channels/{channel_id}/members", params={"page": page, "per_page": POSTS_PER_PAGE})
        user_ids += [m["user_id"] for m in members]
        if len(members) < POSTS_PER_PAGE:
            break
        page += 1
    return user_ids


def get_users_by_ids(user_ids: list[str]) -> list[dict]:
    """
    ユーザーIDの一覧から、ユーザー情報の一覧を返す

    Args
    -----------------
    - user_ids: list[str],  ユーザーIDの一覧

    Returns
    -----------------
    - users: list[dict],  Mattermostのユーザー情報(username, is_bot, delete_at など)の一覧

    """
    users = []
    unique_ids = list(dict.fromkeys(user_ids))

    # 一度に大量のIDを送らないよう、区切って取得する
    for i in range(0, len(unique_ids), POSTS_PER_PAGE):
        users += _post("/api/v4/users/ids", unique_ids[i:i + POSTS_PER_PAGE])
    return users


def build_channel_post_permalink(channel_id: str, post_id: str) -> str:
    """
    チャンネルIDと投稿IDから、投稿のパーマリンクを組み立てる

    Args
    -----------------
    - channel_id: str,  投稿があるチャンネルのID
    - post_id: str,     投稿ID

    Returns
    -----------------
    - url: str,  投稿のパーマリンク

    """
    # DM・グループDMチャンネルは team_id が空文字になるため、参加チームのいずれかで代用する
    channel = get_channel(channel_id)
    if channel.get("team_id"):
        team_name = get_team(channel["team_id"])["name"]
    else:
        my_teams = get_my_teams()
        team_name = my_teams[0]["name"] if my_teams else ""
    return build_post_permalink(team_name, post_id)


def get_channel(channel_id: str) -> dict:
    """チャンネル情報を返す"""
    return _get(f"/api/v4/channels/{channel_id}")


def get_team(team_id: str) -> dict:
    """チーム情報を返す"""
    return _get(f"/api/v4/teams/{team_id}")


def build_post_permalink(team_name: str, post_id: str) -> str:
    """投稿の恒久リンク(パーマリンク)を組み立てる"""
    return f"{_base_url()}/{team_name}/pl/{post_id}"


def get_my_teams() -> list[dict]:
    """自分が参加しているチームの一覧を返す"""
    return _get("/api/v4/users/me/teams")


def list_my_channels() -> list[dict]:
    """
    参加しているチーム横断で、通常チャンネル(公開・非公開)の一覧を返す

    Args
    -----------------
    - なし

    Returns
    -----------------
    - channels: list[dict],  [{"id", "name"(表示名), "team_name"}, ...]

    """
    channels = []
    # チームごとに参加チャンネルを取得し、DM・グループDMを除いて一覧にまとめる
    for team in get_my_teams():
        for channel in _get(f"/api/v4/users/me/teams/{team['id']}/channels"):
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
    """ユーザーIDの一覧から {ユーザーID: ユーザー名} の辞書を返す"""
    if not user_ids:
        return {}
    users = _post("/api/v4/users/ids", list(set(user_ids)))
    return {u["id"]: u["username"] for u in users}


def get_channel_posts_in_range(channel_id: str, start_ts_ms: int, end_ts_ms: int) -> list[dict]:
    """
    指定チャンネルの、指定期間内(create_atがstart~end)の投稿を古い順で返す

    Args
    -----------------
    - channel_id: str,    対象チャンネルのID
    - start_ts_ms: int,   取得開始時刻(epochミリ秒)
    - end_ts_ms: int,     取得終了時刻(epochミリ秒)

    Returns
    -----------------
    - posts: list[dict],  [{"id","channel_id","username","message","create_at","url","props","root_id"}, ...]

    """
    collected = []
    page = 0

    # 新しい投稿から順にページングし、取得開始時刻より古い投稿が出てきたら打ち切る
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

            # 通常メッセージのみ対象（system_join_channel などの通知・削除済み投稿は除外）
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
    if not collected:
        return []

    # 投稿者のユーザー名をまとめて解決する
    usernames = get_usernames_by_ids([p["user_id"] for p in collected])

    # パーマリンク構築用のチーム名を取得する
    # (DM・グループDMチャンネルは team_id が空文字になるため、参加チームのいずれかで代用する)
    channel = get_channel(channel_id)
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
            "props": p.get("props") or {},
            # スレッドへの返信の場合は親投稿のID(返信でなければ空文字)
            "root_id": p.get("root_id") or "",
        }
        for p in collected
    ]
