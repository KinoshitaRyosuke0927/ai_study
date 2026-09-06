"""「Mattermost 情報解析」の DB 入出力。

- ingest_posts()            : mm_channels / mm_users / mm_posts へ upsert(post_id で冪等)
- store_chunks_and_embed()  : mm_chunks へ upsert + 変更分のみ埋め込み(embeddings へ source='mattermost')
- save_/get_/find_cached_/get_latest_/list_account_analyses : アカウント横断分析の保存・取得
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from common.vectors import to_blob
from config.settings import get_settings
from infra.db import get_session_factory
from pipeline.mm_ingest import slice_text


def _new_session() -> Session:
    return get_session_factory(get_settings())()


def _json_col(value: Any) -> Any:
    if value is None:
        return None
    return value if not isinstance(value, (str, bytes)) else json.loads(value)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ----------------------------------------------------------------------
# 取り込み(mm_channels / mm_users / mm_posts / mm_ingest_runs)
# ----------------------------------------------------------------------
def ingest_posts(
    *,
    mode: str,
    channel_ids: list[str],
    window_start: date | None,
    window_end: date | None,
    posts: list[dict[str, Any]],
    content_hash: str,
) -> dict[str, Any]:
    """平坦化済みの投稿一覧を DB へ蓄積する(既存 post_id は上書き更新)。"""
    session = _new_session()
    try:
        now = _now()
        channels = {p["channel_id"]: p["channel_name"] for p in posts if p["channel_id"]}
        users = {p["user_id"]: p["username"] for p in posts if p["user_id"]}

        res = session.execute(
            text(
                """
                INSERT INTO mm_ingest_runs
                  (mode, window_start, window_end, channel_ids, content_hash,
                   post_count, channel_count, user_count)
                VALUES (:mode, :ws, :we, :ch, :h, :pc, :cc, :uc)
                """
            ),
            {
                "mode": mode,
                "ws": window_start,
                "we": window_end,
                "ch": json.dumps(channel_ids, ensure_ascii=False),
                "h": content_hash,
                "pc": len(posts),
                "cc": len(channels),
                "uc": len(users),
            },
        )
        run_id = int(res.lastrowid)

        for cid, cname in channels.items():
            session.execute(
                text(
                    """
                    INSERT INTO mm_channels (channel_id, name, display_name, first_seen_at, last_seen_at)
                    VALUES (:id, :n, :n, :t, :t)
                    ON DUPLICATE KEY UPDATE
                      display_name = VALUES(display_name),
                      first_seen_at = LEAST(COALESCE(first_seen_at, :t), :t),
                      last_seen_at = GREATEST(COALESCE(last_seen_at, :t), :t)
                    """
                ),
                {"id": cid, "n": cname, "t": now},
            )

        for uid, uname in users.items():
            session.execute(
                text(
                    """
                    INSERT INTO mm_users (user_id, username, first_seen_at, last_seen_at)
                    VALUES (:id, :u, :t, :t)
                    ON DUPLICATE KEY UPDATE
                      username = VALUES(username),
                      first_seen_at = LEAST(COALESCE(first_seen_at, :t), :t),
                      last_seen_at = GREATEST(COALESCE(last_seen_at, :t), :t)
                    """
                ),
                {"id": uid, "u": uname, "t": now},
            )

        stmt = text(
            """
            INSERT INTO mm_posts
              (post_id, channel_id, user_id, root_id, is_reply, created_at, week,
               message, reactions, reaction_count, ingest_run_id)
            VALUES (:pid, :cid, :uid, :rid, :ir, :ca, :wk, :msg, :rx, :rc, :run)
            ON DUPLICATE KEY UPDATE
              message = VALUES(message),
              reactions = VALUES(reactions),
              reaction_count = VALUES(reaction_count),
              ingest_run_id = VALUES(ingest_run_id)
            """
        )
        for p in posts:
            dt = datetime.fromtimestamp(p["create_at"] / 1000, tz=timezone.utc).replace(tzinfo=None)
            y, w, _ = datetime.fromtimestamp(p["create_at"] / 1000, tz=timezone.utc).isocalendar()
            session.execute(
                stmt,
                {
                    "pid": p["post_id"],
                    "cid": p["channel_id"],
                    "uid": p["user_id"],
                    "rid": p["root_id"],
                    "ir": 1 if p["is_reply"] else 0,
                    "ca": dt,
                    "wk": f"{y:04d}-W{w:02d}",
                    "msg": p["message"],
                    "rx": json.dumps(p["reactions"], ensure_ascii=False),
                    "rc": p["reaction_count"],
                    "run": run_id,
                },
            )
        session.commit()
        return {
            "ingest_run_id": run_id,
            "post_count": len(posts),
            "channel_count": len(channels),
            "user_count": len(users),
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ----------------------------------------------------------------------
# チャンク + 埋め込み(RAG 用)
# ----------------------------------------------------------------------
def store_chunks_and_embed(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """会話チャンクを mm_chunks へ upsert し、内容が変わったものだけ埋め込み直す。

    埋め込みは既存 embeddings テーブルへ source='mattermost' で書くため、
    既存の /api/search(RAG)がそのまま Mattermost チャンクも検索対象にする。
    """
    from pipeline.ai import AiAnalyzer

    if not chunks:
        return {"chunk_count": 0, "embedded_chunks": 0, "embedding_model": None}

    session = _new_session()
    try:
        existing = dict(
            session.execute(text("SELECT chunk_id, content_hash FROM mm_chunks")).all()
        )
        changed = [c for c in chunks if existing.get(c["chunk_id"]) != c["content_hash"]]

        now = _now()
        cstmt = text(
            """
            INSERT INTO mm_chunks
              (chunk_id, channel_id, root_id, week, start_at, end_at,
               participants, post_ids, text, content_hash, updated_at)
            VALUES (:id, :cid, :rid, :wk, :sa, :ea, :pt, :pids, :txt, :h, :t)
            ON DUPLICATE KEY UPDATE
              root_id = VALUES(root_id), week = VALUES(week),
              start_at = VALUES(start_at), end_at = VALUES(end_at),
              participants = VALUES(participants), post_ids = VALUES(post_ids),
              text = VALUES(text), content_hash = VALUES(content_hash), updated_at = VALUES(updated_at)
            """
        )
        for c in chunks:
            session.execute(
                cstmt,
                {
                    "id": c["chunk_id"], "cid": c["channel_id"], "rid": c["root_id"],
                    "wk": c["week"], "sa": c["start_at"], "ea": c["end_at"],
                    "pt": json.dumps(c["participants"], ensure_ascii=False),
                    "pids": json.dumps(c["post_ids"], ensure_ascii=False),
                    "txt": c["text"], "h": c["content_hash"], "t": now,
                },
            )

        # 変更 / 新規チャンクのみ埋め込み直す(800 文字スライス単位)
        pending: list[tuple[str, str, str, str]] = []  # (chunk_id, week, ref, text)
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
                VALUES (:id, :wk, 'mattermost', :ref, :txt, :vec, :model)
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
        return {
            "chunk_count": len(chunks),
            "embedded_chunks": len(changed),
            "embedding_model": model,
        }
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
            SELECT id, ingest_run_id, window_start, window_end, channel_ids,
                   content_hash, model, topics, stats, status, created_at
            FROM mm_account_analyses WHERE id = :id
            """
        ),
        {"id": analysis_id},
    ).first()
    if not a:
        return None

    items = session.execute(
        text(
            """
            SELECT id, ordinal, user_id, username, overview, stats, sections
            FROM mm_account_analysis_items WHERE analysis_id = :a ORDER BY ordinal
            """
        ),
        {"a": analysis_id},
    ).all()
    refs = session.execute(
        text(
            """
            SELECT item_id, post_id, channel_id, created_at, excerpt
            FROM mm_account_analysis_refs WHERE analysis_id = :a ORDER BY id
            """
        ),
        {"a": analysis_id},
    ).all()
    refs_by_item: dict[int, list[dict[str, Any]]] = {}
    for r in refs:
        refs_by_item.setdefault(r.item_id, []).append({
            "post_id": r.post_id,
            "channel_id": r.channel_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "excerpt": r.excerpt,
        })

    accounts = [
        {
            "id": it.id,
            "user_id": it.user_id,
            "username": it.username,
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
        "window_start": a.window_start.isoformat() if a.window_start else None,
        "window_end": a.window_end.isoformat() if a.window_end else None,
        "channel_ids": _json_col(a.channel_ids) or [],
        "content_hash": a.content_hash,
        "model": a.model,
        "topics": _json_col(a.topics) or [],
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
                SELECT id FROM mm_account_analyses
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
            text(
                "SELECT id FROM mm_account_analyses WHERE status = 'success' ORDER BY id DESC LIMIT 1"
            )
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
                SELECT id, window_start, window_end, channel_ids, model, stats, status, created_at
                FROM mm_account_analyses ORDER BY id DESC LIMIT :lim
                """
            ),
            {"lim": limit},
        ).all()
        counts = dict(
            session.execute(
                text("SELECT analysis_id, COUNT(*) FROM mm_account_analysis_items GROUP BY analysis_id")
            ).all()
        )
        return [
            {
                "id": r.id,
                "window_start": r.window_start.isoformat() if r.window_start else None,
                "window_end": r.window_end.isoformat() if r.window_end else None,
                "channel_ids": _json_col(r.channel_ids) or [],
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
    window_start: date | None,
    window_end: date | None,
    channel_ids: list[str],
    content_hash: str,
    model: str,
    topics: list[str],
    stats: dict[str, Any],
    accounts: list[dict[str, Any]],
) -> dict[str, Any]:
    """アカウント横断分析の結果を保存し、保存後の分析(_get_account_analysis 相当)を返す。"""
    session = _new_session()
    try:
        res = session.execute(
            text(
                """
                INSERT INTO mm_account_analyses
                  (ingest_run_id, window_start, window_end, channel_ids, content_hash,
                   model, topics, stats, status)
                VALUES (:run, :ws, :we, :ch, :h, :model, :topics, :stats, 'success')
                """
            ),
            {
                "run": ingest_run_id,
                "ws": window_start,
                "we": window_end,
                "ch": json.dumps(channel_ids, ensure_ascii=False),
                "h": content_hash,
                "model": model,
                "topics": json.dumps(topics, ensure_ascii=False),
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
                    INSERT INTO mm_account_analysis_items
                      (analysis_id, ordinal, user_id, username, overview, stats, sections)
                    VALUES (:a, :ord, :uid, :un, :ov, :st, :sec)
                    """
                ),
                {
                    "a": analysis_id,
                    "ord": i,
                    "uid": (acc.get("user_id") or "")[:40],
                    "un": (acc.get("username") or "")[:255],
                    "ov": acc.get("overview") or "",
                    "st": json.dumps(item_stats, ensure_ascii=False),
                    "sec": json.dumps(acc.get("sections") or [], ensure_ascii=False),
                },
            )
            item_id = int(ires.lastrowid)

            for ref in acc.get("ref_posts") or []:
                created = ref.get("created_at")
                session.execute(
                    text(
                        """
                        INSERT INTO mm_account_analysis_refs
                          (analysis_id, item_id, post_id, channel_id, created_at, excerpt)
                        VALUES (:a, :it, :pid, :cid, :ca, :ex)
                        """
                    ),
                    {
                        "a": analysis_id,
                        "it": item_id,
                        "pid": (ref.get("post_id") or "")[:40],
                        "cid": (ref.get("channel_id") or "")[:40],
                        "ca": created,
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
