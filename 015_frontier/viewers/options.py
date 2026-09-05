"""設定画面用: Mattermost チャンネル / Trello ボードの選択肢を取得する。

設定画面の表示時に呼ばれ、`.env` のアクセストークンでそのアカウントが
閲覧可能なチャンネル / ボードの一覧を返す。失敗時は空リスト + エラー文言を返し、
画面表示自体は妨げない。
"""

from __future__ import annotations

import logging

import requests

from collectors.base import HttpClient
from config.settings import Settings

logger = logging.getLogger(__name__)


def _status_of(exc: Exception) -> int | None:
    """例外から HTTP ステータスコードを取り出す(取れなければ None)。"""
    resp = getattr(exc, "response", None)
    return getattr(resp, "status_code", None) if resp is not None else None


def is_placeholder_url(url: str) -> bool:
    """.env.example のサンプル値のまま(example.com / xxx.)かどうか。"""
    u = (url or "").lower()
    return (not u) or ("example.com" in u) or ("://xxx." in u)


def trello_board_label(board: dict) -> str:
    """Trello ボードの表示名を「ワークスペース名称/ボード名称」に統一する。

    board は organization(=ワークスペース)を nested 取得した想定。
    ワークスペースが取れない個人ボードはボード名のみ。
    """
    org = board.get("organization") or {}
    workspace = org.get("displayName") or org.get("name")
    name = board.get("name") or board.get("id") or ""
    return f"{workspace}/{name}" if workspace else name

# DM / グループDM はアナリティクス対象外として除外する
_MM_CHANNEL_TYPES = {"O": "public", "P": "private"}


def list_mattermost_channels(settings: Settings) -> tuple[list[dict], str | None]:
    """アカウントが参加している全チーム・全チャンネルを返す。

    Returns:
        (channels, error)。channels は {id, name, team, type} のリスト。
    """
    if (
        is_placeholder_url(settings.mattermost_url)
        or not settings.mattermost_token
        or settings.mattermost_token == "changeme"
    ):
        return [], "Mattermost のURL/アクセストークンが未設定です(.env)"

    base = settings.mattermost_url.rstrip("/")
    http = HttpClient({"Authorization": f"Bearer {settings.mattermost_token}"})
    try:
        teams = http.get_json(f"{base}/api/v4/users/me/teams")
    except requests.ConnectionError as exc:
        logger.error("Mattermost 接続失敗: %s", exc)
        return [], f"Mattermost ({base}) に接続できません(URL の綴り/ネットワーク/VPN を確認してください)"
    except Exception as exc:
        logger.error("Mattermost チーム取得失敗: %s", exc)
        return [], f"チャンネル一覧を取得できませんでした: {exc}"

    channels: list[dict] = []
    for team in teams:
        team_id = team.get("id")
        team_name = team.get("display_name") or team.get("name") or team_id
        try:
            chs = http.get_json(
                f"{base}/api/v4/users/me/teams/{team_id}/channels"
            )
        except Exception as exc:
            logger.warning("Mattermost チャンネル取得失敗 team=%s: %s", team_name, exc)
            continue
        for c in chs:
            ctype = c.get("type")
            if ctype not in _MM_CHANNEL_TYPES:
                continue
            channels.append(
                {
                    "id": c.get("id"),
                    "name": c.get("display_name") or c.get("name"),
                    "team": team_name,
                    "type": _MM_CHANNEL_TYPES[ctype],
                }
            )
    # チーム名 → チャンネル名 で整列
    channels.sort(key=lambda x: (x["team"], x["name"] or ""))
    return channels, None


def list_trello_boards(settings: Settings) -> tuple[list[dict], str | None]:
    """アカウントが閲覧可能な(クローズしていない)ボード一覧を返す。

    Returns:
        (boards, error)。boards は {id, name, workspace} のリスト
        (name はボード名のみ、workspace はワークスペース名)。
    """
    if (
        not settings.trello_api_key
        or not settings.trello_token
        or settings.trello_token == "changeme"
    ):
        return [], "Trello の API キー/トークンが未設定です(.env)"

    http = HttpClient()
    try:
        boards = http.get_json(
            "https://api.trello.com/1/members/me/boards",
            params={
                "key": settings.trello_api_key,
                "token": settings.trello_token,
                "fields": "name,closed",
                "organization": "true",
                "organization_fields": "displayName,name",
            },
        )
    except Exception as exc:
        logger.error("Trello ボード取得失敗: %s", exc)
        return [], f"ボード一覧を取得できませんでした: {exc}"

    result = [
        {
            "id": b.get("id"),
            "name": b.get("name") or "",
            "workspace": (b.get("organization") or {}).get("displayName")
            or (b.get("organization") or {}).get("name")
            or "(個人)",
        }
        for b in boards
        if not b.get("closed")
    ]
    result.sort(key=lambda x: (x["workspace"], x["name"]))
    return result, None


def check_github_repo(settings: Settings, value: str) -> tuple[str | None, str | None]:
    """入力されたリポジトリ名に実際にアクセスできるか確認する。

    - "owner/repo" 形式ならそのまま `GET /repos/{owner}/{repo}` を試す
    - リポジトリ名のみなら、アカウントが参照可能なリポジトリから同名を探す

    Returns:
        (解決した full_name, error)。error が None なら full_name が入る。
    """
    value = (value or "").strip().strip("/")
    if not value:
        return None, "GitHub リポジトリ名称が空です"
    if not settings.github_token or settings.github_token == "changeme":
        return None, "GitHub トークンが未設定です(.env)"

    headers = {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    http = HttpClient(headers)

    if "/" in value:
        # owner/repo 形式: そのリポジトリを直接照会(必要な権限が最小)
        try:
            repo = http.get_json(f"https://api.github.com/repos/{value}")
            return repo.get("full_name", value), None
        except Exception as exc:
            status = _status_of(exc)
            logger.warning("GitHub リポジトリ確認失敗 repo=%s (status=%s): %s", value, status, exc)
            if status in (401, 403):
                return None, (
                    f"GitHub トークンでリポジトリ '{value}' にアクセスできません"
                    "(トークンが無効/期限切れ、または対象リポジトリへの権限が無い)。"
                    ".env の GITHUB_TOKEN を確認し、アプリを再起動してください"
                )
            if status == 404:
                return None, f"リポジトリ '{value}' が見つかりません(名称の綴りを確認してください)"
            return None, f"リポジトリ '{value}' の確認に失敗しました: {exc}"

    # リポジトリ名のみ: アカウントが参照可能なリポジトリから同名を探す
    try:
        page = 1
        while page <= 10:  # 最大 1000 件まで探索
            repos = http.get_json(
                "https://api.github.com/user/repos",
                params={
                    "per_page": 100,
                    "page": page,
                    "affiliation": "owner,collaborator,organization_member",
                },
            )
            if not repos:
                break
            for r in repos:
                if (r.get("name") or "").lower() == value.lower():
                    return r.get("full_name"), None
            if len(repos) < 100:
                break
            page += 1
    except Exception as exc:
        status = _status_of(exc)
        logger.warning("GitHub リポジトリ一覧取得失敗 (status=%s): %s", status, exc)
        if status in (401, 403):
            return None, (
                "GitHub トークンが無効です(401/403)。.env の GITHUB_TOKEN を確認し、"
                "アプリを再起動してください。"
                "なお fine-grained PAT は「リポジトリ一覧」の取得に広い権限が必要です。"
                "リポジトリ名だけでなく 'owner/repo' 形式で入力すると、対象リポジトリのみに"
                "権限があるトークンでも確認できます"
            )
        return None, f"リポジトリ一覧を取得できませんでした: {exc}"

    return None, (
        f"名称 '{value}' に一致するアクセス可能なリポジトリが見つかりません。"
        "'owner/repo' 形式での入力もお試しください"
    )


def check_github_path(settings: Settings, repo: str, path: str) -> str | None:
    """repo(owner/repo)内に path(フォルダ)が存在するか確認する。

    Returns:
        エラー文言。問題なければ None。
    """
    path = (path or "").strip().strip("/")
    if not path:
        return None
    if not repo:
        return "先にリポジトリ名称を有効な値にしてください"
    if not settings.github_token or settings.github_token == "changeme":
        return "GitHub トークンが未設定です(.env)"

    http = HttpClient(
        {
            "Authorization": f"Bearer {settings.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )
    try:
        content = http.get_json(f"https://api.github.com/repos/{repo}/contents/{path}")
    except Exception as exc:
        status = _status_of(exc)
        logger.warning("GitHub パス確認失敗 repo=%s path=%s (status=%s): %s", repo, path, status, exc)
        if status == 404:
            return f"リポジトリ '{repo}' に設計書パス '{path}' が見つかりません"
        if status in (401, 403):
            return "GitHub トークンでこのパスにアクセスできません(.env の GITHUB_TOKEN を確認してください)"
        return f"設計書パス '{path}' の確認に失敗しました: {exc}"

    # ディレクトリなら配列、ファイルならオブジェクトが返る
    if isinstance(content, dict) and content.get("type") == "file":
        return f"'{path}' はフォルダではなくファイルです"
    return None


def check_growi_path(settings: Settings, path: str) -> tuple[int | None, str | None]:
    """入力された GROWI パス配下のページを実際に取得できるか確認する。

    Returns:
        (ページ数, error)。error が None なら取得できたページ数が入る。
    """
    path = (path or "").strip()
    if not path:
        return None, "参照する Wiki のページが空です"
    if is_placeholder_url(settings.growi_url):
        return None, "GROWI の URL が未設定です(.env の GROWI_URL がサンプル値のままです)"
    if not settings.growi_api_token or settings.growi_api_token == "changeme":
        return None, "GROWI の API トークンが未設定です(.env の GROWI_API_TOKEN)"

    base = settings.growi_url.rstrip("/")
    http = HttpClient()
    try:
        data = http.get_json(
            f"{base}/_api/v3/pages/list",
            params={"access_token": settings.growi_api_token, "path": path, "limit": 100},
        )
    except requests.ConnectionError as exc:
        logger.warning("GROWI 接続失敗 path=%s: %s", path, exc)
        return None, (
            f"GROWI ({base}) に接続できません。"
            ".env の GROWI_URL の綴り、ネットワーク/VPN(社内 GROWI の場合)を確認してください"
        )
    except Exception as exc:
        status = _status_of(exc)
        logger.warning("GROWI パス確認失敗 path=%s (status=%s): %s", path, status, exc)
        if status in (401, 403):
            return None, "GROWI の API トークンが無効です(.env の GROWI_API_TOKEN を確認し、アプリを再起動してください)"
        return None, f"パス '{path}' にアクセスできません(存在しない/権限がない): {exc}"

    pages = data.get("pages", data.get("items", []))
    if not pages:
        return None, f"パス '{path}' 配下にページが見つかりません"
    return len(pages), None
