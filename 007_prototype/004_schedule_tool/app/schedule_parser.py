"""GROUPSESSION のスケジュール画面(sch010.do の週間表示)のHTMLから、
マイグループ・メンバー・日付・予定を読み取る関数群。

画面の構造(GROUPSESSION 5.1 で確認)
- グループの選択肢: <select name="sch010DspGpSid">。値が "M" で始まるものがマイグループ
- 日付の見出し: 1行目の各列。moveDailySchedule('day', YYYYMMDD, ...) を持つ
  (土日は bgC_calSaturday / bgC_calSunday のクラスが付く)
- メンバーの行: td.cal_colHeader-sonota(openUserInfoWindow(ユーザーID) と氏名)+ 日ごとの7列
  - 日ごとの列には時刻のある予定が並ぶ(addSchedule('add', YYYYMMDD, ユーザーID, 0) で列の日付がわかる)
- 期間予定の行: メンバーの行の下に続く行(氏名欄の rowspan の分だけ)
  - td.cal_periodCell-less(予定なしの1日)と td.cal_periodCell(colspan=日数)が並ぶ
  - 時刻のない予定(1日だけのものも含む)はこの行に表示される
- 予定1件: <a onclick="editSchedule('edit', YYYYMMDD, 予定ID, ユーザーID, 0)"> の中に
  span.tooltips(マウスを乗せた時の詳細)・span.cal_time(時刻)・div.cal_content / div.cal_todoSpace(タイトル)
"""

from __future__ import annotations

import re
from datetime import date, datetime

import jpholiday
from bs4 import BeautifulSoup, Tag

GROUP_SELECT_NAME = "sch010DspGpSid"
EDIT_PATTERN = re.compile(r"editSchedule\(\s*'\w*'\s*,\s*(\d{8})\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)")
ADD_PATTERN = re.compile(r"addSchedule\(\s*'\w*'\s*,\s*(\d{8})\s*,\s*(\d+)\s*,")
DAY_HEADER_PATTERN = re.compile(r"moveDailySchedule\(\s*'day'\s*,\s*(\d{8})")
USER_PATTERN = re.compile(r"openUserInfoWindow\(\s*(\d+)\s*\)")
TIME_PATTERN = re.compile(r"(\d{1,2}):(\d{2})\s*[-－~〜～]\s*(\d{1,2}):(\d{2})")
COLOR_PREFIX = "cl_fontSchTitle"


def make_soup(html: str) -> BeautifulSoup:
    """
    HTMLを解析する(閉じタグの抜けがあってもブラウザに近い形で読めるよう lxml を使う)

    Args
    -----------------
    - html: str,  画面のHTML

    Returns
    -----------------
    - soup: BeautifulSoup,  解析結果

    """
    return BeautifulSoup(html, "lxml")


def is_login_page(soup: BeautifulSoup) -> bool:
    """
    ログイン画面かどうか(セッション切れで戻された場合など)を判定する

    Args
    -----------------
    - soup: BeautifulSoup,  画面

    Returns
    -----------------
    - is_login: bool,  ログイン画面なら True

    """
    return soup.find("input", attrs={"name": "cmn001Userid"}) is not None


def _ymd_to_iso(ymd: str) -> str:
    """
    "YYYYMMDD" を "YYYY-MM-DD" に変換する

    Args
    -----------------
    - ymd: str,  "YYYYMMDD" 形式の日付

    Returns
    -----------------
    - iso: str,  "YYYY-MM-DD" 形式の日付

    """
    return datetime.strptime(ymd, "%Y%m%d").date().isoformat()


def _clean(text: str) -> str:
    """
    連続する空白・改行を1つの空白にまとめる

    Args
    -----------------
    - text: str,  元の文字列

    Returns
    -----------------
    - cleaned: str,  空白をまとめた文字列

    """
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def form_payload(soup: BeautifulSoup) -> dict:
    """
    画面のフォーム(forms[0])の現在の入力値を、送信用の辞書にする(ブラウザの送信と同じ内容)

    Args
    -----------------
    - soup: BeautifulSoup,  スケジュール画面

    Returns
    -----------------
    - payload: dict,  {項目名: 値}

    """
    form = soup.find("form")
    if form is None:
        raise ValueError("スケジュール画面のフォームが見つかりませんでした")
    payload: dict = {}

    # 入力欄(ボタン類と、チェックされていないチェックボックスは送らない)
    for i in form.find_all("input"):
        name, typ = i.get("name"), (i.get("type") or "text").lower()
        if not name or typ in ("button", "submit", "image", "reset", "file"):
            continue
        if typ in ("checkbox", "radio") and not i.has_attr("checked"):
            continue
        payload[name] = i.get("value", "")

    # 選択欄(選択中の項目。無ければ先頭)
    for s in form.find_all("select"):
        if s.get("name"):
            opt = s.find("option", selected=True) or s.find("option")
            payload[s["name"]] = opt.get("value", "") if opt else ""
    return payload


def parse_groups(soup: BeautifulSoup) -> dict:
    """
    グループの選択肢から、マイグループの一覧と表示中のグループを読み取る

    Args
    -----------------
    - soup: BeautifulSoup,  スケジュール画面

    Returns
    -----------------
    - result: dict,  {"my_groups": [{"value", "name"}], "selected": 表示中のグループの値}

    """
    sel = soup.find("select", attrs={"name": GROUP_SELECT_NAME})
    if sel is None:
        raise ValueError("グループの選択欄が見つかりませんでした")
    options = sel.find_all("option")
    selected = sel.find("option", selected=True)

    # 値が "M" で始まるものがマイグループ
    my_groups = [
        {"value": o.get("value", ""), "name": _clean(o.get_text())}
        for o in options
        if (o.get("value") or "").startswith("M")
    ]
    return {"my_groups": my_groups, "selected": selected.get("value") if selected else None}


def is_holiday(iso: str) -> bool:
    """
    土日・日本の祝日(振替休日・国民の休日を含む)かどうか

    jpholiday はPCの中で祝日を計算するライブラリで、外部には通信しない。

    Args
    -----------------
    - iso: str,  日付 "YYYY-MM-DD"

    Returns
    -----------------
    - holiday: bool,  土日・祝日なら True

    """
    d = date.fromisoformat(iso)
    return d.weekday() >= 5 or jpholiday.is_holiday(d)


def parse_days(soup: BeautifulSoup) -> list[dict]:
    """
    日付の見出しから、表示中の週の日付を読み取る

    Args
    -----------------
    - soup: BeautifulSoup,  スケジュール画面

    Returns
    -----------------
    - days: list[dict],  [{"date": "YYYY-MM-DD", "weekday": 0(月)〜6(日), "holiday": 土日・祝日なら True}]

    """
    # moveDailySchedule('day', ...) を持つ見出しが7つ並んでいる行を探す
    for tr in soup.find_all("tr"):
        cells = [td for td in tr.find_all("td", recursive=False) if DAY_HEADER_PATTERN.search(str(td))]
        if len(cells) < 7:
            continue
        days = []
        for td in cells:
            iso = _ymd_to_iso(DAY_HEADER_PATTERN.search(str(td)).group(1))
            classes = " ".join(td.get("class") or [])
            # 土日は見出しのクラスで色分けされている。日本の祝日(振替休日・国民の休日を含む)は jpholiday で判定する
            holiday = bool(re.search(r"Saturday|Sunday|Holiday", classes)) or is_holiday(iso)
            days.append({"date": iso, "weekday": date.fromisoformat(iso).weekday(), "holiday": holiday})
        return days
    raise ValueError("日付の見出しが見つかりませんでした")


def _member_of(td: Tag) -> dict | None:
    """
    氏名欄のセルから、ユーザーIDと氏名を読み取る

    Args
    -----------------
    - td: Tag,  td.cal_colHeader-sonota

    Returns
    -----------------
    - member: dict | None,  {"uid", "name"}。ユーザーIDが読み取れない場合は None

    """
    link = td.find(onclick=USER_PATTERN)
    if link is None:
        return None
    return {"uid": USER_PATTERN.search(link["onclick"]).group(1), "name": _clean(link.get_text())}


def parse_members(soup: BeautifulSoup) -> list[dict]:
    """
    表示中のグループのメンバー一覧を読み取る

    Args
    -----------------
    - soup: BeautifulSoup,  スケジュール画面

    Returns
    -----------------
    - members: list[dict],  [{"uid", "name"}](画面の表示順)

    """
    members, seen = [], set()
    for td in soup.select("td.cal_colHeader-sonota"):
        member = _member_of(td)
        if member and member["uid"] not in seen:
            seen.add(member["uid"])
            members.append(member)
    return members


def _event_from(container: Tag, uid: str | None) -> dict:
    """
    予定1件分の要素から、時刻・タイトル・詳細・色を読み取る

    Args
    -----------------
    - container: Tag,       予定1件分の要素(editSchedule のリンクなど)
    - uid: str | None,      予定の持ち主のユーザーID(リンクから読めない場合に使う)

    Returns
    -----------------
    - event: dict,  {"sid", "uid", "start_time", "end_time", "title", "detail", "color"}

    """
    m = EDIT_PATTERN.search(container.get("onclick", "")) if container.name == "a" else None

    # 時刻("09:00-10:00")
    time_el = container.select_one(".cal_time")
    start_time = end_time = None
    if time_el:
        t = TIME_PATTERN.search(time_el.get_text())
        if t:
            start_time = f"{int(t.group(1)):02d}:{t.group(2)}"
            end_time = f"{int(t.group(3)):02d}:{t.group(4)}"

    # タイトル(時刻のある予定は .cal_content、時刻のない予定は .cal_todoSpace)
    title_el = container.select_one(".cal_content") or container.select_one(".cal_todoSpace")
    title = _clean(title_el.get_text(" ")) if title_el else ""

    # マウスを乗せた時の詳細(改行ごとに1行)
    tip = container.select_one("span.tooltips")
    detail = []
    if tip:
        for br in tip.find_all("br"):
            br.replace_with("\n")
        detail = [_clean(line) for line in tip.get_text().split("\n") if _clean(line)]

    # タイトルの色(cl_fontSchTitleGreen など → "Green")
    color = ""
    color_el = container.find(class_=re.compile(f"^{COLOR_PREFIX}"))
    if color_el:
        color = next(c for c in color_el["class"] if c.startswith(COLOR_PREFIX))[len(COLOR_PREFIX):]

    return {
        "sid": m.group(2) if m else None,
        "uid": m.group(3) if m else uid,
        "start_time": start_time,
        "end_time": end_time,
        "title": title,
        "detail": detail,
        "color": color,
    }


def _event_containers(cell: Tag) -> list[Tag]:
    """
    セルの中の予定の要素を探す。編集リンクの無い予定(閲覧のみの予定など)も拾う

    Args
    -----------------
    - cell: Tag,  日ごとのセル、または期間予定のセル

    Returns
    -----------------
    - containers: list[Tag],  予定1件ずつの要素

    """
    containers = cell.find_all("a", onclick=EDIT_PATTERN)
    # 編集リンクの外にあるタイトル(リンクの無い予定)は、そのまとまり(.cal_space か自身)を1件とする
    for title_el in cell.select(".cal_content, .cal_todoSpace"):
        if title_el.find_parent("a", onclick=EDIT_PATTERN) is None:
            containers.append(title_el.find_parent(class_="cal_space") or title_el.parent or title_el)
    return containers


def parse_events(soup: BeautifulSoup, days: list[dict]) -> list[dict]:
    """
    週間表示の画面から、予定の一覧を読み取る

    Args
    -----------------
    - soup: BeautifulSoup,  スケジュール画面
    - days: list[dict],     parse_days の結果(表示中の週の日付)

    Returns
    -----------------
    - events: list[dict],  予定の一覧。各要素は _event_from の項目に加えて
                           "start_date", "end_date"("YYYY-MM-DD")、"all_day"(時刻なし・期間予定なら True)を持つ

    """
    events: list[dict] = []
    current_uid: str | None = None
    period_rows_left = 0

    for tr in soup.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        name_td = next((td for td in tds if "cal_colHeader-sonota" in (td.get("class") or [])), None)

        # メンバーの行: 日ごとのセルに並ぶ、時刻のある予定を読む
        if name_td is not None:
            member = _member_of(name_td)
            current_uid = member["uid"] if member else None
            period_rows_left = int(name_td.get("rowspan") or 1) - 1
            for td in tds:
                if td is name_td:
                    continue
                add = ADD_PATTERN.search(str(td))
                for container in _event_containers(td):
                    ev = _event_from(container, current_uid)
                    edit = EDIT_PATTERN.search(container.get("onclick", "")) if container.name == "a" else None
                    ymd = add.group(1) if add else (edit.group(1) if edit else None)
                    if ymd is None:
                        continue
                    iso = _ymd_to_iso(ymd)
                    ev.update({"start_date": iso, "end_date": iso, "all_day": ev["start_time"] is None})
                    events.append(ev)
            continue

        # 期間予定の行: 列の位置から、予定がかかる日付を求める
        if period_rows_left > 0 and any(
            c in (td.get("class") or []) for td in tds for c in ("cal_periodCell", "cal_periodCell-less")
        ):
            period_rows_left -= 1
            col = 0
            for td in tds:
                span = int(td.get("colspan") or 1)
                if "cal_periodCell" in (td.get("class") or []) and col < len(days):
                    start = days[col]["date"]
                    end = days[min(col + span, len(days)) - 1]["date"]
                    for container in _event_containers(td):
                        ev = _event_from(container, current_uid)
                        ev.update({"start_date": start, "end_date": end, "all_day": ev["start_time"] is None})
                        events.append(ev)
                col += span
    return events


def parse_week(html: str) -> dict:
    """
    週間表示の画面を読み取る

    Args
    -----------------
    - html: str,  スケジュール画面のHTML

    Returns
    -----------------
    - week: dict,  {"group", "dsp_date", "days", "members", "events"}

    """
    soup = make_soup(html)
    days = parse_days(soup)
    dsp = soup.find("input", attrs={"name": "sch010DspDate"})
    return {
        "group": parse_groups(soup)["selected"],
        "dsp_date": dsp.get("value") if dsp else None,
        "days": days,
        "members": parse_members(soup),
        "events": parse_events(soup, days),
    }
