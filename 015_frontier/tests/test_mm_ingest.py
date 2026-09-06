"""Mattermost 情報解析の決定的な前処理(pipeline/mm_ingest)のテスト。"""

from __future__ import annotations

from pipeline import mm_ingest


def _view(pid, uid, user, ms, msg, root=None, reactions=None, replies=None):
    return {
        "id": pid, "user_id": uid, "user": user, "create_at": ms, "created": "x",
        "message": msg, "root_id": root,
        "reactions": [{"emoji": k, "count": v} for k, v in (reactions or {}).items()],
        "replies": replies or [],
    }


def _fetch_result():
    r1 = _view("p1", "u1", "alice", 1_700_000_000_000, "スレッド始めます", reactions={"+1": 2},
               replies=[_view("p2", "u2", "bob", 1_700_000_100_000, "了解です", root="p1")])
    r2 = _view("p3", "u1", "alice", 1_700_090_000_000, "単発の連絡")
    standalone = _view("p4", "u2", "bob", 1_700_093_000_000, "期間外スレへの返信", root="pX")
    standalone["root_excerpt"] = "..."
    return {
        "start": "2023-11-14", "end": "2023-11-16", "channel_count": 1, "post_count": 4,
        "channels": [{
            "channel_id": "c1", "channel_name": "general", "post_count": 4,
            "posts": [r1, r2, standalone],
        }],
    }


def test_flatten_posts():
    out = mm_ingest.flatten_posts(_fetch_result())
    assert [p["post_id"] for p in out] == ["p1", "p2", "p3", "p4"]
    by_id = {p["post_id"]: p for p in out}
    assert by_id["p1"]["is_reply"] is False and by_id["p1"]["reactions"] == {"+1": 2}
    assert by_id["p1"]["reaction_count"] == 2
    assert by_id["p2"]["is_reply"] is True and by_id["p2"]["root_id"] == "p1"
    assert by_id["p3"]["is_reply"] is False
    assert by_id["p4"]["is_reply"] is True and by_id["p4"]["root_id"] == "pX"
    assert all(p["channel_id"] == "c1" and p["channel_name"] == "general" for p in out)


def test_flatten_posts_dedup():
    fr = _fetch_result()
    fr["channels"].append(fr["channels"][0])  # 同じチャンネルを二重に
    out = mm_ingest.flatten_posts(fr)
    assert sorted(p["post_id"] for p in out) == ["p1", "p2", "p3", "p4"]


def test_compute_content_hash_stable_and_sensitive():
    posts = mm_ingest.flatten_posts(_fetch_result())
    h1 = mm_ingest.compute_content_hash(["c1"], "2023-11-14", "2023-11-16", posts)
    h2 = mm_ingest.compute_content_hash(["c1"], "2023-11-14", "2023-11-16", list(reversed(posts)))
    assert h1 == h2 and len(h1) == 64
    posts2 = [dict(p) for p in posts]
    posts2[0]["message"] = "編集後"
    assert mm_ingest.compute_content_hash(["c1"], "2023-11-14", "2023-11-16", posts2) != h1
    # 期間が違えば別ハッシュ
    assert mm_ingest.compute_content_hash(["c1"], "2023-11-14", "2023-11-99", posts) != h1


def test_build_chunks_groups_threads():
    posts = mm_ingest.flatten_posts(_fetch_result())
    chunks = {c["chunk_id"]: c for c in mm_ingest.build_chunks(posts)}
    assert set(chunks) == {"mm:c1:p1", "mm:c1:p3", "mm:c1:pX"}
    thread = chunks["mm:c1:p1"]
    assert thread["post_ids"] == ["p1", "p2"]
    assert sorted(thread["participants"]) == ["u1", "u2"]
    assert thread["root_id"] == "p1"
    assert "alice: スレッド始めます" in thread["text"] and "bob: 了解です" in thread["text"]
    # 単発投稿は root_id 空
    assert chunks["mm:c1:p3"]["root_id"] == "" and chunks["mm:c1:p3"]["post_ids"] == ["p3"]


def test_build_account_contexts():
    posts = mm_ingest.flatten_posts(_fetch_result())
    ctxs = {c["username"]: c for c in mm_ingest.build_account_contexts(posts)}
    assert set(ctxs) == {"alice", "bob"}

    a = ctxs["alice"]["stats"]
    assert a["post_count"] == 2 and a["reply_count"] == 0 and a["thread_started"] == 2
    assert a["reactions_received"] == 2 and a["channel_count"] == 1

    b = ctxs["bob"]["stats"]
    assert b["post_count"] == 2 and b["reply_count"] == 2 and b["thread_started"] == 0

    assert "スレッド始めます" in ctxs["alice"]["context"]
    assert "#general" in ctxs["alice"]["context"]
    assert len(ctxs["alice"]["ref_posts"]) == 2
    assert ctxs["alice"]["ref_posts"][0]["post_id"] in ("p1", "p3")
