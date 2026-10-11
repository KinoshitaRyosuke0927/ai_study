"""環境変数から設定値を読み込むモジュール。"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# プロジェクト直下の .env を読み込む（既存の環境変数は上書きしない）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    """アプリ全体の設定値。"""

    azure_endpoint: str
    azure_key: str
    realtime_deployment: str
    transcribe_model: str
    eval_deployment: str
    session_max_minutes: int


def load_settings() -> Settings:
    """環境変数から設定を組み立てる。

    Returns:
        Settings: 読み込んだ設定値。

    Raises:
        RuntimeError: 必須の環境変数が未設定の場合。
    """
    # 必須項目の存在チェック
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
    key = os.getenv("AZURE_OPENAI_KEY", "")
    if not endpoint or not key:
        raise RuntimeError("AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_KEY が .env に設定されていません")

    # 任意項目はデフォルト値で補完
    return Settings(
        azure_endpoint=endpoint,
        azure_key=key,
        realtime_deployment=os.getenv("AZURE_REALTIME_DEPLOYMENT", "gpt-realtime-mini"),
        transcribe_model=os.getenv("AZURE_TRANSCRIBE_MODEL", "gpt-transcribe"),
        eval_deployment=os.getenv("AZURE_EVAL_DEPLOYMENT", "gpt-5.4-mini"),
        session_max_minutes=int(os.getenv("SESSION_MAX_MINUTES", "10")),
    )
