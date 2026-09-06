"""「GitHub 情報取得」の DB 入出力(分析なし)。

- ingest_activity()             : gh_users / gh_branches / gh_pull_requests / gh_activity へ upsert
- store_activity_chunks_and_embed(): gh_activity_chunks へ upsert + 変更分のみ埋め込み(source='github_activity')
- get_activity_summary()        : 画面用(直近アクティビティ + アカウント別カウント)
- latest_content_hash()         : 同一入力の再取り込みを省くための指紋
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from common.vectors import to_blob
from config.settings import get_settings
from infra.db import get_session_factory
from pipeline.github_activity_ingest import (
    RECENT_ACTIVITY_LIMIT,
    _KIND_LABEL,
    build_actor_tally,
    slice_text,
)

EMBED_SOURCE = "github_activity"


def _new_session() -> Session:
    return get_session_factory(get_settings())()


def _json_col(value: Any) -> Any:
    if value is None:
        return None
    return value if not isinstance(value, (str, bytes)) else json.loads(value)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def latest_content_hash(repo: str) -> str | None:
    session = _new_session()
    try:
        row = session.execute(
            text(
                "SELECT content_hash FROM gh_activity_ingest_runs WHERE repo = :r ORDER BY id DESC LIMIT 1"
            ),
            {"r": repo},
        ).first()
        return row.content_hash if row else None
    finally:
        session.close()


# ----------------------------------------------------------------------
# 取り込み
# ----------------------------------------------------------------------
def ingest_activity(*, repo: str, flat: dict[str, Any], content_hash: str) -> dict[str, Any]:
    """正規化済みの GitHub 活動を DB へ蓄積する(event_id / (repo,number) / (repo,name) で冪等)。"""
    session = _new_session()
    try:
        now = _now()
        branches = flat["branches"]
        prs = flat["pull_requests"]
        acts = flat["activities"]

        res = session.execute(
            text(
                """
                INSERT INTO gh_activity_ingest_runs
                  (repo, branch_count, pr_count, activity_count, content_hash)
                VALUES (:r, :bc, :pc, :ac, :h)
                """
            ),
            {"r": repo, "bc": len(branches), "pc": len(prs), "ac": len(acts), "h": content_hash},
        )
        run_id = int(res.lastrowid)

        actors = sorted({a["actor"] for a in acts if a["actor"]} | {p["author"] for p in prs if p["author"]})
        for login in actors:
            session.execute(
                text(
                    """
                    INSERT INTO gh_users (login, first_seen_at, last_seen_at)
                    VALUES (:l, :t, :t)
                    ON DUPLICATE KEY UPDATE
                      first_seen_at = LEAST(COALESCE(first_seen_at, :t), :t),
                      last_seen_at = GREATEST(COALESCE(last_seen_at, :t), :t)
                    """
                ),
                {"l": login[:255], "t": now},
            )

        for b in branches:
            session.execute(
                text(
                    """
                    INSERT INTO gh_branches
                      (repo, name, is_protected, commit_count, last_activity_at, last_author, ingest_run_id, updated_at)
                    VALUES (:r, :n, :pr, :cc, :la, :au, :run, :t)
                    ON DUPLICATE KEY UPDATE
                      is_protected = VALUES(is_protected), commit_count = VALUES(commit_count),
                      last_activity_at = VALUES(last_activity_at), last_author = VALUES(last_author),
                      ingest_run_id = VALUES(ingest_run_id), updated_at = VALUES(updated_at)
                    """
                ),
                {
                    "r": repo, "n": b["name"][:255], "pr": 1 if b["is_protected"] else 0,
                    "cc": b["commit_count"], "la": b["last_activity_at"],
                    "au": (b["last_author"] or "")[:255], "run": run_id, "t": now,
                },
            )

        for p in prs:
            session.execute(
                text(
                    """
                    INSERT INTO gh_pull_requests
                      (repo, number, title, state, merged, author, created_at, closed_at, merged_at,
                       merged_by, comment_count, url, ingest_run_id, updated_at)
                    VALUES (:r, :n, :ti, :st, :mg, :au, :ca, :cl, :ma, :mb, :cc, :u, :run, :t)
                    ON DUPLICATE KEY UPDATE
                      title = VALUES(title), state = VALUES(state), merged = VALUES(merged),
                      author = VALUES(author), created_at = VALUES(created_at), closed_at = VALUES(closed_at),
                      merged_at = VALUES(merged_at), merged_by = VALUES(merged_by),
                      comment_count = VALUES(comment_count), url = VALUES(url),
                      ingest_run_id = VALUES(ingest_run_id), updated_at = VALUES(updated_at)
                    """
                ),
                {
                    "r": repo, "n": p["number"], "ti": p["title"][:1024], "st": p["state"][:12],
                    "mg": 1 if p["merged"] else 0, "au": (p["author"] or "")[:255],
                    "ca": p["created_at"], "cl": p["closed_at"], "ma": p["merged_at"],
                    "mb": (p["merged_by"] or "")[:255], "cc": p["comment_count"],
                    "u": (p["url"] or "")[:512], "run": run_id, "t": now,
                },
            )

        astmt = text(
            """
            INSERT INTO gh_activity
              (event_id, repo, kind, actor, occurred_at, week, pr_number, branch, sha,
               title, summary, body, url, ingest_run_id)
            VALUES (:id, :r, :k, :ac, :oc, :wk, :pn, :br, :sha, :ti, :su, :bo, :u, :run)
            ON DUPLICATE KEY UPDATE
              actor = VALUES(actor), occurred_at = VALUES(occurred_at), week = VALUES(week),
              pr_number = VALUES(pr_number), branch = VALUES(branch), sha = VALUES(sha),
              title = VALUES(title), summary = VALUES(summary), body = VALUES(body),
              url = VALUES(url), ingest_run_id = VALUES(ingest_run_id)
            """
        )
        for a in acts:
            session.execute(astmt, {
                "id": a["event_id"][:96], "r": repo, "k": a["kind"], "ac": (a["actor"] or "")[:255],
                "oc": a.get("occurred_at"), "wk": a.get("week", ""),
                "pn": a.get("pr_number"), "br": a.get("branch"), "sha": a.get("sha"),
                "ti": (a.get("title") or "")[:1024], "su": (a.get("summary") or "")[:512],
                "bo": a.get("body") or "", "u": (a.get("url") or "")[:512], "run": run_id,
            })

        session.commit()
        return {
            "ingest_run_id": run_id,
            "branch_count": len(branches),
            "pr_count": len(prs),
            "activity_count": len(acts),
            "actor_count": len(actors),
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ----------------------------------------------------------------------
# チャンク + 埋め込み
# ----------------------------------------------------------------------
def store_activity_chunks_and_embed(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """PR / ブランチチャンクを gh_activity_chunks へ upsert し、変わったものだけ埋め込み直す。"""
    from pipeline.ai import AiAnalyzer

    if not chunks:
        return {"chunk_count": 0, "embedded_chunks": 0, "embedding_model": None}

    session = _new_session()
    try:
        existing = dict(
            session.execute(text("SELECT chunk_id, content_hash FROM gh_activity_chunks")).all()
        )
        changed = [c for c in chunks if existing.get(c["chunk_id"]) != c["content_hash"]]
        now = _now()

        cstmt = text(
            """
            INSERT INTO gh_activity_chunks
              (chunk_id, kind, repo, pr_number, branch, week, participants, text, content_hash, updated_at)
            VALUES (:id, :k, :r, :pn, :br, :wk, :pt, :txt, :h, :t)
            ON DUPLICATE KEY UPDATE
              kind = VALUES(kind), repo = VALUES(repo), pr_number = VALUES(pr_number),
              branch = VALUES(branch), week = VALUES(week), participants = VALUES(participants),
              text = VALUES(text), content_hash = VALUES(content_hash), updated_at = VALUES(updated_at)
            """
        )
        for c in chunks:
            session.execute(cstmt, {
                "id": c["chunk_id"], "k": c["kind"], "r": c["repo"],
                "pn": c.get("pr_number"), "br": c.get("branch"), "wk": c.get("week", ""),
                "pt": json.dumps(c["participants"], ensure_ascii=False),
                "txt": c["text"], "h": c["content_hash"], "t": now,
            })

        pending: list[tuple[str, str, str, str]] = []
        for c in changed:
            for idx, piece in enumerate(slice_text(c["text"])):
                pending.append((f'{c["chunk_id"]}:{idx}', c.get("week") or "0000-W00", c["chunk_id"], piece))

        model: str | None = None
        if pending:
            analyzer = AiAnalyzer(get_settings())
            vectors, model = analyzer.embed_texts([p[3] for p in pending])
            estmt = text(
                """
                INSERT INTO embeddings (chunk_id, week, source, ref, text, vec, model)
                VALUES (:id, :wk, :src, :ref, :txt, :vec, :model)
                ON DUPLICATE KEY UPDATE
                  text = VALUES(text), vec = VALUES(vec), model = VALUES(model), week = VALUES(week)
                """
            )
            for (eid, wk, ref, piece), vec in zip(pending, vectors):
                session.execute(estmt, {
                    "id": eid, "wk": wk, "src": EMBED_SOURCE, "ref": ref,
                    "txt": piece, "vec": to_blob(vec), "model": model,
                })

        session.commit()
        return {"chunk_count": len(chunks), "embedded_chunks": len(changed), "embedding_model": model}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ----------------------------------------------------------------------
# 画面サマリ
# ----------------------------------------------------------------------
def get_activity_summary(repo: str, limit: int = RECENT_ACTIVITY_LIMIT) -> dict[str, Any] | None:
    """直近のアクティビティ(誰が何をしたか)とアカウント別カウントを返す。"""
    session = _new_session()
    try:
        run = session.execute(
            text(
                """
                SELECT id, branch_count, pr_count, activity_count, created_at
                FROM gh_activity_ingest_runs WHERE repo = :r ORDER BY id DESC LIMIT 1
                """
            ),
            {"r": repo},
        ).first()
        if not run:
            return None

        rows = session.execute(
            text(
                """
                SELECT kind, actor, occurred_at, pr_number, branch, title, summary, body, url
                FROM gh_activity WHERE repo = :r
                ORDER BY occurred_at DESC, event_id DESC LIMIT :lim
                """
            ),
            {"r": repo, "lim": limit},
        ).all()
        activities = [
            {
                "kind": r.kind,
                "kind_label": _KIND_LABEL.get(r.kind, r.kind),
                "actor": r.actor,
                "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
                "pr_number": r.pr_number,
                "branch": r.branch,
                "title": r.title,
                "summary": r.summary,
                "body_excerpt": (r.body or "").strip().replace("\n", " ")[:300],
                "url": r.url,
            }
            for r in rows
        ]

        tally_rows = session.execute(
            text(
                """
                SELECT COALESCE(NULLIF(actor, ''), '(不明)') AS actor, kind, COUNT(*) AS n
                FROM gh_activity WHERE repo = :r GROUP BY actor, kind
                """
            ),
            {"r": repo},
        ).all()
        by_actor: dict[str, dict[str, Any]] = {}
        for tr in tally_rows:
            t = by_actor.setdefault(tr.actor, {"actor": tr.actor, "total": 0, **{k: 0 for k in _KIND_LABEL}})
            t["total"] += tr.n
            if tr.kind in t:
                t[tr.kind] += tr.n
        tally = sorted(by_actor.values(), key=lambda x: x["total"], reverse=True)

        total = session.execute(
            text("SELECT COUNT(*) FROM gh_activity WHERE repo = :r"), {"r": repo}
        ).scalar_one()

        return {
            "repo": repo,
            "last_run_at": run.created_at.isoformat() if run.created_at else None,
            "branch_count": run.branch_count,
            "pr_count": run.pr_count,
            "activity_total": total,
            "activities": activities,
            "by_actor": tally,
        }
    finally:
        session.close()
