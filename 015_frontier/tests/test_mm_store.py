"""Mattermost 情報解析の DB 入出力(pipeline/mm_store)のテスト。"""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from pipeline import mm_ingest, mm_store
from tests.test_mm_ingest import _fetch_result


def _posts():
    return mm_ingest.flatten_posts(_fetch_result())


def test_ingest_posts_is_idempotent_and_updates(db_session):
    posts = _posts()
    ing = mm_store.ingest_posts(
        mode="current", channel_ids=["c1"],
        window_start=date(2023, 11, 14), window_end=date(2023, 11, 16),
        posts=posts, content_hash="h1",
    )
    assert ing["post_count"] == 4 and ing["channel_count"] == 1 and ing["user_count"] == 2

    n = db_session.execute(text("SELECT COUNT(*) FROM mm_posts")).scalar_one()
    assert n == 4
    assert db_session.execute(text("SELECT COUNT(*) FROM mm_channels")).scalar_one() == 1
    assert db_session.execute(text("SELECT COUNT(*) FROM mm_users")).scalar_one() == 2

    # 同じ post_id を message 変更ありで再取り込み → 行は増えず内容だけ更新
    posts2 = [dict(p) for p in posts]
    posts2[0]["message"] = "編集しました"
    mm_store.ingest_posts(
        mode="current", channel_ids=["c1"],
        window_start=date(2023, 11, 14), window_end=date(2023, 11, 16),
        posts=posts2, content_hash="h2",
    )
    # 別セッションのコミットを見るため、このセッションのスナップショットを切る
    db_session.rollback()
    assert db_session.execute(text("SELECT COUNT(*) FROM mm_posts")).scalar_one() == 4
    msg = db_session.execute(
        text("SELECT message FROM mm_posts WHERE post_id = 'p1'")
    ).scalar_one()
    assert msg == "編集しました"


def test_store_chunks_and_embed_only_reembeds_changed(db_session):
    chunks = mm_ingest.build_chunks(_posts())
    out1 = mm_store.store_chunks_and_embed(chunks)
    assert out1["chunk_count"] == 3 and out1["embedded_chunks"] == 3

    # mm_chunks と embeddings(source='mattermost')に入っている
    assert db_session.execute(text("SELECT COUNT(*) FROM mm_chunks")).scalar_one() == 3
    emb = db_session.execute(
        text("SELECT COUNT(*) FROM embeddings WHERE source = 'mattermost'")
    ).scalar_one()
    assert emb >= 3

    # 変更なしで再実行 → 埋め込み直しゼロ
    out2 = mm_store.store_chunks_and_embed(chunks)
    assert out2["embedded_chunks"] == 0

    # 1 チャンクの内容を変える → そのチャンクだけ再埋め込み
    chunks[0] = dict(chunks[0], content_hash="changed", text="alice: 書き換え")
    out3 = mm_store.store_chunks_and_embed(chunks)
    assert out3["embedded_chunks"] == 1


def _accounts():
    return [
        {
            "user_id": "u1", "username": "alice", "overview": "報告が多い",
            "stats": {"post_count": 12, "reply_count": 3},
            "sections": [{"heading": "傾向", "body": "- 進捗報告が中心"}],
            "ref_posts": [
                {"post_id": "p1", "channel_id": "c1", "created_at": None, "excerpt": "スレッド始めます"},
            ],
        },
        {
            "user_id": "u2", "username": "bob", "overview": "",
            "stats": {"post_count": 4, "reply_count": 4},
            "sections": [], "error": "このアカウントの分析に失敗しました",
            "ref_posts": [],
        },
    ]


def test_save_and_get_account_analysis(db_session):
    saved = mm_store.save_account_analysis(
        ingest_run_id=1, window_start=date(2023, 11, 14), window_end=date(2023, 11, 16),
        channel_ids=["c1"], content_hash="hash-A", model="gpt-x",
        topics=["注文量予測", "気象データ"], stats={"post_count": 16, "account_count": 2},
        accounts=_accounts(),
    )
    got = mm_store.get_account_analysis(saved["id"])

    assert got["topics"] == ["注文量予測", "気象データ"]
    assert got["window_start"] == "2023-11-14"
    assert [a["username"] for a in got["accounts"]] == ["alice", "bob"]

    a0 = got["accounts"][0]
    assert a0["overview"] == "報告が多い"
    assert a0["sections"] == [{"heading": "傾向", "body": "- 進捗報告が中心"}]
    assert a0["stats"]["post_count"] == 12
    assert a0["refs"][0]["post_id"] == "p1" and a0["refs"][0]["excerpt"] == "スレッド始めます"
    # 失敗アカウントは stats に error が入る
    assert got["accounts"][1]["stats"]["error"] == "このアカウントの分析に失敗しました"


def test_cache_latest_and_list(db_session):
    mm_store.save_account_analysis(
        ingest_run_id=1, window_start=None, window_end=None, channel_ids=["c1"],
        content_hash="hash-A", model="m", topics=[], stats={}, accounts=_accounts(),
    )
    second = mm_store.save_account_analysis(
        ingest_run_id=2, window_start=None, window_end=None, channel_ids=["c1"],
        content_hash="hash-A", model="m", topics=[], stats={}, accounts=_accounts()[:1],
    )
    cached = mm_store.find_cached_account_analysis("hash-A")
    assert cached["id"] == second["id"]                       # 同一ハッシュの最新
    assert mm_store.find_cached_account_analysis("nope") is None

    latest = mm_store.get_latest_account_analysis()
    assert latest["id"] == second["id"]

    rows = mm_store.list_account_analyses()
    assert len(rows) == 2 and rows[0]["id"] == second["id"]
    assert rows[0]["account_count"] == 1 and rows[1]["account_count"] == 2
