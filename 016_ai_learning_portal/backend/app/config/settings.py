"""アプリ全体の設定を環境変数から一元的に読み込むモジュール。

コード中で直接 os.getenv を書かず、必ず get_settings() 経由で参照する。
ローカルでは backend/.env、Azure 上では App Service / Container Apps の
アプリ設定(環境変数)から同じ名前で読み込む。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ ディレクトリ(.env とフロントエンドのビルド成果物の基準位置)
BACKEND_DIR = Path(__file__).resolve().parents[2]
# リポジトリ直下(AI の接続情報など、ほかのアプリと共通の .env がある)
REPO_ROOT = BACKEND_DIR.parents[1]


class Settings(BaseSettings):
    """.env / 環境変数から読み込むアプリ設定。"""

    # リポジトリ直下の .env → backend/.env の順に読む(後に読んだ方が優先)
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    # --- アプリ ---
    app_env: str = Field(default="local", alias="APP_ENV")  # local / azure
    app_secret_key: str = Field(default="change-me", alias="APP_SECRET_KEY")
    app_session_max_age_days: int = Field(default=14, alias="APP_SESSION_MAX_AGE_DAYS")
    # フロントエンドのビルド成果物(本番配信用)。未ビルドなら API のみ提供する
    app_frontend_dist: str = Field(
        default=str(BACKEND_DIR.parent / "frontend" / "dist"), alias="APP_FRONTEND_DIST"
    )

    # --- MySQL ---
    mysql_host: str = Field(default="localhost", alias="MYSQL_HOST")
    mysql_port: int = Field(default=3306, alias="MYSQL_PORT")
    mysql_user: str = Field(default="ai_learning_portal", alias="MYSQL_USER")
    mysql_password: str = Field(default="changeme", alias="MYSQL_PASSWORD")
    mysql_database: str = Field(default="ai_learning_portal", alias="MYSQL_DATABASE")
    # Azure Database for MySQL は TLS 必須。CA 証明書のパスを指定すると TLS 接続する
    mysql_ssl_ca: str = Field(default="", alias="MYSQL_SSL_CA")

    # --- ブラウザ内 Python 実行(Pyodide) ---
    # CDN を使わず自前配信する場合は、配信先の URL(末尾 /)に差し替える
    pyodide_base_url: str = Field(
        default="https://cdn.jsdelivr.net/pyodide/v314.0.7/full/", alias="PYODIDE_BASE_URL"
    )

    # --- AI(Azure OpenAI。010_ai_reviewer と同じ接続方式) ---
    azure_openai_endpoint: str = Field(default="", alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_key: str = Field(default="", alias="AZURE_OPENAI_KEY")
    # 構成案の生成に使うモデル(デプロイ名)
    ai_model_outline: str = Field(default="gpt-5.4-mini", alias="AI_MODEL_OUTLINE")
    # 単元・小テストの下書き生成に使うモデル(デプロイ名)
    ai_model_draft: str = Field(default="gpt-5.4", alias="AI_MODEL_DRAFT")
    ai_timeout_seconds: int = Field(default=300, alias="AI_TIMEOUT_SECONDS")

    # --- DB の自動起動・停止(Azure Database for MySQL フレキシブルサーバー) ---
    # 有効にすると、DB が停止中のアクセスで DB を起動し、使われていなければ停止できる
    db_autostart_enabled: bool = Field(default=False, alias="DB_AUTOSTART_ENABLED")
    azure_subscription_id: str = Field(default="", alias="AZURE_SUBSCRIPTION_ID")
    azure_resource_group: str = Field(default="", alias="AZURE_RESOURCE_GROUP")
    mysql_server_name: str = Field(default="", alias="MYSQL_SERVER_NAME")
    # この時間(分)アクセスが無ければ、停止ジョブが DB を停止する
    db_idle_stop_minutes: int = Field(default=60, alias="DB_IDLE_STOP_MINUTES")

    # --- 派生プロパティ ---
    @property
    def ai_enabled(self) -> bool:
        """
        AI の接続情報が設定されているかを判定する

        Returns
        -----------------
        - enabled: bool,                    エンドポイントとキーが両方あれば True

        """
        # エンドポイントとキーの両方がそろっていれば利用できる
        return bool(self.azure_openai_endpoint.strip() and self.azure_openai_key.strip())

    @property
    def sqlalchemy_url(self) -> str:
        """
        SQLAlchemy の接続文字列を組み立てる

        Returns
        -----------------
        - url: str,                         MySQL(PyMySQL)の接続文字列

        """
        # パスワードに記号が含まれても壊れないよう URL エンコードする
        password = quote_plus(self.mysql_password)
        # 接続文字列を返却
        return (
            f"mysql+pymysql://{self.mysql_user}:{password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )

    @property
    def is_local(self) -> bool:
        """
        ローカル実行かどうかを判定する

        Returns
        -----------------
        - is_local: bool,                   ローカル実行なら True

        """
        # APP_ENV が local のときだけローカル扱いにする
        return self.app_env.strip().lower() == "local"


@lru_cache
def get_settings() -> Settings:
    """
    設定を読み込んで返す(プロセス内でキャッシュ)

    Returns
    -----------------
    - settings: Settings,               アプリ設定

    """
    # .env / 環境変数から設定を生成して返却
    return Settings()
