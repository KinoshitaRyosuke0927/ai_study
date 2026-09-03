"""イベント / アイテムの永続化と、週次断面・差分計算。

- save_events: events テーブルへ冪等に保存(uq_event)
- upsert_items: items テーブルへ現在状態を反映(first_week / last_week 管理)
- snapshot_week_items: events を再生して「指定週末時点」のアイテム状態を week_items へ保存
- compute_diff: 前週の week_items と比較し added / changed / removed を算出
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import bindparam as __sa_bindparam_factory
from sqlalchemy import text
from sqlalchemy.orm import Session


def __sa_bindparam(name: str):
    """IN 句用の expanding バインドパラメータを生成するヘルパ。"""
    return __sa_bindparam_factory(name, expanding=True)

from collectors.base import Event, ItemRecord
from weeks import iso_week_of, prev_week, week_end

logger = logging.getLogger(__name__)

# done 扱いとするリスト名 / ステータス
DONE_LIST_NAMES = {"Done", "完了", "done"}


# ----------------------------------------------------------------------
# events
# ----------------------------------------------------------------------
def save_events(session: Session, events: Iterable[Event]) -> int:
    """events を保存する。event_uid の重複は無視(冪等)。

    Returns:
        新規に挿入された行数。
    """
    rows = list(events)
    if not rows:
        return 0

    # 既存の event_uid を先に把握して「新規件数」を正確に数える
    uids = list({e.event_uid for e in rows})
    existing: set[str] = set()
    for i in range(0, len(uids), 500):
        chunk = uids[i : i + 500]
        found = session.execute(
            text("SELECT event_uid FROM events WHERE event_uid IN :uids").bindparams(
                __sa_bindparam("uids")
            ),
            {"uids": chunk},
        ).scalars()
        existing.update(found)

    stmt = text(
        """
        INSERT INTO events (week, source, type, actor, ts, ref, payload)
        VALUES (:week, :source, :type, :actor, :ts, :ref, :payload)
        ON DUPLICATE KEY UPDATE id = id
        """
    )
    for e in rows:
        # ts の ISO 週を week カラムへ正規化して格納する
        session.execute(
            stmt,
            {
                "week": iso_week_of(e.ts),
                "source": e.source,
                "type": e.type,
                "actor": e.actor[:255],
                "ts": e.ts,
                "ref": e.ref[:255],
                "payload": json.dumps(e.payload, ensure_ascii=False, default=str),
            },
        )
    inserted = len({e.event_uid for e in rows} - existing)
    logger.info("events 保存: 受領 %d 件 / 新規 %d 件", len(rows), inserted)
    return inserted


# ----------------------------------------------------------------------
# items
# ----------------------------------------------------------------------
def upsert_items(session: Session, items: Iterable[ItemRecord], week: str) -> None:
    """items テーブルへ現在状態を反映する。

    - 新規アイテムは first_week = last_week = week
    - 既存アイテムは status / title / assignee / last_week を更新
    """
    rows = list(items)
    if not rows:
        return
    stmt = text(
        """
        INSERT INTO items
            (item_key, source, type, title, status, assignee, first_week, last_week, payload)
        VALUES
            (:item_key, :source, :type, :title, :status, :assignee, :week, :week, :payload)
        ON DUPLICATE KEY UPDATE
            title = VALUES(title),
            status = VALUES(status),
            assignee = VALUES(assignee),
            last_week = VALUES(last_week),
            payload = VALUES(payload)
        """
    )
    for it in rows:
        session.execute(
            stmt,
            {
                "item_key": it.item_key,
                "source": it.source,
                "type": it.type,
                "title": it.title[:1024],
                "status": it.status,
                "assignee": it.assignee,
                "week": week,
                "payload": json.dumps(it.payload, ensure_ascii=False, default=str),
            },
        )
    logger.info("items upsert: %d 件 (week=%s)", len(rows), week)


# ----------------------------------------------------------------------
# week_items(イベント再生による週末断面)
# ----------------------------------------------------------------------
def _replay_item_states(session: Session, until: datetime) -> dict[str, dict[str, str]]:
    """until 以前のイベントを時系列で再生し、アイテムごとの最終状態を返す。

    Returns:
        {item_key: {"status": ..., "title": ...}} の辞書。
    """
    rows = session.execute(
        text(
            """
            SELECT type, ts, payload
            FROM events
            WHERE ts <= :until
              AND source IN ('trello', 'github', 'growi', 'sample')
              AND type IN (
                'card_created','card_moved','card_archived','card_unarchived',
                'pr_opened','pr_merged',
                'issue_opened','issue_closed','issue_reopened',
                'page_created','page_updated'
              )
            ORDER BY ts ASC, id ASC
            """
        ),
        {"until": until},
    ).all()

    state: dict[str, dict[str, str]] = {}
    for etype, _ts, payload_raw in rows:
        payload: dict[str, Any] = (
            payload_raw if isinstance(payload_raw, dict) else json.loads(payload_raw or "{}")
        )
        # イベント種別ごとにアイテムキーとステータス遷移を決める
        if etype.startswith("card_"):
            key = payload.get("card_key")
            if not key:
                continue
            cur = state.setdefault(key, {"status": "open", "title": payload.get("title", "")})
            if payload.get("title"):
                cur["title"] = payload["title"]
            if etype == "card_created":
                cur["status"] = "open"
            elif etype == "card_moved":
                list_after = payload.get("list_after", "")
                cur["status"] = "done" if list_after in DONE_LIST_NAMES else "open"
            elif etype == "card_archived":
                cur["status"] = "archived"
            elif etype == "card_unarchived":
                cur["status"] = "open"
        elif etype.startswith("pr_"):
            key = payload.get("item_key")
            if not key:
                continue
            cur = state.setdefault(key, {"status": "open", "title": payload.get("title", "")})
            if payload.get("title"):
                cur["title"] = payload["title"]
            cur["status"] = "merged" if etype == "pr_merged" else "open"
        elif etype.startswith("issue_"):
            key = payload.get("item_key")
            if not key:
                continue
            cur = state.setdefault(key, {"status": "open", "title": payload.get("title", "")})
            if payload.get("title"):
                cur["title"] = payload["title"]
            if etype == "issue_closed":
                cur["status"] = "closed"
            else:  # issue_opened / issue_reopened
                cur["status"] = "open"
        elif etype.startswith("page_"):
            key = payload.get("page_key")
            if not key:
                continue
            cur = state.setdefault(key, {"status": "active", "title": payload.get("title", "")})
            if payload.get("title"):
                cur["title"] = payload["title"]
            cur["status"] = "active"
    return state


def snapshot_week_items(session: Session, week: str) -> int:
    """指定週の週末時点のアイテム状態を week_items へ保存する(既存週は置換)。

    Returns:
        保存した行数。
    """
    state = _replay_item_states(session, week_end(week))
    # 当該週の断面を作り直す
    session.execute(text("DELETE FROM week_items WHERE week = :week"), {"week": week})
    if not state:
        return 0
    stmt = text(
        """
        INSERT INTO week_items (week, item_key, status, title)
        VALUES (:week, :item_key, :status, :title)
        """
    )
    for item_key, s in state.items():
        session.execute(
            stmt,
            {
                "week": week,
                "item_key": item_key,
                "status": s["status"],
                "title": (s["title"] or "")[:1024],
            },
        )
    logger.info("week_items 断面保存: %d 件 (week=%s)", len(state), week)
    return len(state)


# ----------------------------------------------------------------------
# 差分
# ----------------------------------------------------------------------
def _source_of(item_key: str) -> str:
    """item_key の接頭辞からソース名を推定する。"""
    return item_key.split(":", 1)[0] if ":" in item_key else "unknown"


def _type_of(item_key: str) -> str:
    """item_key の 2 番目のセグメントから種別を推定する(card / pr / issue / page)。"""
    parts = item_key.split(":")
    return parts[1] if len(parts) >= 2 else "unknown"


def compute_diff(session: Session, week: str) -> dict[str, list[dict[str, Any]]]:
    """前週の week_items と比較し added / changed / removed を返す。

    Returns:
        {"added": [...], "changed": [...], "removed": [...]} 各要素は
        {item_key, source, type, title, status, prev_status?}。
    """
    pw = prev_week(week)
    cur_rows = session.execute(
        text("SELECT item_key, status, title FROM week_items WHERE week = :w"),
        {"w": week},
    ).all()
    prev_rows = session.execute(
        text("SELECT item_key, status, title FROM week_items WHERE week = :w"),
        {"w": pw},
    ).all()
    cur = {k: {"status": s, "title": t} for k, s, t in cur_rows}
    prv = {k: {"status": s, "title": t} for k, s, t in prev_rows}

    added: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []

    for key, val in cur.items():
        if key not in prv:
            added.append(_diff_row(key, val))
        elif prv[key]["status"] != val["status"] or prv[key]["title"] != val["title"]:
            row = _diff_row(key, val)
            row["prev_status"] = prv[key]["status"]
            changed.append(row)
    for key, val in prv.items():
        if key not in cur:
            removed.append(_diff_row(key, val))

    return {"added": added, "changed": changed, "removed": removed}


def _diff_row(item_key: str, val: dict[str, str]) -> dict[str, Any]:
    """差分 1 行分の辞書を組み立てる。"""
    return {
        "item_key": item_key,
        "source": _source_of(item_key),
        "type": _type_of(item_key),
        "title": val["title"],
        "status": val["status"],
    }


def diff_digest(diff: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """AI へ渡すための差分ダイジェスト(種別ごとの件数と代表タイトル)を作る。"""
    digest: dict[str, Any] = {}
    for bucket, rows in diff.items():
        by_type: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "samples": []})
        for r in rows:
            key = f"{r['source']}:{r['type']}"
            by_type[key]["count"] += 1
            if len(by_type[key]["samples"]) < 5:
                by_type[key]["samples"].append(
                    {"title": r["title"], "status": r["status"]}
                )
        digest[bucket] = by_type
    return digest
