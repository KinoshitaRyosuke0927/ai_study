from __future__ import annotations

import os
import sys
import json
from typing import Any
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from openai import OpenAI

# 環境変数(.env)を読み込む
if getattr(sys, "frozen", False):
    _env_path = Path(sys.executable).resolve().parent / ".env"
else:
    _env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_env_path)

## Azure OpenAI の接続情報を環境変数から取得
# Azure OpenAIのエンドポイント
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
# Azure OpenAIのAPIキー
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY", "")
# デプロイしたモデルの名称
MODEL_NAME = "gpt-5.4-mini"

# Azure OpenAI クライアント用意
client = OpenAI(
    base_url=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY
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
