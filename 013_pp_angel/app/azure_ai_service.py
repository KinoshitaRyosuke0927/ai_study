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

from app.prompt import HEARING_SYSTEM_PROMPT, STYLE_ANALYSIS_PROMPT

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
# 画像生成・編集用モデルは、レート制限（RPM）を分散させるため同一モデルを複数デプロイし、
# リクエストごとに交互に振り分けて疑似的に並列度を上げる
MODEL_NAME_IMAGE_DEPLOYMENTS = ("gpt-image-2", "gpt-image-2-2")
# 画像生成・編集APIが受け付けるsizeオプション（幅x高さ）
IMAGE_SIZE_OPTIONS = ("1024x1024", "1536x1024", "1024x1536")
DEFAULT_IMAGE_SIZE = "1536x1024"

# Azure OpenAI クライアント用意
client = OpenAI(
    base_url=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY
)

# 画像生成・編集デプロイのラウンドロビン選択用（複数スレッドから呼ばれるためロックで保護する）
_image_deployment_cycle = itertools.cycle(MODEL_NAME_IMAGE_DEPLOYMENTS)
_image_deployment_lock = threading.Lock()


def _next_image_deployment() -> str:
    """
    画像生成・編集リクエストを振り分けるデプロイ名を、ラウンドロビンで1つ返す
    """
    with _image_deployment_lock:
        return next(_image_deployment_cycle)


def call_chat(history: list[dict[str, Any]]) -> dict[str, Any]:
    """
    会話履歴をAzure OpenAIに送信して、ヒアリング進行状況を表す構造化レスポンスを返す

    Args
    -----------------
    - history: list[dict[str, Any]],   role/content を持つ会話履歴（ユーザー・AIの発言）のリスト

    Returns
    -----------------
    - result: dict[str, Any],          message/options/style_proposals/ready_to_generate/slide_plan を含むJSON

    """
    messages = [{"role": "system", "content": HEARING_SYSTEM_PROMPT}, *history]

    # Azure OpenAI にリクエストを送信
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        response_format={"type": "json_object"},
    )
    text = response.choices[0].message.content.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # まれにAIがJSONオブジェクトの後に余分な文字列を付加することがあるため、
        # 先頭の1つのJSONオブジェクトのみを取り出して救済する
        obj, _ = json.JSONDecoder().raw_decode(text)
        return obj


def analyze_pptx_style(image_bytes: bytes) -> str:
    """
    アップロードされたpptxのスライド画像をVision対応チャットモデルに読み込ませ、
    配色・レイアウト傾向・雰囲気を、style_proposals生成の参考にできる説明文として言語化する

    Args
    -----------------
    - image_bytes: bytes,    分析対象のスライド画像（PNG）のバイト列

    Returns
    -----------------
    - style_description: str,    スタイルの説明文（日本語）

    """
    b64 = base64.b64encode(image_bytes).decode()
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": STYLE_ANALYSIS_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "このスライドのデザインスタイルを分析してください。"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            },
        ],
    )
    return response.choices[0].message.content.strip()


def call_image_generate(prompt: str, size: str = DEFAULT_IMAGE_SIZE) -> bytes:
    """
    元画像なしで、指示文からスライド画像を新規生成する（text-to-image）

    Args
    -----------------
    - prompt: str,    画像生成AIへの指示文
    - size: str,      生成する画像のsize（IMAGE_SIZE_OPTIONSのいずれか）

    Returns
    -----------------
    - image_bytes: bytes,    生成された画像（PNG）のバイト列

    """
    result = client.images.generate(
        model=_next_image_deployment(),
        prompt=prompt,
        size=size,
        n=1,
    )
    return base64.b64decode(result.data[0].b64_json)


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
        IMAGE_SIZE_OPTIONS,
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
        model=_next_image_deployment(),
        image=("slide.png", image_bytes, "image/png"),
        prompt=prompt,
        size=edit_size,
        n=1,
    )
    return base64.b64decode(result.data[0].b64_json)
