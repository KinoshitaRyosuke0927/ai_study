"""データベース接続を扱うモジュール。

SQLAlchemy 2.x(同期)を使用する。テーブル定義の変更は Alembic のマイグレーションで行う。
"""

from __future__ import annotations

from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import Settings, get_settings

# プロセス内で使い回すエンジンとセッションファクトリ
_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def build_engine(settings: Settings) -> Engine:
    """
    設定から SQLAlchemy Engine を生成する

    Args
    -----------------
    - settings: Settings,               アプリ設定

    Returns
    -----------------
    - engine: Engine,                   生成したエンジン

    """
    # 接続オプションの入れ物用意(DB が停止中のとき長く待たないよう、接続のタイムアウトを短くする)
    connect_args: dict = {"connect_timeout": 10}
    # CA 証明書が指定されている場合(Azure Database for MySQL)は TLS で接続する
    if settings.mysql_ssl_ca:
        connect_args["ssl"] = {"ca": settings.mysql_ssl_ca}
    # pool_pre_ping で切断済みコネクションを自動回復する
    return create_engine(
        settings.sqlalchemy_url,
        pool_pre_ping=True,
        pool_recycle=3600,
        connect_args=connect_args,
    )


def configure(engine: Engine) -> None:
    """
    アプリが使うエンジンを差し替える(テストで SQLite を使う場合など)

    Args
    -----------------
    - engine: Engine,                   使用するエンジン

    """
    global _engine, _session_factory
    # エンジンとセッションファクトリを入れ替える
    _engine = engine
    _session_factory = sessionmaker(bind=engine, expire_on_commit=False)


def get_engine() -> Engine:
    """
    アプリが使うエンジンを返す(未生成なら設定から生成)

    Returns
    -----------------
    - engine: Engine,                   エンジン

    """
    # 初回呼び出し時に設定からエンジンを生成する
    if _engine is None:
        configure(build_engine(get_settings()))
    # 生成済みのエンジンを返却
    return _engine  # type: ignore[return-value]


def get_db() -> Iterator[Session]:
    """
    FastAPI の依存性として使う、リクエスト単位のセッションを返す

    正常終了で commit、例外で rollback する。

    Returns
    -----------------
    - session: Session,                 DB セッション(ジェネレータで供給)

    """
    # エンジン未生成なら生成しておく
    get_engine()
    # セッションを開始
    session = _session_factory()  # type: ignore[misc]
    try:
        # リクエスト処理にセッションを渡す
        yield session
        # 正常終了したら確定
        session.commit()
    except Exception:
        # 例外時は巻き戻す
        session.rollback()
        raise
    finally:
        # 最後に必ずセッションを閉じる
        session.close()


def new_session() -> Session:
    """
    CLI など、リクエスト外で使うセッションを生成する

    Returns
    -----------------
    - session: Session,                 DB セッション(呼び出し側で close する)

    """
    # エンジン未生成なら生成しておく
    get_engine()
    # 新しいセッションを返却
    return _session_factory()  # type: ignore[misc]
