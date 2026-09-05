"""週次指標の計算。

指標はすべて Python コードで計算し、AI には数えさせない。
events / week_items テーブルから週単位で集計する。
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from pipeline.store import DONE_LIST_NAMES
from common.weeks import week_end

logger = logging.getLogger(__name__)

# 出力する指標名の一覧(順序はダッシュボード表示に用いる)
METRIC_NAMES = [
    "mattermost_posts",
    "mattermost_active_users",
    "trello_cards_created",
    "trello_cards_done",
    "trello_wip",
    "github_commits",
    "github_prs_merged",
    "github_prs_opened",
    "github_stale_prs",
    "github_issues_reopened",
    "growi_pages_created",
    "growi_pages_updated",
]

# 週内イベント件数をそのまま数える指標(指標名 -> event.type)
_EVENT_COUNT_METRICS = {
    "trello_cards_created": "card_created",
    "github_commits": "commit",
    "github_prs_merged": "pr_merged",
    "github_prs_opened": "pr_opened",
    "github_issues_reopened": "issue_reopened",
    "growi_pages_created": "page_created",
    "growi_pages_updated": "page_updated",
}


def compute_metrics(session: Session, week: str) -> dict[str, float]:
    """指定週の全指標を計算して辞書で返す。"""
    values: dict[str, float] = {name: 0.0 for name in METRIC_NAMES}

    # --- 週内イベント件数系 ---
    rows = session.execute(
        text(
            """
            SELECT type, COUNT(*) AS c
            FROM events
            WHERE week = :week
            GROUP BY type
            """
        ),
        {"week": week},
    ).all()
    count_by_type = {t: c for t, c in rows}
    for metric, etype in _EVENT_COUNT_METRICS.items():
        values[metric] = float(count_by_type.get(etype, 0))

    # --- Mattermost 投稿数 / アクティブ人数 ---
    post_row = session.execute(
        text(
            """
            SELECT COUNT(*) AS posts, COUNT(DISTINCT actor) AS users
            FROM events
            WHERE week = :week AND type = 'post'
            """
        ),
        {"week": week},
    ).one()
    values["mattermost_posts"] = float(post_row.posts or 0)
    values["mattermost_active_users"] = float(post_row.users or 0)

    # --- Trello: done 扱いリストへ移動した数 ---
    values["trello_cards_done"] = float(_count_cards_done(session, week))

    # --- Trello WIP: 週末時点で完了以外に残るカード数 ---
    wip_row = session.execute(
        text(
            """
            SELECT COUNT(*) AS c
            FROM week_items
            WHERE week = :week
              AND item_key LIKE 'trello:%'
              AND status NOT IN ('done', 'archived')
            """
        ),
        {"week": week},
    ).one()
    values["trello_wip"] = float(wip_row.c or 0)

    # --- GitHub stale PR: オープンから 3 日以上マージされていない PR 数 ---
    values["github_stale_prs"] = float(_count_stale_prs(session, week))

    return values


def _count_cards_done(session: Session, week: str) -> int:
    """当該週に done 扱いリストへ移動した card_moved イベントを数える。"""
    rows = session.execute(
        text(
            """
            SELECT payload
            FROM events
            WHERE week = :week AND type = 'card_moved'
            """
        ),
        {"week": week},
    ).all()
    done = 0
    for (payload_raw,) in rows:
        payload = payload_raw if isinstance(payload_raw, dict) else json.loads(payload_raw or "{}")
        if payload.get("list_after") in DONE_LIST_NAMES:
            done += 1
    return done


def _count_stale_prs(session: Session, week: str) -> int:
    """週末時点で open、かつ最初の pr_opened から 3 日以上経過している PR 数。"""
    boundary = week_end(week)
    threshold = boundary - timedelta(days=3)
    # 週末断面で open な PR
    open_prs = session.execute(
        text(
            """
            SELECT item_key
            FROM week_items
            WHERE week = :week
              AND item_key LIKE 'github:pr:%'
              AND status = 'open'
            """
        ),
        {"week": week},
    ).scalars().all()
    if not open_prs:
        return 0
    # 各 PR の最初の pr_opened イベント時刻を Python 側で集計する
    opened_rows = session.execute(
        text("SELECT payload, ts FROM events WHERE type = 'pr_opened'")
    ).all()
    opened_at: dict[str, Any] = {}
    for payload_raw, ts in opened_rows:
        payload = payload_raw if isinstance(payload_raw, dict) else json.loads(payload_raw or "{}")
        key = payload.get("item_key")
        if not key:
            continue
        if key not in opened_at or ts < opened_at[key]:
            opened_at[key] = ts
    stale = 0
    for key in open_prs:
        ts = opened_at.get(key)
        if ts is not None and ts <= threshold:
            stale += 1
    return stale


def save_metrics(session: Session, week: str, values: dict[str, float]) -> None:
    """metrics テーブルへ upsert する。"""
    stmt = text(
        """
        INSERT INTO metrics (week, name, value)
        VALUES (:week, :name, :value)
        ON DUPLICATE KEY UPDATE value = VALUES(value)
        """
    )
    for name, value in values.items():
        session.execute(stmt, {"week": week, "name": name, "value": float(value)})
    logger.info("metrics 保存: %d 指標 (week=%s)", len(values), week)


def load_metrics_trend(session: Session, weeks: list[str]) -> dict[str, dict[str, float]]:
    """指定週リストの指標を {week: {name: value}} で返す(推移グラフ用)。"""
    if not weeks:
        return {}
    rows = session.execute(
        text("SELECT week, name, value FROM metrics WHERE week IN :weeks").bindparams(
            bindparam("weeks", expanding=True)
        ),
        {"weeks": weeks},
    ).all()
    trend: dict[str, dict[str, float]] = {w: {} for w in weeks}
    for w, name, value in rows:
        trend.setdefault(w, {})[name] = value
    return trend
