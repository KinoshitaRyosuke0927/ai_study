"""「wiki 情報取得」画面用: GROWI ページの記事内容・更新履歴・コメントを取得する。

分析パイプラインとは独立しており、DB へは保存しない(結果は画面側でメモリ保持)。
- 更新履歴は「誰がいつ更新したか」のみ取得し、各リビジョンの過去断面(本文)は取得しない。
- ページ添付ファイルは取得しない。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from collectors.base import HttpClient
from provider_options import is_placeholder_url
from settings import Settings

logger = logging.getLogger(__name__)

PAGE_LIST_LIMIT = 100
PAGE_LIST_MAX_PAGES = 20
REVISION_LIMIT = 100
REVISION_MAX_PAGES = 3


class GrowiViewError(Exception):
    """取得条件が不正、または GROWI にアクセスできない場合。"""


def _tz(settings: Settings):
    if ZoneInfo is not None:
        try:
            return ZoneInfo(settings.app_tz)
        except Exception:  # pragma: no cover
            pass
    return timezone.utc


def _fmt_iso(value: str | None, tzinfo) -> str | None:
    """ISO8601 を "YYYY-MM-DD HH:MM"(アプリTZ)へ。None はそのまま。"""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tzinfo).strftime("%Y-%m-%d %H:%M")


def _user_label(user: Any) -> str:
    """GROWI ユーザオブジェクトを "表示名 (@username)" へ。"""
    if not isinstance(user, dict):
        return str(user) if user else "不明"
    username = user.get("username") or ""
    name = (user.get("name") or "").strip()
    if name and username:
        return f"{name} (@{username})"
    return f"@{username}" if username else (name or "不明")


def _require_growi(settings: Settings) -> None:
    """GROWI 接続情報が設定済みか確認する。"""
    if is_placeholder_url(settings.growi_url):
        raise GrowiViewError("GROWI の URL が未設定です(.env の GROWI_URL)")
    if not settings.growi_api_token or settings.growi_api_token == "changeme":
        raise GrowiViewError("GROWI の API トークンが未設定です(.env の GROWI_API_TOKEN)")


class _GrowiApi:
    def __init__(self, settings: Settings) -> None:
        self._base = settings.growi_url.rstrip("/")
        self._token = settings.growi_api_token
        self._http = HttpClient()

    def _get(self, endpoint: str, **params) -> Any:
        # endpoint は URL パス、params は GROWI のクエリ("path" 等と衝突しないよう命名を分ける)
        return self._http.get_json(
            f"{self._base}{endpoint}", params={"access_token": self._token, **params}
        )

    def list_pages(self, base_path: str) -> list[dict]:
        """base_path 配下のページを offset ページングで全取得する。"""
        out: list[dict] = []
        offset = 0
        for _ in range(PAGE_LIST_MAX_PAGES):
            data = self._get(
                "/_api/v3/pages/list", path=base_path, limit=PAGE_LIST_LIMIT, offset=offset
            )
            pages = data.get("pages", data.get("items", []))
            if not pages:
                break
            out.extend(pages)
            if len(pages) < PAGE_LIST_LIMIT:
                break
            offset += PAGE_LIST_LIMIT
        return out

    def get_page(self, page_id: str) -> dict:
        """ページ本体(現在リビジョンの本文を含む)を取得する。"""
        data = self._get("/_api/v3/page", pageId=page_id)
        page = data.get("page") or data.get("data", {}).get("page") or data
        return page if isinstance(page, dict) else {}

    def get_revision_body(self, revision_id: str) -> str:
        """現在リビジョンの本文だけ欲しいとき用(page に body が無い場合のフォールバック)。"""
        data = self._get("/_api/v3/revisions/" + revision_id)
        rev = data.get("revision") or data
        return rev.get("body", "") if isinstance(rev, dict) else ""

    def list_revisions(self, page_id: str) -> list[dict]:
        """更新履歴(メタデータのみ)を新しい順で取得する。"""
        out: list[dict] = []
        for page_no in range(1, REVISION_MAX_PAGES + 1):
            data = self._get(
                "/_api/v3/revisions/list", pageId=page_id, page=page_no, limit=REVISION_LIMIT
            )
            revs = data.get("revisions", data.get("docs", []))
            if not revs:
                break
            out.extend(revs)
            if len(revs) < REVISION_LIMIT:
                break
        return out

    def list_comments(self, page_id: str) -> list[dict]:
        """ページのコメントを取得する。"""
        data = self._get("/_api/v3/comments", pageId=page_id)
        return data.get("comments", data.get("data", []))


def list_pages(settings: Settings, base_path: str) -> dict[str, Any]:
    """設定された「参照する Wiki のページ」配下のページ一覧をプルダウン用に返す。

    Raises:
        GrowiViewError: パス未設定 / GROWI にアクセスできない場合。
    """
    _require_growi(settings)
    base_path = (base_path or "").strip()
    if not base_path:
        raise GrowiViewError("設定画面で「参照する Wiki のページ」を設定してください")

    api = _GrowiApi(settings)
    try:
        raw = api.list_pages(base_path)
    except Exception as exc:
        logger.error("GROWI ページ一覧取得失敗 path=%s: %s", base_path, exc)
        raise GrowiViewError(f"ページ一覧を取得できませんでした: {exc}") from exc

    pages = [
        {
            "id": p.get("_id") or p.get("id"),
            "path": p.get("path", ""),
            # プルダウン表示用: 基準パスより下の相対パス
            "name": _relative_path(p.get("path", ""), base_path),
        }
        for p in raw
        if (p.get("_id") or p.get("id"))
    ]
    pages.sort(key=lambda x: x["path"])
    return {"base_path": base_path, "pages": pages, "page_count": len(pages)}


def _relative_path(page_path: str, base_path: str) -> str:
    """page_path から base_path 部分を取り除いた相対パスを返す。

    - base 自身のページは末尾セグメント(なければフルパス)
    - base 配下に無い想定外ケースはフルパスのまま
    """
    bp = (base_path or "").rstrip("/")
    if not bp:
        return page_path
    if page_path == bp:
        return page_path.rsplit("/", 1)[-1] or page_path
    if page_path.startswith(bp + "/"):
        return page_path[len(bp) + 1 :]
    return page_path


def fetch_page(settings: Settings, page_id: str) -> dict[str, Any]:
    """選択ページの記事内容・更新履歴・コメントを返す。

    Raises:
        GrowiViewError: page_id が空 / GROWI にアクセスできない場合。
    """
    _require_growi(settings)
    page_id = (page_id or "").strip()
    if not page_id:
        raise GrowiViewError("取得対象のページを選択してください")

    tzinfo = _tz(settings)
    api = _GrowiApi(settings)

    try:
        page = api.get_page(page_id)
    except Exception as exc:
        logger.error("GROWI ページ取得失敗 id=%s: %s", page_id, exc)
        raise GrowiViewError(
            f"ページを取得できませんでした(ID/権限/トークンを確認してください): {exc}"
        ) from exc
    if not page:
        raise GrowiViewError("ページが見つかりませんでした")

    # --- 記事内容(現在リビジョンの本文)---
    revision = page.get("revision")
    body = ""
    if isinstance(revision, dict):
        body = revision.get("body", "") or ""
    if not body and isinstance(revision, str):
        try:
            body = api.get_revision_body(revision)
        except Exception as exc:  # 本文が取れなくても他は返す
            logger.warning("GROWI 本文取得失敗 id=%s: %s", page_id, exc)

    path = page.get("path", "")

    # --- 更新履歴(メタデータのみ)---
    revisions_out: list[dict] = []
    try:
        for r in api.list_revisions(page_id):
            revisions_out.append(
                {
                    "id": r.get("_id") or r.get("id"),
                    "author": _user_label(r.get("author")),
                    "date": _fmt_iso(r.get("createdAt") or r.get("updatedAt"), tzinfo),
                }
            )
    except Exception as exc:
        logger.warning("GROWI 更新履歴取得失敗 id=%s: %s", page_id, exc)

    # --- コメント(投稿の古い順)---
    comments_out: list[dict] = []
    try:
        raw_comments = api.list_comments(page_id)
        raw_comments.sort(key=lambda c: c.get("createdAt") or "")
        for c in raw_comments:
            comments_out.append(
                {
                    "author": _user_label(c.get("creator")),
                    "date": _fmt_iso(c.get("createdAt"), tzinfo),
                    "text": c.get("comment", ""),
                    "reply": bool(c.get("replyTo")),
                }
            )
    except Exception as exc:
        logger.warning("GROWI コメント取得失敗 id=%s: %s", page_id, exc)

    return {
        "id": page.get("_id") or page_id,
        "path": path,
        "url": f"{settings.growi_url.rstrip('/')}{path}",
        "creator": _user_label(page.get("creator")),
        "last_updater": _user_label(page.get("lastUpdateUser")),
        "created_at": _fmt_iso(page.get("createdAt"), tzinfo),
        "updated_at": _fmt_iso(page.get("updatedAt"), tzinfo),
        "body": body,
        "revisions": revisions_out,
        "revision_count": len(revisions_out),
        "comments": comments_out,
        "comment_count": len(comments_out),
    }
