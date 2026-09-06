from __future__ import annotations

from typing import Any

from app.core.azure_client import QA_MODEL, call_structured
from app.prompts.qa_prompts import build_anticipated_questions_prompt_package


def generate_anticipated_questions(
    slides: list[dict[str, Any]],
    overall_intended_message: str,
) -> list[dict[str, str]]:
    """
    資料全体のスライド画像から、AI技術者・エンジニア視点での想定質問を生成する
    （010_ai_reviewer の /api/anticipated-questions と同一方針。指摘事項パイプラインとは独立して実行する）

    Args
    -----------------
    - slides: list[dict[str, Any]],     スライドデータ（slide_number, image_png_b64）のリスト
    - overall_intended_message: str,    資料全体で伝えたい内容

    Returns
    -----------------
    - questions: list[dict[str, str]],  question / hint を持つ想定質問のリスト

    """
    # プロンプト構築 → 上位モデルへ1回問い合わせ
    package = build_anticipated_questions_prompt_package(
        slides=slides,
        overall_intended_message=overall_intended_message,
    )
    result = call_structured(package, model=QA_MODEL)

    # AI出力の各要素を question / hint 文字列に正規化する（想定外の形式の要素はスキップ）
    questions: list[dict[str, str]] = []
    for entry in result.get("questions", []):
        if not isinstance(entry, dict):
            continue
        question = str(entry.get("question", "")).strip()
        if not question:
            continue
        questions.append({"question": question, "hint": str(entry.get("hint", "")).strip()})
    return questions
