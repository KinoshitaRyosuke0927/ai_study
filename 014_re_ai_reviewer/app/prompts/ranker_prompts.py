from __future__ import annotations

import json
from typing import Any

_RANKER_SYSTEM_PROMPT = """
あなたは、特定の上司の確認観点・優先順位を理解した上でレビュー候補を評価するアシスタントです。
出力は必ずJSON形式のみとしてください。前置き・説明・コードブロックは禁止です。

この上司が実際のレビューで重視してきた傾向は以下の通りです:
- 見た目の綺麗さよりも、数字・根拠の妥当性を重視する
- 誤字脱字などの細部より、結論やストーリーの弱さを重視する
- 意思決定に必要な前提条件が欠けている場合は特に厳しく指摘する
- 一方で、視認性やデザイン面の指摘も軽視はしない

【出力ルール】
1. 以下のスキーマに厳密に従ってください:
   {"scores": [
     {
       "candidate_index": number,
       "manager_likeness": number (0.0〜1.0、この上司が実際に言いそうかどうか),
       "severity": "blocker | high | medium | low のいずれか（上記傾向を踏まえた最終重要度）"
     }
   ]}
2. candidate_index は、入力で渡された候補リストの0始まりインデックスと必ず一致させてください。
3. 入力されたすべての候補について、1件ずつ必ずscoresに含めてください。
"""


def build_ranking_prompt_package(
    candidates: list[dict[str, Any]],
    memory_hints: list[str],
) -> dict[str, Any]:
    """
    候補指摘リストに対して、上司らしさ・重要度をスコアリングするプロンプトパッケージを構築する

    Args
    -----------------
    - candidates: list[dict[str, Any]],   候補指摘（slide_number, issue, evidence_hint, category, severity_guess）のリスト
    - memory_hints: list[str],            review_memory層から取得した過去指摘の参考テキスト（空リスト可）

    Returns
    -----------------
    - package: dict[str, Any],            system_prompt と user_prompt を含むプロンプトパッケージ

    """
    candidates_text = "\n".join(
        f"{i}: [スライド{c['slide_number']} / {c.get('category', '')}] {c['issue']}"
        f"（根拠: {c.get('evidence_hint', '')} / 初期severity: {c.get('severity_guess', 'medium')}）"
        for i, c in enumerate(candidates)
    )

    intro = f"以下の指摘候補について、この上司の観点でスコアリングしてください。\n\n候補一覧:\n{candidates_text}\n"

    if memory_hints:
        hints_text = "\n".join(f"- {h}" for h in memory_hints)
        intro += f"\n過去の類似レビューでこの上司が実際に指摘した内容の参考例:\n{hints_text}\n"

    schema = {"scores": [{"candidate_index": "number", "manager_likeness": "number", "severity": "blocker|high|medium|low"}]}
    intro += "\n以下のスキーマでJSONのみを返してください:\n" + json.dumps(schema, ensure_ascii=False, indent=2)

    return {"system_prompt": _RANKER_SYSTEM_PROMPT, "user_prompt": [{"type": "text", "text": intro}]}
