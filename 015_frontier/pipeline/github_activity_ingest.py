"""「GitHub 情報取得」の結果を正規化する決定的な前処理(AI なし)。

viewers.github.fetch_repo_activity の戻り(ブランチ活動 + PR + コメント/レビュー)を
「誰が・いつ・どのような操作/コメントをしたか」の活動レコード(gh_activity 相当)へ展開し、
PR / ブランチ単位の RAG チャンクを作る。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

EMBED_SLICE_CHARS = 800
BRANCH_CHUNK_MAX_COMMITS = 15
RECENT_ACTIVITY_LIMIT = 200  # 画面に返す直近アクティビティ数


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _iso_week(dt: datetime | None) -> str:
    if dt is None:
        return ""
    y, w, _ = dt.isocalendar()
    return f"{y:04d}-W{w:02d}"


def _first_line(text: str, limit: int = 160) -> str:
    s = (text or "").strip()
    return (s.splitlines()[0][:limit]) if s else ""


# ----------------------------------------------------------------------
# 正規化(活動レコード)
# ----------------------------------------------------------------------
def flatten_activity(fetch_result: dict[str, Any]) -> dict[str, Any]:
    """fetch_repo_activity の戻りを branches / pull_requests / activities へ展開する。"""
    repo = fetch_result.get("repo", "")
    branches_out: list[dict[str, Any]] = []
    prs_out: list[dict[str, Any]] = []
    acts: list[dict[str, Any]] = []
    seen_events: set[str] = set()

    def _add(event_id: str, **kw: Any) -> None:
        if not event_id or event_id in seen_events:
            return
        seen_events.add(event_id)
        acts.append({"event_id": event_id, "repo": repo, **kw})

    # --- ブランチ + コミット ---
    for b in fetch_result.get("branches", []):
        name = b.get("name", "")
        branches_out.append({
            "repo": repo,
            "name": name,
            "is_protected": bool(b.get("protected")),
            "commit_count": b.get("commit_count", 0),
            "last_activity_at": _parse_iso(
                b.get("last_activity_iso")
                or (b.get("commits", [{}])[0].get("date_iso") if b.get("commits") else None)
            ),
            "last_author": b.get("last_author") or "",
        })
        for c in b.get("commits", []):
            sha = c.get("sha_full") or c.get("sha") or ""
            if not sha:
                continue
            dt = _parse_iso(c.get("date_iso"))
            _add(
                f"commit:{sha}",
                kind="commit",
                actor=c.get("author") or "",
                occurred_at=dt,
                week=_iso_week(dt),
                pr_number=None,
                branch=name,
                sha=sha,
                title=name,
                summary="コミット",
                body=c.get("message_full") or c.get("message") or "",
                url=c.get("url", ""),
            )

    # --- PR + ライフサイクル + コメント/レビュー ---
    for p in fetch_result.get("pull_requests", []):
        num = p.get("number")
        merged = bool(p.get("merged"))
        prs_out.append({
            "repo": repo,
            "number": num,
            "title": p.get("title", ""),
            "state": p.get("state", ""),
            "merged": merged,
            "author": p.get("author") or "",
            "created_at": _parse_iso(p.get("created_iso")),
            "closed_at": _parse_iso(p.get("closed_iso")),
            "merged_at": _parse_iso(p.get("merged_at_iso")),
            "merged_by": p.get("merged_by") or "",
            "comment_count": len(p.get("comments", [])),
            "url": p.get("url", ""),
        })

        created_dt = _parse_iso(p.get("created_iso"))
        _add(
            f"pr_opened:{num}", kind="pr_opened", actor=p.get("author") or "",
            occurred_at=created_dt, week=_iso_week(created_dt),
            pr_number=num, branch=None, sha=None,
            title=p.get("title", ""), summary="PR を作成", body="", url=p.get("url", ""),
        )
        if merged:
            m_dt = _parse_iso(p.get("merged_at_iso"))
            _add(
                f"pr_merged:{num}", kind="pr_merged",
                actor=p.get("merged_by") or p.get("author") or "",
                occurred_at=m_dt, week=_iso_week(m_dt),
                pr_number=num, branch=None, sha=None,
                title=p.get("title", ""), summary="マージを実行", body="", url=p.get("url", ""),
            )
        elif p.get("state") == "closed":
            c_dt = _parse_iso(p.get("closed_iso"))
            _add(
                f"pr_closed:{num}", kind="pr_closed", actor="",  # closed_by は取得していない
                occurred_at=c_dt, week=_iso_week(c_dt),
                pr_number=num, branch=None, sha=None,
                title=p.get("title", ""), summary="PR をクローズ", body="", url=p.get("url", ""),
            )

        for cm in p.get("comments", []):
            cid = cm.get("id")
            if cid is None:
                continue
            dt = _parse_iso(cm.get("date_iso"))
            is_review = cm.get("kind") == "review"
            _add(
                f"pr_{'review' if is_review else 'comment'}:{cid}",
                kind="pr_review" if is_review else "pr_comment",
                actor=cm.get("author") or "",
                occurred_at=dt, week=_iso_week(dt),
                pr_number=num, branch=None, sha=None,
                title=p.get("title", ""),
                summary=("レビュー" if is_review else "コメント"),
                body=cm.get("text", "") or "",
                url=p.get("url", ""),
            )

    acts.sort(key=lambda a: a.get("occurred_at") or datetime.min)
    return {"repo": repo, "branches": branches_out, "pull_requests": prs_out, "activities": acts}


def compute_content_hash(flat: dict[str, Any]) -> str:
    """活動レコード + PR 状態から決定的なハッシュを作る。"""
    h = hashlib.sha256()
    h.update((flat.get("repo") or "").encode("utf-8"))
    h.update(b"\x00")
    for a in sorted(flat["activities"], key=lambda x: x["event_id"]):
        h.update(a["event_id"].encode("utf-8"))
        h.update(b"\x00")
        h.update((a.get("body") or "").encode("utf-8"))
        h.update(b"\x00")
    for p in sorted(flat["pull_requests"], key=lambda x: x["number"] or 0):
        h.update(f"{p['number']}:{p['state']}:{int(p['merged'])}".encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


# ----------------------------------------------------------------------
# 画面サマリ(活動ログ)
# ----------------------------------------------------------------------
_KIND_LABEL = {
    "commit": "コミット",
    "pr_opened": "PR作成",
    "pr_merged": "マージ",
    "pr_closed": "PRクローズ",
    "pr_comment": "コメント",
    "pr_review": "レビュー",
}


def build_actor_tally(activities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """アカウントごとの操作種別カウント。"""
    by_actor: dict[str, dict[str, Any]] = {}
    for a in activities:
        actor = a.get("actor") or "(不明)"
        t = by_actor.setdefault(actor, {"actor": actor, "total": 0, **{k: 0 for k in _KIND_LABEL}})
        t["total"] += 1
        if a["kind"] in t:
            t[a["kind"]] += 1
    out = list(by_actor.values())
    out.sort(key=lambda x: x["total"], reverse=True)
    return out


# ----------------------------------------------------------------------
# RAG チャンク
# ----------------------------------------------------------------------
def build_pr_chunks(
    pull_requests: list[dict[str, Any]], activities: list[dict[str, Any]], repo: str
) -> list[dict[str, Any]]:
    """PR 1 件 = 1 チャンク(タイトル + ライフサイクル + コメント/レビュー)。"""
    acts_by_pr: dict[int, list[dict[str, Any]]] = {}
    for a in activities:
        if a.get("pr_number") is not None and a["kind"] != "commit":
            acts_by_pr.setdefault(a["pr_number"], []).append(a)

    chunks: list[dict[str, Any]] = []
    for p in pull_requests:
        num = p["number"]
        pacts = sorted(acts_by_pr.get(num, []), key=lambda x: x.get("occurred_at") or datetime.min)
        lines = [f"[{repo}] PR #{num}: {p['title']}"]
        state = "マージ済み" if p["merged"] else ("クローズ" if p["state"] == "closed" else "オープン")
        lines.append(
            f"状態: {state} / 作成: {p['author']} ({p['created_at']})"
            + (f" / マージ実行: {p['merged_by']} ({p['merged_at']})" if p["merged"] else "")
        )
        participants = {p["author"]} if p["author"] else set()
        for a in pacts:
            if a["kind"] in ("pr_comment", "pr_review"):
                who = a.get("actor") or "(不明)"
                participants.add(who)
                kind = "レビュー" if a["kind"] == "pr_review" else "コメント"
                lines.append(f"  [{a.get('occurred_at')}] {who} {kind}: {_first_line(a.get('body', ''), 400)}")
        text = "\n".join(str(x) for x in lines)
        chash = hashlib.sha256(
            (
                f"{p['title']}|{p['state']}|{int(p['merged'])}|{p['merged_by']}|"
                + "\n".join(f'{a["event_id"]}={a.get("body", "")}' for a in pacts)
            ).encode("utf-8")
        ).hexdigest()
        dt = p.get("merged_at") or p.get("closed_at") or p.get("created_at")
        chunks.append({
            "chunk_id": f"ghpr:{repo}:{num}",
            "kind": "pr",
            "repo": repo,
            "pr_number": num,
            "branch": None,
            "week": _iso_week(dt),
            "participants": sorted(x for x in participants if x),
            "text": text,
            "content_hash": chash,
        })
    return chunks


def build_branch_chunks(
    branches: list[dict[str, Any]], fetch_result: dict[str, Any], repo: str
) -> list[dict[str, Any]]:
    """ブランチ 1 件 = 1 チャンク(直近コミットの誰が/何を)。"""
    commits_by_branch = {b.get("name", ""): b.get("commits", []) for b in fetch_result.get("branches", [])}
    chunks: list[dict[str, Any]] = []
    for b in branches:
        name = b["name"]
        commits = commits_by_branch.get(name, [])[:BRANCH_CHUNK_MAX_COMMITS]
        if not commits:
            continue
        lines = [f"[{repo}] ブランチ: {name}" + ("(保護)" if b["is_protected"] else "")]
        authors = set()
        for c in commits:
            authors.add(c.get("author") or "")
            lines.append(f"  [{c.get('date_iso') or c.get('date')}] {c.get('author')}: {_first_line(c.get('message', ''))}")
        chash = hashlib.sha256(
            "\n".join(f'{c.get("sha_full") or c.get("sha")}={_first_line(c.get("message", ""))}' for c in commits).encode("utf-8")
        ).hexdigest()
        chunks.append({
            "chunk_id": "ghbranch:" + hashlib.sha1(f"{repo}/{name}".encode("utf-8")).hexdigest()[:16],
            "kind": "branch",
            "repo": repo,
            "pr_number": None,
            "branch": name,
            "week": _iso_week(b.get("last_activity_at")),
            "participants": sorted(a for a in authors if a),
            "text": "\n".join(lines),
            "content_hash": chash,
        })
    return chunks


def slice_text(s: str, size: int = EMBED_SLICE_CHARS) -> list[str]:
    s = (s or "").strip()
    return [s[i : i + size] for i in range(0, len(s), size)] if s else []
