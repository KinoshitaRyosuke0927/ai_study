"""ISO 週(月曜開始)に関するユーティリティ。

week カラムは "YYYY-Www" 形式の文字列(例: "2026-W36")。
日時はすべて UTC で扱う。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def iso_week_of(dt: datetime) -> str:
    """datetime を "YYYY-Www" 形式の ISO 週文字列へ変換する。

    Args:
        dt: 対象の日時。tz 情報が無い場合は UTC とみなす。

    Returns:
        "2026-W36" のような週文字列。
    """
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year:04d}-W{iso_week:02d}"


def week_start(week: str) -> datetime:
    """ISO 週文字列から、その週の月曜 00:00:00 UTC を返す。

    Args:
        week: "2026-W36" 形式の週文字列。

    Returns:
        週初(月曜)の naive datetime(UTC 基準)。
    """
    iso_year_str, iso_week_str = week.split("-W")
    # ISO 週の月曜日を求める(%G-%V-%u, %u=1 が月曜)
    monday = datetime.strptime(f"{iso_year_str}-{int(iso_week_str)}-1", "%G-%V-%u")
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def week_end(week: str) -> datetime:
    """ISO 週文字列から、その週の日曜 23:59:59.999999 UTC を返す。"""
    return week_start(week) + timedelta(days=7) - timedelta(microseconds=1)


def prev_week(week: str) -> str:
    """指定週の 1 週前の週文字列を返す。"""
    return iso_week_of(week_start(week) - timedelta(days=1))


def recent_weeks(week: str, count: int) -> list[str]:
    """指定週を含む直近 count 週分の週文字列を古い順で返す。"""
    weeks = [week]
    cur = week
    for _ in range(count - 1):
        cur = prev_week(cur)
        weeks.append(cur)
    return list(reversed(weeks))


def current_week(now: datetime | None = None) -> str:
    """現在(または指定時刻)の ISO 週文字列。"""
    return iso_week_of(now or datetime.now(timezone.utc))
