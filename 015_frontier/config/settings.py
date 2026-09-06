"""アプリ全体の設定を環境変数から一元的に読み込むモジュール。

コード中で直接 os.getenv を書かず、必ず get_settings() 経由で参照する。
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """.env / 環境変数から読み込むアプリ設定。

    .env が存在しない場合でも各フィールドのデフォルト値で起動でき、
    APP_RUN_MODE=sample のままサンプルデータモードで動作する。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    # --- アプリ ---
    app_tz: str = Field(default="Asia/Tokyo", alias="APP_TZ")
    app_run_mode: str = Field(default="sample", alias="APP_RUN_MODE")  # sample / real

    # --- MySQL ---
    mysql_host: str = Field(default="localhost", alias="MYSQL_HOST")
    mysql_port: int = Field(default=3306, alias="MYSQL_PORT")
    mysql_user: str = Field(default="frontier", alias="MYSQL_USER")
    mysql_password: str = Field(default="changeme", alias="MYSQL_PASSWORD")
    mysql_database: str = Field(default="frontier", alias="MYSQL_DATABASE")

    # --- Mattermost ---
    mattermost_url: str = Field(default="", alias="MATTERMOST_URL")
    mattermost_token: str = Field(default="", alias="MATTERMOST_TOKEN")
    mattermost_channel_id: str = Field(default="", alias="MATTERMOST_CHANNEL_ID")

    # --- GitHub ---
    github_token: str = Field(default="", alias="GITHUB_TOKEN")
    github_repos: str = Field(default="", alias="GITHUB_REPOS")  # カンマ区切り

    # --- GROWI ---
    growi_url: str = Field(default="", alias="GROWI_URL")
    growi_api_token: str = Field(default="", alias="GROWI_API_TOKEN")
    growi_target_paths: str = Field(default="", alias="GROWI_TARGET_PATHS")  # カンマ区切り
    # ID/パスワード: API トークンが使えない構成でフォームログインする場合の予備
    growi_id: str = Field(default="", alias="GROWI_ID")
    growi_password: str = Field(default="", alias="GROWI_PASSWORD")

    # --- Trello ---
    trello_api_key: str = Field(default="", alias="TRELLO_API_KEY")
    trello_token: str = Field(default="", alias="TRELLO_TOKEN")
    trello_board_id: str = Field(default="", alias="TRELLO_BOARD_ID")

    # --- Azure OpenAI ---
    azure_openai_endpoint: str = Field(default="", alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key: str = Field(default="", alias="AZURE_OPENAI_API_KEY")
    azure_openai_api_version: str = Field(
        default="2024-12-01-preview", alias="AZURE_OPENAI_API_VERSION"
    )
    azure_openai_chat_deployment: str = Field(
        default="gpt-4o", alias="AZURE_OPENAI_CHAT_DEPLOYMENT"
    )
    azure_openai_embedding_deployment: str = Field(
        default="text-embedding-3-small", alias="AZURE_OPENAI_EMBEDDING_DEPLOYMENT"
    )

    # --- 派生プロパティ ---
    @property
    def is_sample_mode(self) -> bool:
        """サンプルデータモードかどうか。"""
        return self.app_run_mode.strip().lower() != "real"

    @property
    def sqlalchemy_url(self) -> str:
        """SQLAlchemy 用の MySQL 接続文字列(utf8mb4)。"""
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            f"?charset=utf8mb4"
        )

    @property
    def github_repo_list(self) -> list[str]:
        """"owner/repo" のリスト。"""
        return [r.strip() for r in self.github_repos.split(",") if r.strip()]

    @property
    def growi_path_list(self) -> list[str]:
        """対象 GROWI パスのリスト。"""
        return [p.strip() for p in self.growi_target_paths.split(",") if p.strip()]

    @property
    def ai_enabled(self) -> bool:
        """Azure OpenAI へ実接続できる設定が揃っているか。"""
        return bool(
            self.azure_openai_endpoint
            and self.azure_openai_api_key
            and self.azure_openai_api_key != "changeme"
        )


@lru_cache
def get_settings() -> Settings:
    """設定シングルトンを返す(プロセス内で 1 度だけ読み込む)。"""
    return Settings()  # type: ignore[call-arg]
