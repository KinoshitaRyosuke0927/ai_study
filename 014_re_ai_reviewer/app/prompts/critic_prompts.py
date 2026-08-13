from __future__ import annotations

import json
from typing import Any

_CRITIC_SYSTEM_PROMPT = """
あなたは、他のアシスタントが生成したプレゼンテーション資料への指摘候補を検証するcriticです。
出力は必ずJSON形式のみとしてください。前置き・説明・コードブロックは禁止です。

以下の観点で、1件のスライド画像に対して渡された指摘候補すべてを検証してください:
1. 根拠性: 指摘内容が該当スライドの記載・数値・図表から実際に確認できるか
2. 外挿しすぎていないか: スライドにない事実を勝手に仮定していないか
3. 重複性: 候補同士で実質同じ指摘になっていないか（同じ場合は1件を残しdedup_groupを揃える）
4. 修正可能性: suggestion（修正提案）が具体的で実行可能か

【出力ルール】
1. 以下のスキーマに厳密に従ってください:
   {"verdicts": [
     {
       "candidate_index": number,
       "verdict": "keep または drop",
       "confidence": number (0.0〜1.0),
       "critic_comment": "string（判定理由を簡潔に）",
       "evidence": "string（スライド画像から実際に確認できた根拠）",
       "suggestion": "string（修正提案。判断できなければ空文字でよい）"
     }
   ]}
2. candidate_index は、入力で渡された候補リストの0始まりインデックスと必ず一致させてください。
3. 入力されたすべての候補について、1件ずつ必ずverdictsに含めてください。
4. スライド上で根拠が確認できない、または資料外の事実を仮定している指摘は verdict を "drop" にしてください。
"""


def build_critic_prompt_package(
    slide_number: int,
    slide_image_b64: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    1スライド分の候補指摘をまとめて検証するプロンプトパッケージを構築する

    Args
    -----------------
    - slide_number: int,                対象スライド番号
    - slide_image_b64: str,             対象スライド画像（PNG）のBase64文字列
    - candidates: list[dict[str, Any]], 該当スライドに紐づく候補指摘のリスト

    Returns
    -----------------
    - package: dict[str, Any],          system_prompt と user_prompt を含むプロンプトパッケージ

    """
    candidates_text = "\n".join(
        f"{i}: {c['issue']}（根拠ヒント: {c.get('evidence_hint', '')} / severity: {c.get('severity_guess', 'medium')}）"
        for i, c in enumerate(candidates)
    )

    intro = (
        f"スライド {slide_number} の画像と、それに対する指摘候補一覧です。\n\n候補一覧:\n{candidates_text}\n"
    )
    schema = {
        "verdicts": [
            {
                "candidate_index": "number",
                "verdict": "keep|drop",
                "confidence": "number",
                "critic_comment": "string",
                "evidence": "string",
                "suggestion": "string",
            }
        ]
    }
    intro += "\n以下のスキーマでJSONのみを返してください:\n" + json.dumps(schema, ensure_ascii=False, indent=2)

    content: list[dict[str, Any]] = [
        {"type": "text", "text": intro},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{slide_image_b64}"}},
        {"type": "text", "text": "各候補の検証結果をJSONのみで返してください。"},
    ]
    return {"system_prompt": _CRITIC_SYSTEM_PROMPT, "user_prompt": content}
