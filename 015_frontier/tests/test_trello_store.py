"""Trello 情報解析の DB 入出力(pipeline/trello_store)のテスト。"""

from __future__ import annotations

from sqlalchemy import text

from pipeline import trello_ingest as ti, trello_store as tstore
from tests.test_trello_ingest import _fetch_results


def _flat():
    return ti.flatten_boards(_fetch_results())


def test_ingest_boards_idempotent_and_updates(db_session):
    flat = _flat()
    ing = tstore.ingest_boards(board_ids=["B1", "B2"], flat=flat, content_hash="h1")
    assert ing["card_count"] == 3 and ing["board_count"] == 2 and ing["activity_count"] == 2
    assert ing["member_count"] == 2

    assert db_session.execute(text("SELECT COUNT(*) FROM tr_cards")).scalar_one() == 3
    assert db_session.execute(text("SELECT COUNT(*) FROM tr_activity")).scalar_one() == 2
    # card × member のペア: (c1,alice) (c2,bob) (c3,alice) = 3
    assert db_session.execute(text("SELECT COUNT(*) FROM tr_card_members")).scalar_one() == 3

    flat2 = _flat()
    flat2["cards"][0] = dict(flat2["cards"][0], name="改名しました")
    tstore.ingest_boards(board_ids=["B1", "B2"], flat=flat2, content_hash="h2")
    db_session.rollback()  # 別セッションのコミットを見る
    assert db_session.execute(text("SELECT COUNT(*) FROM tr_cards")).scalar_one() == 3
    nm = db_session.execute(text("SELECT name FROM tr_cards WHERE card_id = 'c1'")).scalar_one()
    assert nm == "改名しました"


def test_store_card_chunks_and_embed(db_session):
    chunks = ti.build_card_chunks(_flat()["cards"], _flat()["activities"])
    out1 = tstore.store_card_chunks_and_embed(chunks)
    assert out1["chunk_count"] == 3 and out1["embedded_chunks"] == 3

    assert db_session.execute(text("SELECT COUNT(*) FROM tr_chunks")).scalar_one() == 3
    assert db_session.execute(
        text("SELECT COUNT(*) FROM embeddings WHERE source = 'trello'")
    ).scalar_one() >= 3

    assert tstore.store_card_chunks_and_embed(chunks)["embedded_chunks"] == 0
    chunks[0] = dict(chunks[0], content_hash="x", text="変更後")
    assert tstore.store_card_chunks_and_embed(chunks)["embedded_chunks"] == 1


def _accounts():
    return [
        {
            "username": "alice", "full_name": "Alice A", "overview": "レビュー役",
            "stats": {"comment_count": 5, "assigned_cards": 3},
            "sections": [{"heading": "役割", "body": "- レビュー中心"}],
            "refs": [
                {"ref_kind": "comment", "card_id": "c1", "board_id": "B1", "created_at": None, "excerpt": "LGTM"},
                {"ref_kind": "card", "card_id": "c3", "board_id": "B2", "created_at": None, "excerpt": "完了 / デプロイ"},
            ],
        },
        {
            "username": "bob", "full_name": "", "overview": "",
            "stats": {"action_count": 2}, "sections": [],
            "error": "このアカウントの分析に失敗しました", "refs": [],
        },
    ]


def test_save_and_get_account_analysis(db_session):
    saved = tstore.save_account_analysis(
        ingest_run_id=1, board_ids=["B1", "B2"], content_hash="hash-T", model="gpt-x",
        themes=["ログイン改修", "デプロイ整備"], stats={"card_count": 3, "account_count": 2},
        accounts=_accounts(),
    )
    got = tstore.get_account_analysis(saved["id"])

    assert got["themes"] == ["ログイン改修", "デプロイ整備"]
    assert [a["username"] for a in got["accounts"]] == ["alice", "bob"]
    a0 = got["accounts"][0]
    assert a0["full_name"] == "Alice A" and a0["overview"] == "レビュー役"
    assert a0["sections"] == [{"heading": "役割", "body": "- レビュー中心"}]
    assert {r["ref_kind"] for r in a0["refs"]} == {"comment", "card"}
    assert a0["refs"][0]["card_id"] == "c1"
    assert got["accounts"][1]["stats"]["error"] == "このアカウントの分析に失敗しました"


def test_cache_latest_and_list(db_session):
    tstore.save_account_analysis(
        ingest_run_id=1, board_ids=["B1"], content_hash="hash-T", model="m",
        themes=[], stats={}, accounts=_accounts(),
    )
    second = tstore.save_account_analysis(
        ingest_run_id=2, board_ids=["B1"], content_hash="hash-T", model="m",
        themes=[], stats={}, accounts=_accounts()[:1],
    )
    assert tstore.find_cached_account_analysis("hash-T")["id"] == second["id"]
    assert tstore.find_cached_account_analysis("nope") is None
    assert tstore.get_latest_account_analysis()["id"] == second["id"]

    rows = tstore.list_account_analyses()
    assert len(rows) == 2 and rows[0]["id"] == second["id"]
    assert rows[0]["account_count"] == 1 and rows[1]["account_count"] == 2
