"""指標計算のユニットテスト。"""

from __future__ import annotations

from datetime import timedelta

from collectors.base import Event
from pipeline.metrics import compute_metrics
from pipeline.store import save_events, snapshot_week_items
from common.weeks import week_start

WEEK = "2026-W20"


def _mk(etype, ref, payload, day=1, hour=10, actor="sato"):
    """当該週内(週初 + day 日 + hour 時)の Event を作る。"""
    ts = week_start(WEEK) + timedelta(days=day, hours=hour)
    return Event("sample", etype, actor, ts, ref, payload)


def test_compute_metrics_counts(db_session):
    events = [
        _mk("post", "p1", {"text": "a"}, actor="sato"),
        _mk("post", "p2", {"text": "b"}, actor="suzuki"),
        _mk("post", "p3", {"text": "c"}, actor="sato"),
        _mk("commit", "s1", {"message": "x"}, actor="sato"),
        _mk("commit", "s2", {"message": "y"}, actor="sato"),
        _mk("commit", "s3", {"message": "z"}, actor="suzuki"),
        _mk("card_created", "act1", {"card_key": "trello:card:1", "title": "A"}),
        _mk("card_created", "act2", {"card_key": "trello:card:2", "title": "B"}),
        _mk("card_moved", "act3", {"card_key": "trello:card:1", "title": "A", "list_after": "Done"}, day=3),
        _mk("card_moved", "act4", {"card_key": "trello:card:2", "title": "B", "list_after": "Doing"}, day=3),
        _mk("pr_opened", "pr-1", {"item_key": "github:pr:1", "title": "PR1"}, day=0),
        _mk("pr_merged", "pr-1", {"item_key": "github:pr:1", "title": "PR1"}, day=4),
        _mk("pr_opened", "pr-2", {"item_key": "github:pr:2", "title": "PR2"}, day=0),
        _mk("issue_reopened", "issue-3-re", {"item_key": "github:issue:3", "title": "bug"}, day=2),
        _mk("page_created", "growi:page:1-r1", {"page_key": "growi:page:1", "title": "P", "path": "/p"}),
        _mk("page_updated", "growi:page:1-r2", {"page_key": "growi:page:1", "title": "P", "path": "/p"}, day=3),
    ]
    save_events(db_session, events)
    db_session.commit()
    snapshot_week_items(db_session, WEEK)
    db_session.commit()

    m = compute_metrics(db_session, WEEK)

    assert m["mattermost_posts"] == 3
    assert m["mattermost_active_users"] == 2
    assert m["trello_cards_created"] == 2
    assert m["trello_cards_done"] == 1          # Done へ移動したのは 1 件
    assert m["trello_wip"] == 1                 # card:2 が Doing に残る
    assert m["github_commits"] == 3
    assert m["github_prs_merged"] == 1
    assert m["github_prs_opened"] == 2
    assert m["github_stale_prs"] == 1           # pr:2 は open のまま(週初オープン → 週末は 3 日超)
    assert m["github_issues_reopened"] == 1
    assert m["growi_pages_created"] == 1
    assert m["growi_pages_updated"] == 1


def test_metrics_saved_and_reloaded(db_session):
    from pipeline.metrics import load_metrics_trend, save_metrics

    save_metrics(db_session, WEEK, {"mattermost_posts": 5.0, "github_commits": 9.0})
    db_session.commit()
    trend = load_metrics_trend(db_session, [WEEK])
    assert trend[WEEK]["mattermost_posts"] == 5.0
    assert trend[WEEK]["github_commits"] == 9.0
