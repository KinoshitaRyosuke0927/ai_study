"""Mattermost コレクタ。

特定チャンネルの投稿を差分取得し、投稿 1 件 = イベント `post` へ正規化する。
API: GET {url}/api/v4/channels/{channel_id}/posts?since=<エポックms>&page=&per_page=
認証: Authorization: Bearer <token>
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from settings import Settings

from .base import Event, HttpClient, ItemRecord

logger = logging.getLogger(__name__)

PER_PAGE = 200


class MattermostCollector:
    """Mattermost チャンネル投稿コレクタ。"""

    source = "mattermost"

    def __init__(
        self,
        settings: Settings,
        http: HttpClient | None = None,
        channel_ids: list[str] | None = None,
    ) -> None:
        self._url = settings.mattermost_url.rstrip("/")
        # 取得対象チャンネル。指定が無ければ .env の単一チャンネルにフォールバック
        self._channel_ids = channel_ids or (
            [settings.mattermost_channel_id] if settings.mattermost_channel_id else []
        )
        # 認証ヘッダをセッションに載せる
        self._http = http or HttpClient(
            {"Authorization": f"Bearer {settings.mattermost_token}"}
        )

    def fetch_since(self, since: datetime) -> list[Event]:
        """since 以降の投稿を取得し `post` イベントの時系列リストで返す。"""
        since_ms = (
            int(since.replace(tzinfo=timezone.utc).timestamp() * 1000)
            if since.tzinfo is None
            else int(since.timestamp() * 1000)
        )
        events: list[Event] = []
        # 取得対象チャンネルを 1 つずつページングして取得する
        for channel_id in self._channel_ids:
            events.extend(self._fetch_channel(channel_id, since_ms))
        # 古い順へ整列
        events.sort(key=lambda e: e.ts)
        return events

    def _fetch_channel(self, channel_id: str, since_ms: int) -> list[Event]:
        """1 チャンネル分の投稿をページングで取得する。"""
        endpoint = f"{self._url}/api/v4/channels/{channel_id}/posts"
        events: list[Event] = []
        page = 0
        # order が空になるか、per_page 未満になるまでページング
        while True:
            data = self._http.get_json(
                endpoint,
                params={"since": since_ms, "page": page, "per_page": PER_PAGE},
            )
            order: list[str] = data.get("order", [])
            posts: dict[str, dict] = data.get("posts", {})
            if not order:
                break
            for post_id in order:
                post = posts.get(post_id)
                if not post:
                    continue
                events.append(self._to_event(post, channel_id))
            if len(order) < PER_PAGE:
                break
            page += 1
        return events

    def fetch_items(self) -> list[ItemRecord]:
        """Mattermost はカード的なアイテムを持たないため空を返す。"""
        return []

    def _to_event(self, post: dict, channel_id: str) -> Event:
        """Mattermost の投稿 JSON を Event へ正規化する。"""
        create_ms = int(post.get("create_at", 0))
        ts = datetime.fromtimestamp(create_ms / 1000, tz=timezone.utc).replace(tzinfo=None)
        root_id = post.get("root_id") or None
        return Event(
            source=self.source,
            type="post",
            actor=post.get("user_id", "unknown"),
            ts=ts,
            ref=post.get("id", ""),
            payload={
                "text": post.get("message", ""),
                "thread_root": root_id,
                "channel_id": post.get("channel_id", channel_id),
                "origin": "mattermost",
            },
        )
