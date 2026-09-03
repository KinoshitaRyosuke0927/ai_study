"""week_items の差分計算(added / changed / removed)のユニットテスト。"""

from __future__ import annotations

from sqlalchemy import text

from store import compute_diff, diff_digest


def _put_week_item(session, week, item_key, status, title):
    """week_items へ 1 行挿入するヘルパ。"""
    session.execute(
        text(
            "INSERT INTO week_items (week, item_key, status, title) "
            "VALUES (:w, :k, :s, :t)"
        ),
        {"w": week, "k": item_key, "s": status, "t": title},
    )


def test_compute_diff_added_changed_removed(db_session):
    prev, cur = "2026-W10", "2026-W11"

    # 前週
    _put_week_item(db_session, prev, "trello:card:1", "open", "カードA")
    _put_week_item(db_session, prev, "trello:card:2", "open", "カードB")
    _put_week_item(db_session, prev, "github:pr:9", "open", "PR9")
    # 今週: card:1 は状態変化 / card:2 は消滅 / card:3 は新規 / pr:9 は変化なし
    _put_week_item(db_session, cur, "trello:card:1", "done", "カードA")
    _put_week_item(db_session, cur, "trello:card:3", "open", "カードC")
    _put_week_item(db_session, cur, "github:pr:9", "open", "PR9")
    db_session.commit()

    diff = compute_diff(db_session, cur)

    added_keys = {r["item_key"] for r in diff["added"]}
    changed_keys = {r["item_key"] for r in diff["changed"]}
    removed_keys = {r["item_key"] for r in diff["removed"]}

    assert added_keys == {"trello:card:3"}
    assert changed_keys == {"trello:card:1"}
    assert removed_keys == {"trello:card:2"}

    changed_row = diff["changed"][0]
    assert changed_row["prev_status"] == "open"
    assert changed_row["status"] == "done"
    assert changed_row["source"] == "trello"
    assert changed_row["type"] == "card"


def test_diff_digest_groups_by_type(db_session):
    prev, cur = "2026-W10", "2026-W11"
    _put_week_item(db_session, cur, "trello:card:3", "open", "カードC")
    _put_week_item(db_session, cur, "trello:card:4", "open", "カードD")
    _put_week_item(db_session, cur, "github:pr:1", "open", "PR1")
    db_session.commit()

    digest = diff_digest(compute_diff(db_session, cur))
    assert digest["added"]["trello:card"]["count"] == 2
    assert digest["added"]["github:pr"]["count"] == 1
    assert len(digest["added"]["trello:card"]["samples"]) == 2
