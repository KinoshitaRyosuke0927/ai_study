from __future__ import annotations

import json
from typing import Any

_CANDIDATE_SYSTEM_PROMPT = """
あなたはプレゼンテーション資料のレビュー専門アシスタントです。
出力は必ずJSON形式のみとしてください。前置き・説明・コードブロックは禁止です。

あなたの役割は、最終的な指摘を1つに絞ることではなく、後続の選別ステップで使う
「指摘候補」をできるだけ広く・多く洗い出すことです。以下の観点ヒントを参考にしつつ、
ヒントに無い問題点も気づいたら積極的に候補として挙げてください。

【出力ルール】
1. 以下のスキーマに厳密に従ってください:
   {"candidates": [
     {
       "slide_number": number,
       "issue": "string（何が問題か、具体的に）",
       "evidence_hint": "string（スライドのどの記載・数値・図表を根拠にした指摘か）",
       "category": "string（観点ヒントのカテゴリ名、または該当なしなら自由記述）",
       "severity_guess": "blocker | high | medium | low のいずれか"
     }
   ]}
2. 1スライドにつき5〜10件程度を目安に、幅広く候補を出してください。重複や粒度違いがあっても構いません（後続ステップで統合・選別します）。
3. 明らかに問題がないスライドについては、無理に候補を作らなくてよいです。
4. この資料は企画会議にて発表することを想定しているため、厳しめにチェックしてください。
"""


def _build_slide_images_content(slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """スライドごとの画像＋ラベルのコンテンツブロックを構築する"""
    content: list[dict[str, Any]] = []
    for slide in slides:
        content.append({"type": "text", "text": f"スライド {slide['slide_number']}"})
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{slide['image_png_b64']}"},
        })
    return content


def build_candidate_generation_prompt_package(
    slides: list[dict[str, Any]],
    overall_intended_message: str,
    seed_points_by_type: dict[str, list[str]],
    memory_hints: list[str],
) -> dict[str, Any]:
    """
    全スライド画像・観点ヒント・過去レビュー参照結果から、指摘候補を複数生成するプロンプトパッケージを構築する

    Args
    -----------------
    - slides: list[dict[str, Any]],              スライドデータ（slide_number, image_png_b64）のリスト
    - overall_intended_message: str,              資料全体で伝えたい内容
    - seed_points_by_type: dict[str, list[str]],  観点カテゴリごとの固定チェックポイント（旧app由来のシード）
    - memory_hints: list[str],                    review_memory層から取得した過去指摘の参考テキスト（0件でも可）

    Returns
    -----------------
    - package: dict[str, Any],                    system_prompt と user_prompt を含むプロンプトパッケージ

    """
    seed_text = "\n".join(
        f"[{ptype}]\n" + "\n".join(f"  - {p}" for p in points)
        for ptype, points in seed_points_by_type.items()
    )

    intro = (
        f"{len(slides)}枚のスライドからなるプレゼンテーション資料全体を確認し、"
        "スライドごとに指摘候補を洗い出してください。\n"
    )
    if overall_intended_message:
        intro += f"\nプレゼンテーション全体の意図: {overall_intended_message}\n"

    intro += f"\n以下は必ず確認すべき観点の例（網羅的に見るためのヒントであり、これに縛られる必要はありません）:\n{seed_text}\n"

    if memory_hints:
        hints_text = "\n".join(f"- {h}" for h in memory_hints)
        intro += f"\n過去の類似レビューで実際に指摘された内容の参考例:\n{hints_text}\n"

    schema = {
        "candidates": [
            {
                "slide_number": "number",
                "issue": "string",
                "evidence_hint": "string",
                "category": "string",
                "severity_guess": "blocker|high|medium|low",
            }
        ]
    }
    intro += "\n以下のスキーマでJSONのみを返してください:\n" + json.dumps(schema, ensure_ascii=False, indent=2)

    content: list[dict[str, Any]] = [{"type": "text", "text": intro}]
    content.extend(_build_slide_images_content(slides))
    content.append({"type": "text", "text": "指摘候補をJSONのみで返してください。"})

    return {"system_prompt": _CANDIDATE_SYSTEM_PROMPT, "user_prompt": content}
