"""「アクティビティ分析」の DB 入出力。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from config.settings import get_settings
from infra.db import get_session_factory


def _new_session() -> Session:
    return get_session_factory(get_settings())()


def _json_col(value: Any) -> Any:
    if value is None:
        return None
    return value if not isinstance(value, (str, bytes)) else json.loads(value)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _get_analysis(session: Session, analysis_id: int) -> dict[str, Any] | None:
    a = session.execute(
        text(
            """
            SELECT id, content_hash, model, source_ids, stats, status, created_at
            FROM user_activity_analyses WHERE id = :id
            """
        ),
        {"id": analysis_id},
    ).first()
    if not a:
        return None
    rows = session.execute(
        text(
            """
            SELECT id, ordinal, is_member, display_name, personal, accounts, sources, overview, sections
            FROM user_activity_analysis_items WHERE analysis_id = :a ORDER BY ordinal
            """
        ),
        {"a": analysis_id},
    ).all()
    items = [
        {
            "id": r.id,
            "is_member": bool(r.is_member),
            "display_name": r.display_name,
            "personal": r.personal,
            "accounts": _json_col(r.accounts) or {},
            "sources": _json_col(r.sources) or [],
            "overview": r.overview,
            "sections": _json_col(r.sections) or [],
        }
        for r in rows
    ]
    return {
        "id": a.id,
        "content_hash": a.content_hash,
        "model": a.model,
        "source_ids": _json_col(a.source_ids) or {},
        "stats": _json_col(a.stats) or {},
        "status": a.status,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "items": items,
    }


def get_analysis(analysis_id: int) -> dict[str, Any] | None:
    session = _new_session()
    try:
        return _get_analysis(session, analysis_id)
    finally:
        session.close()


def find_cached_analysis(content_hash: str) -> dict[str, Any] | None:
    session = _new_session()
    try:
        row = session.execute(
            text(
                """
                SELECT id FROM user_activity_analyses
                WHERE content_hash = :h AND status = 'success' ORDER BY id DESC LIMIT 1
                """
            ),
            {"h": content_hash},
        ).first()
        return _get_analysis(session, row.id) if row else None
    finally:
        session.close()


def get_latest_analysis() -> dict[str, Any] | None:
    session = _new_session()
    try:
        row = session.execute(
            text("SELECT id FROM user_activity_analyses WHERE status = 'success' ORDER BY id DESC LIMIT 1")
        ).first()
        return _get_analysis(session, row.id) if row else None
    finally:
        session.close()


def list_analyses(limit: int = 30) -> list[dict[str, Any]]:
    session = _new_session()
    try:
        rows = session.execute(
            text(
                """
                SELECT id, model, stats, status, created_at
                FROM user_activity_analyses ORDER BY id DESC LIMIT :lim
                """
            ),
            {"lim": limit},
        ).all()
        counts = dict(
            session.execute(
                text("SELECT analysis_id, COUNT(*) FROM user_activity_analysis_items GROUP BY analysis_id")
            ).all()
        )
        return [
            {
                "id": r.id, "model": r.model, "stats": _json_col(r.stats) or {},
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "item_count": int(counts.get(r.id, 0)),
            }
            for r in rows
        ]
    finally:
        session.close()


def save_analysis(
    *,
    content_hash: str,
    model: str,
    source_ids: dict[str, Any],
    stats: dict[str, Any],
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    """アクティビティ分析の結果を保存し、保存後の分析を返す。"""
    session = _new_session()
    try:
        res = session.execute(
            text(
                """
                INSERT INTO user_activity_analyses
                  (content_hash, model, source_ids, stats, status)
                VALUES (:h, :model, :src, :stats, 'success')
                """
            ),
            {
                "h": content_hash,
                "model": model,
                "src": json.dumps(source_ids, ensure_ascii=False),
                "stats": json.dumps(stats, ensure_ascii=False),
            },
        )
        analysis_id = int(res.lastrowid)

        for i, it in enumerate(items):
            session.execute(
                text(
                    """
                    INSERT INTO user_activity_analysis_items
                      (analysis_id, ordinal, is_member, display_name, personal, accounts, sources, overview, sections)
                    VALUES (:a, :ord, :mem, :nm, :pe, :acc, :srcs, :ov, :sec)
                    """
                ),
                {
                    "a": analysis_id, "ord": i,
                    "mem": 1 if it.get("is_member") else 0,
                    "nm": (it.get("display_name") or "")[:255],
                    "pe": it.get("personal") or "",
                    "acc": json.dumps(it.get("accounts") or {}, ensure_ascii=False),
                    "srcs": json.dumps(it.get("sources") or [], ensure_ascii=False),
                    "ov": it.get("overview") or "",
                    "sec": json.dumps(it.get("sections") or [], ensure_ascii=False),
                },
            )
        session.commit()
        return _get_analysis(session, analysis_id)  # type: ignore[return-value]
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
