"""GROWI コレクタ。

特定パス配下のページを一覧取得し、作成 / 更新イベントへ正規化する。
API: GET {url}/_api/v3/pages/list?access_token=<token>&limit=100&offset=N&path=<path>
ページングは offset / limit。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from settings import Settings

from .base import Event, HttpClient, ItemRecord

logger = logging.getLogger(__name__)

LIMIT = 100


def _parse_iso(value: str | None) -> datetime | None:
    """ISO8601 文字列を UTC naive datetime へ変換する。"""
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


class GrowiCollector:
    """GROWI ページコレクタ。"""

    source = "growi"

    def __init__(self, settings: Settings, http: HttpClient | None = None) -> None:
        self._url = settings.growi_url.rstrip("/")
        self._token = settings.growi_api_token
        self._paths = settings.growi_path_list or ["/"]
        self._http = http or HttpClient()
        # 直近取得したページ一覧を fetch_items で再利用するためのキャッシュ
        self._last_pages: list[dict] = []

    def fetch_since(self, since: datetime) -> list[Event]:
        """対象パス配下のページで、since 以降に作成/更新されたものを返す。"""
        events: list[Event] = []
        pages = self._list_all_pages()
        for page in pages:
            updated = _parse_iso(page.get("updatedAt"))
            created = _parse_iso(page.get("createdAt"))
            if updated is None:
                continue
            if updated < since:
                continue
            revision = page.get("revision")
            revision_id = revision.get("_id") if isinstance(revision, dict) else revision
            actor = self._extract_user(page)
            payload = {
                "page_key": f"growi:page:{page.get('_id')}",
                "title": page.get("path", "").rsplit("/", 1)[-1] or page.get("path", ""),
                "path": page.get("path", ""),
                "revision_id": revision_id,
                "updated_at": page.get("updatedAt"),
                "origin": "growi",
            }
            # 作成日時も since 以降なら page_created、そうでなければ page_updated
            is_created = created is not None and created >= since
            events.append(
                Event(
                    source=self.source,
                    type="page_created" if is_created else "page_updated",
                    actor=actor,
                    ts=updated,
                    ref=f"growi:page:{page.get('_id')}-r{revision_id}",
                    payload=payload,
                )
            )
        events.sort(key=lambda e: e.ts)
        return events

    def fetch_items(self) -> list[ItemRecord]:
        """対象パス配下のページ現在状態を返す。"""
        pages = self._last_pages or self._list_all_pages()
        items: list[ItemRecord] = []
        for page in pages:
            items.append(
                ItemRecord(
                    item_key=f"growi:page:{page.get('_id')}",
                    source=self.source,
                    type="page",
                    title=page.get("path", "").rsplit("/", 1)[-1] or page.get("path", ""),
                    status="active",
                    assignee=self._extract_user(page),
                    payload={"path": page.get("path", "")},
                )
            )
        return items

    # ------------------------------------------------------------------
    def _list_all_pages(self) -> list[dict]:
        """全対象パスについて offset ページングでページ一覧を取得する。"""
        all_pages: list[dict] = []
        for path in self._paths:
            offset = 0
            while True:
                data = self._http.get_json(
                    f"{self._url}/_api/v3/pages/list",
                    params={
                        "access_token": self._token,
                        "path": path,
                        "limit": LIMIT,
                        "offset": offset,
                    },
                )
                pages = data.get("pages", data.get("items", []))
                if not pages:
                    break
                all_pages.extend(pages)
                if len(pages) < LIMIT:
                    break
                offset += LIMIT
        self._last_pages = all_pages
        return all_pages

    @staticmethod
    def _extract_user(page: dict) -> str:
        """ページ JSON から更新者名を取り出す(取れなければ unknown)。"""
        user = page.get("lastUpdateUser") or page.get("creator") or {}
        if isinstance(user, dict):
            return user.get("username") or user.get("name") or "unknown"
        return str(user) if user else "unknown"
