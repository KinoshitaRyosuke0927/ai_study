"""MySQL に対する冪等テスト。

uq_event(event_uid の UNIQUE)により、同じイベントを再取り込みしても
重複行が増えないことを確認する。テスト用 DB は frontier_test。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text

from collectors.base import Event
from pipeline.store import save_events

WEEK_TS = datetime(2026, 5, 11, 12, 0, 0)


def _sample_events() -> list[Event]:
    return [
        Event("sample", "post", "sato", WEEK_TS, "p100", {"text": "hello"}),
        Event("sample", "commit", "suzuki", WEEK_TS, "sha100", {"message": "init"}),
    ]


def test_reingest_is_idempotent(db_session):
    # 1 回目
    inserted1 = save_events(db_session, _sample_events())
    db_session.commit()
    # 2 回目(同じ ref / type)
    inserted2 = save_events(db_session, _sample_events())
    db_session.commit()

    total = db_session.execute(text("SELECT COUNT(*) FROM events")).scalar_one()

    assert inserted1 == 2
    assert inserted2 == 0
    assert total == 2


def test_event_uid_generated_column(db_session):
    save_events(db_session, _sample_events())
    db_session.commit()
    uids = set(
        db_session.execute(text("SELECT event_uid FROM events")).scalars().all()
    )
    assert uids == {"sample:p100:post", "sample:sha100:commit"}


def test_apply_schema_twice_ok(settings):
    """schema.sql の再適用でエラーにならないこと(CREATE TABLE IF NOT EXISTS)。"""
    from infra.db import apply_schema

    apply_schema(settings)
    apply_schema(settings)
