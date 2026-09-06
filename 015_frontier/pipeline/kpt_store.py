"""「KPT分析」の DB 入出力。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from config.settings import get_settings
from infra.db import get_session_factory

_KINDS = ("keep", "problem", "try")


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
            FROM kpt_analyses WHERE id = :id
            """
        ),
        {"id": analysis_id},
    ).first()
    if not a:
        return None
    rows = session.execute(
        text(
            """
            SELECT id, kind, ordinal, title, detail, evidence, sources, importance
            FROM kpt_analysis_items WHERE analysis_id = :a ORDER BY kind, ordinal
            """
        ),
        {"a": analysis_id},
    ).all()
    grouped: dict[str, list[dict[str, Any]]] = {k: [] for k in _KINDS}
    for r in rows:
        grouped.setdefault(r.kind, []).append({
            "id": r.id,
            "title": r.title,
            "detail": r.detail,
            "evidence": r.evidence,
            "sources": _json_col(r.sources) or [],
            "importance": int(r.importance or 0),
        })
    return {
        "id": a.id,
        "content_hash": a.content_hash,
        "model": a.model,
        "source_ids": _json_col(a.source_ids) or {},
        "stats": _json_col(a.stats) or {},
        "status": a.status,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "keep": grouped.get("keep", []),
        "problem": grouped.get("problem", []),
        "try": grouped.get("try", []),
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
                SELECT id FROM kpt_analyses
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
            text("SELECT id FROM kpt_analyses WHERE status = 'success' ORDER BY id DESC LIMIT 1")
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
                FROM kpt_analyses ORDER BY id DESC LIMIT :lim
                """
            ),
            {"lim": limit},
        ).all()
        counts = dict(
            session.execute(
                text("SELECT analysis_id, COUNT(*) FROM kpt_analysis_items GROUP BY analysis_id")
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
    """KPT分析の結果を保存し、保存後の分析を返す。

    Args
    -----------------
    - items: [{"kind": "keep"|"problem"|"try", "title", "detail", "evidence", "sources": [...]}]
    """
    session = _new_session()
    try:
        res = session.execute(
            text(
                """
                INSERT INTO kpt_analyses (content_hash, model, source_ids, stats, status)
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

        # kind ごとに ordinal を振り直して保存する
        per_kind: dict[str, int] = {}
        for it in items:
            kind = it.get("kind")
            if kind not in _KINDS:
                continue
            ordinal = per_kind.get(kind, 0)
            per_kind[kind] = ordinal + 1
            _insert_item(session, analysis_id, kind, ordinal, it)
        session.commit()
        return _get_analysis(session, analysis_id)  # type: ignore[return-value]
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _insert_item(
    session: Session, analysis_id: int, kind: str, ordinal: int, it: dict[str, Any]
) -> None:
    """kpt_analysis_items へ 1 行挿入する(save_analysis / replace_items 共通)。"""
    session.execute(
        text(
            """
            INSERT INTO kpt_analysis_items
              (analysis_id, kind, ordinal, title, detail, evidence, sources, importance)
            VALUES (:a, :k, :ord, :t, :d, :e, :s, :imp)
            """
        ),
        {
            "a": analysis_id, "k": kind, "ord": ordinal,
            "t": (it.get("title") or "")[:512],
            "d": it.get("detail") or "",
            "e": it.get("evidence") or "",
            "s": json.dumps(it.get("sources") or [], ensure_ascii=False),
            "imp": max(0, min(5, int(it.get("importance") or 0))),
        },
    )


def replace_items(analysis_id: int, items: list[dict[str, Any]]) -> dict[str, Any] | None:
    """既存の KPT分析の項目を、画面で編集した状態(並び順・列・重要度)で総入れ替えする。

    Args
    -----------------
    - items: [{"kind": "keep"|"problem"|"try", "title", "detail", "evidence",
               "sources": [...], "importance": 0..5}] を画面の表示順で渡す。

    Returns
    -----------------
    - 更新後の分析 dict。analysis_id が存在しなければ None。
    """
    session = _new_session()
    try:
        exists = session.execute(
            text("SELECT id, stats FROM kpt_analyses WHERE id = :id"),
            {"id": analysis_id},
        ).first()
        if not exists:
            return None

        # 既存項目を全削除し、渡された順で kind ごとに ordinal を振り直す
        session.execute(
            text("DELETE FROM kpt_analysis_items WHERE analysis_id = :a"),
            {"a": analysis_id},
        )
        per_kind: dict[str, int] = {}
        for it in items:
            kind = it.get("kind")
            if kind not in _KINDS:
                continue
            ordinal = per_kind.get(kind, 0)
            per_kind[kind] = ordinal + 1
            _insert_item(session, analysis_id, kind, ordinal, it)

        # 件数統計を更新(available_sources など他の項目は保持)
        stats = _json_col(exists.stats) or {}
        stats.update({
            "keep_count": per_kind.get("keep", 0),
            "problem_count": per_kind.get("problem", 0),
            "try_count": per_kind.get("try", 0),
        })
        session.execute(
            text("UPDATE kpt_analyses SET stats = :s WHERE id = :id"),
            {"s": json.dumps(stats, ensure_ascii=False), "id": analysis_id},
        )
        session.commit()
        return _get_analysis(session, analysis_id)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
