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


OUTPUT_SCHEMA = {
    "presentation_summary": {
        "overall_alignment": "string",
        "overall_risks": ["string"],
        "priority_actions": ["string"],
    },
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


def build_review_input(parsed_presentation: dict[str, Any]) -> dict[str, Any]:
    slides = []
    for slide in parsed_presentation["slides"]:
        slide_data: dict = {
            "slide_number": slide["slide_number"],
            "title": slide["title"],
            "intended_message": slide["intended_message"],
            "all_text": slide["all_text"],
            "text_char_count": slide["text_char_count"],
            "bullet_count": slide["bullet_count"],
            "text_block_count": len(slide["text_blocks"]),
            "table_count": slide["table_count"],
            "chart_count": slide["chart_count"],
            "image_count": slide["image_count"],
            "placeholder_count": slide["placeholder_count"],
            "font_stats": slide["font_stats"],
            "shape_counts": slide["shape_counts"],
            "heuristics": slide["heuristics"],
            "text_blocks": slide["text_blocks"],
        }
        # 画像パスが付与されている場合は含める（将来のビジョン API 対応）
        if slide.get("image_png_path"):
            slide_data["image_png_path"] = slide["image_png_path"]
        if slide.get("image_jpg_path"):
            slide_data["image_jpg_path"] = slide["image_jpg_path"]
        slides.append(slide_data)

    return {
        "review_goal": "PowerPointスライドが伝えたい内容を十分に伝えられているかレビューする",
        "focus": REVIEW_FOCUS,
        "instructions": {
            "structure": "タイトル・論点・情報量・階層構造の妥当性を評価する",
            "visual": "視線誘導・可読性・強調・余白・図表の使い方を評価する",
            "content": "意図との一致、結論と根拠のつながり、誤解リスクを評価する",
        },
        "presentation": {
            "file_name": parsed_presentation["file_name"],
            "slide_count": parsed_presentation["slide_count"],
            "overall_intended_message": parsed_presentation["overall_intended_message"],
            "slide_size": parsed_presentation["slide_size"],
            "deck_shape_counts": parsed_presentation["deck_shape_counts"],
        },
        "slides": slides,
        "response_schema": OUTPUT_SCHEMA,
    }


def build_user_prompt(parsed_presentation: dict[str, Any]) -> str:
    payload = build_review_input(parsed_presentation)
    return (
        "以下のPowerPoint解析結果をもとに、各スライドをレビューしてください。"
        "structure / visual / content の3観点を必ず評価し、JSONのみで返してください。\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def build_prompt_package(parsed_presentation: dict[str, Any]) -> dict[str, Any]:
    sample_response = {
        "presentation_summary": {
            "overall_alignment": "全体として意図は伝わるが、要点が各スライドでやや分散している。",
            "overall_risks": [
                "結論型タイトルが不足している",
                "文字量が多いスライドで視線誘導が弱い",
            ],
            "priority_actions": [
                "各スライドのタイトルを結論型に寄せる",
                "重要要素以外の補足文を削る",
            ],
        },
        "slides": [
            {
                "slide_number": 1,
                "intended_message": "このスライドで最も伝えたい主張",
                "summary": "主張は見えるが、補足情報が多く焦点がややぼやけている。",
                "structure_review": {
                    "score": 3,
                    "findings": ["タイトルが結論型ではない", "箇条書きがやや多い"],
                    "suggestions": ["タイトルを主張文に変える", "箇条書きを3点以内に絞る"],
                },
                "visual_review": {
                    "score": 3,
                    "findings": ["テキスト領域が広く余白が少ない"],
                    "suggestions": ["重要文のみ強調し、補足は脚注に寄せる"],
                },
                "content_review": {
                    "score": 4,
                    "findings": ["意図との整合性は高い"],
                    "suggestions": ["根拠と結論のつながりを一文で補強する"],
                },
                "good_point": "主張に関連する要素は一通り揃っている。",
                "priority": "medium",
            }
        ],
    }

    return {
        "system_prompt": SYSTEM_PROMPT,
        "user_prompt": build_user_prompt(parsed_presentation),
        "response_schema": OUTPUT_SCHEMA,
        "sample_response": sample_response,
    }
