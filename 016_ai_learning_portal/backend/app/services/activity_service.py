"""アプリの最終アクセス日時の記録(DB の自動停止の判断に使う)。"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.infra.db import new_session
from app.models import AppState

_KEY = "last_activity"
# 最終アクセスを DB に書き込む間隔(秒)。リクエストのたびには書かない
_WRITE_INTERVAL = 60
_lock = threading.Lock()
_last_write = 0.0


def record_activity() -> None:
    """
    最終アクセス日時を記録する(前回の書き込みから一定時間たっていない場合は何もしない)
    """
    global _last_write
    # 書き込み間隔が空いていなければ何もしない
    with _lock:
        if time.monotonic() - _last_write < _WRITE_INTERVAL:
            return
        _last_write = time.monotonic()
    # 最終アクセス日時(UTC)を保存する
    with new_session() as session:
        state = session.get(AppState, _KEY)
        now = datetime.now(timezone.utc).isoformat()
        if state is None:
            session.add(AppState(key=_KEY, value=now))
        else:
            state.value = now
        session.commit()


def last_activity(session: Session) -> datetime | None:
    """
    最終アクセス日時を返す

    Args
    -----------------
    - session: Session,                 DB セッション

    Returns
    -----------------
    - at: datetime | None,              最終アクセス日時(UTC。記録が無ければ None)

    """
    # 記録を取得して日時に変換して返却
    state = session.get(AppState, _KEY)
    if state is None or not state.value:
        return None
    return datetime.fromisoformat(state.value)


def reset_throttle() -> None:
    """書き込み間隔の記録を消す(テスト用)。"""
    global _last_write
    _last_write = 0.0
