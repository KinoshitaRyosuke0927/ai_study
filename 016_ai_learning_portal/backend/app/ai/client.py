"""AI への接続を扱うモジュール。

010_ai_reviewer と同じく、Azure OpenAI の v1 エンドポイントに OpenAI SDK(base_url 指定)で接続し、
JSON 形式の応答を受け取る。呼び出し側は AIClient の型だけに依存するため、接続方式やモデルを
変えるときはこのモジュールだけを直せばよい。
"""

from __future__ import annotations

from typing import Protocol

from app.config.settings import get_settings


class AIUnavailableError(Exception):
    """AI の接続情報が設定されていない、または AI の呼び出しに失敗した。"""


class AIClient(Protocol):
    """AI クライアントの型(JSON 形式で応答するチャット呼び出し)。"""

    def complete_json(self, system_prompt: str, user_prompt: str, model: str) -> str:
        """
        システムプロンプトとユーザプロンプトを送り、JSON 文字列の応答を返す

        Args
        -----------------
        - system_prompt: str,               システムプロンプト
        - user_prompt: str,                 ユーザプロンプト
        - model: str,                       モデル(デプロイ名)

        Returns
        -----------------
        - text: str,                        応答(JSON 文字列)

        """
        ...


class AzureOpenAIClient:
    """Azure OpenAI(OpenAI SDK + base_url)のクライアント。"""

    def __init__(self, endpoint: str, api_key: str, timeout: int) -> None:
        """
        クライアントを生成する

        Args
        -----------------
        - endpoint: str,                    Azure OpenAI のエンドポイント(v1)
        - api_key: str,                     API キー
        - timeout: int,                     1回の呼び出しのタイムアウト(秒)

        """
        # SDK は使うときだけ読み込む(テストや AI 未設定の環境で不要な初期化をしない)
        from openai import OpenAI

        # 010_ai_reviewer と同じ接続方式でクライアントを用意
        self._client = OpenAI(base_url=endpoint, api_key=api_key, timeout=timeout, max_retries=2)

    def complete_json(self, system_prompt: str, user_prompt: str, model: str) -> str:
        """
        JSON 形式で応答するようにして AI を呼び出す

        Args
        -----------------
        - system_prompt: str,               システムプロンプト
        - user_prompt: str,                 ユーザプロンプト
        - model: str,                       モデル(デプロイ名)

        Returns
        -----------------
        - text: str,                        応答(JSON 文字列)

        """
        # チャット形式で送信(応答は JSON オブジェクトに限定する)
        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )
        except Exception as e:  # SDK の例外を画面に出せる形にまとめる
            raise AIUnavailableError(f"AI の呼び出しに失敗しました: {e}") from e
        # 応答の本文を返却
        return (response.choices[0].message.content or "").strip()


# テストなどで差し替えたクライアント(None なら設定から生成する)
_override: AIClient | None = None


def set_ai_client(client: AIClient | None) -> None:
    """
    使用する AI クライアントを差し替える(テスト用)

    Args
    -----------------
    - client: AIClient | None,          差し替えるクライアント(None で元に戻す)

    """
    global _override
    # 差し替え先を保存
    _override = client


def get_ai_client() -> AIClient:
    """
    使用する AI クライアントを返す

    Returns
    -----------------
    - client: AIClient,                 AI クライアント

    """
    # 差し替えられていればそれを使う
    if _override is not None:
        return _override
    # 接続情報が無ければ使えない
    settings = get_settings()
    if not settings.ai_enabled:
        raise AIUnavailableError("AI の接続情報(AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_KEY)が設定されていません")
    # 設定から Azure OpenAI クライアントを生成して返却
    return AzureOpenAIClient(settings.azure_openai_endpoint, settings.azure_openai_key, settings.ai_timeout_seconds)


def ai_available() -> bool:
    """
    AI を使える状態かを返す

    Returns
    -----------------
    - available: bool,                  差し替え済み、または接続情報が設定されていれば True

    """
    # 差し替え済み、または接続情報があれば使える
    return _override is not None or get_settings().ai_enabled
