"""「Trello 情報解析」の DB 入出力。

- ingest_boards()            : tr_boards / tr_members / tr_lists / tr_cards / tr_card_members / tr_activity へ upsert
- store_card_chunks_and_embed(): tr_chunks へ upsert + 変更分のみ埋め込み(embeddings へ source='trello')
- save_/get_/find_cached_/get_latest_/list_account_analyses : アカウント横断分析の保存・取得
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from common.vectors import to_blob
from config.settings import get_settings
from infra.db import get_session_factory
from pipeline.trello_ingest import _parse_iso, slice_text


def _new_session() -> Session:
    return get_session_factory(get_settings())()


def _json_col(value: Any) -> Any:
    if value is None:
        return None
    return value if not isinstance(value, (str, bytes)) else json.loads(value)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ----------------------------------------------------------------------
# 取り込み
# ----------------------------------------------------------------------
def ingest_boards(
    *, board_ids: list[str], flat: dict[str, Any], content_hash: str
) -> dict[str, Any]:
    """flatten_boards の結果を DB へ蓄積する(既存 id は上書き更新)。"""
    session = _new_session()
    try:
        now = _now()
        boards = flat["boards"]
        lists = flat["lists"]
        cards = flat["cards"]
        activities = flat["activities"]

        members: dict[str, str] = {}
        for c in cards:
            for u in c["member_usernames"]:
                members.setdefault(u, c["member_full_names"].get(u, ""))
        for a in activities:
            if a["username"]:
                members.setdefault(a["username"], a.get("full_name", ""))

        res = session.execute(
            text(
                """
                INSERT INTO tr_ingest_runs
                  (board_ids, content_hash, board_count, list_count, card_count, activity_count, member_count)
                VALUES (:b, :h, :bc, :lc, :cc, :ac, :mc)
                """
            ),
            {
                "b": json.dumps(board_ids, ensure_ascii=False),
                "h": content_hash,
                "bc": len(boards), "lc": len(lists), "cc": len(cards),
                "ac": len(activities), "mc": len(members),
            },
        )
        run_id = int(res.lastrowid)

        for b in boards:
            session.execute(
                text(
                    """
                    INSERT INTO tr_boards (board_id, name, url, first_seen_at, last_seen_at)
                    VALUES (:id, :n, :u, :t, :t)
                    ON DUPLICATE KEY UPDATE name = VALUES(name), url = VALUES(url),
                      first_seen_at = LEAST(COALESCE(first_seen_at, :t), :t),
                      last_seen_at = GREATEST(COALESCE(last_seen_at, :t), :t)
                    """
                ),
                {"id": b["board_id"], "n": b["board_name"], "u": b.get("board_url", ""), "t": now},
            )

        for u, full in members.items():
            session.execute(
                text(
                    """
                    INSERT INTO tr_members (username, full_name, first_seen_at, last_seen_at)
                    VALUES (:u, :f, :t, :t)
                    ON DUPLICATE KEY UPDATE full_name = VALUES(full_name),
                      first_seen_at = LEAST(COALESCE(first_seen_at, :t), :t),
                      last_seen_at = GREATEST(COALESCE(last_seen_at, :t), :t)
                    """
                ),
                {"u": u, "f": full, "t": now},
            )

        for lst in lists:
            session.execute(
                text(
                    """
                    INSERT INTO tr_lists (list_id, board_id, name)
                    VALUES (:id, :b, :n)
                    ON DUPLICATE KEY UPDATE board_id = VALUES(board_id), name = VALUES(name)
                    """
                ),
                {"id": lst["list_id"], "b": lst["board_id"], "n": lst["name"]},
            )

        cstmt = text(
            """
            INSERT INTO tr_cards
              (card_id, board_id, list_id, list_name, name, description, labels, due, due_complete,
               member_usernames, checklists, url, content_hash, snapshot_at, ingest_run_id)
            VALUES (:id, :b, :l, :ln, :n, :d, :lb, :due, :dc, :mu, :cl, :u, :h, :t, :run)
            ON DUPLICATE KEY UPDATE
              board_id = VALUES(board_id), list_id = VALUES(list_id), list_name = VALUES(list_name),
              name = VALUES(name), description = VALUES(description), labels = VALUES(labels),
              due = VALUES(due), due_complete = VALUES(due_complete),
              member_usernames = VALUES(member_usernames), checklists = VALUES(checklists),
              url = VALUES(url), content_hash = VALUES(content_hash),
              snapshot_at = VALUES(snapshot_at), ingest_run_id = VALUES(ingest_run_id)
            """
        )
        for c in cards:
            chash = f'{c["name"]}|{len(c["description"])}|{c["member_usernames"]}|{c["due_iso"]}'
            session.execute(
                cstmt,
                {
                    "id": c["card_id"], "b": c["board_id"], "l": c["list_id"], "ln": c["list_name"],
                    "n": c["name"][:1024], "d": c["description"],
                    "lb": json.dumps(c["labels"], ensure_ascii=False),
                    "due": _parse_iso(c["due_iso"]), "dc": 1 if c["due_complete"] else 0,
                    "mu": json.dumps(c["member_usernames"], ensure_ascii=False),
                    "cl": json.dumps(c["checklists"], ensure_ascii=False),
                    "u": c["url"][:512], "h": chash[:64], "t": now, "run": run_id,
                },
            )
            session.execute(text("DELETE FROM tr_card_members WHERE card_id = :c"), {"c": c["card_id"]})
            for u in c["member_usernames"]:
                session.execute(
                    text("INSERT IGNORE INTO tr_card_members (card_id, username) VALUES (:c, :u)"),
                    {"c": c["card_id"], "u": u},
                )

        astmt = text(
            """
            INSERT INTO tr_activity
              (activity_id, card_id, board_id, username, kind, text, created_at, ingest_run_id)
            VALUES (:id, :c, :b, :u, :k, :txt, :ca, :run)
            ON DUPLICATE KEY UPDATE
              username = VALUES(username), kind = VALUES(kind), text = VALUES(text),
              created_at = VALUES(created_at), ingest_run_id = VALUES(ingest_run_id)
            """
        )
        for a in activities:
            session.execute(
                astmt,
                {
                    "id": a["activity_id"], "c": a["card_id"], "b": a["board_id"],
                    "u": a["username"][:255], "k": a["kind"], "txt": a["text"],
                    "ca": _parse_iso(a.get("date_iso")), "run": run_id,
                },
            )

        session.commit()
        return {
            "ingest_run_id": run_id,
            "board_count": len(boards),
            "list_count": len(lists),
            "card_count": len(cards),
            "activity_count": len(activities),
            "member_count": len(members),
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ----------------------------------------------------------------------
# チャンク + 埋め込み(RAG 用)
# ----------------------------------------------------------------------
def store_card_chunks_and_embed(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """カードチャンクを tr_chunks へ upsert し、内容が変わったものだけ埋め込み直す。

    埋め込みは既存 embeddings テーブルへ source='trello' で書く(既存 /api/search が拾う)。
    """
    from pipeline.ai import AiAnalyzer

    if not chunks:
        return {"chunk_count": 0, "embedded_chunks": 0, "embedding_model": None}

    session = _new_session()
    try:
        existing = dict(
            session.execute(text("SELECT chunk_id, content_hash FROM tr_chunks")).all()
        )
        changed = [c for c in chunks if existing.get(c["chunk_id"]) != c["content_hash"]]
        now = _now()

        cstmt = text(
            """
            INSERT INTO tr_chunks
              (chunk_id, board_id, card_id, list_name, week, participants, text, content_hash, updated_at)
            VALUES (:id, :b, :c, :ln, :wk, :pt, :txt, :h, :t)
            ON DUPLICATE KEY UPDATE
              board_id = VALUES(board_id), card_id = VALUES(card_id), list_name = VALUES(list_name),
              week = VALUES(week), participants = VALUES(participants), text = VALUES(text),
              content_hash = VALUES(content_hash), updated_at = VALUES(updated_at)
            """
        )
        for c in chunks:
            session.execute(
                cstmt,
                {
                    "id": c["chunk_id"], "b": c["board_id"], "c": c["card_id"], "ln": c["list_name"],
                    "wk": c["week"], "pt": json.dumps(c["participants"], ensure_ascii=False),
                    "txt": c["text"], "h": c["content_hash"], "t": now,
                },
            )

        pending: list[tuple[str, str, str, str]] = []
        for c in changed:
            for idx, piece in enumerate(slice_text(c["text"])):
                pending.append((f'{c["chunk_id"]}:{idx}', c["week"], c["chunk_id"], piece))

        model: str | None = None
        if pending:
            analyzer = AiAnalyzer(get_settings())
            vectors, model = analyzer.embed_texts([p[3] for p in pending])
            estmt = text(
                """
                INSERT INTO embeddings (chunk_id, week, source, ref, text, vec, model)
                VALUES (:id, :wk, 'trello', :ref, :txt, :vec, :model)
                ON DUPLICATE KEY UPDATE
                  text = VALUES(text), vec = VALUES(vec), model = VALUES(model), week = VALUES(week)
                """
            )
            for (eid, wk, ref, piece), vec in zip(pending, vectors):
                session.execute(
                    estmt,
                    {"id": eid, "wk": wk, "ref": ref, "txt": piece, "vec": to_blob(vec), "model": model},
                )

        session.commit()
        return {"chunk_count": len(chunks), "embedded_chunks": len(changed), "embedding_model": model}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ----------------------------------------------------------------------
# アカウント横断分析の保存・取得
# ----------------------------------------------------------------------
def _get_account_analysis(session: Session, analysis_id: int) -> dict[str, Any] | None:
    a = session.execute(
        text(
            """
            SELECT id, ingest_run_id, board_ids, content_hash, model, themes, stats, status, created_at
            FROM tr_account_analyses WHERE id = :id
            """
        ),
        {"id": analysis_id},
    ).first()
    if not a:
        return None

    items = session.execute(
        text(
            """
            SELECT id, ordinal, username, full_name, overview, stats, sections
            FROM tr_account_analysis_items WHERE analysis_id = :a ORDER BY ordinal
            """
        ),
        {"a": analysis_id},
    ).all()
    refs = session.execute(
        text(
            """
            SELECT item_id, ref_kind, card_id, board_id, created_at, excerpt
            FROM tr_account_analysis_refs WHERE analysis_id = :a ORDER BY id
            """
        ),
        {"a": analysis_id},
    ).all()
    refs_by_item: dict[int, list[dict[str, Any]]] = {}
    for r in refs:
        refs_by_item.setdefault(r.item_id, []).append({
            "ref_kind": r.ref_kind,
            "card_id": r.card_id,
            "board_id": r.board_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "excerpt": r.excerpt,
        })

    accounts = [
        {
            "id": it.id,
            "username": it.username,
            "full_name": it.full_name,
            "overview": it.overview,
            "stats": _json_col(it.stats) or {},
            "sections": _json_col(it.sections) or [],
            "refs": refs_by_item.get(it.id, []),
        }
        for it in items
    ]
    return {
        "id": a.id,
        "ingest_run_id": a.ingest_run_id,
        "board_ids": _json_col(a.board_ids) or [],
        "content_hash": a.content_hash,
        "model": a.model,
        "themes": _json_col(a.themes) or [],
        "stats": _json_col(a.stats) or {},
        "status": a.status,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "accounts": accounts,
    }


def get_account_analysis(analysis_id: int) -> dict[str, Any] | None:
    session = _new_session()
    try:
        return _get_account_analysis(session, analysis_id)
    finally:
        session.close()


def find_cached_account_analysis(content_hash: str) -> dict[str, Any] | None:
    session = _new_session()
    try:
        row = session.execute(
            text(
                """
                SELECT id FROM tr_account_analyses
                WHERE content_hash = :h AND status = 'success'
                ORDER BY id DESC LIMIT 1
                """
            ),
            {"h": content_hash},
        ).first()
        return _get_account_analysis(session, row.id) if row else None
    finally:
        session.close()


def get_latest_account_analysis() -> dict[str, Any] | None:
    session = _new_session()
    try:
        row = session.execute(
            text("SELECT id FROM tr_account_analyses WHERE status = 'success' ORDER BY id DESC LIMIT 1")
        ).first()
        return _get_account_analysis(session, row.id) if row else None
    finally:
        session.close()


def list_account_analyses(limit: int = 30) -> list[dict[str, Any]]:
    session = _new_session()
    try:
        rows = session.execute(
            text(
                """
                SELECT id, board_ids, model, stats, status, created_at
                FROM tr_account_analyses ORDER BY id DESC LIMIT :lim
                """
            ),
            {"lim": limit},
        ).all()
        counts = dict(
            session.execute(
                text("SELECT analysis_id, COUNT(*) FROM tr_account_analysis_items GROUP BY analysis_id")
            ).all()
        )
        return [
            {
                "id": r.id,
                "board_ids": _json_col(r.board_ids) or [],
                "model": r.model,
                "stats": _json_col(r.stats) or {},
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "account_count": int(counts.get(r.id, 0)),
            }
            for r in rows
        ]
    finally:
        session.close()


def save_account_analysis(
    *,
    ingest_run_id: int,
    board_ids: list[str],
    content_hash: str,
    model: str,
    themes: list[str],
    stats: dict[str, Any],
    accounts: list[dict[str, Any]],
) -> dict[str, Any]:
    """アカウント横断分析の結果を保存し、保存後の分析を返す。"""
    session = _new_session()
    try:
        res = session.execute(
            text(
                """
                INSERT INTO tr_account_analyses
                  (ingest_run_id, board_ids, content_hash, model, themes, stats, status)
                VALUES (:run, :b, :h, :model, :themes, :stats, 'success')
                """
            ),
            {
                "run": ingest_run_id,
                "b": json.dumps(board_ids, ensure_ascii=False),
                "h": content_hash,
                "model": model,
                "themes": json.dumps(themes, ensure_ascii=False),
                "stats": json.dumps(stats, ensure_ascii=False),
            },
        )
        analysis_id = int(res.lastrowid)

        for i, acc in enumerate(accounts):
            item_stats = dict(acc.get("stats") or {})
            if acc.get("error"):
                item_stats["error"] = acc["error"]
            ires = session.execute(
                text(
                    """
                    INSERT INTO tr_account_analysis_items
                      (analysis_id, ordinal, username, full_name, overview, stats, sections)
                    VALUES (:a, :ord, :u, :f, :ov, :st, :sec)
                    """
                ),
                {
                    "a": analysis_id, "ord": i,
                    "u": (acc.get("username") or "")[:255],
                    "f": (acc.get("full_name") or "")[:255],
                    "ov": acc.get("overview") or "",
                    "st": json.dumps(item_stats, ensure_ascii=False),
                    "sec": json.dumps(acc.get("sections") or [], ensure_ascii=False),
                },
            )
            item_id = int(ires.lastrowid)

            for ref in acc.get("refs") or []:
                session.execute(
                    text(
                        """
                        INSERT INTO tr_account_analysis_refs
                          (analysis_id, item_id, ref_kind, card_id, board_id, created_at, excerpt)
                        VALUES (:a, :it, :rk, :cid, :bid, :ca, :ex)
                        """
                    ),
                    {
                        "a": analysis_id, "it": item_id,
                        "rk": (ref.get("ref_kind") or "card")[:12],
                        "cid": (ref.get("card_id") or "")[:40],
                        "bid": (ref.get("board_id") or "")[:40],
                        "ca": ref.get("created_at"),
                        "ex": (ref.get("excerpt") or "")[:500],
                    },
                )
        session.commit()
        return _get_account_analysis(session, analysis_id)  # type: ignore[return-value]
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
