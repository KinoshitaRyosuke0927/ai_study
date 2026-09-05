"""「Mattermost 情報取得」画面用: 指定期間の投稿をチャンネル別・スレッド構造で取得する。

このモジュールは分析パイプラインとは独立しており、DB へは保存しない
(取得結果は画面側でメモリ保持する)。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timezone
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python 3.8 以前
    ZoneInfo = None  # type: ignore

from collectors.base import HttpClient
from provider_options import is_placeholder_url
from settings import Settings

logger = logging.getLogger(__name__)

PER_PAGE = 200


class MattermostViewError(Exception):
    """取得条件が不正、または Mattermost にアクセスできない場合。"""


def _tz(settings: Settings):
    """アプリのタイムゾーン(zoneinfo)。取得できなければ UTC。"""
    if ZoneInfo is not None:
        try:
            return ZoneInfo(settings.app_tz)
        except Exception:  # pragma: no cover
            pass
    return timezone.utc


def _day_bounds_ms(d: date, tzinfo) -> tuple[int, int]:
    """指定日の 00:00:00 と 23:59:59.999 を、その TZ 基準で epoch ミリ秒に変換する。"""
    start = datetime.combine(d, time.min, tzinfo=tzinfo)
    end = datetime.combine(d, time.max, tzinfo=tzinfo)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def _fmt(ms: int, tzinfo) -> str:
    """epoch ミリ秒を "YYYY-MM-DD HH:MM"(アプリTZ)へ整形する。"""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone(tzinfo).strftime(
        "%Y-%m-%d %H:%M"
    )


def _aggregate_reactions(post: dict) -> list[dict]:
    """post.metadata.reactions を絵文字名ごとに件数集計する。"""
    reactions = (post.get("metadata") or {}).get("reactions") or []
    counts: dict[str, int] = {}
    for r in reactions:
        name = r.get("emoji_name")
        if name:
            counts[name] = counts.get(name, 0) + 1
    return [{"emoji": k, "count": v} for k, v in sorted(counts.items())]


class _MattermostApi:
    """必要最小限の Mattermost API 呼び出し。"""

    def __init__(self, settings: Settings) -> None:
        self._base = settings.mattermost_url.rstrip("/")
        self._http = HttpClient({"Authorization": f"Bearer {settings.mattermost_token}"})

    def channel(self, channel_id: str) -> dict:
        """チャンネル情報(display_name 等)。"""
        return self._http.get_json(f"{self._base}/api/v4/channels/{channel_id}")

    def usernames(self, user_ids: list[str]) -> dict[str, str]:
        """user_id -> username のマップ(取得できなかった ID は含めない)。"""
        uniq = sorted({u for u in user_ids if u})
        result: dict[str, str] = {}
        # /users/ids は 1 リクエストに複数 ID を渡せる
        for i in range(0, len(uniq), 100):
            chunk = uniq[i : i + 100]
            try:
                users = self._http.post_json(
                    f"{self._base}/api/v4/users/ids", json_body=chunk
                )
            except Exception as exc:  # 解決失敗時は raw id 表示にフォールバック
                logger.warning("Mattermost ユーザ名解決に失敗: %s", exc)
                continue
            for u in users:
                if u.get("id"):
                    result[u["id"]] = u.get("username") or u["id"]
        return result

    def posts_since(self, channel_id: str, since_ms: int) -> dict[str, dict]:
        """since_ms 以降の投稿をページングで全取得し、id -> post のマップで返す。

        Mattermost はスレッドのルート投稿を since より前でも同梱するため、
        戻り値には期間外のルート投稿が含まれることがある。
        """
        posts: dict[str, dict] = {}
        page = 0
        while True:
            data = self._http.get_json(
                f"{self._base}/api/v4/channels/{channel_id}/posts",
                params={"since": since_ms, "page": page, "per_page": PER_PAGE},
            )
            order: list[str] = data.get("order", [])
            page_posts: dict[str, dict] = data.get("posts", {})
            posts.update(page_posts)
            if len(order) < PER_PAGE:
                break
            page += 1
        return posts


def _is_visible_post(post: dict) -> bool:
    """システムメッセージ・削除済み投稿を除外する。"""
    if post.get("delete_at"):
        return False
    ptype = post.get("type") or ""
    return not ptype.startswith("system_")


def _post_view(post: dict, username_by_id: dict[str, str], tzinfo) -> dict:
    """1 投稿を画面表示用の辞書へ整形する。"""
    uid = post.get("user_id", "")
    create_at = int(post.get("create_at", 0))
    return {
        "id": post.get("id"),
        "user_id": uid,
        "user": username_by_id.get(uid, uid),  # 解決できなければ raw id
        "create_at": create_at,
        "created": _fmt(create_at, tzinfo),
        "message": post.get("message", ""),
        "reactions": _aggregate_reactions(post),
        "root_id": post.get("root_id") or None,
    }


def fetch_posts(
    settings: Settings,
    channel_ids: list[str],
    start_d: date,
    end_d: date,
) -> dict[str, Any]:
    """設定チャンネルの [start_d, end_d] の投稿をチャンネル別・スレッド構造で返す。

    Raises:
        MattermostViewError: 取得条件が不正 / Mattermost にアクセスできない場合。
    """
    if is_placeholder_url(settings.mattermost_url) or not settings.mattermost_token or settings.mattermost_token == "changeme":
        raise MattermostViewError("Mattermost の URL / アクセストークンが未設定です(.env)")
    if not channel_ids:
        raise MattermostViewError("設定画面で取得対象チャンネルを選択してください")
    if start_d > end_d:
        raise MattermostViewError("開始日が終了日より後になっています")

    tzinfo = _tz(settings)
    start_ms, _ = _day_bounds_ms(start_d, tzinfo)
    _, end_ms = _day_bounds_ms(end_d, tzinfo)

    api = _MattermostApi(settings)
    channels_out: list[dict] = []
    total_posts = 0

    for channel_id in channel_ids:
        try:
            ch = api.channel(channel_id)
            channel_name = ch.get("display_name") or ch.get("name") or channel_id
        except Exception as exc:
            logger.warning("Mattermost チャンネル情報取得失敗 id=%s: %s", channel_id, exc)
            channel_name = channel_id

        try:
            raw = api.posts_since(channel_id, start_ms)
        except Exception as exc:
            logger.error("Mattermost 投稿取得失敗 channel=%s: %s", channel_name, exc)
            raise MattermostViewError(
                f"チャンネル '{channel_name}' の投稿を取得できませんでした: {exc}"
            ) from exc

        # 期間内かつ表示対象の投稿だけに絞る
        in_window = {
            pid: p
            for pid, p in raw.items()
            if _is_visible_post(p) and start_ms <= int(p.get("create_at", 0)) <= end_ms
        }

        # ユーザ名解決(期間内投稿の投稿者ぶんだけ)
        username_by_id = api.usernames([p.get("user_id", "") for p in in_window.values()])

        # ルート投稿 → その返信、の順に組み立てる
        roots: list[dict] = []
        replies_by_root: dict[str, list[dict]] = {}
        standalone_replies: list[dict] = []
        for p in in_window.values():
            view = _post_view(p, username_by_id, tzinfo)
            if not view["root_id"]:
                view["replies"] = []
                roots.append(view)
            else:
                root_id = view["root_id"]
                if root_id in in_window:
                    replies_by_root.setdefault(root_id, []).append(view)
                else:
                    # ルートが期間外 → 単独の返信として時系列に並べる
                    root_msg = (raw.get(root_id) or {}).get("message", "")
                    view["root_excerpt"] = root_msg[:60]
                    view["replies"] = []  # 形を揃える(返信を内包しない)
                    standalone_replies.append(view)

        for r in roots:
            r["replies"] = sorted(
                replies_by_root.get(r["id"], []), key=lambda x: x["create_at"]
            )

        # ルート投稿と「ルート不明の返信」を時系列(昇順)にマージ
        timeline = sorted(
            roots + standalone_replies, key=lambda x: x["create_at"]
        )
        n = sum(1 + len(r["replies"]) for r in timeline)
        total_posts += n
        channels_out.append(
            {
                "channel_id": channel_id,
                "channel_name": channel_name,
                "post_count": n,
                "posts": timeline,
            }
        )

    return {
        "start": start_d.isoformat(),
        "end": end_d.isoformat(),
        "channel_count": len(channels_out),
        "post_count": total_posts,
        "channels": channels_out,
    }
