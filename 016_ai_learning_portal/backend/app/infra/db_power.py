"""Azure Database for MySQL フレキシブルサーバーの状態確認・起動・停止を扱うモジュール。

フレキシブルサーバーには「接続が来たら自動で起動する」機能が無いため、アプリが Azure の管理 API で起動する。
- アプリ(Container Apps)のマネージド ID に、MySQL サーバーを操作できる権限を付けておく
- 認証は azure-identity の DefaultAzureCredential(Azure 上はマネージド ID、ローカルは az login)
"""

from __future__ import annotations

import threading
import time
from typing import Protocol

import httpx

from app.config.settings import Settings, get_settings

_API_VERSION = "2023-12-30"
_MANAGEMENT_SCOPE = "https://management.azure.com/.default"

# サーバーの状態(Azure の表記)
STATE_READY = "Ready"
STATE_STOPPED = "Stopped"
STATE_STARTING = "Starting"
STATE_STOPPING = "Stopping"


class DbPowerError(Exception):
    """DB の状態確認・起動・停止に失敗した。"""


class DbPower(Protocol):
    """DB の電源操作の型(テストでは偽物に差し替える)。"""

    def state(self) -> str:
        """現在の状態(Ready / Stopped / Starting / Stopping など)を返す。"""
        ...

    def start(self) -> None:
        """起動を要求する(完了は待たない)。"""
        ...

    def stop(self) -> None:
        """停止を要求する(完了は待たない)。"""
        ...


class AzureMySqlPower:
    """Azure の管理 API で MySQL フレキシブルサーバーを操作する。"""

    def __init__(self, settings: Settings) -> None:
        """
        操作対象のサーバーを設定する

        Args
        -----------------
        - settings: Settings,               アプリ設定(サブスクリプション・リソースグループ・サーバー名)

        """
        # 操作対象のサーバーの URL を組み立てる
        if not (settings.azure_subscription_id and settings.azure_resource_group and settings.mysql_server_name):
            raise DbPowerError("AZURE_SUBSCRIPTION_ID / AZURE_RESOURCE_GROUP / MYSQL_SERVER_NAME を設定してください")
        self._base = (
            f"https://management.azure.com/subscriptions/{settings.azure_subscription_id}"
            f"/resourceGroups/{settings.azure_resource_group}"
            f"/providers/Microsoft.DBforMySQL/flexibleServers/{settings.mysql_server_name}"
        )
        self._credential = None

    def _headers(self) -> dict[str, str]:
        """
        管理 API のアクセストークンを付けたヘッダを返す

        Returns
        -----------------
        - headers: dict[str, str],          Authorization ヘッダ

        """
        # 資格情報は最初の呼び出しで用意する(SDK の読み込みを遅らせる)
        if self._credential is None:
            from azure.identity import DefaultAzureCredential

            self._credential = DefaultAzureCredential()
        token = self._credential.get_token(_MANAGEMENT_SCOPE).token
        return {"Authorization": f"Bearer {token}"}

    def state(self) -> str:
        """
        サーバーの状態を返す

        Returns
        -----------------
        - state: str,                       Ready / Stopped / Starting / Stopping など

        """
        # サーバーの情報を取得して状態を返却
        try:
            res = httpx.get(self._base, params={"api-version": _API_VERSION}, headers=self._headers(), timeout=30)
            res.raise_for_status()
        except Exception as e:
            raise DbPowerError(f"DB の状態を取得できませんでした: {e}") from e
        return res.json().get("properties", {}).get("state", "")

    def _action(self, action: str) -> None:
        """
        起動・停止を要求する

        Args
        -----------------
        - action: str,                      start / stop

        """
        # 非同期の操作として受け付けられれば成功(202)
        try:
            res = httpx.post(
                f"{self._base}/{action}", params={"api-version": _API_VERSION}, headers=self._headers(), timeout=30
            )
            res.raise_for_status()
        except Exception as e:
            raise DbPowerError(f"DB の {action} を要求できませんでした: {e}") from e

    def start(self) -> None:
        """サーバーの起動を要求する。"""
        self._action("start")

    def stop(self) -> None:
        """サーバーの停止を要求する。"""
        self._action("stop")


# テストなどで差し替えた操作部品
_override: DbPower | None = None
# 起動の要求を短時間に何度も送らないための記録
_start_lock = threading.Lock()
_last_start_request = 0.0
# 起動を要求してから、次の要求を送るまでの間隔(秒)
_START_REQUEST_INTERVAL = 60


def set_db_power(power: DbPower | None) -> None:
    """
    DB の電源操作を差し替える(テスト用)

    Args
    -----------------
    - power: DbPower | None,            差し替える操作部品(None で元に戻す)

    """
    global _override, _last_start_request
    # 差し替え先を保存し、起動要求の記録を消す
    _override = power
    _last_start_request = 0.0


def get_db_power() -> DbPower:
    """
    DB の電源操作を返す

    Returns
    -----------------
    - power: DbPower,                   操作部品

    """
    # 差し替えられていればそれを使い、無ければ設定から生成して返却
    return _override if _override is not None else AzureMySqlPower(get_settings())


def ensure_starting() -> str:
    """
    DB に接続できないときに呼ぶ。停止中なら起動を要求し、現在の状態を返す

    Returns
    -----------------
    - state: str,                       DB の状態(起動を要求した場合は Starting)

    """
    global _last_start_request
    power = get_db_power()
    # 現在の状態を確認
    state = power.state()
    # 停止中なら起動を要求する(同時に複数のリクエストが来ても、一定間隔に1回だけ送る)
    if state == STATE_STOPPED:
        with _start_lock:
            if time.monotonic() - _last_start_request > _START_REQUEST_INTERVAL:
                power.start()
                _last_start_request = time.monotonic()
        return STATE_STARTING
    # それ以外(起動中・停止処理中など)はそのまま返却
    return state
