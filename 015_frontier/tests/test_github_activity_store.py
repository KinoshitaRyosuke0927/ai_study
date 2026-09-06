"""GitHub 情報取得の DB 入出力(pipeline/github_activity_store)のテスト。"""

from __future__ import annotations

from sqlalchemy import text

from pipeline import github_activity_ingest as gai, github_activity_store as gastore
from tests.test_github_activity_ingest import FETCH


def _flat():
    return gai.flatten_activity(FETCH)


def test_ingest_activity_idempotent(db_session):
    flat = _flat()
    h = gai.compute_content_hash(flat)
    ing = gastore.ingest_activity(repo="acme/app", flat=flat, content_hash=h)
    assert ing["branch_count"] == 2 and ing["pr_count"] == 2
    assert ing["activity_count"] == 7 and ing["actor_count"] == 3

    assert db_session.execute(text("SELECT COUNT(*) FROM gh_activity")).scalar_one() == 7
    assert db_session.execute(text("SELECT COUNT(*) FROM gh_branches")).scalar_one() == 2
    assert db_session.execute(text("SELECT COUNT(*) FROM gh_pull_requests")).scalar_one() == 2
    assert db_session.execute(text("SELECT COUNT(*) FROM gh_users")).scalar_one() == 3

    gastore.ingest_activity(repo="acme/app", flat=_flat(), content_hash=h)
    db_session.rollback()
    assert db_session.execute(text("SELECT COUNT(*) FROM gh_activity")).scalar_one() == 7
    assert gastore.latest_content_hash("acme/app") == h


def test_store_activity_chunks_and_embed(db_session):
    flat = _flat()
    gastore.ingest_activity(repo="acme/app", flat=flat, content_hash="h1")
    chunks = (
        gai.build_pr_chunks(flat["pull_requests"], flat["activities"], "acme/app")
        + gai.build_branch_chunks(flat["branches"], FETCH, "acme/app")
    )
    out1 = gastore.store_activity_chunks_and_embed(chunks)
    assert out1["chunk_count"] == 4 and out1["embedded_chunks"] == 4   # 2 PR + 2 branch

    assert db_session.execute(text("SELECT COUNT(*) FROM gh_activity_chunks")).scalar_one() == 4
    assert db_session.execute(
        text("SELECT COUNT(*) FROM embeddings WHERE source = 'github_activity'")
    ).scalar_one() >= 4

    assert gastore.store_activity_chunks_and_embed(chunks)["embedded_chunks"] == 0
    chunks[0] = dict(chunks[0], content_hash="x", text="変更後")
    assert gastore.store_activity_chunks_and_embed(chunks)["embedded_chunks"] == 1


def test_get_activity_summary(db_session):
    gastore.ingest_activity(repo="acme/app", flat=_flat(), content_hash="h1")
    s = gastore.get_activity_summary("acme/app")
    assert s["activity_total"] == 7 and s["branch_count"] == 2 and s["pr_count"] == 2

    # 直近順(新しい順)
    times = [a["occurred_at"] for a in s["activities"] if a["occurred_at"]]
    assert times == sorted(times, reverse=True)

    by_actor = {a["actor"]: a for a in s["by_actor"]}
    assert by_actor["bob"]["pr_merged"] == 1 and by_actor["bob"]["pr_review"] == 1
    assert by_actor["bob"]["total"] == 3
    # コメント本文が確認できる
    comment = next(a for a in s["activities"] if a["kind"] == "pr_comment")
    assert comment["actor"] == "carol" and "typo" in comment["body_excerpt"]
