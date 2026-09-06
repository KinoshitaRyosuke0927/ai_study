from __future__ import annotations

import os
import sys
import json
import base64
import itertools
import threading
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image
from dotenv import load_dotenv
from openai import OpenAI

# 環境変数(.env)を読み込む（010_ai_reviewerと同じリポジトリ直下の.envを共有する）
if getattr(sys, "frozen", False):
    _env_path = Path(sys.executable).resolve().parent / ".env"
else:
    _env_path = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(_env_path)

## Azure OpenAI の接続情報を環境変数から取得（010_ai_reviewerと共有）
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY", "")

# テキスト＋画像を扱う既定デプロイ（010_ai_reviewerのレビュー用モデルと共通）
DEFAULT_MODEL = "gpt-5.4-mini"

# 技術面レビュー（実装利用者・利用シーンを具体的に想像した上での実現可能性評価）は
# より踏み込んだ推論が必要なため、010_ai_reviewerの想定質問生成と同じ上位モデルを使う
TECHNICAL_MODEL = "gpt-5.4"

# 想定質問生成（AI技術者・エンジニア視点で資料に出そうな技術的質問を予測）も、
# 010_ai_reviewer と同じく上位モデルを使う
QA_MODEL = "gpt-5.4"

# 画像編集用モデルは、レート制限（RPM）を分散させるため同一モデルを複数デプロイし、
# リクエストごとに交互に振り分けて疑似的に並列度を上げる（010_ai_reviewerと同じ構成）
MODEL_NAME_IMAGE_DEPLOYMENTS = ("gpt-image-2", "gpt-image-2-2")
# 画像編集APIが受け付けるsizeオプション（幅x高さ）
IMAGE_EDIT_SIZE_OPTIONS = ("1024x1024", "1536x1024", "1024x1536")

# Azure OpenAI クライアント用意
client = OpenAI(
    base_url=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY,
)

# 画像編集デプロイのラウンドロビン選択用（複数スレッドから呼ばれるためロックで保護する）
_image_deployment_cycle = itertools.cycle(MODEL_NAME_IMAGE_DEPLOYMENTS)
_image_deployment_lock = threading.Lock()


def _next_image_deployment() -> str:
    """画像編集リクエストを振り分けるデプロイ名を、ラウンドロビンで1つ返す"""
    with _image_deployment_lock:
        return next(_image_deployment_cycle)


def call_structured(prompt_package: dict[str, Any], model: str = DEFAULT_MODEL) -> dict[str, Any]:
    """
    プロンプトパッケージを指定モデルでAzure OpenAIに送信し、JSON形式の結果を返す

    候補生成・上司嗜好スコアリング・criticのすべての層がこの関数を共通で呼び出す
    （010_ai_reviewer/app/azure_ai_service.py の _call_chat を汎用化したもの）

    Args
    -----------------
    - prompt_package: dict[str, Any],   system_prompt と user_prompt を含むプロンプトパッケージ
    - model: str,                       送信先のAzure OpenAIデプロイモデル名

    Returns
    -----------------
    - result: dict[str, Any],           AIが生成した結果（JSON形式）

    """
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": prompt_package["system_prompt"]},
            {"role": "user", "content": prompt_package["user_prompt"]},
        ],
        response_format={"type": "json_object"},
    )
    text = response.choices[0].message.content.strip()
    return json.loads(text)


def _pick_edit_size(width: int, height: int) -> str:
    """
    元画像の縦横比に最も近い画像編集APIのsizeオプションを選ぶ（010_ai_reviewerと同一ロジック）

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
    元のスライド画像を指示文に従って編集し、修正後の画像バイト列を返す（010_ai_reviewerと同一ロジック）

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

    edit_size = _pick_edit_size(original_width, original_height)

    result = client.images.edit(
        model=_next_image_deployment(),
        image=("slide.png", image_bytes, "image/png"),
        prompt=prompt,
        size=edit_size,
        n=1,
    )
    return base64.b64decode(result.data[0].b64_json)
