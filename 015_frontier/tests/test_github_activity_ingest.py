"""GitHub 情報取得の正規化(pipeline/github_activity_ingest)のテスト。"""

from __future__ import annotations

from pipeline import github_activity_ingest as gai


def _commit(sha, author, date_iso, msg):
    return {
        "sha": sha[:7], "sha_full": sha, "author": author,
        "date": "x", "date_iso": date_iso,
        "message": msg.splitlines()[0], "message_full": msg,
        "url": f"https://gh/c/{sha}",
    }


def _branch(name, commits, protected=False):
    return {
        "name": name, "protected": protected,
        "last_activity": "x",
        "last_activity_iso": commits[0]["date_iso"] if commits else None,
        "last_author": commits[0]["author"] if commits else None,
        "commit_count": len(commits), "commits": commits,
    }


def _comment(cid, author, date_iso, textv, kind="comment"):
    d = {"id": cid, "kind": kind, "author": author, "date": "x", "date_iso": date_iso, "text": textv}
    if kind == "review":
        d["review_state"] = "APPROVED"
    return d


def _pr(num, title, author, state, merged, created_iso, merged_iso=None, merged_by=None, comments=()):
    return {
        "number": num, "title": title, "state": state, "merged": merged, "author": author,
        "created": "x", "created_iso": created_iso,
        "closed": "x", "closed_iso": merged_iso if merged else None,
        "merged_at": "x", "merged_at_iso": merged_iso, "merged_by": merged_by,
        "url": f"https://gh/pr/{num}", "detail_loaded": True, "comments": list(comments),
    }


FETCH = {
    "repo": "acme/app",
    "branch_count": 2, "pr_count": 2, "pr_detail_count": 2,
    "branches": [
        _branch("main", [
            _commit("s1", "alice", "2026-08-01T10:00:00Z", "初期化"),
            _commit("s2", "bob", "2026-08-02T11:00:00Z", "修正"),
        ], protected=True),
        _branch("feature/x", [_commit("s2", "bob", "2026-08-02T11:00:00Z", "修正")]),  # s2 は重複
    ],
    "pull_requests": [
        _pr(1, "ログイン追加", "alice", "closed", True, "2026-08-03T09:00:00Z",
            merged_iso="2026-08-04T09:00:00Z", merged_by="bob",
            comments=[
                _comment(101, "bob", "2026-08-03T12:00:00Z", "[承認] LGTM", "review"),
                _comment(102, "carol", "2026-08-03T13:00:00Z", "typo あり"),
            ]),
        _pr(2, "作業中PR", "carol", "open", False, "2026-08-05T09:00:00Z"),
    ],
}


def test_flatten_activity():
    flat = gai.flatten_activity(FETCH)
    assert len(flat["branches"]) == 2 and len(flat["pull_requests"]) == 2

    ids = {a["event_id"]: a for a in flat["activities"]}
    assert set(ids) == {
        "commit:s1", "commit:s2", "pr_opened:1", "pr_merged:1",
        "pr_review:101", "pr_comment:102", "pr_opened:2",
    }
    assert ids["commit:s2"]["branch"] == "main"          # 先に見た main が残る(重複は無視)
    assert ids["pr_merged:1"]["actor"] == "bob" and ids["pr_merged:1"]["kind"] == "pr_merged"
    assert ids["pr_review:101"]["kind"] == "pr_review" and ids["pr_review:101"]["actor"] == "bob"
    assert ids["pr_comment:102"]["actor"] == "carol"
    assert ids["pr_comment:102"]["body"] == "typo あり"
    # occurred_at 昇順
    times = [a["occurred_at"] for a in flat["activities"] if a["occurred_at"]]
    assert times == sorted(times)

    pr1 = next(p for p in flat["pull_requests"] if p["number"] == 1)
    assert pr1["merged"] is True and pr1["merged_by"] == "bob" and pr1["comment_count"] == 2


def test_content_hash_stable_and_sensitive():
    flat = gai.flatten_activity(FETCH)
    h1 = gai.compute_content_hash(flat)
    assert h1 == gai.compute_content_hash(gai.flatten_activity(FETCH))
    changed = gai.flatten_activity(FETCH)
    changed["activities"][0]["body"] = "書き換え"
    assert gai.compute_content_hash(changed) != h1
    assert len(h1) == 64


def test_build_pr_chunks():
    flat = gai.flatten_activity(FETCH)
    chunks = {c["chunk_id"]: c for c in gai.build_pr_chunks(flat["pull_requests"], flat["activities"], "acme/app")}
    assert set(chunks) == {"ghpr:acme/app:1", "ghpr:acme/app:2"}
    c1 = chunks["ghpr:acme/app:1"]
    assert c1["kind"] == "pr" and "PR #1: ログイン追加" in c1["text"]
    assert "作成: alice" in c1["text"] and "マージ実行: bob" in c1["text"]
    assert "bob レビュー:" in c1["text"] and "carol コメント:" in c1["text"]
    assert set(c1["participants"]) == {"alice", "bob", "carol"}


def test_build_branch_chunks():
    flat = gai.flatten_activity(FETCH)
    chunks = {c["chunk_id"]: c for c in gai.build_branch_chunks(flat["branches"], FETCH, "acme/app")}
    assert len(chunks) == 2
    main = next(c for c in chunks.values() if c["branch"] == "main")
    assert "ブランチ: main(保護)" in main["text"] and "alice: 初期化" in main["text"]
    assert set(main["participants"]) == {"alice", "bob"}


def test_build_actor_tally():
    flat = gai.flatten_activity(FETCH)
    t = {x["actor"]: x for x in gai.build_actor_tally(flat["activities"])}
    assert t["bob"]["commit"] == 1 and t["bob"]["pr_merged"] == 1 and t["bob"]["pr_review"] == 1
    assert t["bob"]["total"] == 3
    assert t["alice"]["pr_opened"] == 1 and t["alice"]["commit"] == 1
    assert t["carol"]["pr_comment"] == 1 and t["carol"]["pr_opened"] == 1
