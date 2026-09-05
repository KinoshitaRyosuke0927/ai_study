"""「wiki 情報取得」画面用の GROWI ページ取得ロジックのテスト。"""

from __future__ import annotations

import pytest
import responses

from growi_view import GrowiViewError, _relative_path, fetch_page, list_pages
from settings import Settings


def test_relative_path():
    base = "/a/b/400_開発"
    assert _relative_path("/a/b/400_開発/子/孫", base) == "子/孫"
    assert _relative_path("/a/b/400_開発", base) == "400_開発"        # base 自身 → 末尾セグメント
    assert _relative_path("/a/b/400_開発", base + "/") == "400_開発"  # base 末尾スラッシュ耐性
    assert _relative_path("/other/page", base) == "/other/page"     # 想定外はフルパス
    assert _relative_path("/x", "") == "/x"                          # base 空

GW = "https://growi.internal.test"


def _settings(**over) -> Settings:
    base = dict(GROWI_URL=GW, GROWI_API_TOKEN="tok", APP_TZ="Asia/Tokyo")
    base.update(over)
    return Settings(_env_file=None, **base)


# ----------------------------------------------------------------------
# list_pages
# ----------------------------------------------------------------------
@responses.activate
def test_list_pages_sorted():
    responses.add(
        responses.GET, f"{GW}/_api/v3/pages/list",
        json={"pages": [
            {"_id": "p2", "path": "/projects/foo/zeta"},
            {"_id": "p1", "path": "/projects/foo/alpha"},
        ]},
    )
    out = list_pages(_settings(), "/projects/foo")
    assert out["base_path"] == "/projects/foo"
    assert [p["path"] for p in out["pages"]] == ["/projects/foo/alpha", "/projects/foo/zeta"]
    # プルダウン表示用の name は基準パスより下の相対パス
    assert [p["name"] for p in out["pages"]] == ["alpha", "zeta"]
    assert out["page_count"] == 2
    from urllib.parse import parse_qs, urlparse

    q = parse_qs(urlparse(responses.calls[0].request.url).query)
    assert q["access_token"] == ["tok"]
    assert q["path"] == ["/projects/foo"]


def test_list_pages_validation():
    with pytest.raises(GrowiViewError):
        list_pages(_settings(), "")
    with pytest.raises(GrowiViewError):
        list_pages(_settings(GROWI_URL="https://growi.example.com"), "/x")
    with pytest.raises(GrowiViewError):
        list_pages(_settings(GROWI_API_TOKEN="changeme"), "/x")


# ----------------------------------------------------------------------
# fetch_page
# ----------------------------------------------------------------------
def _register_page(body_inline=True):
    revision = (
        {"_id": "rev9", "body": "# 見出し\n本文です"} if body_inline else "rev9"
    )
    responses.add(
        responses.GET, f"{GW}/_api/v3/page",
        json={"page": {
            "_id": "pg1", "path": "/projects/foo/design",
            "revision": revision,
            "creator": {"username": "sato", "name": "佐藤 太郎"},
            "lastUpdateUser": {"username": "suzuki", "name": "鈴木 花子"},
            "createdAt": "2026-08-01T00:00:00.000Z",
            "updatedAt": "2026-09-01T03:00:00.000Z",
        }},
    )
    responses.add(
        responses.GET, f"{GW}/_api/v3/revisions/list",
        json={"revisions": [
            {"_id": "rev9", "author": {"username": "suzuki", "name": "鈴木 花子"},
             "createdAt": "2026-09-01T03:00:00.000Z"},
            {"_id": "rev8", "author": {"username": "sato", "name": "佐藤 太郎"},
             "createdAt": "2026-08-01T00:00:00.000Z"},
        ]},
    )
    responses.add(
        responses.GET, f"{GW}/_api/v3/comments",
        json={"comments": [
            {"comment": "2つ目", "creator": {"username": "sato"}, "createdAt": "2026-09-02T01:00:00.000Z", "replyTo": "c1"},
            {"comment": "1つ目", "creator": {"username": "suzuki"}, "createdAt": "2026-09-01T09:00:00.000Z"},
        ]},
    )


@responses.activate
def test_fetch_page_full():
    _register_page(body_inline=True)
    out = fetch_page(_settings(), "pg1")

    assert out["path"] == "/projects/foo/design"
    assert out["body"] == "# 見出し\n本文です"
    assert out["creator"] == "佐藤 太郎 (@sato)"
    assert out["last_updater"] == "鈴木 花子 (@suzuki)"
    assert out["updated_at"] == "2026-09-01 12:00"  # 03:00Z + 9h(JST)

    # 更新履歴: メタデータのみ、新しい順(GROWI の返り順を維持)
    assert out["revision_count"] == 2
    assert out["revisions"][0]["author"] == "鈴木 花子 (@suzuki)"
    assert out["revisions"][0]["date"] == "2026-09-01 12:00"
    assert "body" not in out["revisions"][0]  # 過去断面は取得しない

    # コメント: createdAt 昇順、返信フラグ
    assert [c["text"] for c in out["comments"]] == ["1つ目", "2つ目"]
    assert out["comments"][0]["reply"] is False
    assert out["comments"][1]["reply"] is True
    assert out["comments"][0]["author"] == "@suzuki"


@responses.activate
def test_fetch_page_body_fallback_to_revision():
    _register_page(body_inline=False)  # page.revision が id 文字列
    responses.add(
        responses.GET, f"{GW}/_api/v3/revisions/rev9",
        json={"revision": {"_id": "rev9", "body": "フォールバック本文"}},
    )
    out = fetch_page(_settings(), "pg1")
    assert out["body"] == "フォールバック本文"


@responses.activate
def test_fetch_page_survives_history_failure(monkeypatch):
    import collectors.base as base

    monkeypatch.setattr(base.time, "sleep", lambda _s: None)  # リトライ待ちを飛ばす
    responses.add(
        responses.GET, f"{GW}/_api/v3/page",
        json={"page": {"_id": "pg1", "path": "/x", "revision": {"body": "本文"}}},
    )
    responses.add(responses.GET, f"{GW}/_api/v3/revisions/list", status=500)
    responses.add(responses.GET, f"{GW}/_api/v3/comments", status=500)
    out = fetch_page(_settings(), "pg1")
    assert out["body"] == "本文"
    assert out["revisions"] == [] and out["comments"] == []


def test_fetch_page_validation():
    with pytest.raises(GrowiViewError):
        fetch_page(_settings(), "")
