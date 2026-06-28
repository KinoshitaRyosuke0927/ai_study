from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


_CSV_PATH = Path(__file__).parent.parent / "review_point.csv"


def _load_review_points() -> tuple[list[str], dict[str, list[str]]]:
    """CSVからレビュー観点を読み込み、overall と perspective_type別辞書に分けて返す"""
    overall: list[str] = []
    by_type: dict[str, list[str]] = {}
    with _CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            detail = row.get("detail", "").strip()
            if not detail:
                continue
            ptype = row.get("perspective_type", "").strip()
            if ptype == "overall":
                overall.append(detail)
            else:
                by_type.setdefault(ptype, []).append(detail)
    return overall, by_type


SYSTEM_PROMPT = """
あなたはプレゼンテーション資料のレビュー専門アシスタントです。
出力は必ずJSONのみで返してください。文章の前置きやコードブロックは禁止です。
各レビュー観点について、以下のルールに従って result フィールドを返してください:
- インプットの情報からは判断がつかない場合には、「判断ができません」とだけ返してください。他の文章を追加することは禁止です。
- レビューした結果、問題がない場合は「指摘事項はありません」とだけ返してください。無理に指摘事項を挙げることはせず、他の文章を追加することも禁止です。
- 問題がある場合のみ、具体的な指摘内容を返してください。
"""


def _build_slide_images_content(slides: list[dict]) -> list[dict[str, Any]]:
    """スライドごとの画像＋ラベルのコンテンツブロックを構築する"""
    content: list[dict[str, Any]] = []
    for slide in slides:
        label = f"スライド {slide['slide_number']}"
        if slide.get("intended_message"):
            label += f" / 伝えたい内容: {slide['intended_message']}"
        content.append({"type": "text", "text": label})
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{slide['image_jpeg_b64']}"},
        })
    return content


def build_overall_prompt_package(review_request: dict[str, Any]) -> dict[str, Any]:
    """全体評価用プロンプトパッケージを構築する"""
    overall_points, _ = _load_review_points()
    slides = review_request["slides"]
    overall_msg = review_request.get("overall_intended_message", "")

    questions_text = "\n".join(f"- {p}" for p in overall_points)
    schema = {
        "presentation_summary": {
            "reviews": [{"question": p, "result": "string"} for p in overall_points]
        }
    }

    intro = f"{len(slides)}枚のスライドからなるプレゼンテーション全体を評価してください。"
    if overall_msg:
        intro += f"\nプレゼンテーション全体の意図: {overall_msg}"
    intro += f"\n\nレビュー観点:\n{questions_text}"
    intro += "\n\n以下のスキーマでJSONのみを返してください:\n" + json.dumps(schema, ensure_ascii=False, indent=2)

    content: list[dict[str, Any]] = [{"type": "text", "text": intro}]
    content.extend(_build_slide_images_content(slides))
    content.append({"type": "text", "text": "プレゼンテーション全体を評価し、JSONのみで返してください。"})

    return {"system_prompt": SYSTEM_PROMPT, "user_prompt": content}


def _build_slides_prompt_package_for_points(
    review_request: dict[str, Any],
    review_points: list[str],
) -> dict[str, Any]:
    """指定したレビュー観点セットでスライド個別評価プロンプトパッケージを構築する"""
    slides = review_request["slides"]
    overall_msg = review_request.get("overall_intended_message", "")

    questions_text = "\n".join(f"- {p}" for p in review_points)
    schema = {
        "slides": [
            {
                "slide_number": 1,
                "reviews": [{"question": p, "result": "string"} for p in review_points],
            }
        ]
    }

    intro = f"{len(slides)}枚のスライドをそれぞれ個別にレビューしてください。"
    if overall_msg:
        intro += f"\nプレゼンテーション全体の意図: {overall_msg}"
    intro += f"\n\nレビュー観点:\n{questions_text}"
    intro += "\n\n以下のスキーマでJSONのみを返してください:\n" + json.dumps(schema, ensure_ascii=False, indent=2)

    content: list[dict[str, Any]] = [{"type": "text", "text": intro}]
    content.extend(_build_slide_images_content(slides))
    content.append({"type": "text", "text": "各スライドを個別にレビューし、JSONのみで返してください。"})

    return {"system_prompt": SYSTEM_PROMPT, "user_prompt": content}


_SUMMARIZE_SYSTEM_PROMPT = """
あなたはプレゼンテーション資料のレビュー専門アシスタントです。
出力は必ずJSONのみで返してください。文章の前置きやコードブロックは禁止です。
各スライドのレビュー結果（Q&A形式）を、スライドごとに自然な日本語文章にまとめてください。
- 「判断ができません」の結果がある場合は、判断するための情報が足りていない旨を記載してください。
- 「指摘事項はありません」の結果は無視し、まとめ文には含めないでください。
- 実際の指摘事項がある結果のみを対象に、まとめた文章を作成してください。複数文になっても構いません。
- 対象となる指摘事項が1件もない場合は summary に「特に指摘事項はありません」とだけ返してください。
"""


def build_summarize_prompt_package(
    ptype_label: str,
    slides_reviews: list[dict[str, Any]],
) -> dict[str, Any]:
    """perspective_typeのQ&Aレビュー結果を集約するプロンプトパッケージを構築する"""
    reviews_text = ""
    for slide in slides_reviews:
        reviews_text += f"\nスライド {slide['slide_number']}:\n"
        for r in slide.get("reviews", []):
            reviews_text += f"  Q: {r['question']}\n  A: {r['result']}\n"

    schema = {"slides": [{"slide_number": 1, "summary": "string"}]}

    prompt = (
        f"観点カテゴリ「{ptype_label}」に関する各スライドのレビュー結果を、"
        "スライドごとにまとめた文章にしてください。\n"
        f"\nレビュー結果:{reviews_text}"
        "\n\n以下のスキーマでJSONのみを返してください:\n"
        + json.dumps(schema, ensure_ascii=False, indent=2)
    )

    return {
        "system_prompt": _SUMMARIZE_SYSTEM_PROMPT,
        "user_prompt": [{"type": "text", "text": prompt}],
    }


def build_slides_prompt_packages_by_type(
    review_request: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    """perspective_typeごとの (perspective_type, プロンプトパッケージ) リストを返す"""
    _, by_type = _load_review_points()
    return [
        (ptype, _build_slides_prompt_package_for_points(review_request, points))
        for ptype, points in by_type.items()
    ]
