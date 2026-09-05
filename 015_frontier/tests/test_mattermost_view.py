"""「Mattermost 情報取得」画面用の投稿取得ロジックのテスト。"""

from __future__ import annotations

from datetime import date

import pytest
import responses

import mattermost_view as mv
from mattermost_view import MattermostViewError, fetch_posts
from settings import Settings

MM = "https://mm.internal.test"


def _settings(**over) -> Settings:
    base = dict(
        MATTERMOST_URL=MM,
        MATTERMOST_TOKEN="tok",
        APP_TZ="Asia/Tokyo",
    )
    base.update(over)
    return Settings(_env_file=None, **base)


@responses.activate
def test_fetch_posts_groups_threads_and_orders():
    s = _settings()
    tz = mv._tz(s)
    start_ms, _ = mv._day_bounds_ms(date(2026, 9, 1), tz)

    posts = {
        # ルート A(後の時刻)+ リアクション
        "r1": {
            "id": "r1", "user_id": "u1", "create_at": start_ms + 3000,
            "message": "root A", "root_id": "",
            "metadata": {"reactions": [
                {"emoji_name": "+1"}, {"emoji_name": "+1"}, {"emoji_name": "tada"},
            ]},
        },
        # A への返信
        "p2": {"id": "p2", "user_id": "u2", "create_at": start_ms + 5000,
               "message": "reply to A", "root_id": "r1"},
        # ルート B(早い時刻)
        "r3": {"id": "r3", "user_id": "u1", "create_at": start_ms + 1000,
               "message": "root B", "root_id": ""},
        # ルートが期間外の返信
        "p4": {"id": "p4", "user_id": "u2", "create_at": start_ms + 7000,
               "message": "orphan reply", "root_id": "rX"},
        "rX": {"id": "rX", "user_id": "u1", "create_at": start_ms - 100000,
               "message": "old root msg", "root_id": ""},
        # システムメッセージ・削除済みは除外される
        "s1": {"id": "s1", "user_id": "u1", "create_at": start_ms + 1500,
               "message": "joined", "type": "system_join_channel", "root_id": ""},
        "d1": {"id": "d1", "user_id": "u1", "create_at": start_ms + 1600,
               "message": "gone", "delete_at": 123, "root_id": ""},
    }
    responses.add(responses.GET, f"{MM}/api/v4/channels/ch1", json={"display_name": "業務連絡"})
    responses.add(
        responses.GET, f"{MM}/api/v4/channels/ch1/posts",
        json={"order": ["r1", "p2", "r3", "p4"], "posts": posts},
    )
    responses.add(
        responses.POST, f"{MM}/api/v4/users/ids",
        json=[{"id": "u1", "username": "alice"}, {"id": "u2", "username": "bob"}],
    )

    out = fetch_posts(s, ["ch1"], date(2026, 9, 1), date(2026, 9, 2))

    assert out["channel_count"] == 1
    ch = out["channels"][0]
    assert ch["channel_name"] == "業務連絡"
    # since パラメータは期間開始日の 0:00(アプリTZ)
    from urllib.parse import parse_qs, urlparse

    q = parse_qs(urlparse(responses.calls[1].request.url).query)
    assert q["since"] == [str(start_ms)]
    # 時系列: r3(早) → r1(遅, 返信 p2 を内包) → 孤立返信 p4
    assert [p["id"] for p in ch["posts"]] == ["r3", "r1", "p4"]
    r1 = ch["posts"][1]
    assert r1["user"] == "alice"
    assert [rp["id"] for rp in r1["replies"]] == ["p2"]
    assert r1["replies"][0]["user"] == "bob"
    assert {x["emoji"]: x["count"] for x in r1["reactions"]} == {"+1": 2, "tada": 1}
    # ルート期間外の返信は excerpt を持ち、単独で時系列に並ぶ
    assert ch["posts"][2]["root_excerpt"] == "old root msg"
    # system / deleted は除外
    ids = [p["id"] for p in ch["posts"]]
    assert "s1" not in ids and "d1" not in ids
    # 件数 = ルート + 返信(r3=1, r1+p2=2, p4=1)
    assert ch["post_count"] == 4
    assert out["post_count"] == 4


@responses.activate
def test_fetch_posts_multiple_channels_kept_separate():
    s = _settings()
    tz = mv._tz(s)
    start_ms, _ = mv._day_bounds_ms(date(2026, 9, 1), tz)
    for cid, name, msg in [("ch1", "A", "hello A"), ("ch2", "B", "hello B")]:
        responses.add(responses.GET, f"{MM}/api/v4/channels/{cid}", json={"display_name": name})
        responses.add(
            responses.GET, f"{MM}/api/v4/channels/{cid}/posts",
            json={"order": ["x"], "posts": {"x": {
                "id": "x", "user_id": "u1", "create_at": start_ms + 10, "message": msg, "root_id": "",
            }}},
        )
    responses.add(responses.POST, f"{MM}/api/v4/users/ids", json=[{"id": "u1", "username": "alice"}])

    out = fetch_posts(s, ["ch1", "ch2"], date(2026, 9, 1), date(2026, 9, 1))
    names = [c["channel_name"] for c in out["channels"]]
    assert names == ["A", "B"]
    assert out["channels"][0]["posts"][0]["message"] == "hello A"
    assert out["channels"][1]["posts"][0]["message"] == "hello B"


def test_fetch_posts_validation_errors():
    with pytest.raises(MattermostViewError):
        fetch_posts(_settings(), [], date(2026, 9, 1), date(2026, 9, 2))
    with pytest.raises(MattermostViewError):
        fetch_posts(
            _settings(MATTERMOST_URL="https://mattermost.example.com"),
            ["ch1"], date(2026, 9, 1), date(2026, 9, 2),
        )
    with pytest.raises(MattermostViewError):
        fetch_posts(_settings(), ["ch1"], date(2026, 9, 3), date(2026, 9, 1))
