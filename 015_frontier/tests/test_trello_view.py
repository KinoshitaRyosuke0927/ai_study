"""「Trello 情報取得」画面用のボード取得ロジックのテスト。"""

from __future__ import annotations

import pytest
import responses

from config.settings import Settings
from viewers.trello import TrelloViewError, fetch_board, list_configured_boards

API = "https://api.trello.com/1"


def _settings(**over) -> Settings:
    base = dict(TRELLO_API_KEY="k", TRELLO_TOKEN="t", APP_TZ="Asia/Tokyo")
    base.update(over)
    return Settings(_env_file=None, **base)


_SNAPSHOT = {
    "id": "b1", "name": "のみどき", "url": "https://trello.com/b/b1",
    "organization": {"displayName": "AIビジネス研究室", "name": "aislab"},
    "lists": [
        {"id": "l2", "name": "Doing", "pos": 200},
        {"id": "l1", "name": "Backlog", "pos": 100},
    ],
    "cards": [
        {
            "id": "c1", "name": "実装", "idList": "l1", "pos": 50, "desc": "説明文",
            "due": "2026-09-10T03:00:00.000Z", "dueComplete": False,
            "labels": [{"name": "bug", "color": "red"}], "cover": {"color": "green"},
            "closed": False, "isTemplate": False,
            "members": [{"fullName": "Kino Ryo", "username": "rkino"}],
        },
        {"id": "c2", "name": "テンプレ", "idList": "l1", "pos": 10, "closed": False,
         "isTemplate": True, "labels": [], "members": []},
        {"id": "c3", "name": "完了済", "idList": "l2", "pos": 20, "closed": True,
         "isTemplate": False, "labels": [], "members": []},
        {"id": "c4", "name": "レビュー", "idList": "l2", "pos": 5, "closed": False,
         "isTemplate": False, "labels": [], "members": [], "cover": {"idAttachment": "a1"}},
    ],
    "checklists": [
        {"id": "cl1", "name": "TODO", "idCard": "c1", "checkItems": [
            {"name": "設計", "state": "complete"},
            {"name": "実装", "state": "incomplete"},
        ]},
    ],
    "labels": [],
}

_ACTIONS = [  # Trello は新しい順で返す
    {"id": "a3", "type": "updateCheckItemStateOnCard", "date": "2026-09-02T01:00:00.000Z",
     "memberCreator": {"username": "rkino", "fullName": "Kino Ryo"},
     "data": {"card": {"id": "c1"}, "checkItem": {"name": "設計", "state": "complete"}}},
    {"id": "a2", "type": "commentCard", "date": "2026-09-01T05:00:00.000Z",
     "memberCreator": {"username": "unno", "fullName": "M Unno"},
     "data": {"card": {"id": "c1"}, "text": "確認しました"}},
    {"id": "a1", "type": "createCard", "date": "2026-08-30T00:00:00.000Z",
     "memberCreator": {"username": "rkino", "fullName": "Kino Ryo"},
     "data": {"card": {"id": "c1"}, "list": {"name": "Backlog"}}},
]


@responses.activate
def test_fetch_board_structure():
    responses.add(responses.GET, f"{API}/boards/b1", json=_SNAPSHOT)
    responses.add(responses.GET, f"{API}/boards/b1/actions", json=_ACTIONS)

    out = fetch_board(_settings(), "b1")

    assert out["board_name"] == "AIビジネス研究室/のみどき"  # ワークスペース名/ボード名
    assert out["card_count"] == 2  # テンプレ / アーカイブは除外
    # リストは pos 昇順(Backlog → Doing)
    assert [l["name"] for l in out["lists"]] == ["Backlog", "Doing"]

    backlog, doing = out["lists"]
    assert [c["name"] for c in backlog["cards"]] == ["実装"]
    assert [c["name"] for c in doing["cards"]] == ["レビュー"]

    c1 = backlog["cards"][0]
    assert c1["members"] == ["Kino Ryo (@rkino)"]
    assert c1["due"] == "2026-09-10 12:00"          # 03:00Z + 9h(JST)
    assert c1["labels"] == [{"name": "bug", "color": "red"}]
    assert c1["cover"] == "green"  # 色カバーは色名
    assert c1["desc"] == "説明文"
    assert c1["checklists"] == [
        {"name": "TODO", "items": [
            {"name": "設計", "checked": True},
            {"name": "実装", "checked": False},
        ], "done": 1, "total": 2},
    ]
    # 画像カバーは表示対象外(None)
    assert doing["cards"][0]["cover"] is None

    # 活動は古い順で、コメント / アクティビティを区別
    acts = c1["activity"]
    assert [a["kind"] for a in acts] == ["activity", "comment", "activity"]
    assert acts[0]["summary"] == "リスト「Backlog」にカードを作成"
    assert acts[0]["date"] == "2026-08-30 09:00"
    assert acts[1]["text"] == "確認しました"
    assert acts[1]["user"] == "M Unno (@unno)"
    assert acts[2]["summary"] == "チェック項目「設計」を完了"


@responses.activate
def test_fetch_board_survives_actions_failure(monkeypatch):
    import collectors.base as base

    monkeypatch.setattr(base.time, "sleep", lambda _s: None)  # リトライ待ちを飛ばす
    responses.add(responses.GET, f"{API}/boards/b1", json=_SNAPSHOT)
    responses.add(responses.GET, f"{API}/boards/b1/actions", status=500)

    out = fetch_board(_settings(), "b1")  # アクション取得失敗でも本体は返す
    assert out["card_count"] == 2
    assert out["lists"][0]["cards"][0]["activity"] == []


def test_fetch_board_validation():
    with pytest.raises(TrelloViewError):
        fetch_board(_settings(TRELLO_TOKEN="changeme"), "b1")
    with pytest.raises(TrelloViewError):
        fetch_board(_settings(), "")


@responses.activate
def test_list_configured_boards_resolves_names():
    responses.add(
        responses.GET, f"{API}/members/me/boards",
        json=[
            {"id": "b1", "name": "のみどき", "organization": {"displayName": "AIビジネス研究室"}},
            {"id": "b9", "name": "別", "organization": {"displayName": "他"}},
        ],
    )
    boards, err = list_configured_boards(_settings(), ["b1"])
    assert err is None
    assert boards == [{"id": "b1", "name": "AIビジネス研究室/のみどき"}]


def test_list_configured_boards_empty():
    boards, err = list_configured_boards(_settings(), [])
    assert boards == []
    assert err
