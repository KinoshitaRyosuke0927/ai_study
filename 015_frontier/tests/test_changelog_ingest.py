"""変更履歴取得の決定的な前処理(pipeline/changelog_ingest)のテスト。"""

from __future__ import annotations

from pipeline import changelog_ingest as ci


def _commit(sha, login, name, dt, msg, files):
    recs = [
        {
            "path": p, "previous_path": None, "status": st, "additions": a, "deletions": d,
            "hunk_headers": h, "patch_excerpt": None, "binary": False, "truncated": False,
            "is_source": src,
        }
        for (p, st, a, d, h, src) in files
    ]
    return {
        "sha": sha, "author_login": login, "author_name": name, "author_email": f"{login}@x",
        "committed_at": dt, "message": msg, "is_merge": False,
        "additions": sum(r["additions"] for r in recs),
        "deletions": sum(r["deletions"] for r in recs),
        "files_changed": len(recs), "files": recs,
    }


C1 = _commit("s1", "alice", "Alice", "2026-08-01T10:00:00Z", "ログイン追加\n詳細をここに書く", [
    ("app/auth.py", "added", 40, 0, ["@@ -0,0 +1,40 @@ def login("], True),
    ("README.md", "modified", 2, 1, [], False),
])
C2 = _commit("s2", "bob", "Bob", "2026-08-02T09:00:00Z", "auth のバグ修正", [
    ("app/auth.py", "modified", 5, 3, ["@@ -10,7 +10,9 @@ def login("], True),
])
C3 = _commit("s3", "alice", "Alice", "2026-08-03T12:00:00Z", "テスト追加", [
    ("tests/test_auth.py", "added", 30, 0, ["@@ -0,0 +1,30 @@ def test_login("], True),
])
COMMITS = [C1, C2, C3]


def test_content_hash_stable_and_sensitive():
    h1 = ci.compute_content_hash("acme/app", "main", "s3", "2026-08-01")
    assert h1 == ci.compute_content_hash("acme/app", "main", "s3", "2026-08-01")
    assert h1 != ci.compute_content_hash("acme/app", "main", "s4", "2026-08-01")
    assert len(h1) == 64


def test_build_commit_chunks():
    chunks = {c["chunk_id"]: c for c in ci.build_commit_chunks(COMMITS, "acme/app")}
    assert set(chunks) == {"ghchange:s1", "ghchange:s2", "ghchange:s3"}
    c1 = chunks["ghchange:s1"]
    assert c1["kind"] == "commit" and c1["participants"] == ["alice"]
    assert "ログイン追加" in c1["text"] and "変更ファイル:" in c1["text"]
    assert "app/auth.py (+40/-0)" in c1["text"]
    assert "@@ -0,0 +1,40 @@ def login(" in c1["text"]


def test_build_file_rollup_chunks_excludes_non_source():
    chunks = {c["chunk_id"]: c for c in ci.build_file_rollup_chunks(COMMITS, "acme/app")}
    texts = {c["path"]: c["text"] for c in chunks.values()}
    assert set(texts) == {"app/auth.py", "tests/test_auth.py"}   # README.md は対象外
    assert "変更回数 2" in texts["app/auth.py"]
    assert "変更者: alice, bob" in texts["app/auth.py"]


def test_build_user_summary():
    us = {u["author"]: u for u in ci.build_user_summary(COMMITS)}
    assert us["alice"]["commit_count"] == 2
    assert us["alice"]["additions"] == 42 + 30 and us["alice"]["deletions"] == 1
    assert us["alice"]["files_touched"] == 2
    assert us["bob"]["commit_count"] == 1 and us["bob"]["files_touched"] == 1


def test_build_file_summary():
    fs = ci.build_file_summary(COMMITS)
    assert fs[0]["path"] == "app/auth.py" and fs[0]["change_count"] == 2
    assert {f["path"] for f in fs} == {"app/auth.py", "tests/test_auth.py"}


def test_build_author_contexts():
    ctxs = {c["author"]: c for c in ci.build_author_contexts(COMMITS)}
    assert set(ctxs) == {"alice", "bob"}
    assert "ログイン追加" in ctxs["alice"]["context"]
    assert "app/auth.py" in ctxs["alice"]["stats"]["top_files"]
    assert ctxs["alice"]["stats"]["commit_count"] == 2
    assert [r["sha"] for r in ctxs["alice"]["refs"]] and ctxs["alice"]["refs"][0]["sha"] in ("s1", "s3")
