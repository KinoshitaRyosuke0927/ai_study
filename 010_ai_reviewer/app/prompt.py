from __future__ import annotations

import json
from typing import Any


REVIEW_FOCUS = {
    "structure": [
        "タイトルが結論または主張になっているか",
        "1スライド1メッセージになっているか",
        "箇条書きや情報の階層が破綻していないか",
        "余計な情報が多すぎないか",
    ],
    "visual": [
        "強調箇所が明確か",
        "文字サイズや余白が読みやすいか",
        "図表や画像が主張を支えているか",
        "重要情報が埋もれていないか",
    ],
    "content": [
        "伝えたい内容とスライド内容が一致しているか",
        "結論・根拠・示唆のつながりがあるか",
        "誤解を招く表現や曖昧さがないか",
        "聞き手が次に理解すべき要点が分かるか",
    ],
}

OVERALL_SCHEMA = {
    "presentation_summary": {
        "overall_alignment": "string",
        "overall_risks": ["string"],
        "priority_actions": ["string"],
    }
}

SLIDES_SCHEMA = {
    "slides": [
        {
            "slide_number": 1,
            "intended_message": "string",
            "summary": "string",
            "structure_review": {
                "score": 1,
                "findings": ["string"],
                "suggestions": ["string"],
            },
            "visual_review": {
                "score": 1,
                "findings": ["string"],
                "suggestions": ["string"],
            },
            "content_review": {
                "score": 1,
                "findings": ["string"],
                "suggestions": ["string"],
            },
            "good_point": "string",
            "priority": "high | medium | low",
        }
    ],
}

SYSTEM_PROMPT = """あなたはPowerPointレビュー専門のアシスタントです。
出力は必ずJSONのみで返してください。文章の前置きやコードブロックは禁止です。
レビュー観点は structure / visual / content の3つです。
各観点は5点満点で採点し、根拠と改善提案を短く具体的に返してください。
レビューでは、ユーザーが入力した『伝えたい内容』が本当に伝わる構成・見た目・内容になっているかを最優先で見てください。
抽象論ではなく、各スライドで直すべき点が分かる実務的な指摘を返してください。"""


def _build_slide_images_content(slides: list[dict]) -> list[dict[str, Any]]:
    """スライドごとの画像＋ラベルのコンテンツブロックを構築する"""
    content: list[dict[str, Any]] = []
    for slide in slides:
        label = f"スライド {slide['slide_number']}"
        if slide.get("intended_message"):
            label += f" / 伝えたいこと: {slide['intended_message']}"
        content.append({"type": "text", "text": label})
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{slide['image_jpeg_b64']}"},
        })
    return content


def build_overall_prompt_package(review_request: dict[str, Any]) -> dict[str, Any]:
    """全体評価（presentation_summary）用プロンプトパッケージを構築する"""
    slides = review_request["slides"]
    overall_msg = review_request.get("overall_intended_message", "")

    intro = f"{len(slides)}枚のスライドからなるプレゼンテーション全体を評価してください。"
    if overall_msg:
        intro += f"\nプレゼンテーション全体の意図: {overall_msg}"
    intro += "\n\nレビュー観点:\n" + json.dumps(REVIEW_FOCUS, ensure_ascii=False, indent=2)
    intro += "\n\n以下のスキーマでJSONのみを返してください:\n" + json.dumps(OVERALL_SCHEMA, ensure_ascii=False, indent=2)

    content: list[dict[str, Any]] = [{"type": "text", "text": intro}]
    content.extend(_build_slide_images_content(slides))
    content.append({"type": "text", "text": "プレゼンテーション全体を評価し、JSONのみで返してください。"})

    return {"system_prompt": SYSTEM_PROMPT, "user_prompt": content}


def build_slides_prompt_package(review_request: dict[str, Any]) -> dict[str, Any]:
    """スライド個別評価（slides）用プロンプトパッケージを構築する"""
    slides = review_request["slides"]
    overall_msg = review_request.get("overall_intended_message", "")

    intro = f"{len(slides)}枚のスライドをそれぞれ個別にレビューしてください。"
    if overall_msg:
        intro += f"\nプレゼンテーション全体の意図: {overall_msg}"
    intro += "\n\nレビュー観点:\n" + json.dumps(REVIEW_FOCUS, ensure_ascii=False, indent=2)
    intro += "\n\n以下のスキーマでJSONのみを返してください:\n" + json.dumps(SLIDES_SCHEMA, ensure_ascii=False, indent=2)

    content: list[dict[str, Any]] = [{"type": "text", "text": intro}]
    content.extend(_build_slide_images_content(slides))
    content.append({"type": "text", "text": "各スライドを個別にレビューし、JSONのみで返してください。"})

    return {"system_prompt": SYSTEM_PROMPT, "user_prompt": content}
