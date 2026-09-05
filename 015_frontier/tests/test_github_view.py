"""「GitHub 情報取得」画面用のリポジトリ活動取得ロジックのテスト。"""

from __future__ import annotations

import pytest
import responses
from responses import matchers

from github_view import GitHubViewError, fetch_repo_activity
from settings import Settings

REPO = "acme/app"
BASE = f"https://api.github.com/repos/{REPO}"


def _settings(**over) -> Settings:
    base = dict(GITHUB_TOKEN="tok-gh", APP_TZ="Asia/Tokyo")
    base.update(over)
    return Settings(_env_file=None, **base)


def _commit(sha, login, date, msg):
    return {
        "sha": sha, "html_url": f"https://x/{sha}",
        "author": {"login": login},
        "commit": {"message": msg, "author": {"date": date}},
    }


@responses.activate
def test_fetch_repo_activity_full():
    responses.add(responses.GET, BASE, json={"full_name": REPO})

    # ブランチ一覧
    responses.add(
        responses.GET, f"{BASE}/branches",
        json=[
            {"name": "main", "protected": True, "commit": {"sha": "aaa"}},
            {"name": "feature/x", "protected": False, "commit": {"sha": "bbb"}},
        ],
    )
    # ブランチごとのコミット(query で振り分け)
    responses.add(
        responses.GET, f"{BASE}/commits",
        match=[matchers.query_param_matcher({"sha": "main"}, strict_match=False)],
        json=[_commit("a1b2c3d4", "sato", "2026-09-05T03:00:00Z", "fix: 修正\n\n詳細")],
    )
    responses.add(
        responses.GET, f"{BASE}/commits",
        match=[matchers.query_param_matcher({"sha": "feature/x"}, strict_match=False)],
        json=[_commit("e5f6a7b8", "suzuki", "2026-09-06T03:00:00Z", "feat: 追加")],
    )

    # PR 一覧(更新降順)
    responses.add(
        responses.GET, f"{BASE}/pulls",
        json=[
            {"number": 10, "title": "機能A", "state": "closed", "user": {"login": "sato"},
             "created_at": "2026-09-01T00:00:00Z", "merged_at": "2026-09-03T05:00:00Z",
             "closed_at": "2026-09-03T05:00:00Z", "html_url": "u10"},
            {"number": 11, "title": "機能B", "state": "open", "user": {"login": "suzuki"},
             "created_at": "2026-09-04T00:00:00Z", "merged_at": None, "closed_at": None, "html_url": "u11"},
        ],
    )
    # PR#10 詳細(マージ済み → merged_by)
    responses.add(responses.GET, f"{BASE}/pulls/10", json={"merged_by": {"login": "tanaka"}})
    responses.add(
        responses.GET, f"{BASE}/issues/10/comments",
        json=[{"user": {"login": "suzuki"}, "created_at": "2026-09-02T01:00:00Z", "body": "確認しました"}],
    )
    responses.add(
        responses.GET, f"{BASE}/pulls/10/reviews",
        json=[{"user": {"login": "tanaka"}, "state": "APPROVED", "submitted_at": "2026-09-02T09:00:00Z", "body": "LGTM"},
              {"user": {"login": "x"}, "state": "PENDING", "submitted_at": None, "body": ""}],
    )
    # PR#11(open, マージなし)
    responses.add(responses.GET, f"{BASE}/issues/11/comments", json=[])
    responses.add(responses.GET, f"{BASE}/pulls/11/reviews", json=[])

    out = fetch_repo_activity(_settings(), REPO)

    assert out["repo"] == REPO
    assert out["branch_count"] == 2
    assert out["pr_count"] == 2
    assert out["pr_detail_count"] == 2

    # ブランチは直近アクティビティ新しい順(feature/x が新しい)
    assert [b["name"] for b in out["branches"]] == ["feature/x", "main"]
    main = next(b for b in out["branches"] if b["name"] == "main")
    assert main["protected"] is True
    assert main["commits"][0]["author"] == "sato"
    assert main["commits"][0]["sha"] == "a1b2c3d"          # 先頭7桁
    assert main["commits"][0]["message"] == "fix: 修正"     # 1 行目のみ
    assert main["commits"][0]["date"] == "2026-09-05 12:00"  # JST

    pr10 = next(p for p in out["pull_requests"] if p["number"] == 10)
    assert pr10["state"] == "closed" and pr10["merged"] is True
    assert pr10["author"] == "sato"
    assert pr10["merged_by"] == "tanaka"
    assert pr10["merged_at"] == "2026-09-03 14:00"
    # コメント: 会話 + レビュー、日時昇順、レビューはラベル付き
    assert [c["kind"] for c in pr10["comments"]] == ["comment", "review"]
    assert pr10["comments"][0]["text"] == "確認しました"
    assert pr10["comments"][1]["text"] == "[承認] LGTM"

    pr11 = next(p for p in out["pull_requests"] if p["number"] == 11)
    assert pr11["state"] == "open" and pr11["merged"] is False
    assert pr11["merged_by"] is None
    assert pr11["comments"] == []


@responses.activate
def test_repo_not_accessible():
    responses.add(responses.GET, BASE, status=404, json={"message": "Not Found"})
    with pytest.raises(GitHubViewError):
        fetch_repo_activity(_settings(), REPO)


def test_validation():
    with pytest.raises(GitHubViewError):
        fetch_repo_activity(_settings(GITHUB_TOKEN=""), REPO)          # トークン無し
    with pytest.raises(GitHubViewError):
        fetch_repo_activity(_settings(), "")                          # リポジトリ未設定
    with pytest.raises(GitHubViewError):
        fetch_repo_activity(_settings(), "just-a-name")               # owner/repo 形式でない
