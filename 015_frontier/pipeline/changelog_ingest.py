"""「変更履歴取得」の決定的な前処理(AI なし)。

- compute_content_hash(): (repo + branch + HEAD SHA + since) から決定的なハッシュを作る。
- build_commit_chunks(): 1 コミット = 1 チャンク(RAG 用。メッセージ + 変更ファイル + ハンク見出し)。
- build_file_rollup_chunks(): 1 ファイル = 1 チャンク(変遷・変更者のロールアップ)。
- build_user_summary() / build_file_summary(): 画面の「ユーザごと / ファイルごと」表。
- build_author_contexts(): アカウントごとの変更履歴テキストと統計(2 段目の AI 分析の入力)。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

MAX_AUTHOR_CONTEXT_CHARS = 16000
MAX_REFS_PER_AUTHOR = 60
EMBED_SLICE_CHARS = 800
FILE_ROLLUP_MAX_COMMITS = 30     # file チャンクに載せるコミット数
FILE_SUMMARY_TOP = 60           # 画面の「ファイルごと」表の行数


def _parse_iso(value: str | None) -> datetime | None:
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


def _author_key(c: dict[str, Any]) -> str:
    """コミットの代表アカウント名(login 優先、無ければ commit author name)。"""
    return c.get("author_login") or c.get("author_name") or "(unknown)"


def _first_line(msg: str) -> str:
    return (msg or "").strip().splitlines()[0].strip() if (msg or "").strip() else "(no message)"


def compute_content_hash(
    repo: str, branch: str, head_sha: str | None, since_iso: str | None
) -> str:
    h = hashlib.sha256()
    for part in (repo, branch, head_sha or "-", since_iso or "-"):
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


# ----------------------------------------------------------------------
# RAG チャンク
# ----------------------------------------------------------------------
def build_commit_chunks(commits: list[dict[str, Any]], repo: str) -> list[dict[str, Any]]:
    """1 コミット = 1 チャンク。メッセージ + 変更ファイル + ハンク見出し。"""
    chunks: list[dict[str, Any]] = []
    for c in commits:
        dt = _parse_iso(c.get("committed_at")) or datetime.now(timezone.utc).replace(tzinfo=None)
        author = _author_key(c)
        msg = (c.get("message") or "").strip()
        lines = [f"[{repo}] {dt.isoformat()} {author}: {_first_line(msg)}"]
        rest = "\n".join(msg.splitlines()[1:]).strip()
        if rest:
            lines.append(rest[:1500])
        src_files = [f for f in c.get("files", []) if f.get("is_source")] or c.get("files", [])
        if src_files:
            lines.append("変更ファイル:")
            for f in src_files[:60]:
                lines.append(f" - {f['path']} (+{f['additions']}/-{f['deletions']}) [{f['status']}]")
                for h in f.get("hunk_headers", [])[:8]:
                    lines.append(f"     {h}")
        text = "\n".join(lines)
        chash = hashlib.sha256(
            (msg + "\x00" + "\n".join(
                f'{f["path"]}|{f["status"]}|{",".join(f.get("hunk_headers", []))}'
                for f in c.get("files", [])
            )).encode("utf-8")
        ).hexdigest()
        chunks.append({
            "chunk_id": f"ghchange:{c['sha']}",
            "kind": "commit",
            "repo": repo,
            "sha": c["sha"],
            "path": None,
            "week": _iso_week(dt),
            "participants": [author],
            "text": text,
            "content_hash": chash,
        })
    return chunks


def build_file_rollup_chunks(
    commits: list[dict[str, Any]], repo: str
) -> list[dict[str, Any]]:
    """1 ファイル = 1 チャンク。そのファイルを変更したコミットの履歴。"""
    by_path: dict[str, list[tuple[datetime, str, str]]] = {}
    for c in commits:
        dt = _parse_iso(c.get("committed_at")) or datetime.now(timezone.utc).replace(tzinfo=None)
        author = _author_key(c)
        for f in c.get("files", []):
            if not f.get("is_source"):
                continue
            by_path.setdefault(f["path"], []).append((dt, author, _first_line(c.get("message", ""))))

    chunks: list[dict[str, Any]] = []
    for path, entries in by_path.items():
        entries.sort(key=lambda x: x[0], reverse=True)
        authors = sorted({a for _, a, _ in entries})
        last_dt = entries[0][0]
        lines = [
            f"ファイル: {path}",
            f"変更回数 {len(entries)} / 変更者: {', '.join(authors)}",
            "主な変更(新しい順):",
        ]
        for dt, author, msg in entries[:FILE_ROLLUP_MAX_COMMITS]:
            lines.append(f" - {dt.isoformat()} {author}: {msg}")
        text = "\n".join(lines)
        chash = hashlib.sha256(
            (path + "\x00" + ",".join(f'{dt.isoformat()}:{a}' for dt, a, _ in entries)).encode("utf-8")
        ).hexdigest()
        chunks.append({
            "chunk_id": "ghfile:" + hashlib.sha1(path.encode("utf-8")).hexdigest()[:16],
            "kind": "file",
            "repo": repo,
            "sha": None,
            "path": path,
            "week": _iso_week(last_dt),
            "participants": authors,
            "text": text,
            "content_hash": chash,
        })
    return chunks


def slice_text(s: str, size: int = EMBED_SLICE_CHARS) -> list[str]:
    s = (s or "").strip()
    return [s[i : i + size] for i in range(0, len(s), size)] if s else []


# ----------------------------------------------------------------------
# 画面サマリ(ユーザごと / ファイルごと)
# ----------------------------------------------------------------------
def build_user_summary(commits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """ユーザ(author)ごとの変更集計。"""
    by_user: dict[str, dict[str, Any]] = {}
    for c in commits:
        key = _author_key(c)
        dt = _parse_iso(c.get("committed_at"))
        u = by_user.setdefault(key, {
            "author": key, "author_name": c.get("author_name", ""),
            "commit_count": 0, "additions": 0, "deletions": 0,
            "files": set(), "first_at": None, "last_at": None,
        })
        u["commit_count"] += 1
        u["additions"] += c.get("additions", 0)
        u["deletions"] += c.get("deletions", 0)
        u["files"].update(f["path"] for f in c.get("files", []) if f.get("is_source"))
        if dt:
            u["first_at"] = dt if u["first_at"] is None else min(u["first_at"], dt)
            u["last_at"] = dt if u["last_at"] is None else max(u["last_at"], dt)
    out = []
    for u in by_user.values():
        out.append({
            "author": u["author"], "author_name": u["author_name"],
            "commit_count": u["commit_count"], "additions": u["additions"], "deletions": u["deletions"],
            "files_touched": len(u["files"]),
            "first_at": u["first_at"].isoformat() if u["first_at"] else None,
            "last_at": u["last_at"].isoformat() if u["last_at"] else None,
        })
    out.sort(key=lambda x: x["commit_count"], reverse=True)
    return out


def build_file_summary(commits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """ファイルごとの変更集計(変更回数の多い順、上位のみ)。"""
    by_path: dict[str, dict[str, Any]] = {}
    for c in commits:
        dt = _parse_iso(c.get("committed_at"))
        author = _author_key(c)
        for f in c.get("files", []):
            if not f.get("is_source"):
                continue
            p = by_path.setdefault(f["path"], {
                "path": f["path"], "change_count": 0, "additions": 0, "deletions": 0,
                "authors": set(), "last_at": None,
            })
            p["change_count"] += 1
            p["additions"] += f.get("additions", 0)
            p["deletions"] += f.get("deletions", 0)
            p["authors"].add(author)
            if dt:
                p["last_at"] = dt if p["last_at"] is None else max(p["last_at"], dt)
    out = [
        {
            "path": p["path"], "change_count": p["change_count"],
            "additions": p["additions"], "deletions": p["deletions"],
            "authors": sorted(p["authors"]),
            "last_at": p["last_at"].isoformat() if p["last_at"] else None,
        }
        for p in by_path.values()
    ]
    out.sort(key=lambda x: x["change_count"], reverse=True)
    return out[:FILE_SUMMARY_TOP]


# ----------------------------------------------------------------------
# アカウントごとのコンテキスト(2 段目 AI の入力)
# ----------------------------------------------------------------------
def _render_author(commits: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    rows: list[tuple[dict[str, Any], str]] = []
    for c in sorted(commits, key=lambda x: x.get("committed_at") or ""):
        dt = _parse_iso(c.get("committed_at"))
        ts = dt.strftime("%Y-%m-%d %H:%M") if dt else "?"
        src = [f for f in c.get("files", []) if f.get("is_source")]
        paths = ", ".join(f["path"] for f in src[:12])
        rows.append((
            c,
            f"[{ts}] {_first_line(c.get('message', ''))}  (+{c.get('additions', 0)}/-{c.get('deletions', 0)}, {len(src)}ファイル) {paths}",
        ))

    note = ""
    total = sum(len(t) for _, t in rows)
    if total > MAX_AUTHOR_CONTEXT_CHARS and len(rows) > 20:
        keep = max(20, int(len(rows) * MAX_AUTHOR_CONTEXT_CHARS / total))
        step = len(rows) / keep
        idxs = sorted({0, len(rows) - 1} | {int(i * step) for i in range(keep)})
        rows = [rows[i] for i in idxs if i < len(rows)]
        note = "\n...(コミットが多いため一部を抜粋)..."

    context = ("=== コミット履歴(時系列)===\n" + "\n".join(t for _, t in rows) + note)[:MAX_AUTHOR_CONTEXT_CHARS]
    refs = [
        {"sha": c["sha"], "committed_at": _parse_iso(c.get("committed_at")),
         "excerpt": _first_line(c.get("message", ""))[:500]}
        for c, _ in rows[:MAX_REFS_PER_AUTHOR]
    ]
    return context, refs


def build_author_contexts(commits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """アカウントごとに {author, author_name, stats, context, refs} を作る。"""
    by_user: dict[str, list[dict[str, Any]]] = {}
    for c in commits:
        by_user.setdefault(_author_key(c), []).append(c)

    summary = {u["author"]: u for u in build_user_summary(commits)}
    out: list[dict[str, Any]] = []
    for key, clist in by_user.items():
        context, refs = _render_author(clist)
        # そのユーザがよく触るファイル上位
        fcount: dict[str, int] = {}
        for c in clist:
            for f in c.get("files", []):
                if f.get("is_source"):
                    fcount[f["path"]] = fcount.get(f["path"], 0) + 1
        top_files = [p for p, _ in sorted(fcount.items(), key=lambda kv: -kv[1])[:12]]
        stats = dict(summary.get(key, {}))
        stats["top_files"] = top_files
        out.append({
            "author": key,
            "author_name": clist[-1].get("author_name", ""),
            "stats": stats,
            "context": context,
            "refs": refs,
        })
    out.sort(key=lambda a: a["stats"].get("commit_count", 0), reverse=True)
    return out
