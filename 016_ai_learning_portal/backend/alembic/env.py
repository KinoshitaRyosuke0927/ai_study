"""Alembic のマイグレーション実行環境。

接続先はアプリと同じ設定(.env / 環境変数)から読み込む。
    alembic upgrade head                            … 最新まで適用
    alembic revision --autogenerate -m "説明"       … モデル変更からマイグレーションを作成
"""

from __future__ import annotations

from alembic import context

from app.config.settings import get_settings
from app.infra.db import build_engine
from app.models import Base

# 比較対象のメタデータ(autogenerate 用)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    DB に接続せず SQL を出力するモードで実行する
    """
    # 接続文字列だけを渡して SQL を生成
    context.configure(
        url=get_settings().sqlalchemy_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    DB に接続してマイグレーションを適用する
    """
    # アプリと同じ設定でエンジンを生成(TLS 設定も共通)
    engine = build_engine(get_settings())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


# 実行モードに応じて分岐
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
