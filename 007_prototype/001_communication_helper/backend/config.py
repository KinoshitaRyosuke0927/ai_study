"""環境変数から設定値を読み込むモジュール。"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# パスの基準
# - APP_DIR: .env を置く場所（開発時はプロジェクト直下、exe 化時は exe と同じフォルダ）
# - RESOURCE_DIR: 同梱する画面・画像（frontend/, image/）の場所（exe 化時は PyInstaller の _internal/）
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
else:
    APP_DIR = Path(__file__).resolve().parent.parent
    RESOURCE_DIR = APP_DIR

# .env を読み込む（既存の環境変数は上書きしない）
load_dotenv(APP_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    """アプリ全体の設定値。"""

    azure_endpoint: str
    azure_key: str
    realtime_deployment: str
    transcribe_model: str
    eval_deployment: str
    session_max_minutes: int
    proactive_silence_sec: float


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
        proactive_silence_sec=float(os.getenv("PROACTIVE_SILENCE_SEC", "8")),
    )
