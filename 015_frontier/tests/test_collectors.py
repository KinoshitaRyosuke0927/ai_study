"""4 コレクタの HTTP モックテスト。

各コレクタについて
  (1) 正しいエンドポイント・パラメータで呼ぶこと
  (2) JSON レスポンスが Event へ正しく正規化されること
  (3) ページングが機能すること
を検証する。
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import responses

from collectors.base import HttpClient
from settings import Settings

SINCE = datetime(2026, 8, 1, 0, 0, 0)
SINCE_MS = int(SINCE.replace(tzinfo=timezone.utc).timestamp() * 1000)


def _make_settings(**over) -> Settings:
    """.env を無視した最小 Settings。"""
    base = dict(
        MATTERMOST_URL="https://mm.example.com",
        MATTERMOST_TOKEN="tok-mm",
        MATTERMOST_CHANNEL_ID="chan1",
        GITHUB_TOKEN="tok-gh",
        GITHUB_REPOS="acme/app",
        GROWI_URL="https://growi.example.com",
        GROWI_API_TOKEN="tok-growi",
        GROWI_TARGET_PATHS="/projects/foo",
        TRELLO_API_KEY="k",
        TRELLO_TOKEN="t",
        TRELLO_BOARD_ID="board1",
    )
    base.update(over)
    return Settings(_env_file=None, **base)


# ----------------------------------------------------------------------
# Mattermost
# ----------------------------------------------------------------------
@responses.activate
def test_mattermost_collector(monkeypatch):
    import collectors.mattermost as mm

    monkeypatch.setattr(mm, "PER_PAGE", 2)  # ページング検証のため小さくする

    url = "https://mm.example.com/api/v4/channels/chan1/posts"
    responses.add(
        responses.GET, url,
        json={"order": ["p1", "p2"], "posts": {
            "p1": {"id": "p1", "user_id": "u1", "message": "こんにちは😀", "create_at": SINCE_MS + 3_600_000, "channel_id": "chan1", "root_id": ""},
            "p2": {"id": "p2", "user_id": "u2", "message": "レビューします", "create_at": SINCE_MS + 7_200_000, "channel_id": "chan1", "root_id": "p1"},
        }},
    )
    responses.add(
        responses.GET, url,
        json={"order": ["p3"], "posts": {
            "p3": {"id": "p3", "user_id": "u1", "message": "完了", "create_at": SINCE_MS + 10_800_000, "channel_id": "chan1", "root_id": ""},
        }},
    )

    col = mm.MattermostCollector(_make_settings())
    events = col.fetch_since(SINCE)

    # (1) エンドポイント・パラメータ
    first = responses.calls[0].request
    assert first.url.startswith(url)
    q = parse_qs(urlparse(first.url).query)
    assert q["since"] == [str(SINCE_MS)]
    assert q["per_page"] == ["2"]
    assert q["page"] == ["0"]
    assert responses.calls[0].request.headers["Authorization"] == "Bearer tok-mm"
    # (3) ページング: 2 ページ取得
    assert len(responses.calls) == 2
    assert parse_qs(urlparse(responses.calls[1].request.url).query)["page"] == ["1"]
    # (2) 正規化
    assert [e.ref for e in events] == ["p1", "p2", "p3"]
    assert all(e.source == "mattermost" and e.type == "post" for e in events)
    assert events[0].payload["text"] == "こんにちは😀"
    assert events[1].payload["thread_root"] == "p1"
    assert events[0].ts < events[2].ts  # 時系列


# ----------------------------------------------------------------------
# GitHub
# ----------------------------------------------------------------------
@responses.activate
def test_github_collector():
    root = "https://api.github.com/repos/acme/app"

    # commits: 2 ページ(Link ヘッダで next)
    responses.add(
        responses.GET, f"{root}/commits",
        json=[{"sha": "abc", "html_url": "u", "author": {"login": "sato"},
               "commit": {"message": "初期化", "author": {"date": "2026-08-10T09:00:00Z"}}}],
        headers={"Link": f'<{root}/commits?page=2>; rel="next"'},
    )
    responses.add(
        responses.GET, f"{root}/commits",
        json=[{"sha": "def", "html_url": "u", "author": {"login": "suzuki"},
               "commit": {"message": "修正", "author": {"date": "2026-08-11T09:00:00Z"}}}],
    )
    # pulls
    responses.add(
        responses.GET, f"{root}/pulls",
        json=[{"number": 7, "title": "PR7", "html_url": "u7", "assignee": {"login": "sato"},
               "labels": [], "created_at": "2026-08-12T00:00:00Z", "merged_at": "2026-08-14T00:00:00Z",
               "updated_at": "2026-08-14T00:00:00Z", "state": "closed"}],
    )
    # issues
    responses.add(
        responses.GET, f"{root}/issues",
        json=[{"number": 3, "title": "バグ", "html_url": "u3", "assignee": None, "labels": [{"name": "bug"}],
               "created_at": "2026-08-13T00:00:00Z", "closed_at": None, "updated_at": "2026-08-13T00:00:00Z",
               "state": "open", "state_reason": None}],
    )

    from collectors.github import GitHubCollector

    col = GitHubCollector(_make_settings())
    events = col.fetch_since(SINCE)

    # (1) 認証ヘッダ + since パラメータ(ISO8601)
    assert responses.calls[0].request.headers["Authorization"] == "Bearer tok-gh"
    q = parse_qs(urlparse(responses.calls[0].request.url).query)
    assert q["since"][0].startswith("2026-08-01T00:00:00")
    # (3) ページング: commits が 2 ページ
    commit_calls = [c for c in responses.calls if "/commits" in c.request.url]
    assert len(commit_calls) == 2
    # (2) 正規化
    types = sorted({e.type for e in events})
    assert "commit" in types and "pr_opened" in types and "pr_merged" in types and "issue_opened" in types
    pr_merged = [e for e in events if e.type == "pr_merged"][0]
    assert pr_merged.payload["item_key"] == "github:pr:7"


# ----------------------------------------------------------------------
# GROWI
# ----------------------------------------------------------------------
@responses.activate
def test_growi_collector(monkeypatch):
    import collectors.growi as growi

    monkeypatch.setattr(growi, "LIMIT", 2)

    url = "https://growi.example.com/_api/v3/pages/list"
    responses.add(
        responses.GET, url,
        json={"pages": [
            {"_id": "pg1", "path": "/projects/foo/設計", "createdAt": "2026-08-05T00:00:00Z",
             "updatedAt": "2026-08-05T00:00:00Z", "revision": {"_id": "r1"}, "lastUpdateUser": {"username": "sato"}},
            {"_id": "pg2", "path": "/projects/foo/手順", "createdAt": "2026-07-01T00:00:00Z",
             "updatedAt": "2026-08-09T00:00:00Z", "revision": {"_id": "r5"}, "lastUpdateUser": {"username": "suzuki"}},
        ]},
    )
    responses.add(
        responses.GET, url,
        json={"pages": [
            {"_id": "pg3", "path": "/projects/foo/古い", "createdAt": "2026-01-01T00:00:00Z",
             "updatedAt": "2026-01-02T00:00:00Z", "revision": {"_id": "r2"}, "lastUpdateUser": {"username": "tanaka"}},
        ]},
    )

    from collectors.growi import GrowiCollector

    col = GrowiCollector(_make_settings())
    events = col.fetch_since(SINCE)

    # (1) access_token / path / limit / offset
    q0 = parse_qs(urlparse(responses.calls[0].request.url).query)
    assert q0["access_token"] == ["tok-growi"]
    assert q0["path"] == ["/projects/foo"]
    assert q0["limit"] == ["2"]
    assert q0["offset"] == ["0"]
    # (3) ページング: offset=2 で 2 回目
    assert parse_qs(urlparse(responses.calls[1].request.url).query)["offset"] == ["2"]
    # (2) 正規化: since 以降のみ、作成/更新の判定
    refs = {e.payload["page_key"]: e.type for e in events}
    assert refs["growi:page:pg1"] == "page_created"   # createdAt >= since
    assert refs["growi:page:pg2"] == "page_updated"   # createdAt < since, updatedAt >= since
    assert "growi:page:pg3" not in refs               # updatedAt < since は除外


# ----------------------------------------------------------------------
# Trello
# ----------------------------------------------------------------------
@responses.activate
def test_trello_collector(monkeypatch):
    import collectors.trello as trello

    monkeypatch.setattr(trello, "ACTION_LIMIT", 2)

    url = "https://api.trello.com/1/boards/board1/actions"
    responses.add(
        responses.GET, url,
        json=[
            {"id": "a1", "type": "createCard", "date": "2026-08-05T10:00:00.000Z",
             "memberCreator": {"username": "sato"},
             "data": {"card": {"id": "c1", "name": "ログイン改修"}, "list": {"name": "Backlog"}}},
            {"id": "a2", "type": "updateCard", "date": "2026-08-06T10:00:00.000Z",
             "memberCreator": {"username": "suzuki"},
             "data": {"card": {"id": "c1", "name": "ログイン改修"}, "listAfter": {"name": "Done"}, "listBefore": {"name": "Doing"}}},
        ],
    )
    responses.add(
        responses.GET, url,
        json=[
            {"id": "a3", "type": "updateCard", "date": "2026-08-07T10:00:00.000Z",
             "memberCreator": {"username": "tanaka"},
             "data": {"card": {"id": "c2", "name": "調査", "closed": True}}},
        ],
    )

    from collectors.trello import TrelloCollector

    col = TrelloCollector(_make_settings())
    events = col.fetch_since(SINCE)

    # (1) key / token / since(YYYY-MM-DD)/ limit
    q0 = parse_qs(urlparse(responses.calls[0].request.url).query)
    assert q0["key"] == ["k"] and q0["token"] == ["t"]
    assert q0["since"] == ["2026-08-01"]
    assert q0["limit"] == ["2"]
    # (3) ページング: before= 最古アクション ID
    assert parse_qs(urlparse(responses.calls[1].request.url).query)["before"] == ["a2"]
    # (2) 正規化
    by_type = {e.type for e in events}
    assert by_type == {"card_created", "card_moved", "card_archived"}
    moved = [e for e in events if e.type == "card_moved"][0]
    assert moved.payload["list_after"] == "Done"
    assert moved.payload["card_key"] == "trello:card:c1"


def test_httpclient_retries(monkeypatch):
    """HttpClient が 5xx を指数バックオフでリトライすること。"""
    import collectors.base as base

    sleeps: list[float] = []
    monkeypatch.setattr(base.time, "sleep", lambda s: sleeps.append(s))

    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, "https://x.example.com/y", status=503)
        rsps.add(responses.GET, "https://x.example.com/y", status=503)
        rsps.add(responses.GET, "https://x.example.com/y", json={"ok": True})
        client = HttpClient()
        data = client.get_json("https://x.example.com/y")

    assert data == {"ok": True}
    assert len(sleeps) == 2  # 2 回リトライして 3 回目で成功
