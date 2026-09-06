"""「Trello 情報取得」画面用: 指定ボードの現在の状況(リスト/カード/詳細/活動)を取得する。

分析パイプラインとは独立しており、DB へは保存しない(結果は画面側でメモリ保持)。
添付ファイルとテンプレートカードは取得対象外。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from collectors.base import HttpClient
from viewers.options import trello_board_label
from config.settings import Settings

logger = logging.getLogger(__name__)

API_ROOT = "https://api.trello.com/1"
ACTIONS_LIMIT = 1000
ACTIONS_MAX_PAGES = 5

# 取得するアクション種別(コメント + 主要なカード操作)。添付関連は含めない。
ACTION_FILTER = ",".join(
    [
        "commentCard",
        "createCard",
        "copyCard",
        "updateCard",
        "addMemberToCard",
        "removeMemberFromCard",
        "addChecklistToCard",
        "removeChecklistFromCard",
        "updateCheckItemStateOnCard",
        "addLabelToCard",
        "removeLabelFromCard",
    ]
)


class TrelloViewError(Exception):
    """取得条件が不正、または Trello にアクセスできない場合。"""


def _tz(settings: Settings):
    if ZoneInfo is not None:
        try:
            return ZoneInfo(settings.app_tz)
        except Exception:  # pragma: no cover
            pass
    return timezone.utc


def _fmt_iso(value: str | None, tzinfo) -> str | None:
    """Trello の ISO8601(UTC)を "YYYY-MM-DD HH:MM"(アプリTZ)へ。None はそのまま。"""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return dt.astimezone(tzinfo).strftime("%Y-%m-%d %H:%M")


def _member_label(m: dict) -> str:
    """メンバー表示名: "氏名 (@username)" / "@username"。"""
    username = m.get("username") or ""
    full = (m.get("fullName") or "").strip()
    if full and username:
        return f"{full} (@{username})"
    return f"@{username}" if username else (full or "不明")


def _member_ident(m: dict) -> dict:
    """メンバーの識別情報(分析/蓄積用): username / 氏名 / 表示ラベル。"""
    return {
        "username": (m.get("username") or "").strip(),
        "full_name": (m.get("fullName") or "").strip(),
        "label": _member_label(m),
    }


def _cover_color(cover: dict | None) -> str | None:
    """カバーに「色」が設定されていればその色名。画像カバー・未設定は None。"""
    return (cover or {}).get("color") or None


def _summarize_action(action: dict) -> dict:
    """アクションを「誰が / いつ / 何をしたか(またはコメント本文)」へ整形する。"""
    atype = action.get("type", "")
    data = action.get("data", {})
    creator = action.get("memberCreator") or {}
    who = _member_label(creator)
    ident = {"username": (creator.get("username") or "").strip(), "full_name": (creator.get("fullName") or "").strip()}
    target = _member_label(action.get("member") or {}) if action.get("member") else ""

    if atype == "commentCard":
        return {"kind": "comment", "user": who, **ident, "date": None, "text": data.get("text", ""), "summary": ""}

    summary = atype  # 既定はタイプ名
    if atype in ("createCard", "copyCard"):
        lst = (data.get("list") or {}).get("name", "")
        summary = f"リスト「{lst}」にカードを作成" if lst else "カードを作成"
    elif atype == "updateCard":
        if data.get("listBefore") or data.get("listAfter"):
            b = (data.get("listBefore") or {}).get("name", "?")
            a = (data.get("listAfter") or {}).get("name", "?")
            summary = f"「{b}」→「{a}」へ移動"
        elif "closed" in (data.get("card") or {}):
            summary = "カードをアーカイブ" if data["card"]["closed"] else "アーカイブを解除"
        elif "name" in (data.get("old") or {}):
            summary = f"カード名を変更: 「{data['old']['name']}」→「{(data.get('card') or {}).get('name', '')}」"
        elif "desc" in (data.get("old") or {}):
            summary = "説明を変更"
        elif "due" in (data.get("old") or {}) or "due" in (data.get("card") or {}):
            summary = "期限を変更"
        else:
            summary = "カードを更新"
    elif atype == "addMemberToCard":
        summary = f"メンバーを追加: {target}" if target else "メンバーを追加"
    elif atype == "removeMemberFromCard":
        summary = f"メンバーを除外: {target}" if target else "メンバーを除外"
    elif atype == "addChecklistToCard":
        summary = f"チェックリスト「{(data.get('checklist') or {}).get('name', '')}」を追加"
    elif atype == "removeChecklistFromCard":
        summary = f"チェックリスト「{(data.get('checklist') or {}).get('name', '')}」を削除"
    elif atype == "updateCheckItemStateOnCard":
        item = (data.get("checkItem") or {}).get("name", "")
        state = (data.get("checkItem") or {}).get("state", "")
        mark = "完了" if state == "complete" else "未完了に変更"
        summary = f"チェック項目「{item}」を{mark}"
    elif atype == "addLabelToCard":
        lbl = (data.get("label") or {})
        summary = f"ラベルを追加: {lbl.get('name') or lbl.get('color') or ''}"
    elif atype == "removeLabelFromCard":
        lbl = (data.get("label") or {})
        summary = f"ラベルを除外: {lbl.get('name') or lbl.get('color') or ''}"

    return {"kind": "activity", "user": who, **ident, "date": None, "text": "", "summary": summary}


class _TrelloApi:
    def __init__(self, settings: Settings) -> None:
        self._auth = {"key": settings.trello_api_key, "token": settings.trello_token}
        self._http = HttpClient()

    def board_snapshot(self, board_id: str) -> dict:
        """ボード + リスト + カード + チェックリスト + ラベルを 1 リクエストで取得する。"""
        return self._http.get_json(
            f"{API_ROOT}/boards/{board_id}",
            params={
                **self._auth,
                "fields": "name,url",
                "organization": "true",
                "organization_fields": "displayName,name",
                "lists": "open",
                "list_fields": "name,pos",
                "cards": "visible",
                "card_fields": (
                    "name,desc,due,dueComplete,idList,labels,cover,closed,isTemplate,url,pos"
                ),
                "card_members": "true",
                "card_member_fields": "fullName,username",
                "checklists": "all",
                "checklist_fields": "name,idCard,pos",
                "labels": "all",
                "label_fields": "name,color",
                "card_attachments": "false",
            },
        )

    def board_actions(self, board_id: str) -> list[dict]:
        """ボードのカード関連アクション(コメント/操作)をページングで取得する。"""
        out: list[dict] = []
        before: str | None = None
        for _ in range(ACTIONS_MAX_PAGES):
            params = {
                **self._auth,
                "filter": ACTION_FILTER,
                "limit": ACTIONS_LIMIT,
                "memberCreator": "true",
                "memberCreator_fields": "username,fullName",
                "member": "true",
                "member_fields": "username,fullName",
            }
            if before:
                params["before"] = before
            page = self._http.get_json(
                f"{API_ROOT}/boards/{board_id}/actions", params=params
            )
            if not page:
                break
            out.extend(page)
            if len(page) < ACTIONS_LIMIT:
                break
            before = page[-1].get("id")
        return out


def fetch_board(settings: Settings, board_id: str) -> dict[str, Any]:
    """指定ボードの現在の状況を、リスト → カード → 詳細/活動の構造で返す。

    Raises:
        TrelloViewError: 認証情報が未設定 / board_id が空 / Trello にアクセスできない場合。
    """
    if (
        not settings.trello_api_key
        or not settings.trello_token
        or settings.trello_token == "changeme"
        or settings.trello_api_key == "changeme"
    ):
        raise TrelloViewError("Trello の API キー / トークンが未設定です(.env)")
    if not board_id:
        raise TrelloViewError("取得対象のボードを選択してください")

    tzinfo = _tz(settings)
    api = _TrelloApi(settings)

    try:
        snap = api.board_snapshot(board_id)
    except Exception as exc:
        logger.error("Trello ボード取得失敗 board=%s: %s", board_id, exc)
        raise TrelloViewError(
            f"ボードを取得できませんでした(ID/権限/トークンを確認してください): {exc}"
        ) from exc

    try:
        actions = api.board_actions(board_id)
    except Exception as exc:  # 活動が取れなくても本体は返す
        logger.warning("Trello アクション取得失敗 board=%s: %s", board_id, exc)
        actions = []

    # チェックリストをカード ID ごとにまとめる
    checklists_by_card: dict[str, list[dict]] = {}
    for cl in snap.get("checklists", []):
        items = [
            {"name": ci.get("name", ""), "checked": ci.get("state") == "complete"}
            for ci in cl.get("checkItems", [])
        ]
        checklists_by_card.setdefault(cl.get("idCard"), []).append(
            {
                "name": cl.get("name", ""),
                "items": items,
                "done": sum(1 for i in items if i["checked"]),
                "total": len(items),
            }
        )

    # アクションをカード ID ごとにまとめる(古い順)
    activity_by_card: dict[str, list[dict]] = {}
    for a in reversed(actions):  # Trello は新しい順で返るため反転して古い順に
        card = (a.get("data") or {}).get("card") or {}
        cid = card.get("id")
        if not cid:
            continue
        entry = _summarize_action(a)
        entry["id"] = a.get("id")
        entry["date"] = _fmt_iso(a.get("date"), tzinfo)
        entry["date_iso"] = a.get("date")  # 生 ISO(蓄積用)
        activity_by_card.setdefault(cid, []).append(entry)

    # リスト → カード
    lists_sorted = sorted(snap.get("lists", []), key=lambda x: x.get("pos", 0))
    cards_by_list: dict[str, list[dict]] = {}
    for c in snap.get("cards", []):
        if c.get("closed") or c.get("isTemplate"):
            continue  # アーカイブ済み / テンプレートカードは除外
        cards_by_list.setdefault(c.get("idList"), []).append(c)

    total_cards = 0
    lists_out: list[dict] = []
    for lst in lists_sorted:
        lid = lst.get("id")
        cards_out: list[dict] = []
        for c in sorted(cards_by_list.get(lid, []), key=lambda x: x.get("pos", 0)):
            cid = c.get("id")
            cards_out.append(
                {
                    "id": cid,
                    "name": c.get("name", ""),
                    "url": c.get("url", ""),
                    "members": [_member_label(m) for m in c.get("members", [])],
                    "member_details": [_member_ident(m) for m in c.get("members", [])],
                    "due": _fmt_iso(c.get("due"), tzinfo),
                    "due_iso": c.get("due"),  # 生 ISO(蓄積用)
                    "due_complete": bool(c.get("dueComplete")),
                    "labels": [
                        {"name": lb.get("name", ""), "color": lb.get("color") or "none"}
                        for lb in c.get("labels", [])
                    ],
                    "cover": _cover_color(c.get("cover")),
                    "desc": c.get("desc", "") or "",
                    "checklists": checklists_by_card.get(cid, []),
                    "activity": activity_by_card.get(cid, []),
                }
            )
        total_cards += len(cards_out)
        lists_out.append(
            {
                "id": lid,
                "name": lst.get("name", ""),
                "card_count": len(cards_out),
                "cards": cards_out,
            }
        )

    return {
        "board_id": board_id,
        "board_name": trello_board_label(snap) or board_id,
        "board_url": snap.get("url", ""),
        "list_count": len(lists_out),
        "card_count": total_cards,
        "lists": lists_out,
    }


def list_configured_boards(settings: Settings, board_ids: list[str]) -> tuple[list[dict], str | None]:
    """設定画面で選択済みのボード ID を、名前付きの選択肢へ解決する。

    Returns:
        (boards, error)。boards は {id, name} のリスト(設定順)。
    """
    if not board_ids:
        return [], "設定画面で取得対象ボードを選択してください"
    if (
        not settings.trello_api_key
        or not settings.trello_token
        or settings.trello_token == "changeme"
    ):
        # 名前解決はできないが ID だけは返す
        return [{"id": b, "name": b} for b in board_ids], "Trello の API キー/トークンが未設定です(.env)"

    http = HttpClient()
    try:
        boards = http.get_json(
            f"{API_ROOT}/members/me/boards",
            params={
                "key": settings.trello_api_key,
                "token": settings.trello_token,
                "fields": "name",
                "organization": "true",
                "organization_fields": "displayName,name",
            },
        )
        label_by_id = {b.get("id"): trello_board_label(b) for b in boards}
    except Exception as exc:
        logger.warning("Trello ボード名解決に失敗: %s", exc)
        return [{"id": b, "name": b} for b in board_ids], None

    return [{"id": b, "name": label_by_id.get(b, b)} for b in board_ids], None
