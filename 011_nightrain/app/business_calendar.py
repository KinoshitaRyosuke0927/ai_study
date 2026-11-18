"""営業日・営業時間の判定。

リマインドの投稿は、平日(土日・祝日・会社独自の休日を除く)の営業時間内だけ行う。
営業時間外は監視処理そのものを行わず、確認位置(cursor)も進めないため、
営業時間外に投稿された内容は、次の営業日の営業開始後最初の実行でまとめてリマインドされる。

関連するアプリケーション設定:
- BUSINESS_START_HOUR: 営業開始の時(JST、既定 9)
- BUSINESS_END_HOUR:   営業終了の時(JST、既定 18。この時刻ちょうど以降は営業時間外)
- COMPANY_HOLIDAYS:    会社独自の休日(カンマ区切り)。"MM-DD" は毎年、"YYYY-MM-DD" はその日だけ休日として扱う
                       例: "12-29, 12-30, 12-31, 01-02, 01-03, 2027-05-06"
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

import jpholiday

from app import config

# 営業日・営業時間の判定に使うタイムゾーン(Azure Functions上はUTCで動くため、固定オフセットのJSTを使う)
JST = timezone(timedelta(hours=9), "JST")

_YEARLY_PATTERN = re.compile(r"^\d{2}-\d{2}$")
_ONCE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _load_company_holidays() -> tuple[set[str], set[date]]:
    """
    アプリケーション設定 COMPANY_HOLIDAYS を読み込む

    Args
    -----------------
    - なし

    Returns
    -----------------
    - holidays: tuple[set[str], set[date]],  (毎年の休日 "MM-DD" の集合, 特定日の休日の集合)

    """
    yearly: set[str] = set()
    once: set[date] = set()
    for value in config.get_list("COMPANY_HOLIDAYS"):
        # "MM-DD" は毎年の休日として扱う(日付として正しいかは閏年の2/29も通るよう2000年で確認する)
        if _YEARLY_PATTERN.match(value):
            try:
                datetime.strptime(f"2000-{value}", "%Y-%m-%d")
            except ValueError as exc:
                raise RuntimeError(f"アプリケーション設定 COMPANY_HOLIDAYS の日付が正しくありません: {value}") from exc
            yearly.add(value)
        # "YYYY-MM-DD" はその日だけの休日として扱う
        elif _ONCE_PATTERN.match(value):
            try:
                once.add(datetime.strptime(value, "%Y-%m-%d").date())
            except ValueError as exc:
                raise RuntimeError(f"アプリケーション設定 COMPANY_HOLIDAYS の日付が正しくありません: {value}") from exc
        else:
            raise RuntimeError(
                f"アプリケーション設定 COMPANY_HOLIDAYS は MM-DD または YYYY-MM-DD 形式で指定してください(現在値: {value})"
            )
    return yearly, once


def get_non_business_reason(now: datetime) -> str | None:
    """
    指定時刻が営業時間外であれば、その理由を返す(営業時間内なら None)

    Args
    -----------------
    - now: datetime,  判定する時刻(タイムゾーン付き。JSTに変換して判定する)

    Returns
    -----------------
    - reason: str | None,  営業時間外の理由(例: "土日"、"祝日(勤労感謝の日)")。営業時間内なら None

    """
    now_jst = now.astimezone(JST)

    # 休日(土日・祝日・会社独自の休日)
    holiday_reason = get_holiday_reason(now_jst.date())
    if holiday_reason:
        return holiday_reason

    # 営業時間(開始時刻以上、終了時刻未満を営業時間とする)
    start_hour = config.get_int("BUSINESS_START_HOUR", 9)
    end_hour = config.get_int("BUSINESS_END_HOUR", 18)
    if not (start_hour <= now_jst.hour < end_hour):
        return f"営業時間外({start_hour}:00-{end_hour}:00 以外)"

    return None


def get_holiday_reason(day: date) -> str | None:
    """
    指定日が休日(土日・祝日・会社独自の休日)であれば、その理由を返す(営業日なら None)

    Args
    -----------------
    - day: date,  判定する日付(JST)

    Returns
    -----------------
    - reason: str | None,  休日の理由(例: "土日"、"祝日(勤労感謝の日)"、"会社独自の休日")。営業日なら None

    """
    # 土日
    if day.weekday() >= 5:
        return "土日"

    # 祝日(振替休日・国民の休日を含む)
    holiday_name = jpholiday.is_holiday_name(day)
    if holiday_name:
        return f"祝日({holiday_name})"

    # 会社独自の休日
    yearly, once = _load_company_holidays()
    if day.strftime("%m-%d") in yearly or day in once:
        return "会社独自の休日"

    return None


def is_business_day(day: date) -> bool:
    """指定日が営業日(土日・祝日・会社独自の休日以外)かどうかを返す"""
    return get_holiday_reason(day) is None


def add_business_days(day: date, count: int) -> date:
    """
    指定日から営業日で count 日進めた(負の値ならさかのぼった)日付を返す

    Args
    -----------------
    - day: date,    基準日(基準日自体が休日でもよい)
    - count: int,   進める営業日数(例: -3 なら3営業日前、1 なら翌営業日)

    Returns
    -----------------
    - result: date,  count 営業日後(前)の日付

    """
    # 1日ずつ動かし、営業日に当たるたびに残り日数を減らす
    step = 1 if count >= 0 else -1
    remaining = abs(count)
    result = day
    while remaining > 0:
        result += timedelta(days=step)
        if is_business_day(result):
            remaining -= 1
    return result
