"""GROUPSESSION(社内掲示板)のスクレイピング用ラッパー関数群。

GROUPSESSIONにはAPIが無いため、ブラウザが送信するのと同じフォームの
POSTリクエストを再現する。bbs060.do への各POSTはJSONを返す
(ログイン画面のみ通常のHTML)。

ログインID・パスワードは、Azure Functionsのアプリケーション設定
(GROUPSESSION_USERNAME / GROUPSESSION_PASSWORD。Key Vault参照を推奨)から読み込む。
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlparse

from bs4 import BeautifulSoup
import requests

from app import config

# GROUPSESSIONの日時表示はJST。Azure Functions上はサーバのローカル時刻がUTCになるため、
# 実行環境に依存しないよう固定オフセットのJSTとして解釈する
JST = timezone(timedelta(hours=9), "JST")

DATE_PATTERN = re.compile(r"(\d{4})/(\d{2})/(\d{2}).*?(\d{2}):(\d{2}):(\d{2})")


def _base_url() -> str:
    """末尾のスラッシュを除いたGROUPSESSIONのURLを返す"""
    return config.get_required("GROUPSESSION_BASE_URL").rstrip("/")


def _login_url() -> str:
    """ログイン画面のURLを返す"""
    return f"{_base_url()}/common/cmn001.do"


def _bulletin_url() -> str:
    """掲示板(bbs060.do)のURLを返す"""
    return f"{_base_url()}/bulletin/bbs060.do"


def _build_thread_url(forum_sid: int, thread_sid: int) -> str:
    """
    ログイン後にそのスレッドへ直接遷移できるURLを組み立てる

    Args
    -----------------
    - forum_sid: int,   フォーラムID
    - thread_sid: int,  スレッドID

    Returns
    -----------------
    - url: str,  ログイン画面経由でスレッドを開くURL

    """
    parsed = urlparse(_base_url())
    origin = f"{parsed.scheme}://{parsed.netloc}"
    target_path = f"{parsed.path}/bulletin/bbs060.do?bbs010forumSid={forum_sid}&threadSid={thread_sid}"
    return f"{origin}{parsed.path}/common/cmn001.do?url={quote(target_path, safe='')}"


def _unescape(text: str) -> str:
    """HTMLエンティティをデコードし、ノーブレークスペースを通常の空白にする"""
    return html.unescape(text).replace("\xa0", " ")


def _parse_datetime_to_epoch_ms(text: str) -> int | None:
    """
    "YYYY/MM/DD( 曜 ) HH:MM:SS" 形式(JST)の文字列をepochミリ秒に変換する

    Args
    -----------------
    - text: str,  GROUPSESSIONの日時文字列

    Returns
    -----------------
    - epoch_ms: int | None,  epochミリ秒(形式が一致しない場合はNone)

    """
    match = DATE_PATTERN.search(text)
    if not match:
        return None
    year, month, day, hour, minute, second = (int(g) for g in match.groups())
    dt = datetime(year, month, day, hour, minute, second, tzinfo=JST)
    return int(dt.timestamp() * 1000)


def _login() -> requests.Session:
    """
    ログイン画面からCSRFトークンを取得し、ログイン済みセッションを返す

    Args
    -----------------
    - なし

    Returns
    -----------------
    - session: requests.Session,  ログイン済みのセッション

    """
    username = config.get_required("GROUPSESSION_USERNAME")
    password = config.get_required("GROUPSESSION_PASSWORD")

    session = requests.Session()

    # ログイン画面を取得し、Struts のCSRFトークンを取り出す
    login_page = session.get(_login_url(), timeout=10)
    login_page.raise_for_status()
    soup = BeautifulSoup(login_page.text, "html.parser")
    token_input = soup.find("input", attrs={"name": "org.apache.struts.taglib.html.TOKEN"})
    token = token_input["value"] if token_input else ""

    # トークンとID・パスワードを送信してログインする
    response = session.post(
        _login_url(),
        data={
            "org.apache.struts.taglib.html.TOKEN": token,
            "CMD": "login",
            "cmn001loginType": "1",
            "url": "",
            "cmn001initAccess": "1",
            "cmn001Userid": username,
            "cmn001Passwd": password,
        },
        timeout=10,
    )
    response.raise_for_status()

    # ID・パスワードが誤っている場合もHTTPステータスは200で返り、
    # ログイン画面がそのまま再表示されるため、フォームの有無で成否を判定する
    result_soup = BeautifulSoup(response.text, "html.parser")
    if result_soup.find("input", attrs={"name": "cmn001Userid"}) is not None:
        raise ValueError("GROUPSESSIONのIDまたはパスワードが正しくありません")

    return session


def _bbs060_base_payload(forum_sid: int) -> dict:
    """bbs060.do への各種POSTで共通して必要な隠しフィールド一式"""
    today = datetime.now(JST)
    return {
        "bbs010page1": "0",
        "bbs010forumSid": str(forum_sid),
        "threadSid": "",
        "bbsmainFlg": "0",
        "bbs060sortKey": "5",
        "bbs060orderKey": "0",
        "bbs060page1": "1",
        "bbs060page2": "0",
        "searchDspID": "",
        "bbs040forumSid": "0",
        "bbs040keyKbn": "0",
        "bbs040taisyouThread": "0",
        "bbs040taisyouNaiyou": "0",
        "bbs040userName": "",
        "bbs040readKbn": "0",
        "bbs040dateNoKbn": "0",
        "bbs040fromYear": "0",
        "bbs040fromMonth": "0",
        "bbs040fromDay": "0",
        "bbs040toYear": str(today.year),
        "bbs040toMonth": str(today.month),
        "bbs040toDay": str(today.day),
        "bbs041page1": "0",
        "bbs060postOrderKey": "-1",
        "bbs060postPage1": "1",
        "bbs060reply": "",
        "bbs060showThreBtn": "0",
        "bbs060postBinSid": "0",
        "bbs060postSid": "0",
        "helpPrm": "0",
    }


def _parse_thread_entries(data: dict) -> list[dict]:
    """getThreadDataのJSONレスポンス(1ページ分)から、各スレッドの情報を抽出する"""
    rows = []
    for entry in data.get("threadList", []):
        posted_at = _parse_datetime_to_epoch_ms(entry.get("strWriteDate", ""))
        if posted_at is None:
            continue
        rows.append({
            "thread_sid": entry["btiSid"],
            "title": _unescape(entry.get("btiTitle", "")),
            "author": _unescape(entry.get("userName", "")),
            "posted_at": posted_at,
        })
    return rows


def _get_forum_threads(
    session: requests.Session, forum_sid: int, since_ts_ms: int, until_ts_ms: int
) -> list[dict]:
    """
    指定フォーラムの、指定期間内に最終更新されたスレッド一覧を返す

    Args
    -----------------
    - session: requests.Session,  ログイン済みのセッション
    - forum_sid: int,             フォーラムID
    - since_ts_ms: int,           取得開始時刻(epochミリ秒)
    - until_ts_ms: int,           取得終了時刻(epochミリ秒)

    Returns
    -----------------
    - threads: list[dict],  [{"thread_sid","title","author","posted_at"}, ...]

    """
    base_payload = _bbs060_base_payload(forum_sid)
    threads: list[dict] = []

    page = 1
    total_pages = 1
    while page <= total_pages:
        payload = {**base_payload, "CMD": "getThreadData", "bbs060page1": str(page)}
        response = session.post(_bulletin_url(), data=payload, timeout=10)
        response.raise_for_status()
        data = response.json()

        if page == 1:
            total_pages = len(data.get("bbsPageLabel", [])) or 1

        rows = _parse_thread_entries(data)
        threads.extend(r for r in rows if since_ts_ms <= r["posted_at"] <= until_ts_ms)

        # スレッド一覧は最新書き込み日時の降順なので、ページ内の最古の投稿が
        # 対象期間より前であれば、それ以降のページを取得する必要はない
        if rows and min(r["posted_at"] for r in rows) < since_ts_ms:
            break
        page += 1

    return threads


def _get_thread_text(session: requests.Session, forum_sid: int, thread_sid: int) -> str:
    """
    スレッドの投稿本文(プレーンテキスト)を取得する

    Args
    -----------------
    - session: requests.Session,  ログイン済みのセッション
    - forum_sid: int,             フォーラムID
    - thread_sid: int,            スレッドID

    Returns
    -----------------
    - text: str,  本文のプレーンテキスト(取得できない場合は空文字)

    """
    payload = {
        **_bbs060_base_payload(forum_sid),
        "CMD": "getPostData",
        "threadSid": str(thread_sid),
        "helpPrm": "1",
    }
    response = session.post(_bulletin_url(), data=payload, timeout=10)
    response.raise_for_status()
    data = response.json()

    post_list = data.get("postList", [])
    if not post_list:
        return ""
    post = post_list[0]

    plain_html = _unescape(post.get("bwiValuePlain", ""))
    text = BeautifulSoup(plain_html, "html.parser").get_text(separator="\n").strip()

    # 記事によっては bwiValuePlain が空で、本文が bwiValue 側にしか無いことがあるため、
    # その場合は bwiValue(HTMLタグを含むことがある)からテキストを抽出する
    if not text:
        text = BeautifulSoup(_unescape(post.get("bwiValue", "")), "html.parser").get_text(separator="\n").strip()
    return text


def get_recent_announcements(forum_sid: int, since_ts_ms: int, until_ts_ms: int) -> list[dict]:
    """
    指定フォーラムの、指定期間内に投稿(最終更新)されたアナウンス記事を取得する
    (Mattermostの投稿一覧と同じ形状で返し、同じスコアリング・リマインド処理を使えるようにする)

    Args
    -----------------
    - forum_sid: int,     フォーラムID
    - since_ts_ms: int,   取得開始時刻(epochミリ秒)
    - until_ts_ms: int,   取得終了時刻(epochミリ秒)

    Returns
    -----------------
    - announcements: list[dict],  [{"id","username","message","create_at","url"}, ...](古い順)

    """
    # ログインして期間内のスレッド一覧を取得する
    session = _login()
    threads = _get_forum_threads(session, forum_sid, since_ts_ms, until_ts_ms)

    # スレッドごとに本文を取得し、タイトルと本文をつなげてスコアリング対象のテキストにする
    announcements = []
    for thread in threads:
        text = _get_thread_text(session, forum_sid, thread["thread_sid"])
        message = f"{thread['title']}\n{text}" if text else thread["title"]
        announcements.append({
            "id": f"{forum_sid}-{thread['thread_sid']}",
            "username": thread["author"],
            "message": message,
            "create_at": thread["posted_at"],
            "url": _build_thread_url(forum_sid, thread["thread_sid"]),
        })

    announcements.sort(key=lambda a: a["create_at"])
    return announcements
