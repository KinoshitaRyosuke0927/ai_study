"""GROUPSESSION のスケジュールを読み取るためのクライアント。

GROUPSESSION には API が無いため、ブラウザの操作と同じフォームの送信を再現する。
このツールは参照専用のため、送信するのは次の2種類だけに限定している。
- ログイン(common/cmn001.do)
- スケジュール画面の表示の切り替え(schedule/sch010.do に CMD を空にして送信。グループ・表示する週の切り替えと同じ操作)
予定の追加・編集・削除、在席状況の変更につながる送信は、送信前に _post_view で止める。

ID・パスワードとログイン中のセッションはメモリ上にのみ保持し、ファイルには保存しない。
"""

from __future__ import annotations

import threading
from datetime import date, timedelta

import requests
from bs4 import BeautifulSoup

from app import schedule_parser as parser

# 表示の切り替えとして送信してよい CMD(空文字 = グループ・日付の切り替え)
SAFE_CMDS = {""}
# GROUPSESSION 側の画面(sch010.do)の項目名
FIELD_GROUP = "sch010DspGpSid"
FIELD_DATE = "sch010DspDate"


class GroupsessionClient:
    """GROUPSESSION へのログインと、スケジュール画面の読み取りを行う"""

    def __init__(self, base_url: str) -> None:
        """
        クライアントを用意する(この時点ではログインしない)

        Args
        -----------------
        - base_url: str,  GROUPSESSION のURL(例: https://example.com/gsession)

        Returns
        -----------------
        - None

        """
        self.base_url = base_url.rstrip("/")
        self.login_url = f"{self.base_url}/common/cmn001.do"
        self.schedule_url = f"{self.base_url}/schedule/sch010.do"
        self._credentials: dict[str, str] = {}
        self._session: requests.Session | None = None
        # スケジュール画面は「今表示している画面」の状態をサーバ側で持つため、同時に操作しないようにする
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ ログイン

    @property
    def logged_in(self) -> bool:
        """ログイン済み(ID・パスワードを保持している)かどうか"""
        return bool(self._credentials)

    def login(self, username: str, password: str) -> None:
        """
        指定のID・パスワードでログインし、成功した場合だけメモリに保持する

        Args
        -----------------
        - username: str,  GROUPSESSION のID
        - password: str,  GROUPSESSION のパスワード

        Returns
        -----------------
        - None(失敗した場合は ValueError / requests.RequestException)

        """
        with self._lock:
            session = self._new_session(username, password)
            self._credentials = {"username": username, "password": password}
            self._session = session

    def logout(self) -> None:
        """メモリ上のID・パスワードとセッションを破棄する"""
        with self._lock:
            self._credentials = {}
            self._session = None

    def _new_session(self, username: str, password: str) -> requests.Session:
        """
        ログイン画面の CSRF トークンを取得してログインし、ログイン済みのセッションを返す

        Args
        -----------------
        - username: str,  GROUPSESSION のID
        - password: str,  GROUPSESSION のパスワード

        Returns
        -----------------
        - session: requests.Session,  ログイン済みのセッション

        """
        session = requests.Session()

        # ログイン画面から CSRF トークンを取得する
        page = session.get(self.login_url, timeout=15)
        page.raise_for_status()
        soup = BeautifulSoup(page.text, "html.parser")
        token_input = soup.find("input", attrs={"name": "org.apache.struts.taglib.html.TOKEN"})

        # ログインする(ID・パスワードが誤っていても HTTP 200 でログイン画面が再表示される)
        res = session.post(
            self.login_url,
            data={
                "org.apache.struts.taglib.html.TOKEN": token_input["value"] if token_input else "",
                "CMD": "login",
                "cmn001loginType": "1",
                "url": "",
                "cmn001initAccess": "1",
                "cmn001Userid": username,
                "cmn001Passwd": password,
            },
            timeout=15,
        )
        res.raise_for_status()
        if parser.is_login_page(BeautifulSoup(res.text, "html.parser")):
            raise ValueError("IDまたはパスワードが正しくありません")
        return session

    def _relogin(self) -> None:
        """
        セッション切れの時に、保持しているID・パスワードでログインし直す

        Args
        -----------------
        - なし

        Returns
        -----------------
        - None

        """
        if not self._credentials:
            raise PermissionError("GROUPSESSIONにログインしてください")
        self._session = self._new_session(self._credentials["username"], self._credentials["password"])

    # ------------------------------------------------------------------ 画面の取得

    def _get_initial(self) -> BeautifulSoup:
        """
        スケジュール画面の初期表示を取得する(GET)。セッション切れなら1回だけログインし直す

        Args
        -----------------
        - なし

        Returns
        -----------------
        - soup: BeautifulSoup,  スケジュール画面

        """
        if self._session is None:
            self._relogin()
        for attempt in range(2):
            res = self._session.get(self.schedule_url, timeout=30)
            res.raise_for_status()
            soup = parser.make_soup(res.text)
            if not parser.is_login_page(soup):
                return soup
            if attempt == 0:
                self._relogin()
        raise PermissionError("GROUPSESSIONへのログインが切れました。ログインし直してください")

    def _post_view(self, base: BeautifulSoup, overrides: dict) -> str:
        """
        表示の切り替えだけを送信して、スケジュール画面のHTMLを取得する

        Args
        -----------------
        - base: BeautifulSoup,  今表示している画面(フォームの入力値の元にする)
        - overrides: dict,      上書きする入力値(グループ・日付など)

        Returns
        -----------------
        - html: str,  取得したHTML

        """
        payload = parser.form_payload(base)
        payload.update({"CMD": "", "cmd": "", "sch010SchSid": ""})
        payload.update(overrides)

        # 参照専用のツールのため、表示の切り替え以外の送信は行わない(念のため送信前に確認する)
        if payload.get("CMD") not in SAFE_CMDS or payload.get("cmd") not in SAFE_CMDS:
            raise RuntimeError("表示の切り替え以外の操作は送信できません")
        if payload.get("sch010SchSid"):
            raise RuntimeError("予定を指定した送信はできません")

        res = self._session.post(self.schedule_url, data=payload, timeout=30)
        res.raise_for_status()
        return res.text

    # ------------------------------------------------------------------ 公開する操作

    def get_my_groups(self) -> list[dict]:
        """
        ログインしたユーザーのマイグループ一覧を取得する

        Args
        -----------------
        - なし

        Returns
        -----------------
        - groups: list[dict],  [{"value": "M1143", "name": "グループ名"}]

        """
        with self._lock:
            return parser.parse_groups(self._get_initial())["my_groups"]

    def get_group_members(self, group: str) -> list[dict]:
        """
        マイグループに所属するメンバーを取得する(そのグループの今週を表示して、氏名欄を読む)

        Args
        -----------------
        - group: str,  マイグループの値(例: "M1143")

        Returns
        -----------------
        - members: list[dict],  [{"uid", "name"}]

        """
        with self._lock:
            html = self._post_view(self._get_initial(), {FIELD_GROUP: group})
            soup = parser.make_soup(html)
            if parser.parse_groups(soup)["selected"] != group:
                raise ValueError("マイグループを表示できませんでした")
            return parser.parse_members(soup)

    def get_schedule(self, group: str, start: date, end: date) -> dict:
        """
        マイグループの、指定期間の予定を週ごとに取得してまとめる

        Args
        -----------------
        - group: str,   マイグループの値(例: "M1143")
        - start: date,  期間の開始日
        - end: date,    期間の終了日(この日を含む)

        Returns
        -----------------
        - schedule: dict,  {"days": [...], "members": [...], "events": [...]}(期間外の日・予定は除く)

        """
        with self._lock:
            soup = self._get_initial()
            days: dict[str, dict] = {}
            members: dict[str, dict] = {}
            timed_events: list[dict] = []
            all_day_events: dict[tuple, dict] = {}

            # 開始日から7日ずつ、表示する週を切り替えて取得する
            # (iniDsp=0・changeDateFlg=1 を付けると、指定した日から始まる週が表示される)
            cursor = start
            while cursor <= end:
                ymd = cursor.strftime("%Y%m%d")
                html = self._post_view(soup, {FIELD_GROUP: group, FIELD_DATE: ymd, "iniDsp": "0", "changeDateFlg": "1"})
                soup = parser.make_soup(html)
                if parser.is_login_page(soup):
                    raise PermissionError("GROUPSESSIONへのログインが切れました。ログインし直してください")
                week = parser.parse_week(html)
                if week["group"] != group or week["dsp_date"] != ymd:
                    raise ValueError(f"{cursor.isoformat()} の週を表示できませんでした")

                # 日付・メンバー・予定をまとめる
                for d in week["days"]:
                    days[d["date"]] = d
                for m in week["members"]:
                    members.setdefault(m["uid"], m)
                for ev in week["events"]:
                    # 時刻のある予定は日ごとのセルに1件ずつ表示され、週が重ならないので、そのまま追加する
                    if not ev["all_day"]:
                        timed_events.append(ev)
                        continue
                    # 時刻のない予定・期間予定は、週をまたぐと各週に表示されるため、予定ごとに日付の範囲をつなげる
                    key = (ev["uid"], ev["sid"]) if ev["sid"] else (ev["uid"], ev["title"], ev["start_date"])
                    if key in all_day_events:
                        merged = all_day_events[key]
                        merged["start_date"] = min(merged["start_date"], ev["start_date"])
                        merged["end_date"] = max(merged["end_date"], ev["end_date"])
                    else:
                        all_day_events[key] = ev
                cursor += timedelta(days=7)

        # 期間内の日付・予定だけを返す(期間予定は期間内に切り詰める)
        s_iso, e_iso = start.isoformat(), end.isoformat()
        result_events = []
        for ev in [*timed_events, *all_day_events.values()]:
            if ev["end_date"] < s_iso or ev["start_date"] > e_iso:
                continue
            result_events.append({**ev, "start_date": max(ev["start_date"], s_iso), "end_date": min(ev["end_date"], e_iso)})
        result_events.sort(key=lambda e: (e["start_date"], e["start_time"] or "", e["uid"]))
        return {
            "days": [d for k, d in sorted(days.items()) if s_iso <= k <= e_iso],
            "members": list(members.values()),
            "events": result_events,
        }
