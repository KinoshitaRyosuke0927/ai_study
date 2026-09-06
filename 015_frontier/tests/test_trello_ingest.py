"""Trello 情報解析の決定的な前処理(pipeline/trello_ingest)のテスト。"""

from __future__ import annotations

from pipeline import trello_ingest as ti


def _act(aid, kind, username, text, summary="", date_iso="2026-08-01T10:00:00.000Z"):
    return {
        "id": aid, "kind": kind, "user": f"氏名 (@{username})", "username": username,
        "full_name": f"{username}_full", "date": "x", "date_iso": date_iso,
        "text": text, "summary": summary,
    }


def _card(cid, name, members=(), acts=(), desc="", checklists=()):
    return {
        "id": cid, "name": name, "url": f"https://trello.com/c/{cid}",
        "members": [], "member_details": [
            {"username": u, "full_name": f"{u}_full", "label": f"{u}_full (@{u})"} for u in members
        ],
        "due": None, "due_iso": None, "due_complete": False, "labels": [], "cover": None,
        "desc": desc, "checklists": list(checklists), "activity": list(acts),
    }


def _board(bid, name, lists):
    return {
        "board_id": bid, "board_name": name, "board_url": f"https://trello.com/b/{bid}",
        "list_count": len(lists),
        "card_count": sum(len(x["cards"]) for x in lists), "lists": lists,
    }


def _fetch_results():
    b1 = _board("B1", "開発ボード", [
        {"id": "L1", "name": "作業中", "card_count": 2, "cards": [
            _card("c1", "ログイン改修", members=["alice"], acts=[
                _act("a1", "comment", "alice", "レビューお願いします"),
                _act("a2", "activity", "bob", "", summary="「作業中」→「レビュー」へ移動"),
            ]),
            _card("c2", "APIエラー調査", members=["bob"]),
        ]},
    ])
    b2 = _board("B2", "運用ボード", [
        {"id": "L2", "name": "完了", "card_count": 1, "cards": [
            _card("c3", "デプロイ手順整備", members=["alice"], desc="手順書を更新"),
        ]},
    ])
    return [b1, b2]


def test_flatten_boards():
    flat = ti.flatten_boards(_fetch_results())
    assert sorted(c["card_id"] for c in flat["cards"]) == ["c1", "c2", "c3"]
    assert sorted(l["list_id"] for l in flat["lists"]) == ["L1", "L2"]
    assert len(flat["activities"]) == 2

    c1 = next(c for c in flat["cards"] if c["card_id"] == "c1")
    assert c1["member_usernames"] == ["alice"] and c1["board_name"] == "開発ボード"

    act = next(a for a in flat["activities"] if a["activity_id"] == "a2")
    assert act["username"] == "bob" and act["kind"] == "activity"
    assert act["board_name"] == "開発ボード" and act["card_name"] == "ログイン改修"
    assert act["text"] == "「作業中」→「レビュー」へ移動"


def test_content_hash_stable_and_sensitive():
    flat = ti.flatten_boards(_fetch_results())
    h1 = ti.compute_content_hash(["B1", "B2"], flat["cards"], flat["activities"])
    h2 = ti.compute_content_hash(["B2", "B1"], list(reversed(flat["cards"])), flat["activities"])
    assert h1 == h2 and len(h1) == 64
    cards2 = [dict(c) for c in flat["cards"]]
    cards2[0] = dict(cards2[0], name="改名")
    assert ti.compute_content_hash(["B1", "B2"], cards2, flat["activities"]) != h1


def test_build_card_chunks():
    flat = ti.flatten_boards(_fetch_results())
    chunks = {c["chunk_id"]: c for c in ti.build_card_chunks(flat["cards"], flat["activities"])}
    assert set(chunks) == {"trello:c1", "trello:c2", "trello:c3"}
    c1 = chunks["trello:c1"]
    assert "カード: ログイン改修" in c1["text"] and "アクティビティ:" in c1["text"]
    assert "alice コメント: レビューお願いします" in c1["text"]
    assert sorted(c1["participants"]) == ["alice", "bob"]
    assert chunks["trello:c3"]["text"].count("説明:") == 1


def test_build_account_contexts():
    flat = ti.flatten_boards(_fetch_results())
    ctxs = {c["username"]: c for c in ti.build_account_contexts(flat["cards"], flat["activities"])}
    assert set(ctxs) == {"alice", "bob"}

    a = ctxs["alice"]["stats"]
    assert a["comment_count"] == 1 and a["action_count"] == 0
    assert a["assigned_cards"] == 2 and a["board_count"] == 2

    b = ctxs["bob"]["stats"]
    assert b["action_count"] == 1 and b["assigned_cards"] == 1

    assert "レビューお願いします" in ctxs["alice"]["context"]
    assert "担当カード" in ctxs["alice"]["context"]
    assert ctxs["alice"]["full_name"] == "alice_full"
    assert len(ctxs["alice"]["refs"]) >= 1
    assert {r["ref_kind"] for r in ctxs["alice"]["refs"]} <= {"comment", "activity", "card"}
