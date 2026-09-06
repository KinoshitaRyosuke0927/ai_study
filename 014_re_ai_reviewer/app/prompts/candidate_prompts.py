from __future__ import annotations

import json
from typing import Any

_CANDIDATE_SYSTEM_PROMPT = """
あなたはプレゼンテーション資料のレビュー専門アシスタントです。
出力は必ずJSON形式のみとしてください。前置き・説明・コードブロックは禁止です。

あなたの役割は、最終的な指摘を1つに絞ることではなく、後続の選別ステップで使う
「指摘候補」を洗い出すことです。今回のレビューでは指定された1つの観点だけに集中し、
その観点の確認項目を主な手がかりにしつつ、項目に無い問題点でもその観点に関係するものは
気づいたら積極的に候補として挙げてください（指定された観点と無関係な指摘は挙げないでください）。

なお、文字・配色・レイアウト・図表の見やすさなど「資料のデザイン」に関する指摘は、
別の専用レビューで網羅的にチェックするため、ここでは対象外としてください
（資料の「内容」に関する指摘のみを挙げてください）。

また、技術的な実現方法に関する指摘（実装方式・アーキテクチャ・採用技術の妥当性、
AI/機械学習のモデル選定・精度・評価方法、性能・スケーラビリティ、既存システム連携・
データ連携方式、セキュリティ・データの取り扱い、運用・保守性、実装時の技術的な
未確認事項など）も、別の専用レビューで扱うため、ここでは一切挙げないでください。
企画・提案としての内容面（課題設定、狙い、ストーリー、前提条件、効果・優先度、
計画の妥当性など）のみをレビューしてください。

【出力ルール】
1. 以下のスキーマに厳密に従ってください:
   {"candidates": [
     {
       "slide_number": number,
       "issue": "string（何が問題か、具体的に）",
       "evidence_hint": "string（スライドのどの記載・数値・図表を根拠にした指摘か）",
       "category": "string（観点ヒントのカテゴリ名、または該当なしなら自由記述）",
       "severity_guess": "high | medium | low のいずれか"
     }
   ]}
2. 指定された観点について、スライドごとに問題と言える箇所を漏れなく挙げてください（1スライドあたり0〜5件程度が目安。無理に件数を増やす必要はありません）。重複や粒度違いがあっても構いません（後続ステップで統合・選別します）。
3. 明らかに問題がないスライド、またはその観点で問題がないスライドについては、無理に候補を作らなくてよいです。
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
    perspective_type: str,
    checklist_items: list[str],
    memory_hints: list[str],
) -> dict[str, Any]:
    """
    全スライド画像・1観点分の確認項目・過去レビュー参照結果から、その観点に絞った指摘候補を生成するプロンプトパッケージを構築する

    内容観点は観点タイプ（assignment / plan / story など）ごとに独立したLLM呼び出しに分割しており、
    この関数は1タイプ分のプロンプトを組み立てる。

    Args
    -----------------
    - slides: list[dict[str, Any]],       スライドデータ（slide_number, image_png_b64）のリスト
    - overall_intended_message: str,       資料全体で伝えたい内容
    - perspective_type: str,               レビュー対象の観点タイプ名（seed_review_points.csv の perspective_type）
    - checklist_items: list[str],           その観点タイプの確認項目一覧（seed_review_points.csv 由来）
    - memory_hints: list[str],             review_memory層から取得した過去指摘の参考テキスト（0件でも可）

    Returns
    -----------------
    - package: dict[str, Any],             system_prompt と user_prompt を含むプロンプトパッケージ

    """
    seed_text = "\n".join(f"  - {p}" for p in checklist_items)

    intro = (
        f"{len(slides)}枚のスライドからなるプレゼンテーション資料全体を、"
        f"「{perspective_type}」の観点に絞って確認し、スライドごとに指摘候補を洗い出してください。\n"
        "この呼び出しではこの観点以外の指摘は不要です（他の観点は別途レビューします）。\n"
    )
    if overall_intended_message:
        intro += f"\nプレゼンテーション全体の意図: {overall_intended_message}\n"

    intro += (
        f"\n「{perspective_type}」観点の主な確認項目（網羅的に見るための手がかりであり、"
        f"これに縛られる必要はありません。この観点に関係する問題は項目外でも挙げてください）:\n{seed_text}\n"
    )

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
                "severity_guess": "high|medium|low",
            }
        ]
    }
    intro += "\n以下のスキーマでJSONのみを返してください:\n" + json.dumps(schema, ensure_ascii=False, indent=2)

    content: list[dict[str, Any]] = [{"type": "text", "text": intro}]
    content.extend(_build_slide_images_content(slides))
    content.append({"type": "text", "text": "指摘候補をJSONのみで返してください。"})

    return {"system_prompt": _CANDIDATE_SYSTEM_PROMPT, "user_prompt": content}
