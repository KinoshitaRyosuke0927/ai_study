"""データベース接続とスキーマ適用を扱うモジュール。

SQLAlchemy 2.x(同期)を使用。プロトタイプのため Alembic は使わず、
起動時に schema.sql を CREATE TABLE IF NOT EXISTS で適用する。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from settings import Settings, get_settings

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# プロセス内でエンジンを使い回すためのキャッシュ(接続文字列ごと)
_engines: dict[str, Engine] = {}
_session_factories: dict[str, sessionmaker] = {}


def get_engine(settings: Settings | None = None) -> Engine:
    """接続文字列に対応する SQLAlchemy Engine を返す(生成済みなら再利用)。"""
    settings = settings or get_settings()
    url = settings.sqlalchemy_url
    if url not in _engines:
        # pool_pre_ping で切断済みコネクションを自動回復する
        _engines[url] = create_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=3600,
            future=True,
        )
        _session_factories[url] = sessionmaker(
            bind=_engines[url], expire_on_commit=False, future=True
        )
    return _engines[url]


def get_session_factory(settings: Settings | None = None) -> sessionmaker:
    """セッションファクトリを返す。"""
    get_engine(settings)
    settings = settings or get_settings()
    return _session_factories[settings.sqlalchemy_url]


def session_scope(settings: Settings | None = None) -> Iterator[Session]:
    """with 文で使うトランザクション境界付きセッション。

    正常終了で commit、例外で rollback する。
    """
    factory = get_session_factory(settings)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _split_sql_statements(sql: str) -> list[str]:
    """schema.sql をステートメント単位へ分割する。

    行コメント(-- )を除去したうえでセミコロンで分割する。
    プロトタイプの schema.sql は関数定義など複雑な区切りを含まない前提。
    """
    # 各行から行コメントを除去
    lines: list[str] = []
    for raw in sql.splitlines():
        without_comment = re.sub(r"--.*$", "", raw)
        lines.append(without_comment)
    joined = "\n".join(lines)
    # セミコロン区切りで分割し、空要素を落とす
    return [s.strip() for s in joined.split(";") if s.strip()]


def apply_schema(settings: Settings | None = None) -> None:
    """schema.sql を読み込み、各 CREATE TABLE を実行する。"""
    settings = settings or get_settings()
    engine = get_engine(settings)
    statements = _split_sql_statements(_SCHEMA_PATH.read_text(encoding="utf-8"))
    # 1 ステートメントずつ実行(IF NOT EXISTS のため再実行しても安全)
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
    logger.info("スキーマ適用完了: %d ステートメント / db=%s", len(statements), settings.mysql_database)


def ping(settings: Settings | None = None) -> bool:
    """DB へ接続できるか確認する(ヘルスチェック用)。"""
    try:
        engine = get_engine(settings)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # pragma: no cover - 接続失敗時のログのみ
        logger.error("DB ping 失敗: %s", exc)
        return False


def reset_engine_cache() -> None:
    """テストで接続先を切り替える際にキャッシュを破棄する。"""
    for engine in _engines.values():
        engine.dispose()
    _engines.clear()
    _session_factories.clear()
