"""「Trello 情報解析」の決定的な前処理(AI なし)。

- flatten_boards(): viewers.trello.fetch_board の戻り(ボード → リスト → カード → 活動)を
  ボード群でまとめ、カード / 活動を平坦なリストへ展開する。
- compute_content_hash(): (対象ボード + カードスナップショット + 活動) から決定的なハッシュを作る。
- build_card_chunks(): カード 1 枚 = 1 チャンク(RAG 用)。
- build_account_contexts(): アカウント(username)ごとに、ボード横断の活動テキストと統計を作る
  (2 段目の AI 分析の入力)。
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

MAX_ACCOUNT_CONTEXT_CHARS = 16000
MAX_REFS_PER_ACCOUNT = 60
EMBED_SLICE_CHARS = 800

_USERNAME_RE = re.compile(r"@([A-Za-z0-9_.\-]+)")


def _parse_iso(value: str | None) -> datetime | None:
    """Trello の ISO8601(...Z)を naive UTC datetime へ。失敗時は None。"""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _iso_week(dt: datetime) -> str:
    y, w, _ = dt.isocalendar()
    return f"{y:04d}-W{w:02d}"


def _username_from_label(label: str) -> str:
    """"氏名 (@foo)" / "@foo" から username を取り出す。取れなければラベルを縮めて返す。"""
    m = _USERNAME_RE.search(label or "")
    if m:
        return m.group(1)
    return (label or "").strip()[:255]


# ----------------------------------------------------------------------
# 平坦化
# ----------------------------------------------------------------------
def flatten_board(fb: dict[str, Any]) -> dict[str, Any]:
    """1 ボードぶんの fetch_board 戻りを、リスト/カード/活動の平坦なリストへ展開する。"""
    board_id = fb.get("board_id") or ""
    board_name = fb.get("board_name") or board_id

    lists_out: list[dict[str, Any]] = []
    cards_out: list[dict[str, Any]] = []
    activities_out: list[dict[str, Any]] = []

    for lst in fb.get("lists", []):
        lid = lst.get("id") or ""
        lname = lst.get("name", "")
        lists_out.append({"list_id": lid, "board_id": board_id, "name": lname})

        for c in lst.get("cards", []):
            cid = c.get("id") or ""
            details = c.get("member_details") or []
            member_usernames = sorted({d.get("username") for d in details if d.get("username")})
            full_by_user = {d["username"]: d.get("full_name", "") for d in details if d.get("username")}
            cards_out.append({
                "card_id": cid,
                "board_id": board_id,
                "board_name": board_name,
                "list_id": lid,
                "list_name": lname,
                "name": c.get("name", ""),
                "description": c.get("desc", "") or "",
                "labels": c.get("labels", []) or [],
                "due_iso": c.get("due_iso"),
                "due_complete": bool(c.get("due_complete")),
                "member_usernames": member_usernames,
                "member_full_names": full_by_user,
                "checklists": c.get("checklists", []) or [],
                "url": c.get("url", ""),
            })

            for a in c.get("activity", []) or []:
                aid = a.get("id")
                if not aid:
                    continue
                body = (a.get("text") or a.get("summary") or "").strip()
                if not body:
                    continue
                username = (a.get("username") or "").strip() or _username_from_label(a.get("user", ""))
                activities_out.append({
                    "activity_id": aid,
                    "card_id": cid,
                    "board_id": board_id,
                    "board_name": board_name,
                    "list_name": lname,
                    "card_name": c.get("name", ""),
                    "username": username,
                    "full_name": (a.get("full_name") or "").strip(),
                    "kind": "comment" if a.get("kind") == "comment" else "activity",
                    "text": body,
                    "date_iso": a.get("date_iso"),
                })

    return {
        "board_id": board_id,
        "board_name": board_name,
        "board_url": fb.get("board_url", ""),
        "lists": lists_out,
        "cards": cards_out,
        "activities": activities_out,
    }


def flatten_boards(fetch_results: list[dict[str, Any]]) -> dict[str, Any]:
    """複数ボードの fetch_board 戻りを 1 つに束ねる。"""
    boards: list[dict[str, Any]] = []
    lists: list[dict[str, Any]] = []
    cards: list[dict[str, Any]] = []
    activities: list[dict[str, Any]] = []
    seen_cards: set[str] = set()
    seen_acts: set[str] = set()
    for fb in fetch_results:
        flat = flatten_board(fb)
        boards.append({"board_id": flat["board_id"], "board_name": flat["board_name"], "board_url": flat["board_url"]})
        lists.extend(flat["lists"])
        for c in flat["cards"]:
            if c["card_id"] and c["card_id"] not in seen_cards:
                seen_cards.add(c["card_id"])
                cards.append(c)
        for a in flat["activities"]:
            if a["activity_id"] not in seen_acts:
                seen_acts.add(a["activity_id"])
                activities.append(a)
    return {"boards": boards, "lists": lists, "cards": cards, "activities": activities}


def compute_content_hash(
    board_ids: list[str], cards: list[dict[str, Any]], activities: list[dict[str, Any]]
) -> str:
    """(対象ボード + カードスナップショット + 活動) から決定的なハッシュを作る。"""
    h = hashlib.sha256()
    h.update("|".join(sorted(board_ids)).encode("utf-8"))
    h.update(b"\x00")
    for c in sorted(cards, key=lambda x: x["card_id"]):
        for part in (
            c["card_id"], c["list_id"], c["name"], c["description"],
            json.dumps(c["labels"], sort_keys=True, ensure_ascii=False),
            str(c["due_iso"]), str(c["due_complete"]),
            json.dumps(c["member_usernames"], ensure_ascii=False),
            json.dumps(c["checklists"], sort_keys=True, ensure_ascii=False),
        ):
            h.update(part.encode("utf-8"))
            h.update(b"\x00")
    for a in sorted(activities, key=lambda x: x["activity_id"]):
        h.update(a["activity_id"].encode("utf-8"))
        h.update(b"\x00")
        h.update(a["text"].encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


# ----------------------------------------------------------------------
# チャンク化(カード 1 枚 = 1 チャンク / RAG 用)
# ----------------------------------------------------------------------
def _acts_by_card(activities: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for a in activities:
        out.setdefault(a["card_id"], []).append(a)
    for lst in out.values():
        lst.sort(key=lambda x: x.get("date_iso") or "")
    return out


def build_card_chunks(
    cards: list[dict[str, Any]], activities: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """カードごとに、ボード/リスト/説明/チェックリスト/コメント/操作を整形した 1 チャンクを作る。"""
    by_card = _acts_by_card(activities)
    chunks: list[dict[str, Any]] = []
    for c in cards:
        acts = by_card.get(c["card_id"], [])
        lines = [
            f"ボード: {c['board_name']}",
            f"リスト: {c['list_name']}",
            f"カード: {c['name']}",
        ]
        if c["description"].strip():
            lines.append(f"説明:\n{c['description'].strip()}")
        for cl in c["checklists"]:
            items = ", ".join(
                ("[x] " if i.get("checked") else "[ ] ") + i.get("name", "")
                for i in cl.get("items", [])
            )
            lines.append(f"チェックリスト「{cl.get('name', '')}」({cl.get('done', 0)}/{cl.get('total', 0)}): {items}")
        if c["member_usernames"]:
            lines.append("担当: " + ", ".join(c["member_usernames"]))
        if c["due_iso"]:
            lines.append(f"期限: {c['due_iso']}" + ("(完了)" if c["due_complete"] else ""))
        if acts:
            lines.append("アクティビティ:")
            for a in acts:
                kind = "コメント" if a["kind"] == "comment" else "操作"
                lines.append(f"  [{a.get('date_iso') or ''}] {a['username']} {kind}: {a['text']}")

        text = "\n".join(lines)
        latest = max(
            [d for d in ([a.get("date_iso") for a in acts] + [c["due_iso"]]) if d],
            default=None,
        )
        dt = _parse_iso(latest) or datetime.now(timezone.utc).replace(tzinfo=None)
        participants = sorted(
            set(c["member_usernames"]) | {a["username"] for a in acts if a["username"]}
        )
        chash = hashlib.sha256(
            (
                c["name"] + "\x00" + c["description"] + "\x00"
                + json.dumps(c["checklists"], sort_keys=True, ensure_ascii=False) + "\x00"
                + json.dumps(c["member_usernames"], ensure_ascii=False) + "\x00"
                + "\n".join(f'{a["activity_id"]}={a["text"]}' for a in acts)
            ).encode("utf-8")
        ).hexdigest()
        chunks.append({
            "chunk_id": f"trello:{c['card_id']}",
            "board_id": c["board_id"],
            "card_id": c["card_id"],
            "list_name": c["list_name"],
            "week": _iso_week(dt),
            "participants": participants,
            "text": text,
            "content_hash": chash,
        })
    return chunks


def slice_text(s: str, size: int = EMBED_SLICE_CHARS) -> list[str]:
    s = (s or "").strip()
    return [s[i : i + size] for i in range(0, len(s), size)] if s else []


# ----------------------------------------------------------------------
# アカウントごとのコンテキスト(2 段目 AI の入力)
# ----------------------------------------------------------------------
def _card_by_id(cards: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {c["card_id"]: c for c in cards}


def account_stats(
    activities: list[dict[str, Any]], assigned_cards: list[dict[str, Any]]
) -> dict[str, Any]:
    """1 アカウントの活動統計。"""
    dates = [a["date_iso"] for a in activities if a.get("date_iso")]
    boards = {a["board_name"] for a in activities} | {c["board_name"] for c in assigned_cards}
    lists = {a["list_name"] for a in activities if a.get("list_name")} | {c["list_name"] for c in assigned_cards}
    return {
        "comment_count": sum(1 for a in activities if a["kind"] == "comment"),
        "action_count": sum(1 for a in activities if a["kind"] == "activity"),
        "assigned_cards": len(assigned_cards),
        "board_count": len(boards),
        "boards": sorted(boards),
        "list_count": len(lists),
        "first_at": min(dates) if dates else None,
        "last_at": max(dates) if dates else None,
    }


def _render_account(
    username: str, activities: list[dict[str, Any]], assigned_cards: list[dict[str, Any]]
) -> tuple[str, list[dict[str, Any]]]:
    """アカウントの活動を分析用テキストへ整形する。多すぎる場合は等間隔で抜粋する。"""
    act_rows: list[tuple[dict[str, Any], str]] = []
    for a in sorted(activities, key=lambda x: x.get("date_iso") or ""):
        kind = "コメント" if a["kind"] == "comment" else "操作"
        act_rows.append((
            a,
            f'[{a.get("date_iso") or ""}] #{a["board_name"]} / {a["list_name"]} / {a["card_name"]}  {kind}: {a["text"]}',
        ))

    note = ""
    total = sum(len(t) for _, t in act_rows)
    if total > MAX_ACCOUNT_CONTEXT_CHARS and len(act_rows) > 20:
        keep = max(20, int(len(act_rows) * MAX_ACCOUNT_CONTEXT_CHARS / total))
        step = len(act_rows) / keep
        idxs = sorted({0, len(act_rows) - 1} | {int(i * step) for i in range(keep)})
        act_rows = [act_rows[i] for i in idxs if i < len(act_rows)]
        note = "\n...(活動が多いため一部を抜粋)..."

    card_lines = []
    for c in assigned_cards:
        done = sum(cl.get("done", 0) for cl in c["checklists"])
        tot = sum(cl.get("total", 0) for cl in c["checklists"])
        prog = f" チェック{done}/{tot}" if tot else ""
        due = f" 期限{c['due_iso']}" if c["due_iso"] else ""
        card_lines.append(f'- #{c["board_name"]} / {c["list_name"]} / {c["name"]}{due}{prog}')

    parts = []
    if act_rows:
        parts.append("=== コメント・操作(時系列)===\n" + "\n".join(t for _, t in act_rows) + note)
    if card_lines:
        parts.append("=== 担当カード ===\n" + "\n".join(card_lines))
    context = ("\n\n".join(parts) or "(活動なし)")[:MAX_ACCOUNT_CONTEXT_CHARS]

    refs: list[dict[str, Any]] = []
    for a, _ in act_rows[:MAX_REFS_PER_ACCOUNT]:
        refs.append({
            "ref_kind": "comment" if a["kind"] == "comment" else "activity",
            "card_id": a["card_id"],
            "board_id": a["board_id"],
            "created_at": _parse_iso(a.get("date_iso")),
            "excerpt": a["text"][:500],
        })
    for c in assigned_cards[: max(0, MAX_REFS_PER_ACCOUNT - len(refs))]:
        refs.append({
            "ref_kind": "card",
            "card_id": c["card_id"],
            "board_id": c["board_id"],
            "created_at": None,
            "excerpt": f'{c["list_name"]} / {c["name"]}'[:500],
        })
    return context, refs


def build_account_contexts(
    cards: list[dict[str, Any]], activities: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """アカウント(username)ごとに {username, full_name, stats, context, refs} を作る。"""
    cards_by_id = _card_by_id(cards)

    acts_by_user: dict[str, list[dict[str, Any]]] = {}
    full_by_user: dict[str, str] = {}
    for a in activities:
        if not a["username"]:
            continue
        acts_by_user.setdefault(a["username"], []).append(a)
        if a.get("full_name"):
            full_by_user.setdefault(a["username"], a["full_name"])

    assigned_by_user: dict[str, list[dict[str, Any]]] = {}
    for c in cards:
        for u in c["member_usernames"]:
            assigned_by_user.setdefault(u, []).append(c)
            full_by_user.setdefault(u, c["member_full_names"].get(u, ""))

    usernames = set(acts_by_user) | set(assigned_by_user)
    out: list[dict[str, Any]] = []
    for u in usernames:
        acts = acts_by_user.get(u, [])
        assigned = assigned_by_user.get(u, [])
        context, refs = _render_account(u, acts, assigned)
        out.append({
            "username": u,
            "full_name": full_by_user.get(u, ""),
            "stats": account_stats(acts, assigned),
            "context": context,
            "refs": refs,
        })
    out.sort(
        key=lambda a: a["stats"]["comment_count"] + a["stats"]["action_count"] + a["stats"]["assigned_cards"],
        reverse=True,
    )
    return out
