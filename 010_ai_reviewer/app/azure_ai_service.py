from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

from dotenv import load_dotenv
from openai import AzureOpenAI

# education 直下の .env を読み込む
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

## Azure OpenAI の接続情報を環境変数から取得
_raw_endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
# .env のエンドポイントが完全 URL の場合はベース URL だけを取り出す
_parsed = urlparse(_raw_endpoint)
AZURE_OPENAI_ENDPOINT = f"{_parsed.scheme}://{_parsed.netloc}/"

AZURE_OPENAI_KEY = os.environ["AZURE_OPENAI_KEY"]
API_VERSION = os.environ.get("AZURE_API_VERSION", "2024-12-01-preview")
MODEL_NAME = os.environ.get("AZURE_MODEL_NAME", "gpt-4o")

## Azure OpenAI クライアントを初期化
client = AzureOpenAI(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY,
    api_version=API_VERSION,
)


def call_review(prompt_package: dict[str, Any]) -> dict[str, Any]:
    """
    プロンプトパッケージをAzure OpenAIに送信してレビュー結果を返す

    Args
    -----------------
    - prompt_package: dict[str, Any],   system_prompt と user_prompt を含むプロンプトパッケージ

    Returns
    -----------------
    - result: dict[str, Any],           AIが生成したレビュー結果（JSON形式）

    """
    # Azure OpenAI にリクエストを送信
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": prompt_package["system_prompt"]},
            {"role": "user", "content": prompt_package["user_prompt"]},
        ],
        response_format={"type": "json_object"},
    )
    # レスポンスをJSONとして解析して返却
    text = response.choices[0].message.content.strip()
    return json.loads(text)
