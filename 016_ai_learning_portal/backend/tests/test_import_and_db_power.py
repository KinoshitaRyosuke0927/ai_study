"""画面からの .ipynb 取り込みと、DB の自動起動・停止のテスト。"""

import io
import zipfile
from argparse import Namespace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.infra import db
from app.infra.db_power import set_db_power
from app.models import AppState
from tests.conftest import SAMPLE_COURSE


@pytest.fixture()
def admin(seeded):
    from app.main import app

    c = TestClient(app)
    assert c.post("/api/auth/login", json={"login_name": "admin", "password": "pw-admin"}).status_code == 200
    return c


def _course_zip(slug: str, top: str = "") -> bytes:
    """サンプル講座を、識別名を変えて zip にする。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for path in SAMPLE_COURSE.rglob("*"):
            if path.is_file():
                data = path.read_bytes()
                if path.name == "course.json":
                    data = data.replace(b'"statistics-basics"', f'"{slug}"'.encode())
                z.writestr(top + str(path.relative_to(SAMPLE_COURSE)).replace("\\", "/"), data)
    return buf.getvalue()


def test_import_course_zip_as_draft(admin):
    # フォルダごと zip にしたもの(1階層下に course.json)を取り込むと、下書きで登録される
    res = admin.post("/api/admin/import/course", files={"file": ("course.zip", _course_zip("zip-course", "statistics-basics/"), "application/zip")})
    assert res.status_code == 200
    editor = res.json()
    assert editor["slug"] == "zip-course" and editor["status"] == "draft"
    assert len(editor["units"]) == 5 and len(editor["quiz"]) == 10 and editor["datasets"][0]["filename"] == "scores.csv"
    # 同じ識別名は置き換え指定が無ければエラー
    res = admin.post("/api/admin/import/course", files={"file": ("c.zip", _course_zip("zip-course"), "application/zip")})
    assert res.status_code == 400
    res = admin.post("/api/admin/import/course", data={"replace": "true"}, files={"file": ("c.zip", _course_zip("zip-course"), "application/zip")})
    assert res.status_code == 200


def test_import_rejects_unsafe_zip(admin):
    # 展開先の外を指すパスを含む zip は拒否する
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../evil.txt", "x")
    res = admin.post("/api/admin/import/course", files={"file": ("e.zip", buf.getvalue(), "application/zip")})
    assert res.status_code == 400 and "不正なパス" in res.json()["detail"]
    # zip でないファイルも拒否する
    res = admin.post("/api/admin/import/course", files={"file": ("e.zip", b"not zip", "application/zip")})
    assert res.status_code == 400


def test_import_unit_notebook(admin):
    course = admin.get("/api/admin/courses").json()[0]
    nb = (SAMPLE_COURSE / "03_central_tendency.ipynb").read_bytes()
    res = admin.post(f"/api/admin/courses/{course['id']}/import-unit", files={"file": ("03.ipynb", nb, "application/json")})
    assert res.status_code == 200
    unit = res.json()
    assert unit["position"] == 6 and unit["title"].startswith("代表値")
    # 書き方の誤りは理由つきでエラー
    res = admin.post(f"/api/admin/courses/{course['id']}/import-unit", files={"file": ("bad.ipynb", b"{}", "application/json")})
    assert res.status_code == 400


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
