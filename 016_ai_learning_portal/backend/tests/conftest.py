"""テスト共通の準備(SQLite のインメモリ DB で API を動かす)。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

from app.infra import db
from app.models import Base
from app.services.auth_service import create_user
from app.services.notebook_import import import_course

# サンプル講座のフォルダ
SAMPLE_COURSE = Path(__file__).resolve().parents[2] / "content" / "statistics-basics"


@pytest.fixture()
def engine():
    """
    テスト用のインメモリ DB を用意する

    Returns
    -----------------
    - engine: Engine,                   SQLite のエンジン(テストごとに作り直す)

    """
    # 全コネクションで同じインメモリ DB を共有する
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    # SQLite で外部キー制約(ON DELETE CASCADE)を有効にする
    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    # テーブルを作成し、アプリのエンジンを差し替える
    Base.metadata.create_all(eng)
    db.configure(eng)
    yield eng
    # 差し替えた AI・DB 操作・アクセス記録の状態を元に戻す
    from app.ai.client import set_ai_client
    from app.infra.db_power import set_db_power
    from app.services.activity_service import reset_throttle

    set_ai_client(None)
    set_db_power(None)
    reset_throttle()
    eng.dispose()


@pytest.fixture()
def seeded(engine):
    """
    ユーザ2名とサンプル講座を登録する

    Args
    -----------------
    - engine: Engine,                   テスト用 DB

    """
    # 受講者・管理者とサンプル講座を登録して確定
    with db.new_session() as session:
        create_user(session, "learner", "受講者", "pw-learner", is_admin=False)
        admin = create_user(session, "admin", "管理者", "pw-admin", is_admin=True)
        import_course(session, SAMPLE_COURSE, author=admin)
        session.commit()


@pytest.fixture()
def client(seeded):
    """
    受講者でログイン済みの API クライアントを返す

    Args
    -----------------
    - seeded: None,                     データ登録済みの DB

    Returns
    -----------------
    - client: TestClient,               ログイン済みクライアント

    """
    # アプリを読み込んでクライアントを生成
    from app.main import app

    c = TestClient(app)
    # 受講者でログイン
    res = c.post("/api/auth/login", json={"login_name": "learner", "password": "pw-learner"})
    assert res.status_code == 200
    return c
