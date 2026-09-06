from __future__ import annotations

import json
from typing import Any

# 資料の性格（企画書／設計書など）によらず、資料内に「これから開発・設計しようとしている
# アプリケーション／システム」の説明が含まれる場合にのみ技術面のレビューを行う。
# 含まれない場合（純粋な事業提案・数値報告など）は candidates を空配列で返す前提判定を含む。
_TECHNICAL_CANDIDATE_SYSTEM_PROMPT = """
あなたは、AI技術者・アプリケーションエンジニアの視点でプレゼンテーション資料をレビューする専門アシスタントです。
出力は必ずJSON形式のみとしてください。前置き・説明・コードブロックは禁止です。

【前提判定】
まず、この資料の中に「これから開発・設計しようとしているアプリケーション／システム」の説明が
含まれているかを判断してください。
- 含まれていない場合（具体的に実装するシステムの説明がない、純粋な事業提案・数値報告などの資料）は、
  candidates を空配列 [] として返してください。無理に技術的指摘を作らないでください。

【技術レビューの進め方】
アプリケーション／システムの説明が含まれている場合は、まず記載内容から次を具体的に想像してください:
- 実際にこのアプリケーションを使うのは誰か（利用者像・役職・スキルレベル）
- その利用者がどんな場面・頻度・データ量で使うか（利用シーン）
この想像を土台に、以下の技術的な実現方式・課題の観点で指摘候補を挙げてください:
- 実装方式・アーキテクチャの妥当性（採用技術・構成が目的や想定利用シーンに対して適切か）
- AI/機械学習を用いる場合のモデル選定・精度・評価方法（学習データ、評価指標、失敗時の挙動など）
- システムの性能・スケーラビリティ（想定利用者数・データ量に対する処理能力、レスポンス速度）
- 既存システムとの連携・データ連携方式（API、データ形式、認証など）
- セキュリティ・データの取り扱い（機密情報の扱い、権限管理、脆弱性など）
- 運用・保守性（監視方法、障害時の対応、アップデートのしやすさなど）
- 資料に書かれていない技術的な前提や、実装時に問題になりそうな未確認事項

以下は対象外とし、指摘に含めないでください（別のレビューで扱うため）:
- ROIやKPI、投資対効果、事業インパクトなど、意思決定・経営判断に関する観点
- 誤字脱字、フォント、配色、レイアウトなど見た目に関する観点

【出力ルール】
1. 以下のスキーマに厳密に従ってください:
   {"candidates": [
     {
       "slide_number": number,
       "issue": "string（技術的に何が問題・未確認か、具体的に）",
       "evidence_hint": "string（スライドのどの記載を根拠にした指摘か）",
       "category": "technical",
       "severity_guess": "high | medium | low のいずれか"
     }
   ]}
2. 想像した利用者・利用シーンは issue または evidence_hint の中で簡潔に触れてください
   （例:「現場のPMが日次で使う想定の場合、〜」）。
3. 資料の内容から本当に問題になりそうな指摘だけを厳選してください。無理に件数を増やす必要はありません。
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


def build_technical_candidate_prompt_package(
    slides: list[dict[str, Any]],
    overall_intended_message: str,
) -> dict[str, Any]:
    """
    技術面（実装利用者・利用シーンを踏まえた実現可能性）の指摘候補を生成するプロンプトパッケージを構築する

    汎用の候補生成層（candidate_prompts.py）とは別モデル・別プロンプトで独立して実行する想定のため、
    観点シードCSVや過去レビュー参照は使わず、技術レビューに特化した指示のみを渡す。

    Args
    -----------------
    - slides: list[dict[str, Any]],     スライドデータ（slide_number, image_png_b64）のリスト
    - overall_intended_message: str,    資料全体で伝えたい内容

    Returns
    -----------------
    - package: dict[str, Any],          system_prompt と user_prompt を含むプロンプトパッケージ

    """
    intro = (
        f"{len(slides)}枚のスライドからなるプレゼンテーション資料全体を確認し、"
        "技術面（実現可能性）の観点で指摘候補を洗い出してください。\n"
    )
    if overall_intended_message:
        intro += f"\nプレゼンテーション全体の意図: {overall_intended_message}\n"

    schema = {
        "candidates": [
            {
                "slide_number": "number",
                "issue": "string",
                "evidence_hint": "string",
                "category": "technical",
                "severity_guess": "high|medium|low",
            }
        ]
    }
    intro += "\n以下のスキーマでJSONのみを返してください:\n" + json.dumps(schema, ensure_ascii=False, indent=2)

    content: list[dict[str, Any]] = [{"type": "text", "text": intro}]
    content.extend(_build_slide_images_content(slides))
    content.append({"type": "text", "text": "技術面の指摘候補をJSONのみで返してください（対象アプリケーションがなければ空配列）。"})

    return {"system_prompt": _TECHNICAL_CANDIDATE_SYSTEM_PROMPT, "user_prompt": content}
