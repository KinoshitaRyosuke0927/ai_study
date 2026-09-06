"""pytest 共通設定。

- テスト用 DB(frontier_test)を使うよう環境変数を上書きする。
  環境変数は .env より優先されるため、これで接続先が切り替わる。
- リポジトリルートを import パスへ追加する。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

# --- テスト用 DB / モード ---
os.environ.setdefault("MYSQL_DATABASE", "frontier_test")
os.environ.setdefault("MYSQL_USER", os.environ.get("MYSQL_USER", "frontier"))
os.environ.setdefault("MYSQL_PASSWORD", os.environ.get("MYSQL_PASSWORD", "frontier_pw"))
os.environ.setdefault("MYSQL_HOST", "localhost")
os.environ.setdefault("MYSQL_PORT", "3306")
os.environ.setdefault("APP_RUN_MODE", "sample")
os.environ.setdefault("APP_SCHEDULE_ENABLED", "false")
# AI は必ずフォールバックに(テストで Azure OpenAI を呼ばない)
os.environ["AZURE_OPENAI_ENDPOINT"] = ""
os.environ["AZURE_OPENAI_API_KEY"] = "changeme"

import pytest  # noqa: E402

from infra.db import apply_schema, get_engine, get_session_factory  # noqa: E402
from config.settings import get_settings  # noqa: E402


@pytest.fixture(scope="session")
def settings():
    """テスト用 Settings。"""
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture()
def db_session(settings):
    """スキーマ適用済みのクリーンな DB セッションを返す。

    各テストの冒頭で全テーブルを TRUNCATE する。
    """
    from sqlalchemy import text

    apply_schema(settings)
    factory = get_session_factory(settings)
    session = factory()
    # 依存関係の無い順で全消去
    session.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
    for table in [
        "embeddings",
        "analysis_feature_refs", "analysis_features", "analysis_runs",
        "spec_code_diff_items", "spec_code_diffs",
        "mm_account_analysis_refs", "mm_account_analysis_items", "mm_account_analyses",
        "mm_chunks", "mm_posts", "mm_users", "mm_channels", "mm_ingest_runs",
        "tr_account_analysis_refs", "tr_account_analysis_items", "tr_account_analyses",
        "tr_chunks", "tr_activity", "tr_card_members", "tr_cards", "tr_lists",
        "tr_members", "tr_boards", "tr_ingest_runs",
        "gh_author_analysis_refs", "gh_author_analysis_items", "gh_author_analyses",
        "gh_change_chunks", "gh_commit_files", "gh_commits", "gh_files",
        "gh_history_ingest_runs",
        "gh_activity_chunks", "gh_activity", "gh_pull_requests", "gh_branches",
        "gh_activity_ingest_runs", "gh_users",
        "user_activity_analysis_items", "user_activity_analyses",
        "kpt_analysis_items", "kpt_analyses",
        "pipeline_run_steps", "pipeline_runs",
    ]:
        session.execute(text(f"TRUNCATE TABLE {table}"))
    session.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    session.commit()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
