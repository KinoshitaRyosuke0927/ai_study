"""「Mattermost 情報解析」の決定的な前処理(AI なし)。

- flatten_posts(): viewers.mattermost.fetch_posts の戻り(チャンネル別・スレッド構造)を
  1 投稿 1 レコードの平坦なリストへ展開する。
- compute_content_hash(): (対象チャンネル + 期間 + 投稿内容) から決定的なハッシュを作る
  (同一入力の分析はキャッシュ再利用する)。
- build_chunks(): 会話をスレッド単位のチャンクへまとめる(RAG 用)。
- build_account_contexts(): アカウントごとに、チャンネル横断の発言テキストと統計を作る
  (2 段目の AI 分析の入力)。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

# 2 段目の AI へ渡す、1 アカウントぶんの発言テキストの文字数上限
MAX_ACCOUNT_CONTEXT_CHARS = 16000
# 1 アカウントの分析に紐づけて保存する参照投稿(トレーサビリティ)の上限
MAX_REFS_PER_ACCOUNT = 60
# RAG 埋め込み用にチャンク本文を分割する単位
EMBED_SLICE_CHARS = 800


def _utc(ms: int) -> datetime:
    """epoch ミリ秒 → naive UTC datetime。"""
    return datetime.fromtimestamp((ms or 0) / 1000, tz=timezone.utc).replace(tzinfo=None)


def _iso_week(ms: int) -> str:
    """epoch ミリ秒 → ISO 週文字列 "YYYY-Www"。"""
    y, w, _ = datetime.fromtimestamp((ms or 0) / 1000, tz=timezone.utc).isocalendar()
    return f"{y:04d}-W{w:02d}"


# ----------------------------------------------------------------------
# 平坦化
# ----------------------------------------------------------------------
def _post_record(channel_id: str, channel_name: str, view: dict, is_reply: bool) -> dict[str, Any]:
    reactions = {r["emoji"]: r["count"] for r in view.get("reactions", []) if r.get("emoji")}
    return {
        "post_id": view.get("id") or "",
        "channel_id": channel_id,
        "channel_name": channel_name,
        "user_id": view.get("user_id") or "",
        "username": view.get("user") or view.get("user_id") or "",
        "root_id": view.get("root_id") or "",
        "is_reply": bool(is_reply),
        "create_at": int(view.get("create_at") or 0),  # epoch ミリ秒
        "message": view.get("message") or "",
        "reactions": reactions,
        "reaction_count": sum(reactions.values()),
    }


def flatten_posts(fetch_result: dict[str, Any]) -> list[dict[str, Any]]:
    """fetch_posts の戻りを 1 投稿 1 レコードの平坦なリストへ展開する。"""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ch in fetch_result.get("channels", []):
        cid = ch.get("channel_id") or ""
        cname = ch.get("channel_name") or cid
        for root in ch.get("posts", []):
            for view, is_reply in [(root, bool(root.get("root_id")))] + [
                (rep, True) for rep in root.get("replies", [])
            ]:
                rec = _post_record(cid, cname, view, is_reply)
                if rec["post_id"] and rec["post_id"] not in seen:
                    seen.add(rec["post_id"])
                    out.append(rec)
    return out


def compute_content_hash(
    channel_ids: list[str], window_start: str | None, window_end: str | None,
    posts: list[dict[str, Any]],
) -> str:
    """(対象チャンネル + 期間 + 投稿内容) から決定的なハッシュを作る。"""
    h = hashlib.sha256()
    h.update("|".join(sorted(channel_ids)).encode("utf-8"))
    h.update(f"\x00{window_start}..{window_end}\x00".encode("utf-8"))
    for p in sorted(posts, key=lambda x: x["post_id"]):
        h.update(p["post_id"].encode("utf-8"))
        h.update(b"\x00")
        h.update(p["message"].encode("utf-8"))
        h.update(b"\x00")
        h.update(json.dumps(p["reactions"], sort_keys=True, ensure_ascii=False).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


# ----------------------------------------------------------------------
# チャンク化(RAG 用)
# ----------------------------------------------------------------------
def build_chunks(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """会話をスレッド単位(ルート + 返信)のチャンクへまとめる。

    返信を持たない単発投稿はそれ自体が 1 チャンクになる。
    """
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for p in posts:
        # ルート投稿は自分の post_id、返信は root_id でグループ化する
        root_key = p["root_id"] or p["post_id"]
        groups.setdefault((p["channel_id"], root_key), []).append(p)

    chunks: list[dict[str, Any]] = []
    for (cid, root_key), plist in groups.items():
        plist.sort(key=lambda x: x["create_at"])
        lines = [
            f'{p["username"]}: {p["message"].strip()}'
            for p in plist
            if p["message"].strip()
        ]
        if not lines:
            continue
        starts = [p["create_at"] for p in plist]
        body = "\n".join(lines)
        chash = hashlib.sha256(
            "\n".join(sorted(f'{p["post_id"]}={p["message"]}' for p in plist)).encode("utf-8")
        ).hexdigest()
        has_thread = any(p["is_reply"] for p in plist)
        chunks.append({
            "chunk_id": f"mm:{cid}:{root_key}",
            "channel_id": cid,
            "root_id": root_key if has_thread else "",
            "week": _iso_week(min(starts)),
            "start_at": _utc(min(starts)),
            "end_at": _utc(max(starts)),
            "participants": sorted({p["user_id"] for p in plist if p["user_id"]}),
            "post_ids": [p["post_id"] for p in plist],
            "text": body,
            "content_hash": chash,
        })
    return chunks


def slice_text(s: str, size: int = EMBED_SLICE_CHARS) -> list[str]:
    """埋め込み用にテキストを size 文字ごとに分割する。"""
    s = (s or "").strip()
    return [s[i : i + size] for i in range(0, len(s), size)] if s else []


# ----------------------------------------------------------------------
# アカウントごとのコンテキスト(2 段目 AI の入力)
# ----------------------------------------------------------------------
def account_stats(plist: list[dict[str, Any]]) -> dict[str, Any]:
    """1 アカウントの投稿群から活動統計を算出する。"""
    days = {_utc(p["create_at"]).date().isoformat() for p in plist}
    ch_count: dict[str, int] = {}
    for p in plist:
        ch_count[p["channel_name"]] = ch_count.get(p["channel_name"], 0) + 1
    return {
        "post_count": len(plist),
        "reply_count": sum(1 for p in plist if p["is_reply"]),
        "thread_started": sum(1 for p in plist if not p["is_reply"]),
        "reactions_received": sum(p["reaction_count"] for p in plist),
        "channel_count": len(ch_count),
        "channels": sorted(ch_count, key=lambda k: -ch_count[k]),
        "active_days": len(days),
        "first_at": _utc(min(p["create_at"] for p in plist)).isoformat(),
        "last_at": _utc(max(p["create_at"] for p in plist)).isoformat(),
    }


def _render_account_posts(
    plist: list[dict[str, Any]]
) -> tuple[str, list[dict[str, Any]]]:
    """アカウントの発言を時系列テキスト化する。多すぎる場合は等間隔で抜粋する。

    Returns:
        (context_text, ref_posts)  ref_posts は分析の根拠として保存する投稿
    """
    rows: list[tuple[dict[str, Any], str]] = []
    for p in plist:
        msg = p["message"].replace("\n", " ").strip()
        if not msg:
            continue
        ts = _utc(p["create_at"]).strftime("%Y-%m-%d %H:%M")
        tag = " (返信)" if p["is_reply"] else ""
        rows.append((p, f'[{ts}] #{p["channel_name"]}{tag} {msg}'))

    note = ""
    total = sum(len(t) for _, t in rows)
    if total > MAX_ACCOUNT_CONTEXT_CHARS and len(rows) > 20:
        keep = max(20, int(len(rows) * MAX_ACCOUNT_CONTEXT_CHARS / total))
        step = len(rows) / keep
        idxs = sorted({0, len(rows) - 1} | {int(i * step) for i in range(keep)})
        rows = [rows[i] for i in idxs if i < len(rows)]
        note = "\n...(投稿数が多いため一部を抜粋)..."

    context = "\n".join(t for _, t in rows)[:MAX_ACCOUNT_CONTEXT_CHARS] + note
    ref_posts = [
        {
            "post_id": p["post_id"],
            "channel_id": p["channel_id"],
            "created_at": _utc(p["create_at"]),
            "excerpt": p["message"].replace("\n", " ").strip()[:500],
        }
        for p, _ in rows[:MAX_REFS_PER_ACCOUNT]
    ]
    return context, ref_posts


def build_account_contexts(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """アカウントごとに {user_id, username, stats, context, ref_posts} を作る。

    投稿数の多い順に並べて返す。
    """
    by_user: dict[str, list[dict[str, Any]]] = {}
    for p in posts:
        if p["user_id"]:
            by_user.setdefault(p["user_id"], []).append(p)

    out: list[dict[str, Any]] = []
    for uid, plist in by_user.items():
        plist.sort(key=lambda x: x["create_at"])
        context, ref_posts = _render_account_posts(plist)
        out.append({
            "user_id": uid,
            "username": plist[-1]["username"],
            "stats": account_stats(plist),
            "context": context,
            "ref_posts": ref_posts,
        })
    out.sort(key=lambda a: a["stats"]["post_count"], reverse=True)
    return out
