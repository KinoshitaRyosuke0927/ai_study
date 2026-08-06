from __future__ import annotations

import os
import sys
import json
import base64
from io import BytesIO
from typing import Any
from pathlib import Path

from PIL import Image
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
# 想定質問生成用のモデルの名称
MODEL_NAME_QA = "gpt-5.4"
MODEL_NAME_IMAGE = "gpt-image-2"
# 画像編集APIが受け付けるsizeオプション（幅x高さ）
IMAGE_EDIT_SIZE_OPTIONS = ("1024x1024", "1536x1024", "1024x1536")

# Azure OpenAI クライアント用意
client = OpenAI(
    base_url=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY
)


def _call_chat(prompt_package: dict[str, Any], model: str) -> dict[str, Any]:
    """
    プロンプトパッケージを指定モデルでAzure OpenAIに送信し、JSON形式の結果を返す

    Args
    -----------------
    - prompt_package: dict[str, Any],   system_prompt と user_prompt を含むプロンプトパッケージ
    - model: str,                       送信先のAzure OpenAIデプロイモデル名

    Returns
    -----------------
    - result: dict[str, Any],           AIが生成した結果（JSON形式）

    """
    # Azure OpenAI にリクエストを送信
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": prompt_package["system_prompt"]},
            {"role": "user", "content": prompt_package["user_prompt"]},
        ],
        response_format={"type": "json_object"},
    )
    # レスポンスをJSONとして解析して返却
    text = response.choices[0].message.content.strip()
    return json.loads(text)


def call_review(prompt_package: dict[str, Any]) -> dict[str, Any]:
    """
    プロンプトパッケージをAzure OpenAI（レビュー用モデル）に送信してレビュー結果を返す

    Args
    -----------------
    - prompt_package: dict[str, Any],   system_prompt と user_prompt を含むプロンプトパッケージ

    Returns
    -----------------
    - result: dict[str, Any],           AIが生成したレビュー結果（JSON形式）

    """
    return _call_chat(prompt_package, MODEL_NAME)


def call_qa(prompt_package: dict[str, Any]) -> dict[str, Any]:
    """
    プロンプトパッケージをAzure OpenAI（想定質問生成用モデル）に送信して想定質問の生成結果を返す

    Args
    -----------------
    - prompt_package: dict[str, Any],   system_prompt と user_prompt を含むプロンプトパッケージ

    Returns
    -----------------
    - result: dict[str, Any],           AIが生成した想定質問の生成結果（JSON形式）

    """
    return _call_chat(prompt_package, MODEL_NAME_QA)


def _pick_edit_size(width: int, height: int) -> str:
    """
    元画像の縦横比に最も近い画像編集APIのsizeオプションを選ぶ

    Args
    -----------------
    - width: int,    元画像の幅
    - height: int,   元画像の高さ

    Returns
    -----------------
    - size: str,     画像編集APIに渡すsizeオプション（例: "1536x1024"）

    """
    ratio = width / height
    return min(
        IMAGE_EDIT_SIZE_OPTIONS,
        key=lambda size: abs((lambda w, h: w / h)(*(int(v) for v in size.split("x"))) - ratio),
    )


def call_image_edit(prompt: str, image_bytes: bytes) -> bytes:
    """
    元のスライド画像を指示文に従って編集し、修正後の画像バイト列を返す

    画像編集APIは元画像と縦横比が異なるsizeでしか生成できないため、最も近いsizeオプションを選ぶ

    Args
    -----------------
    - prompt: str,           画像編集AIへの指示文
    - image_bytes: bytes,    編集対象の元スライド画像（PNG）のバイト列

    Returns
    -----------------
    - image_bytes: bytes,    編集後のスライド画像（PNG）のバイト列

    """
    with Image.open(BytesIO(image_bytes)) as original_img:
        original_width, original_height = original_img.size

    # 元画像の縦横比に最も近いsizeオプションを選んで画像編集APIにリクエストを送信
    edit_size = _pick_edit_size(original_width, original_height)

    result = client.images.edit(
        model=MODEL_NAME_IMAGE,
        image=("slide.png", image_bytes, "image/png"),
        prompt=prompt,
        size=edit_size,
        n=1,
    )
    return base64.b64decode(result.data[0].b64_json)
