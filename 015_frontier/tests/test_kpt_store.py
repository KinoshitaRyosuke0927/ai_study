"""KPT分析の DB 入出力(pipeline/kpt_store)のテスト。"""

from __future__ import annotations

from pipeline import kpt_store


def _items():
    return [
        {"kind": "keep", "title": "レビュー文化", "detail": "PR レビューが活発",
         "evidence": "GitHub でレビュー多数", "sources": ["github"], "importance": 4},
        {"kind": "keep", "title": "こまめな連絡", "detail": "", "evidence": "", "sources": ["mattermost"]},
        {"kind": "problem", "title": "設計と実装の乖離", "detail": "high が 1 件",
         "evidence": "実装差分解析", "sources": ["spec_diff"], "importance": 5},
        {"kind": "try", "title": "差分の棚卸し会", "detail": "週次で実施",
         "evidence": "", "sources": ["spec_diff", "trello"]},
        {"kind": "bogus", "title": "捨てられる", "sources": []},
    ]


def test_save_and_get(db_session):
    saved = kpt_store.save_analysis(
        content_hash="hash-KPT", model="gpt-x",
        source_ids={"mattermost": 1, "trello": 2, "changelog": 3,
                    "github_content_hash": "abc", "spec_diff": 7},
        stats={"keep_count": 2, "problem_count": 1, "try_count": 1,
               "available_sources": ["mattermost", "github", "spec_diff"]},
        items=_items(),
    )
    got = kpt_store.get_analysis(saved["id"])
    assert got["source_ids"]["spec_diff"] == 7
    assert got["stats"]["keep_count"] == 2

    assert [i["title"] for i in got["keep"]] == ["レビュー文化", "こまめな連絡"]
    assert got["keep"][0]["sources"] == ["github"]
    assert got["keep"][0]["importance"] == 4 and got["keep"][1]["importance"] == 0
    assert [i["title"] for i in got["problem"]] == ["設計と実装の乖離"]
    assert got["problem"][0]["importance"] == 5
    assert got["try"][0]["sources"] == ["spec_diff", "trello"]
    # 未知の kind は保存されない
    assert all("捨てられる" != i["title"] for i in got["keep"] + got["problem"] + got["try"])


def test_replace_items_reorders_moves_and_rates(db_session):
    saved = kpt_store.save_analysis(
        content_hash="h-rep", model="m",
        source_ids={}, stats={"available_sources": ["github", "spec_diff"], "keep_count": 2},
        items=_items(),
    )
    aid = saved["id"]

    # 「こまめな連絡」を try 列の先頭へ移動し重要度 3、「差分の棚卸し会」を keep に移動
    new_items = [
        {"kind": "keep", "title": "レビュー文化", "detail": "", "evidence": "e1",
         "sources": ["github"], "importance": 2},
        {"kind": "keep", "title": "差分の棚卸し会", "detail": "", "evidence": "",
         "sources": ["spec_diff"], "importance": 0},
        {"kind": "try", "title": "こまめな連絡", "detail": "", "evidence": "",
         "sources": ["mattermost"], "importance": 3},
        {"kind": "problem", "title": "設計と実装の乖離", "detail": "", "evidence": "",
         "sources": ["spec_diff"], "importance": 5},
    ]
    got = kpt_store.replace_items(aid, new_items)

    assert [i["title"] for i in got["keep"]] == ["レビュー文化", "差分の棚卸し会"]
    assert got["keep"][0]["importance"] == 2
    assert [i["title"] for i in got["try"]] == ["こまめな連絡"]
    assert got["try"][0]["importance"] == 3
    # stats の件数は更新され、available_sources は保持される
    assert got["stats"]["keep_count"] == 2 and got["stats"]["try_count"] == 1
    assert got["stats"]["problem_count"] == 1
    assert got["stats"]["available_sources"] == ["github", "spec_diff"]
    # 総入れ替えなので古い項目は残らない
    assert len(got["keep"]) + len(got["problem"]) + len(got["try"]) == 4


def test_replace_items_unknown_id_returns_none(db_session):
    assert kpt_store.replace_items(999999, []) is None


def test_cache_latest_list(db_session):
    kpt_store.save_analysis(content_hash="h", model="m", source_ids={}, stats={}, items=_items())
    second = kpt_store.save_analysis(content_hash="h", model="m", source_ids={}, stats={},
                                    items=_items()[:1])

    assert kpt_store.find_cached_analysis("h")["id"] == second["id"]
    assert kpt_store.find_cached_analysis("nope") is None
    assert kpt_store.get_latest_analysis()["id"] == second["id"]

    rows = kpt_store.list_analyses()
    assert len(rows) == 2 and rows[0]["id"] == second["id"]
    assert rows[0]["item_count"] == 1 and rows[1]["item_count"] == 4
