"""「変更履歴取得」の DB 入出力。

- ingest_commits()            : gh_users / gh_commits / gh_commit_files / gh_files へ upsert
- load_commits()              : 分析用にコミットレコードを DB から復元
- store_change_chunks_and_embed(): gh_change_chunks へ upsert + 変更分のみ埋め込み(source='github_change')
- get_summary()               : 画面の「ユーザごと / ファイルごと」表
- save_/get_/find_cached_/get_latest_/list_author_analyses : アカウント別分析の保存・取得
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from common.vectors import to_blob
from config.settings import get_settings
from infra.db import get_session_factory
from pipeline.changelog_ingest import _parse_iso, slice_text

EMBED_SOURCE = "github_change"
FILE_SUMMARY_TOP = 60


def _new_session() -> Session:
    return get_session_factory(get_settings())()


def _json_col(value: Any) -> Any:
    if value is None:
        return None
    return value if not isinstance(value, (str, bytes)) else json.loads(value)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _week(dt: datetime | None) -> str:
    if dt is None:
        return ""
    y, w, _ = dt.isocalendar()
    return f"{y:04d}-W{w:02d}"


def latest_ingest_run_id(repo: str) -> int | None:
    """指定 repo の最新の取り込み run の id。"""
    session = _new_session()
    try:
        row = session.execute(
            text("SELECT id FROM gh_history_ingest_runs WHERE repo = :r ORDER BY id DESC LIMIT 1"),
            {"r": repo},
        ).first()
        return int(row.id) if row else None
    finally:
        session.close()


def get_latest_head_sha(repo: str) -> str | None:
    """指定 repo で最後に取り込んだ HEAD SHA(増分取得の基点)。"""
    session = _new_session()
    try:
        row = session.execute(
            text(
                "SELECT head_sha FROM gh_history_ingest_runs WHERE repo = :r ORDER BY id DESC LIMIT 1"
            ),
            {"r": repo},
        ).first()
        return row.head_sha if row and row.head_sha else None
    finally:
        session.close()


# ----------------------------------------------------------------------
# 取り込み
# ----------------------------------------------------------------------
def ingest_commits(
    *,
    repo: str,
    branch: str,
    head_sha: str | None,
    base_sha: str | None,
    since_date: date | None,
    commits: list[dict[str, Any]],
    content_hash: str,
) -> dict[str, Any]:
    """取得したコミット群を DB へ蓄積する(sha / (sha,path) で冪等)。"""
    session = _new_session()
    try:
        now = _now()
        file_change_count = sum(len(c.get("files", [])) for c in commits)

        res = session.execute(
            text(
                """
                INSERT INTO gh_history_ingest_runs
                  (repo, branch, since_date, base_sha, head_sha, commit_count, file_change_count, content_hash)
                VALUES (:r, :b, :sd, :base, :head, :cc, :fc, :h)
                """
            ),
            {
                "r": repo, "b": branch, "sd": since_date, "base": base_sha, "head": head_sha,
                "cc": len(commits), "fc": file_change_count, "h": content_hash,
            },
        )
        run_id = int(res.lastrowid)

        # gh_users
        users: dict[str, tuple[str, str]] = {}
        for c in commits:
            login = c.get("author_login") or ""
            key = login or c.get("author_name") or ""
            if key:
                users[key] = (c.get("author_name", ""), c.get("author_email", ""))
        for login, (nm, em) in users.items():
            session.execute(
                text(
                    """
                    INSERT INTO gh_users (login, name, email, first_seen_at, last_seen_at)
                    VALUES (:l, :n, :e, :t, :t)
                    ON DUPLICATE KEY UPDATE name = VALUES(name), email = VALUES(email),
                      first_seen_at = LEAST(COALESCE(first_seen_at, :t), :t),
                      last_seen_at = GREATEST(COALESCE(last_seen_at, :t), :t)
                    """
                ),
                {"l": login[:255], "n": nm[:255], "e": em[:255], "t": now},
            )

        cstmt = text(
            """
            INSERT INTO gh_commits
              (sha, repo, branch, author_login, author_name, author_email, committed_at, week,
               message, files_changed, additions, deletions, is_merge, ingest_run_id)
            VALUES (:sha, :r, :b, :al, :an, :ae, :ca, :wk, :msg, :fc, :ad, :de, :mg, :run)
            ON DUPLICATE KEY UPDATE
              author_login = VALUES(author_login), author_name = VALUES(author_name),
              committed_at = VALUES(committed_at), week = VALUES(week), message = VALUES(message),
              files_changed = VALUES(files_changed), additions = VALUES(additions),
              deletions = VALUES(deletions), is_merge = VALUES(is_merge), ingest_run_id = VALUES(ingest_run_id)
            """
        )
        fstmt = text(
            """
            INSERT INTO gh_commit_files
              (sha, path, previous_path, status, additions, deletions, hunk_headers,
               patch_excerpt, is_binary, truncated, is_source)
            VALUES (:sha, :p, :pp, :st, :ad, :de, :hh, :pe, :bin, :tr, :src)
            ON DUPLICATE KEY UPDATE
              previous_path = VALUES(previous_path), status = VALUES(status),
              additions = VALUES(additions), deletions = VALUES(deletions),
              hunk_headers = VALUES(hunk_headers), patch_excerpt = VALUES(patch_excerpt),
              is_binary = VALUES(is_binary), truncated = VALUES(truncated), is_source = VALUES(is_source)
            """
        )
        for c in commits:
            dt = _parse_iso(c.get("committed_at"))
            session.execute(cstmt, {
                "sha": c["sha"], "r": repo, "b": branch,
                "al": (c.get("author_login") or "")[:255],
                "an": (c.get("author_name") or "")[:255],
                "ae": (c.get("author_email") or "")[:255],
                "ca": dt, "wk": _week(dt), "msg": c.get("message", ""),
                "fc": c.get("files_changed", 0), "ad": c.get("additions", 0),
                "de": c.get("deletions", 0), "mg": 1 if c.get("is_merge") else 0, "run": run_id,
            })
            for f in c.get("files", []):
                session.execute(fstmt, {
                    "sha": c["sha"], "p": f["path"][:512],
                    "pp": (f.get("previous_path") or None),
                    "st": (f.get("status") or "")[:12],
                    "ad": f.get("additions", 0), "de": f.get("deletions", 0),
                    "hh": json.dumps(f.get("hunk_headers", []), ensure_ascii=False),
                    "pe": f.get("patch_excerpt"),
                    "bin": 1 if f.get("binary") else 0,
                    "tr": 1 if f.get("truncated") else 0,
                    "src": 1 if f.get("is_source") else 0,
                })

        # gh_files ロールアップ(今回触れたソースパスを再計算)
        paths = sorted({f["path"] for c in commits for f in c.get("files", []) if f.get("is_source")})
        if paths:
            rows = session.execute(
                text(
                    """
                    SELECT cf.path AS path, cf.additions AS ad, cf.deletions AS de,
                           c.committed_at AS ca,
                           COALESCE(NULLIF(c.author_login, ''), c.author_name) AS au
                    FROM gh_commit_files cf JOIN gh_commits c ON c.sha = cf.sha
                    WHERE cf.is_source = 1 AND c.repo = :repo AND cf.path IN :paths
                    """
                ).bindparams(bindparam("paths", expanding=True)),
                {"repo": repo, "paths": paths},
            ).all()
            agg: dict[str, dict[str, Any]] = {}
            for r in rows:
                a = agg.setdefault(r.path, {"cc": 0, "ad": 0, "de": 0, "au": set(), "fa": None, "la": None})
                a["cc"] += 1
                a["ad"] += r.ad or 0
                a["de"] += r.de or 0
                if r.au:
                    a["au"].add(r.au)
                if r.ca:
                    a["fa"] = r.ca if a["fa"] is None else min(a["fa"], r.ca)
                    a["la"] = r.ca if a["la"] is None else max(a["la"], r.ca)
            for path, a in agg.items():
                session.execute(
                    text(
                        """
                        INSERT INTO gh_files
                          (path, repo, change_count, additions, deletions, author_logins,
                           first_change_at, last_change_at)
                        VALUES (:p, :r, :cc, :ad, :de, :au, :fa, :la)
                        ON DUPLICATE KEY UPDATE
                          repo = VALUES(repo), change_count = VALUES(change_count),
                          additions = VALUES(additions), deletions = VALUES(deletions),
                          author_logins = VALUES(author_logins),
                          first_change_at = VALUES(first_change_at), last_change_at = VALUES(last_change_at)
                        """
                    ),
                    {
                        "p": path[:512], "r": repo, "cc": a["cc"], "ad": a["ad"], "de": a["de"],
                        "au": json.dumps(sorted(a["au"]), ensure_ascii=False),
                        "fa": a["fa"], "la": a["la"],
                    },
                )

        session.commit()
        return {
            "ingest_run_id": run_id,
            "commit_count": len(commits),
            "file_change_count": file_change_count,
            "user_count": len(users),
            "file_count": len(paths),
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ----------------------------------------------------------------------
# 分析用: DB からコミットレコードを復元
# ----------------------------------------------------------------------
def load_commits(repo: str, limit: int = 4000) -> list[dict[str, Any]]:
    """gh_commits + gh_commit_files から、ingest 時と同じ形のコミットレコードを復元する。"""
    session = _new_session()
    try:
        crows = session.execute(
            text(
                """
                SELECT sha, author_login, author_name, author_email, committed_at, message,
                       additions, deletions, files_changed, is_merge
                FROM gh_commits WHERE repo = :r ORDER BY committed_at ASC LIMIT :lim
                """
            ),
            {"r": repo, "lim": limit},
        ).all()
        if not crows:
            return []
        shas = [r.sha for r in crows]
        frows = session.execute(
            text(
                """
                SELECT sha, path, previous_path, status, additions, deletions, hunk_headers, is_source
                FROM gh_commit_files WHERE sha IN :shas
                """
            ).bindparams(bindparam("shas", expanding=True)),
            {"shas": shas},
        ).all()
        files_by_sha: dict[str, list[dict[str, Any]]] = {}
        for f in frows:
            files_by_sha.setdefault(f.sha, []).append({
                "path": f.path, "previous_path": f.previous_path, "status": f.status,
                "additions": f.additions, "deletions": f.deletions,
                "hunk_headers": _json_col(f.hunk_headers) or [],
                "is_source": bool(f.is_source),
            })
        return [
            {
                "sha": c.sha,
                "author_login": c.author_login, "author_name": c.author_name,
                "author_email": c.author_email,
                "committed_at": c.committed_at.isoformat() if c.committed_at else None,
                "message": c.message, "additions": c.additions, "deletions": c.deletions,
                "files_changed": c.files_changed, "is_merge": bool(c.is_merge),
                "files": files_by_sha.get(c.sha, []),
            }
            for c in crows
        ]
    finally:
        session.close()


# ----------------------------------------------------------------------
# チャンク + 埋め込み
# ----------------------------------------------------------------------
def store_change_chunks_and_embed(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """変更履歴チャンクを gh_change_chunks へ upsert し、変わったものだけ埋め込み直す。"""
    from pipeline.ai import AiAnalyzer

    if not chunks:
        return {"chunk_count": 0, "embedded_chunks": 0, "embedding_model": None}

    session = _new_session()
    try:
        existing = dict(
            session.execute(text("SELECT chunk_id, content_hash FROM gh_change_chunks")).all()
        )
        changed = [c for c in chunks if existing.get(c["chunk_id"]) != c["content_hash"]]
        now = _now()

        cstmt = text(
            """
            INSERT INTO gh_change_chunks
              (chunk_id, kind, repo, sha, path, week, participants, text, content_hash, updated_at)
            VALUES (:id, :k, :r, :sha, :p, :wk, :pt, :txt, :h, :t)
            ON DUPLICATE KEY UPDATE
              kind = VALUES(kind), repo = VALUES(repo), sha = VALUES(sha), path = VALUES(path),
              week = VALUES(week), participants = VALUES(participants), text = VALUES(text),
              content_hash = VALUES(content_hash), updated_at = VALUES(updated_at)
            """
        )
        for c in chunks:
            session.execute(cstmt, {
                "id": c["chunk_id"], "k": c["kind"], "r": c["repo"], "sha": c.get("sha"),
                "p": c.get("path"), "wk": c["week"],
                "pt": json.dumps(c["participants"], ensure_ascii=False),
                "txt": c["text"], "h": c["content_hash"], "t": now,
            })

        pending: list[tuple[str, str, str, str]] = []
        for c in changed:
            for idx, piece in enumerate(slice_text(c["text"])):
                pending.append((f'{c["chunk_id"]}:{idx}', c["week"] or "0000-W00", c["chunk_id"], piece))

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
# 画面サマリ(ユーザごと / ファイルごと)
# ----------------------------------------------------------------------
def get_summary(repo: str) -> dict[str, Any] | None:
    """最新の取り込み状況 + ユーザごと / ファイルごとの集計を返す。"""
    session = _new_session()
    try:
        run = session.execute(
            text(
                """
                SELECT id, branch, since_date, head_sha, commit_count, file_change_count, created_at
                FROM gh_history_ingest_runs WHERE repo = :r ORDER BY id DESC LIMIT 1
                """
            ),
            {"r": repo},
        ).first()
        if not run:
            return None

        # コミット集計(ファイル JOIN で水増ししないよう分けて集計する)
        users = session.execute(
            text(
                """
                SELECT COALESCE(NULLIF(author_login, ''), author_name) AS author,
                       MAX(author_name) AS author_name,
                       COUNT(*) AS commit_count, SUM(additions) AS additions, SUM(deletions) AS deletions,
                       MIN(committed_at) AS first_at, MAX(committed_at) AS last_at
                FROM gh_commits WHERE repo = :r
                GROUP BY author ORDER BY commit_count DESC
                """
            ),
            {"r": repo},
        ).all()
        touched = dict(
            session.execute(
                text(
                    """
                    SELECT COALESCE(NULLIF(c.author_login, ''), c.author_name) AS author,
                           COUNT(DISTINCT cf.path) AS files_touched
                    FROM gh_commits c
                    JOIN gh_commit_files cf ON cf.sha = c.sha AND cf.is_source = 1
                    WHERE c.repo = :r
                    GROUP BY author
                    """
                ),
                {"r": repo},
            ).all()
        )
        files = session.execute(
            text(
                """
                SELECT path, change_count, additions, deletions, author_logins, last_change_at
                FROM gh_files WHERE repo = :r ORDER BY change_count DESC LIMIT :n
                """
            ),
            {"r": repo, "n": FILE_SUMMARY_TOP},
        ).all()

        return {
            "repo": repo,
            "branch": run.branch,
            "since_date": run.since_date.isoformat() if run.since_date else None,
            "head_sha": run.head_sha,
            "last_run_at": run.created_at.isoformat() if run.created_at else None,
            "commit_count": session.execute(
                text("SELECT COUNT(*) FROM gh_commits WHERE repo = :r"), {"r": repo}
            ).scalar_one(),
            "last_ingest_commit_count": run.commit_count,
            "users": [
                {
                    "author": u.author, "author_name": u.author_name,
                    "commit_count": u.commit_count, "additions": int(u.additions or 0),
                    "deletions": int(u.deletions or 0),
                    "files_touched": int(touched.get(u.author, 0)),
                    "first_at": u.first_at.isoformat() if u.first_at else None,
                    "last_at": u.last_at.isoformat() if u.last_at else None,
                }
                for u in users
            ],
            "files": [
                {
                    "path": f.path, "change_count": f.change_count,
                    "additions": int(f.additions or 0), "deletions": int(f.deletions or 0),
                    "authors": _json_col(f.author_logins) or [],
                    "last_at": f.last_change_at.isoformat() if f.last_change_at else None,
                }
                for f in files
            ],
        }
    finally:
        session.close()


# ----------------------------------------------------------------------
# アカウント別分析の保存・取得
# ----------------------------------------------------------------------
def _get_author_analysis(session: Session, analysis_id: int) -> dict[str, Any] | None:
    a = session.execute(
        text(
            """
            SELECT id, ingest_run_id, repo, head_sha, content_hash, model, themes, stats, status, created_at
            FROM gh_author_analyses WHERE id = :id
            """
        ),
        {"id": analysis_id},
    ).first()
    if not a:
        return None
    items = session.execute(
        text(
            """
            SELECT id, ordinal, author, author_name, overview, stats, sections
            FROM gh_author_analysis_items WHERE analysis_id = :a ORDER BY ordinal
            """
        ),
        {"a": analysis_id},
    ).all()
    refs = session.execute(
        text(
            """
            SELECT item_id, sha, created_at, excerpt
            FROM gh_author_analysis_refs WHERE analysis_id = :a ORDER BY id
            """
        ),
        {"a": analysis_id},
    ).all()
    refs_by_item: dict[int, list[dict[str, Any]]] = {}
    for r in refs:
        refs_by_item.setdefault(r.item_id, []).append({
            "sha": r.sha,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "excerpt": r.excerpt,
        })
    accounts = [
        {
            "id": it.id, "username": it.author, "full_name": it.author_name,
            "overview": it.overview,
            "stats": _json_col(it.stats) or {},
            "sections": _json_col(it.sections) or [],
            "refs": refs_by_item.get(it.id, []),
        }
        for it in items
    ]
    return {
        "id": a.id, "ingest_run_id": a.ingest_run_id, "repo": a.repo, "head_sha": a.head_sha,
        "content_hash": a.content_hash, "model": a.model,
        "themes": _json_col(a.themes) or [], "stats": _json_col(a.stats) or {},
        "status": a.status,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "accounts": accounts,
    }


def get_author_analysis(analysis_id: int) -> dict[str, Any] | None:
    session = _new_session()
    try:
        return _get_author_analysis(session, analysis_id)
    finally:
        session.close()


def find_cached_author_analysis(content_hash: str) -> dict[str, Any] | None:
    session = _new_session()
    try:
        row = session.execute(
            text(
                """
                SELECT id FROM gh_author_analyses
                WHERE content_hash = :h AND status = 'success' ORDER BY id DESC LIMIT 1
                """
            ),
            {"h": content_hash},
        ).first()
        return _get_author_analysis(session, row.id) if row else None
    finally:
        session.close()


def get_latest_author_analysis() -> dict[str, Any] | None:
    session = _new_session()
    try:
        row = session.execute(
            text("SELECT id FROM gh_author_analyses WHERE status = 'success' ORDER BY id DESC LIMIT 1")
        ).first()
        return _get_author_analysis(session, row.id) if row else None
    finally:
        session.close()


def list_author_analyses(limit: int = 30) -> list[dict[str, Any]]:
    session = _new_session()
    try:
        rows = session.execute(
            text(
                """
                SELECT id, repo, model, stats, status, created_at
                FROM gh_author_analyses ORDER BY id DESC LIMIT :lim
                """
            ),
            {"lim": limit},
        ).all()
        counts = dict(
            session.execute(
                text("SELECT analysis_id, COUNT(*) FROM gh_author_analysis_items GROUP BY analysis_id")
            ).all()
        )
        return [
            {
                "id": r.id, "repo": r.repo, "model": r.model,
                "stats": _json_col(r.stats) or {}, "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "account_count": int(counts.get(r.id, 0)),
            }
            for r in rows
        ]
    finally:
        session.close()


def save_author_analysis(
    *,
    ingest_run_id: int,
    repo: str,
    head_sha: str | None,
    content_hash: str,
    model: str,
    themes: list[str],
    stats: dict[str, Any],
    accounts: list[dict[str, Any]],
) -> dict[str, Any]:
    """アカウント別分析の結果を保存し、保存後の分析を返す。"""
    session = _new_session()
    try:
        res = session.execute(
            text(
                """
                INSERT INTO gh_author_analyses
                  (ingest_run_id, repo, head_sha, content_hash, model, themes, stats, status)
                VALUES (:run, :r, :head, :h, :model, :themes, :stats, 'success')
                """
            ),
            {
                "run": ingest_run_id, "r": repo, "head": head_sha, "h": content_hash,
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
                    INSERT INTO gh_author_analysis_items
                      (analysis_id, ordinal, author, author_name, overview, stats, sections)
                    VALUES (:a, :ord, :au, :nm, :ov, :st, :sec)
                    """
                ),
                {
                    "a": analysis_id, "ord": i,
                    "au": (acc.get("author") or "")[:255],
                    "nm": (acc.get("author_name") or "")[:255],
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
                        INSERT INTO gh_author_analysis_refs (analysis_id, item_id, sha, created_at, excerpt)
                        VALUES (:a, :it, :sha, :ca, :ex)
                        """
                    ),
                    {
                        "a": analysis_id, "it": item_id,
                        "sha": (ref.get("sha") or "")[:40],
                        "ca": ref.get("committed_at") or ref.get("created_at"),
                        "ex": (ref.get("excerpt") or "")[:500],
                    },
                )
        session.commit()
        return _get_author_analysis(session, analysis_id)  # type: ignore[return-value]
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
