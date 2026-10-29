"""DB の自動起動・停止のテスト。"""

from argparse import Namespace
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import OperationalError

from app.infra import db
from app.infra.db_power import set_db_power
from app.models import AppState


class FakePower:
    """状態を変えられる偽の DB 操作。"""

    def __init__(self, state: str):
        self._state = state
        self.started = 0
        self.stopped = 0

    def state(self):
        return self._state

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1


def test_db_starting_when_stopped(client, monkeypatch):
    # DB に接続できないとき、自動起動が有効なら停止中の DB の起動を要求して 503(db_starting)を返す
    from app.config.settings import get_settings
    from app.services import course_service

    power = FakePower("Stopped")
    set_db_power(power)
    monkeypatch.setattr(get_settings(), "db_autostart_enabled", True)

    def down(*args, **kwargs):
        raise OperationalError("SELECT 1", None, Exception("Can't connect to MySQL server"))

    monkeypatch.setattr(course_service, "list_courses", down)
    res = client.get("/api/courses")
    assert res.status_code == 503 and res.json()["code"] == "db_starting"
    # 続けてアクセスしても、起動の要求は一定時間に1回だけ
    client.get("/api/courses")
    assert power.started == 1
    # 自動起動が無効なら、起動は要求せず db_unavailable を返す
    monkeypatch.setattr(get_settings(), "db_autostart_enabled", False)
    assert client.get("/api/courses").json()["code"] == "db_unavailable"


def test_activity_recorded_and_idle_stop(client):
    from app.cli import cmd_db_idle_stop

    # API へのアクセスで最終アクセス日時が記録される
    client.get("/api/courses")
    with db.new_session() as s:
        assert s.get(AppState, "last_activity") is not None
    # 最近アクセスがあれば停止しない
    power = FakePower("Ready")
    set_db_power(power)
    cmd_db_idle_stop(Namespace(idle_minutes=60))
    assert power.stopped == 0
    # 一定時間アクセスが無ければ停止する
    with db.new_session() as s:
        s.get(AppState, "last_activity").value = (datetime.now(timezone.utc) - timedelta(minutes=90)).isoformat()
        s.commit()
    cmd_db_idle_stop(Namespace(idle_minutes=60))
    assert power.stopped == 1
    # 停止済みなら何もしない
    set_db_power(FakePower("Stopped"))
    cmd_db_idle_stop(Namespace(idle_minutes=60))

