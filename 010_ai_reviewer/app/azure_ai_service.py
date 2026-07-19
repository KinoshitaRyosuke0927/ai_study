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
MODEL_NAME_IMAGE = "gpt-image-2"
# 画像編集APIが受け付けるsizeオプション（幅x高さ）
IMAGE_EDIT_SIZE_OPTIONS = ("1024x1024", "1536x1024", "1024x1536")

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


def _fit_to_size(image_bytes: bytes, target_width: int, target_height: int) -> bytes:
    """
    画像を中央基準でクロップ・リサイズし、指定した幅・高さ（縦横比）に合わせる

    Args
    -----------------
    - image_bytes: bytes,      対象画像のバイト列
    - target_width: int,       合わせたい幅
    - target_height: int,      合わせたい高さ

    Returns
    -----------------
    - image_bytes: bytes,      幅・高さを合わせた画像（PNG）のバイト列

    """
    target_ratio = target_width / target_height
    with Image.open(BytesIO(image_bytes)) as img:
        img = img.convert("RGB")
        width, height = img.size
        current_ratio = width / height
        if current_ratio > target_ratio:
            # 横長すぎる場合は左右をクロップ
            crop_width = round(height * target_ratio)
            left = (width - crop_width) // 2
            img = img.crop((left, 0, left + crop_width, height))
        elif current_ratio < target_ratio:
            # 縦長すぎる場合は上下をクロップ
            crop_height = round(width / target_ratio)
            top = (height - crop_height) // 2
            img = img.crop((0, top, width, top + crop_height))
        img = img.resize((target_width, target_height), Image.LANCZOS)

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()


def _build_safe_area_instruction(edit_width: int, edit_height: int, target_width: int, target_height: int) -> str:
    """
    生成後に中央クロップされる範囲を踏まえ、要素が見切れないようにする指示文を作成する

    Args
    -----------------
    - edit_width: int,      画像編集APIに指定するsizeの幅
    - edit_height: int,     画像編集APIに指定するsizeの高さ
    - target_width: int,    最終的に合わせたい幅（元スライド画像の幅）
    - target_height: int,   最終的に合わせたい高さ（元スライド画像の高さ）

    Returns
    -----------------
    - instruction: str,     セーフエリアに関する追加指示文（クロップが発生しない場合は空文字）

    """
    edit_ratio = edit_width / edit_height
    target_ratio = target_width / target_height
    if abs(edit_ratio - target_ratio) < 1e-6:
        return ""

    if edit_ratio > target_ratio:
        # 生成画像は横長すぎるため、生成後に左右を中央クロップする
        visible_ratio = target_ratio / edit_ratio
        margin_percent = round((1 - visible_ratio) / 2 * 100)
        side = "左右"
    else:
        # 生成画像は縦長すぎるため、生成後に上下を中央クロップする
        visible_ratio = edit_ratio / target_ratio
        margin_percent = round((1 - visible_ratio) / 2 * 100)
        side = "上下"

    return (
        f"この画像は生成後に中央基準で{side}をそれぞれ約{margin_percent}%トリミングされます。"
        f"文字・見出し・図表・ロゴなど、見切れて困る要素は画像の{side}端から約{margin_percent}%の範囲には配置せず、"
        "中央のセーフエリア内に収めてください。"
    )


def call_image_edit(prompt: str, image_bytes: bytes) -> bytes:
    """
    元のスライド画像を指示文に従って編集し、修正後の画像バイト列を返す

    元画像と縦横比が異なるsizeでしか生成できないため、生成後に元画像と同じ幅・高さへ
    中央クロップ＋リサイズして、縦横比を元画像に合わせる。クロップで要素が見切れないよう、
    生成前にセーフエリアの指示をプロンプトへ追加する。

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
    edit_width, edit_height = (int(v) for v in edit_size.split("x"))

    # 生成後のクロップで要素が見切れないよう、セーフエリアの指示を追加
    safe_area_instruction = _build_safe_area_instruction(edit_width, edit_height, original_width, original_height)
    if safe_area_instruction:
        prompt = f"{prompt}\n{safe_area_instruction}"

    result = client.images.edit(
        model=MODEL_NAME_IMAGE,
        image=("slide.png", image_bytes, "image/png"),
        prompt=prompt,
        size=edit_size,
        n=1,
    )
    edited_bytes = base64.b64decode(result.data[0].b64_json)

    # 生成された画像を元画像と同じ縦横比になるよう調整
    return _fit_to_size(edited_bytes, original_width, original_height)
