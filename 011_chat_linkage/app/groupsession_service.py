"""GROUPSESSION(社内掲示板)のスクレイピング用ラッパー関数群。

GROUPSESSIONにはAPIが無いため、ブラウザが送信するのと同じフォームの
POSTリクエストを再現する。bbs060.do への各POSTはJSONを返す
(ログイン画面のみ通常のHTML)。
"""

from __future__ import annotations

import html
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlparse

from bs4 import BeautifulSoup
from dotenv import load_dotenv
import requests

# 環境変数(.env)を読み込む
if getattr(sys, "frozen", False):
    _env_path = Path(sys.executable).resolve().parent / ".env"
else:
    _env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(_env_path)

GROUPSESSION_BASE_URL = os.environ["GROUPSESSION_BASE_URL"].rstrip("/")

LOGIN_URL = f"{GROUPSESSION_BASE_URL}/common/cmn001.do"
BULLETIN_URL = f"{GROUPSESSION_BASE_URL}/bulletin/bbs060.do"

_BASE_PARSED = urlparse(GROUPSESSION_BASE_URL)
_ORIGIN = f"{_BASE_PARSED.scheme}://{_BASE_PARSED.netloc}"

# ID・パスワードは.envに保存せず、画面から入力してもらいメモリ上にのみ保持する
_credentials: dict[str, str] = {}


def has_credentials() -> bool:
    return bool(_credentials.get("username")) and bool(_credentials.get("password"))


def logout() -> None:
    _credentials.clear()


def login(username: str, password: str) -> None:
    """指定のID・パスワードで実際にログインできるか検証し、成功した場合のみメモリに保持する"""
    previous = dict(_credentials)
    _credentials["username"] = username
    _credentials["password"] = password
    try:
        _login()
    except Exception:
        _credentials.clear()
        _credentials.update(previous)
        raise


def _build_thread_url(forum_sid: int, thread_sid: int) -> str:
    """ログイン後にそのスレッドへ直接遷移できるURLを組み立てる"""
    target_path = f"{_BASE_PARSED.path}/bulletin/bbs060.do?bbs010forumSid={forum_sid}&threadSid={thread_sid}"
    return f"{_ORIGIN}{_BASE_PARSED.path}/common/cmn001.do?url={quote(target_path, safe='')}"

DATE_PATTERN = re.compile(r"(\d{4})/(\d{2})/(\d{2}).*?(\d{2}):(\d{2}):(\d{2})")

# 記事本文の表示に許可するタグ・属性(script等は除外し、簡易的なサニタイズを行う)
ALLOWED_TAGS = {
    "p", "br", "strong", "b", "em", "i", "u", "span", "div",
    "ul", "ol", "li", "a", "table", "tbody", "thead", "tr", "td", "th",
}
ALLOWED_ATTRS = {"a": {"href"}, "span": {"style"}, "div": {"style"}}


def _unescape(text: str) -> str:
    """HTMLエンティティをデコードし、ノーブレークスペースを通常の空白にする"""
    return html.unescape(text).replace("\xa0", " ")


def _parse_datetime_to_epoch_ms(text: str) -> int | None:
    """"YYYY/MM/DD( 曜 ) HH:MM:SS" 形式の文字列をepochミリ秒に変換する"""
    match = DATE_PATTERN.search(text)
    if not match:
        return None
    year, month, day, hour, minute, second = (int(g) for g in match.groups())
    dt = datetime(year, month, day, hour, minute, second)
    return int(dt.timestamp() * 1000)


DANGEROUS_TAGS = {"script", "style", "iframe", "object", "embed"}


def _sanitize_html(raw_html: str) -> str:
    """記事本文HTMLから、script等の危険なタグ・属性を取り除く"""
    soup = BeautifulSoup(raw_html, "html.parser")

    for tag in soup.find_all(DANGEROUS_TAGS):
        tag.decompose()

    for tag in soup.find_all(True):
        if tag.name not in ALLOWED_TAGS:
            tag.unwrap()
            continue

        allowed_attrs = ALLOWED_ATTRS.get(tag.name, set())
        for attr in list(tag.attrs):
            if attr not in allowed_attrs:
                del tag[attr]

        if tag.name == "a" and tag.get("href", "").lower().startswith("javascript:"):
            del tag["href"]

    return str(soup)


def _login() -> requests.Session:
    """ログイン画面からCSRFトークンを取得し、ログイン済みセッションを返す"""
    if not has_credentials():
        raise RuntimeError("GROUPSESSIONのID・パスワードが未設定です。先にログインしてください。")

    session = requests.Session()

    login_page = session.get(LOGIN_URL, timeout=10)
    login_page.raise_for_status()
    soup = BeautifulSoup(login_page.text, "html.parser")
    token_input = soup.find("input", attrs={"name": "org.apache.struts.taglib.html.TOKEN"})
    token = token_input["value"] if token_input else ""

    response = session.post(
        LOGIN_URL,
        data={
            "org.apache.struts.taglib.html.TOKEN": token,
            "CMD": "login",
            "cmn001loginType": "1",
            "url": "",
            "cmn001initAccess": "1",
            "cmn001Userid": _credentials["username"],
            "cmn001Passwd": _credentials["password"],
        },
        timeout=10,
    )
    response.raise_for_status()

    # ID・パスワードが誤っている場合もHTTPステータスは200で返り、
    # ログイン画面がそのまま再表示されるため、フォームの有無で成否を判定する
    result_soup = BeautifulSoup(response.text, "html.parser")
    if result_soup.find("input", attrs={"name": "cmn001Userid"}) is not None:
        raise ValueError("IDまたはパスワードが正しくありません")

    return session


def _bbs060_base_payload(forum_sid: int) -> dict:
    """bbs060.do への各種POSTで共通して必要な隠しフィールド一式"""
    today = datetime.now()
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
    """指定フォーラムの、指定期間内に最終更新されたスレッド一覧を返す"""
    base_payload = _bbs060_base_payload(forum_sid)
    threads: list[dict] = []

    page = 1
    total_pages = 1
    while page <= total_pages:
        payload = {**base_payload, "CMD": "getThreadData", "bbs060page1": str(page)}
        response = session.post(BULLETIN_URL, data=payload, timeout=10)
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


def _get_thread_detail(session: requests.Session, forum_sid: int, thread_sid: int) -> dict:
    """スレッドの投稿本文(プレーンテキスト・HTML・添付ファイル一覧)を取得する"""
    payload = {
        **_bbs060_base_payload(forum_sid),
        "CMD": "getPostData",
        "threadSid": str(thread_sid),
        "helpPrm": "1",
    }
    response = session.post(BULLETIN_URL, data=payload, timeout=10)
    response.raise_for_status()
    data = response.json()

    post_list = data.get("postList", [])
    if not post_list:
        return {"text": "", "html": "", "attachments": []}

    post = post_list[0]

    plain_html = _unescape(post.get("bwiValuePlain", ""))
    text = BeautifulSoup(plain_html, "html.parser").get_text(separator="\n").strip()

    # 記事によっては bwiValuePlain が空で、本文が bwiValue 側にしか無いことがあるため、
    # その場合は bwiValue(HTMLタグを含むことがある)からテキストを抽出する
    if not text:
        text = BeautifulSoup(_unescape(post.get("bwiValue", "")), "html.parser").get_text(separator="\n").strip()

    rich_html = _sanitize_html(post.get("bwiValue", ""))

    post_sid = post.get("bwiSid", 0)
    attachments = [
        {
            "name": file.get("binFileName", ""),
            "size": file.get("binFileSizeDsp", "").strip("()"),
            "url": (
                f"{BULLETIN_URL}?CMD=fileDownload&bbs010forumSid={forum_sid}"
                f"&threadSid={thread_sid}&bbs060postBinSid={file.get('binSid', 0)}"
                f"&bbs060postSid={post_sid}"
            ),
        }
        for file in post.get("tmpFileList", [])
    ]

    return {"text": text, "html": rich_html, "attachments": attachments}


def get_recent_announcements(forum_sid: int, since_ts_ms: int, until_ts_ms: int) -> list[dict]:
    """
    指定フォーラムの、指定期間内に投稿されたアナウンス記事を取得する。
    Mattermostの投稿一覧と同じ形状({id, username, message, create_at})で返し、
    既存のAI抽出・リマインド生成ロジックをそのまま利用できるようにする。
    """
    session = _login()
    threads = _get_forum_threads(session, forum_sid, since_ts_ms, until_ts_ms)

    announcements = []
    for thread in threads:
        detail = _get_thread_detail(session, forum_sid, thread["thread_sid"])
        message = f"{thread['title']}\n{detail['text']}" if detail["text"] else thread["title"]
        announcements.append({
            "id": f"{forum_sid}-{thread['thread_sid']}",
            "username": thread["author"],
            "message": message,
            "create_at": thread["posted_at"],
            "detail_html": detail["html"],
            "attachments": detail["attachments"],
            "url": _build_thread_url(forum_sid, thread["thread_sid"]),
        })

    announcements.sort(key=lambda a: a["create_at"])
    return announcements
