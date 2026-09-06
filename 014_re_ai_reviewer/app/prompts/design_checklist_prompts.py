from __future__ import annotations

import json
from typing import Any

# 資料の「内容」観点（candidate_prompts.py）とは異なり、デザイン観点はCSVの
# チェック項目を「ヒント」ではなく「必須チェックリスト」として扱う。項目ごとに
# 全スライドを実際に見比べ、人が目で見て気づくレベルの粗探しを行わせる。
_DESIGN_CHECKLIST_SYSTEM_PROMPT = """
あなたは、プレゼンテーション資料のデザイン・体裁を厳しくチェックする専門レビュアーです。
出力は必ずJSON形式のみとしてください。前置き・説明・コードブロックは禁止です。

これから渡すチェック項目は、参考例ではなく「必ず1つずつ確認すべきチェックリスト」です。
各項目について、提示されたスライド画像すべてを1枚ずつ実際に見比べ、人が目で見て
気になるレベルの粗探しのつもりで、問題がないか厳密に確認してください。
（例:「文字が小さい」「余白が窮屈」「色が浮いている」など、パッと見て気になる箇所は
見落とさず拾ってください。）

【出力ルール】
1. 出力は必ずJSON形式のみとしてください。前置き・説明・コードブロックは禁止です。
2. 以下のスキーマに厳密に従ってください:
   {"results": [
     {
       "question": "string（渡されたチェック項目の文言をそのまま記載）",
       "occurrences": [
         {
           "slide_number": number,
           "detail": "string（そのスライドで具体的に何が問題か）",
           "severity_guess": "high | medium | low のいずれか"
         }
       ]
     }
   ]}
3. 渡されたチェック項目すべてについて、1件ずつ必ず results に含めてください。
4. 問題が見つからなかった項目は、occurrences を空配列 [] にしてください。
5. 1つの項目で複数スライドに問題がある場合は、occurrences に複数件含めてください。
6. 同じスライドで複数の項目に該当する問題があっても構いません（項目ごとに独立して判定してください）。
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


def build_design_checklist_prompt_package(
    category: str,
    checklist_items: list[str],
    slides: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    1つのデザイン観点カテゴリについて、チェックリスト項目を全スライドに照らして確認するプロンプトパッケージを構築する

    Args
    -----------------
    - category: str,                     観点カテゴリ名（character / colors / composition / figures / sentence）
    - checklist_items: list[str],        そのカテゴリのチェック項目一覧（seed_review_points.csv由来）
    - slides: list[dict[str, Any]],      スライドデータ（slide_number, image_png_b64）のリスト

    Returns
    -----------------
    - package: dict[str, Any],           system_prompt と user_prompt を含むプロンプトパッケージ

    """
    items_text = "\n".join(f"- {item}" for item in checklist_items)
    intro = (
        f"観点カテゴリ「{category}」について、以下のチェック項目を{len(slides)}枚のスライドすべてに"
        f"照らして確認してください。\n\nチェック項目:\n{items_text}\n"
    )

    schema = {
        "results": [
            {
                "question": "string",
                "occurrences": [{"slide_number": "number", "detail": "string", "severity_guess": "high|medium|low"}],
            }
        ]
    }
    intro += "\n以下のスキーマでJSONのみを返してください:\n" + json.dumps(schema, ensure_ascii=False, indent=2)

    content: list[dict[str, Any]] = [{"type": "text", "text": intro}]
    content.extend(_build_slide_images_content(slides))
    content.append({"type": "text", "text": "チェック結果をJSONのみで返してください。"})

    return {"system_prompt": _DESIGN_CHECKLIST_SYSTEM_PROMPT, "user_prompt": content}
