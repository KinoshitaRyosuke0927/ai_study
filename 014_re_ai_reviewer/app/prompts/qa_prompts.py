from __future__ import annotations

import json
from typing import Any

# 010_ai_reviewer の想定質問生成機能（build_anticipated_questions_prompt_package）を移植したもの。
# 企画会議に同席するAI技術者・エンジニア視点で、資料に対して出そうな「技術的な質問・課題提起」だけを
# 予測させる。事業性・デザイン・文章表現などは別レビューで扱うため対象外とする。
_ANTICIPATED_QUESTIONS_SYSTEM_PROMPT = """
あなたは、企画会議に同席するAI技術者・アプリケーションエンジニアの視点に立ち、
資料に対してどのような技術的な質問や課題提起が出るかを予測する専門アシスタントです。
出力は必ずJSONのみで返してください。文章の前置きやコードブロックは禁止です。

想定質問を挙げる際は、以下の「技術的な実現方式・課題」に関する観点にのみ着目してください:
- 実装方式・アーキテクチャの妥当性（採用技術・構成が目的に対して適切か）
- AI/機械学習を用いる場合のモデル選定・精度・評価方法（学習データ、評価指標、失敗時の挙動など）
- システムの性能・スケーラビリティ（処理量増加時の限界、レスポンス速度など）
- 既存システムとの連携・データ連携方式（API、データ形式、認証など）
- セキュリティ・データの取り扱い（機密情報の扱い、権限管理、脆弱性など）
- 運用・保守性（監視方法、障害時の対応、アップデートのしやすさなど）
- 技術的な実現性・リスク（未検証の技術要素、依存ライブラリやサービスの制約など）
- 資料に書かれていない技術的な前提や、実装時に問題になりそうな未確認事項

ROIやKPI、投資対効果、事業インパクトなど、意思決定・経営判断に関する観点は対象外です。
また、以下の「見た目・ルール」に関する観点も、別のレビュー機能で扱うため想定質問には含めないでください:
- 誤字脱字、表記ゆれなどの文章表現
- フォント、配色、レイアウト、図表の見やすさなどのデザイン
- スライドの構成・順序などのフォーマット

各想定質問について、question（技術者が実際に問いそうな質問文、または指摘しそうな技術的課題）と
hint（発表者が回答を準備する際に押さえておくべき技術的観点）を返してください。
資料の内容から本当に問われそうな質問だけを厳選してください。無理に質問数を増やす必要はありません。
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


def build_anticipated_questions_prompt_package(
    slides: list[dict[str, Any]],
    overall_intended_message: str,
) -> dict[str, Any]:
    """
    プレゼンテーション全体に対して、AI技術者・アプリケーションエンジニア視点での想定質問を生成する
    プロンプトパッケージを構築する（010_ai_reviewer と同一方針）

    Args
    -----------------
    - slides: list[dict[str, Any]],     スライドデータ（slide_number, image_png_b64）のリスト
    - overall_intended_message: str,    資料全体で伝えたい内容

    Returns
    -----------------
    - package: dict[str, Any],          system_prompt と user_prompt を含むプロンプトパッケージ

    """
    schema = {"questions": [{"question": "string", "hint": "string"}]}

    intro = f"{len(slides)}枚のスライドからなるプレゼンテーション全体を確認し、想定質問を提案してください。"
    if overall_intended_message:
        intro += f"\nプレゼンテーション全体の意図: {overall_intended_message}"
    intro += "\n\n以下のスキーマでJSONのみを返してください:\n" + json.dumps(schema, ensure_ascii=False, indent=2)

    content: list[dict[str, Any]] = [{"type": "text", "text": intro}]
    content.extend(_build_slide_images_content(slides))
    content.append({"type": "text", "text": "資料全体を確認し、想定質問をJSONのみで返してください。"})

    return {"system_prompt": _ANTICIPATED_QUESTIONS_SYSTEM_PROMPT, "user_prompt": content}
