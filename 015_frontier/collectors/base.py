"""コレクタ共通の型と HTTP ユーティリティ。

すべてのコレクタは活動を正規化イベント(Event)へ変換して返す。
アイテム(カード / PR / issue / ページ)の現在状態は ItemRecord で返す。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

import requests

logger = logging.getLogger(__name__)

# HTTP 既定値
HTTP_TIMEOUT = 30  # 秒
HTTP_MAX_RETRY = 3
HTTP_BACKOFF_BASE = 1.5  # 秒(指数バックオフの基数)


@dataclass
class Event:
    """正規化された活動イベント。"""

    source: str  # mattermost / trello / growi / github / sample
    type: str  # post / card_moved / pr_merged / page_updated / ...
    actor: str
    ts: datetime  # UTC(naive, UTC 基準)
    ref: str  # ソース内一意キー
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def event_uid(self) -> str:
        """events テーブルの生成カラムと同じ一意キー。"""
        return f"{self.source}:{self.ref}:{self.type}"


@dataclass
class ItemRecord:
    """カード / PR / issue / ページの現在状態。"""

    item_key: str  # "trello:card:abc123" など
    source: str
    type: str  # card / issue / pr / page / thread
    title: str
    status: str  # open / done / merged / archived / ...
    assignee: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Collector(Protocol):
    """コレクタが満たすインターフェース。"""

    source: str

    def fetch_since(self, since: datetime) -> list[Event]:
        """since 以降のイベントのみを返す(差分取得)。"""
        ...

    def fetch_items(self) -> list[ItemRecord]:
        """アイテムの現在状態を返す(差分計算・WIP 集計に使用)。"""
        ...


class HttpClient:
    """タイムアウト・リトライ付きの薄い HTTP ラッパー。

    セッションを使い回し、429 / 5xx は指数バックオフで最大 3 回リトライする。
    """

    def __init__(self, base_headers: dict[str, str] | None = None) -> None:
        # セッションを 1 つ保持して接続を再利用する
        self._session = requests.Session()
        if base_headers:
            self._session.headers.update(base_headers)

    def _request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json_body: Any | None = None,
    ) -> requests.Response:
        """共通リクエスト処理。リトライ後も失敗したら例外を送出する。

        リトライ対象は 429 / 5xx / 接続エラー / タイムアウトのみ。
        400〜499(429 を除く)はリトライせず即座に送出する。
        """
        last_exc: Exception | None = None
        for attempt in range(1, HTTP_MAX_RETRY + 1):
            try:
                resp = self._session.request(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    json=json_body,
                    timeout=HTTP_TIMEOUT,
                )
                # 429 / 5xx はリトライ対象
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise _RetryableStatus(resp.status_code)
                # 4xx(429 以外)は即エラー(リトライしない)
                resp.raise_for_status()
                return resp
            except requests.HTTPError:
                raise
            except (_RetryableStatus, requests.RequestException) as exc:
                last_exc = exc
                if attempt >= HTTP_MAX_RETRY:
                    break
                wait = HTTP_BACKOFF_BASE ** attempt
                logger.warning(
                    "HTTP %s 失敗 (%s) attempt=%d/%d %.1fs 後に再試行: %s",
                    method,
                    url,
                    attempt,
                    HTTP_MAX_RETRY,
                    wait,
                    exc,
                )
                time.sleep(wait)
        assert last_exc is not None
        raise last_exc

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> requests.Response:
        """GET リクエストを送る。"""
        return self._request("GET", url, params=params, headers=headers)

    def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """GET してレスポンス JSON を返す。"""
        return self.get(url, params=params, headers=headers).json()

    def post_json(
        self,
        url: str,
        json_body: Any,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """JSON ボディを POST してレスポンス JSON を返す。"""
        return self._request(
            "POST", url, params=params, headers=headers, json_body=json_body
        ).json()


class _RetryableStatus(Exception):
    """リトライ対象の HTTP ステータスを表す内部例外。"""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"retryable status {status_code}")
        self.status_code = status_code
