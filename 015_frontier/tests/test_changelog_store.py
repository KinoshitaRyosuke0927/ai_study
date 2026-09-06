"""変更履歴取得の DB 入出力(pipeline/changelog_store)のテスト。"""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from pipeline import changelog_ingest as ci, changelog_store as cstore
from tests.test_changelog_ingest import COMMITS


def _ingest(commits=COMMITS, head="s3", h="h1"):
    return cstore.ingest_commits(
        repo="acme/app", branch="main", head_sha=head, base_sha=None,
        since_date=date(2026, 8, 1), commits=commits, content_hash=h,
    )


def test_ingest_commits_idempotent_and_rollup(db_session):
    ing = _ingest()
    assert ing["commit_count"] == 3 and ing["user_count"] == 2 and ing["file_count"] == 2

    assert db_session.execute(text("SELECT COUNT(*) FROM gh_commits")).scalar_one() == 3
    assert db_session.execute(text("SELECT COUNT(*) FROM gh_commit_files")).scalar_one() == 4
    assert db_session.execute(text("SELECT COUNT(*) FROM gh_files")).scalar_one() == 2

    _ingest(h="h2")  # 再取り込み(同 sha)
    db_session.rollback()
    assert db_session.execute(text("SELECT COUNT(*) FROM gh_commits")).scalar_one() == 3
    assert db_session.execute(text("SELECT COUNT(*) FROM gh_commit_files")).scalar_one() == 4
    cc = db_session.execute(
        text("SELECT change_count FROM gh_files WHERE path = 'app/auth.py'")
    ).scalar_one()
    assert cc == 2

    assert cstore.get_latest_head_sha("acme/app") == "s3"
    assert cstore.latest_ingest_run_id("acme/app") is not None


def test_load_commits_roundtrip(db_session):
    _ingest()
    loaded = cstore.load_commits("acme/app")
    assert [c["sha"] for c in loaded] == ["s1", "s2", "s3"]  # committed_at 昇順
    c1 = loaded[0]
    assert c1["author_login"] == "alice"
    src = [f for f in c1["files"] if f["is_source"]]
    assert [f["path"] for f in src] == ["app/auth.py"]
    assert src[0]["hunk_headers"] == ["@@ -0,0 +1,40 @@ def login("]


def test_store_change_chunks_and_embed(db_session):
    _ingest()
    commits = cstore.load_commits("acme/app")
    chunks = ci.build_commit_chunks(commits, "acme/app") + ci.build_file_rollup_chunks(commits, "acme/app")
    out1 = cstore.store_change_chunks_and_embed(chunks)
    assert out1["chunk_count"] == 5 and out1["embedded_chunks"] == 5   # 3 commit + 2 file

    assert db_session.execute(text("SELECT COUNT(*) FROM gh_change_chunks")).scalar_one() == 5
    assert db_session.execute(
        text("SELECT COUNT(*) FROM embeddings WHERE source = 'github_change'")
    ).scalar_one() >= 5

    assert cstore.store_change_chunks_and_embed(chunks)["embedded_chunks"] == 0
    chunks[0] = dict(chunks[0], content_hash="x", text="変更後")
    assert cstore.store_change_chunks_and_embed(chunks)["embedded_chunks"] == 1


def test_get_summary(db_session):
    _ingest()
    s = cstore.get_summary("acme/app")
    assert s["commit_count"] == 3
    us = {u["author"]: u for u in s["users"]}
    assert us["alice"]["commit_count"] == 2 and us["alice"]["files_touched"] == 2
    fs = {f["path"]: f for f in s["files"]}
    assert fs["app/auth.py"]["change_count"] == 2
    assert set(fs["app/auth.py"]["authors"]) == {"alice", "bob"}


def _accounts():
    return [
        {
            "author": "alice", "author_name": "Alice", "overview": "認証まわり担当",
            "stats": {"commit_count": 2, "additions": 72, "top_files": ["app/auth.py"]},
            "sections": [{"heading": "担当", "body": "- 認証"}],
            "refs": [{"sha": "s1", "committed_at": None, "excerpt": "ログイン追加"}],
        },
        {
            "author": "bob", "author_name": "Bob", "overview": "",
            "stats": {"commit_count": 1}, "sections": [],
            "error": "このアカウントの分析に失敗しました", "refs": [],
        },
    ]


def test_save_and_get_author_analysis(db_session):
    saved = cstore.save_author_analysis(
        ingest_run_id=1, repo="acme/app", head_sha="s3", content_hash="hash-C", model="gpt-x",
        themes=["ログイン", "テスト整備"], stats={"commit_count": 3, "account_count": 2},
        accounts=_accounts(),
    )
    got = cstore.get_author_analysis(saved["id"])
    assert got["themes"] == ["ログイン", "テスト整備"]
    assert [a["username"] for a in got["accounts"]] == ["alice", "bob"]
    a0 = got["accounts"][0]
    assert a0["full_name"] == "Alice" and a0["sections"] == [{"heading": "担当", "body": "- 認証"}]
    assert a0["refs"][0]["sha"] == "s1"
    assert got["accounts"][1]["stats"]["error"] == "このアカウントの分析に失敗しました"

    assert cstore.find_cached_author_analysis("hash-C")["id"] == saved["id"]
    assert cstore.find_cached_author_analysis("nope") is None
    assert cstore.get_latest_author_analysis()["id"] == saved["id"]
    rows = cstore.list_author_analyses()
    assert rows and rows[0]["account_count"] == 2
