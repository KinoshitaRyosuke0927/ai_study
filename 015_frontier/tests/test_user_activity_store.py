"""アクティビティ分析の DB 入出力(pipeline/user_activity_store)のテスト。"""

from __future__ import annotations

from pipeline import user_activity_store as uastore


def _items():
    return [
        {
            "is_member": True, "display_name": "海野 亮", "personal": "PO",
            "accounts": {"mattermost": "m-unno", "trello": "munno3", "github": "JBD-Makoto-Unno"},
            "sources": ["Mattermost:m-unno", "Trello:munno3", "GitHub:JBD-Makoto-Unno"],
            "overview": "PO として評価とレビュー",
            "sections": [{"heading": "役割", "body": "- 仕様確認"}],
        },
        {
            "is_member": False, "display_name": "copilot[bot]", "personal": "(未登録)",
            "accounts": {"github": "copilot[bot]"}, "sources": ["GitHub:copilot[bot]"],
            "overview": "自動レビュー", "sections": [],
        },
    ]


def test_save_and_get(db_session):
    saved = uastore.save_analysis(
        content_hash="hash-UA", model="gpt-x",
        source_ids={"mattermost": 1, "trello": 2, "changelog": 3, "github_content_hash": "abc"},
        stats={"member_count": 1, "other_count": 1, "available_sources": ["mattermost", "trello"]},
        items=_items(),
    )
    got = uastore.get_analysis(saved["id"])
    assert got["source_ids"]["mattermost"] == 1 and got["source_ids"]["github_content_hash"] == "abc"
    assert got["stats"]["member_count"] == 1

    members = [it for it in got["items"] if it["is_member"]]
    others = [it for it in got["items"] if not it["is_member"]]
    assert len(members) == 1 and len(others) == 1
    assert members[0]["display_name"] == "海野 亮"
    assert members[0]["accounts"]["github"] == "JBD-Makoto-Unno"
    assert members[0]["sources"] == ["Mattermost:m-unno", "Trello:munno3", "GitHub:JBD-Makoto-Unno"]
    assert members[0]["sections"] == [{"heading": "役割", "body": "- 仕様確認"}]
    assert others[0]["display_name"] == "copilot[bot]"


def test_cache_latest_list(db_session):
    uastore.save_analysis(content_hash="h", model="m", source_ids={}, stats={}, items=_items())
    second = uastore.save_analysis(content_hash="h", model="m", source_ids={}, stats={}, items=_items()[:1])

    assert uastore.find_cached_analysis("h")["id"] == second["id"]
    assert uastore.find_cached_analysis("nope") is None
    assert uastore.get_latest_analysis()["id"] == second["id"]

    rows = uastore.list_analyses()
    assert len(rows) == 2 and rows[0]["id"] == second["id"]
    assert rows[0]["item_count"] == 1 and rows[1]["item_count"] == 2
