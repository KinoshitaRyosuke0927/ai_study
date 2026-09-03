"""Trello コレクタ。

特定ボードのアクションを差分取得し、カード関連イベントへ正規化する。
API: GET https://api.trello.com/1/boards/{board_id}/actions?since=<YYYY-MM-DD>&limit=1000&key=&token=
1,000 件上限のため before(最古アクションID)でページングする。
カードの現在状態は GET /1/boards/{id}/cards から取得する。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from settings import Settings

from .base import Event, HttpClient, ItemRecord

logger = logging.getLogger(__name__)

API_ROOT = "https://api.trello.com/1"
ACTION_LIMIT = 1000
DONE_LIST_NAMES = {"Done", "完了", "done"}


def _parse_iso(value: str | None) -> datetime | None:
    """ISO8601(末尾 Z)を UTC naive datetime へ。"""
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class TrelloCollector:
    """Trello ボードのアクション / カードコレクタ。"""

    source = "trello"

    def __init__(self, settings: Settings, http: HttpClient | None = None) -> None:
        self._board_id = settings.trello_board_id
        self._auth = {"key": settings.trello_api_key, "token": settings.trello_token}
        self._http = http or HttpClient()

    def fetch_since(self, since: datetime) -> list[Event]:
        """since 以降のボードアクションをカードイベントへ正規化して返す。"""
        since_date = since.strftime("%Y-%m-%d")
        events: list[Event] = []
        before: str | None = None
        while True:
            params = {
                **self._auth,
                "since": since_date,
                "limit": ACTION_LIMIT,
                "filter": "createCard,updateCard",
            }
            if before:
                params["before"] = before
            actions = self._http.get_json(
                f"{API_ROOT}/boards/{self._board_id}/actions", params=params
            )
            if not actions:
                break
            for action in actions:
                event = self._to_event(action)
                if event is not None:
                    events.append(event)
            if len(actions) < ACTION_LIMIT:
                break
            # 最古アクションの id を次ページの before に使う
            before = actions[-1].get("id")
        events.sort(key=lambda e: e.ts)
        return events

    def fetch_items(self) -> list[ItemRecord]:
        """ボード上のカード現在状態を返す(リスト名で done 判定)。"""
        lists = self._http.get_json(
            f"{API_ROOT}/boards/{self._board_id}/lists",
            params={**self._auth, "fields": "name"},
        )
        list_name_by_id = {lst["id"]: lst.get("name", "") for lst in lists}
        cards = self._http.get_json(
            f"{API_ROOT}/boards/{self._board_id}/cards",
            params={**self._auth, "fields": "name,closed,idList,idMembers"},
        )
        items: list[ItemRecord] = []
        for card in cards:
            list_name = list_name_by_id.get(card.get("idList"), "")
            if card.get("closed"):
                status = "archived"
            elif list_name in DONE_LIST_NAMES:
                status = "done"
            else:
                status = "open"
            members = card.get("idMembers") or []
            items.append(
                ItemRecord(
                    item_key=f"trello:card:{card.get('id')}",
                    source=self.source,
                    type="card",
                    title=card.get("name", ""),
                    status=status,
                    assignee=members[0] if members else None,
                    payload={"list": list_name},
                )
            )
        return items

    # ------------------------------------------------------------------
    def _to_event(self, action: dict) -> Event | None:
        """Trello アクション JSON を Event へ正規化する(対象外なら None)。"""
        action_type = action.get("type")
        data = action.get("data", {})
        card = data.get("card", {})
        card_id = card.get("id")
        if not card_id:
            return None
        ts = _parse_iso(action.get("date"))
        if ts is None:
            return None
        actor = (action.get("memberCreator") or {}).get("username", "unknown")
        card_key = f"trello:card:{card_id}"
        common = {
            "card_key": card_key,
            "title": card.get("name", ""),
            "origin": "trello",
        }

        if action_type == "createCard":
            return Event(
                self.source, "card_created", actor, ts, action.get("id", ""),
                {**common, "list": (data.get("list") or {}).get("name", "")},
            )
        if action_type == "updateCard":
            # リスト移動
            if "listAfter" in data:
                list_after = (data.get("listAfter") or {}).get("name", "")
                return Event(
                    self.source, "card_moved", actor, ts, action.get("id", ""),
                    {**common, "list_after": list_after},
                )
            # アーカイブ / 復帰
            if "closed" in card:
                event_type = "card_archived" if card.get("closed") else "card_unarchived"
                return Event(
                    self.source, event_type, actor, ts, action.get("id", ""), common
                )
        return None
