from __future__ import annotations

import json
from typing import Any

# 画像編集AIへの指示文に、AIの出力内容によらず必ず付加する余白確保のガイダンス（010_ai_reviewerと同一）
LAYOUT_GUIDANCE_SUFFIX = (
    "スライド全体に要素を詰め込みすぎないこと。上下左右に十分な余白（マージン）を確保し、"
    "文字や図表をスライドの端ギリギリまで配置しないこと。情報量を減らさず、"
    "余白を活かした読みやすいレイアウトに整えること。"
)

# 画像編集AIへの指示文に、AIの出力内容によらず必ず付加する「AIらしさ」を排除するためのガイダンス。
# 画像編集AI特有の光沢・グラデーション・過度な立体感などが乗ってしまい、人が作成した
# PowerPointスライドから浮いて見える問題を防ぐために付加する。
NATURALNESS_GUIDANCE_SUFFIX = (
    "生成する画像は、AIが生成したとひと目でわかるような見た目にしないこと。"
    "光沢・グラデーション・立体的な質感・不要な影や光彩・ぼかしなど、画像生成AI特有の"
    "装飾的な表現を加えないこと。アイコン・図形・グラフは、元のスライドと同じフラットな配色、"
    "線の太さ、書体の雰囲気を維持し、実際にPowerPointで人が作成したスライドと見分けがつかない"
    "仕上がりにすること。テキストは正確な日本語表記で、文字が崩れたりにじんだりせず、"
    "くっきりと読める状態で描画すること。"
)

_SLIDE_EDIT_PLAN_SYSTEM_PROMPT = """
あなたは、プレゼンテーション資料へのレビュー指摘をもとに、画像編集AI（元のスライド画像1枚を
書き換えるimage-to-image編集モデル）向けの指示文をスライドごとに作成するアシスタントです。

各スライドに割り当てられた指摘事項はあらかじめ整理済みです。あなたの役割は「どのスライドに
該当するか」を判断することではなく、指摘事項の文章を、画像編集AIがそのまま実行できるレベルの
具体的な視覚編集指示に変換することです。

画像編集AIは、元のスライド画像とテキストの指示だけを受け取り、画像そのものを直接書き換えます。
レビュー指摘の文章をそのまま渡しても意図通りに編集されないため、画像編集に適した具体的な指示文を
作成してください。

【出力ルール】
1. 出力は必ずJSON形式のみとしてください。前置き・説明・コードブロックは禁止です。
2. 以下のスキーマに厳密に従ってください:
   {"slide_plans": [{"slide_number": number, "instruction": "string"}]}
3. instruction には、画像編集AIがそのまま実行できるレベルで、視覚的に何をどう変えるかを具体的に記述してください。
   - どのテキスト・見出し・数値・図表・レイアウトを、どう変更するかを明確に書く
   - 差し替えるべきテキストがある場合は、実際の日本語の文言をそのまま指示文中に含める
   - 元のスライドのデザイン・配色・フォント・レイアウトの雰囲気はできる限り維持し、指摘のあった箇所のみを変更するよう指示する
   - 「わかりやすくして」のような抽象的な表現は禁止し、誰が実行しても同じ結果になるよう具体化する
   - スライドの端から端まで要素を詰め込まず、上下左右に十分な余白を確保した、企画資料として読みやすいレイアウトを維持するよう明記する
   - 光沢・グラデーション・立体的な質感などの画像生成AIらしい装飾を加えず、元のスライドと同じフラットなデザインを維持するよう明記する
   - 1枚のスライドに複数の指摘が該当する場合は、すべてを1つの指示文にまとめて記載してください
4. 提示されたスライド番号すべてについて、1件ずつ必ず slide_plans に含めてください。
"""


def build_findings_text_by_slide(findings: list[dict[str, Any]]) -> dict[int, str]:
    """
    critic検証済みのFinding一覧を、スライド番号ごとの指摘事項テキストにまとめる

    Args
    -----------------
    - findings: list[dict[str, Any]],   /api/review が返したFinding（slide_number, issue, evidence, severity, suggestion等）のリスト

    Returns
    -----------------
    - text_by_slide: dict[int, str],    slide_number をキーとする指摘事項テキスト（該当スライドがないキーは含まれない）

    """
    text_by_slide: dict[int, list[str]] = {}
    for f in findings:
        slide_number = f.get("slide_number")
        if not isinstance(slide_number, int):
            continue
        line = f"- [{f.get('severity', 'medium')}] {f.get('issue', '')}"
        if f.get("evidence"):
            line += f"（根拠: {f['evidence']}）"
        if f.get("suggestion"):
            line += f" / 修正提案: {f['suggestion']}"
        text_by_slide.setdefault(slide_number, []).append(line)

    return {slide_number: "\n".join(lines) for slide_number, lines in text_by_slide.items()}


def build_slide_edit_plan_prompt_package(
    slides: list[dict[str, Any]],
    findings_text_by_slide: dict[int, str],
) -> dict[str, Any]:
    """
    指摘事項が割り当て済みのスライドについて、画像編集AI向けの具体的な指示文を一括生成するプロンプトパッケージを構築する

    Args
    -----------------
    - slides: list[dict[str, Any]],             指摘事項があるスライドのみ（slide_number, image_png_b64）のリスト
    - findings_text_by_slide: dict[int, str],    slide_number をキーとする指摘事項テキスト

    Returns
    -----------------
    - package: dict[str, Any],                   system_prompt と user_prompt を含むプロンプトパッケージ

    """
    slide_numbers = [slide["slide_number"] for slide in slides]
    findings_block = "\n\n".join(
        f"[スライド {n}]\n{findings_text_by_slide.get(n, '')}" for n in slide_numbers
    )
    intro = (
        f"以下は、スライドごとに割り当て済みの指摘事項です。\n\n{findings_block}\n\n"
        "各スライドの画像を確認した上で、画像編集AI向けの指示をJSONのみで返してください。"
        f"\n対象スライド番号: {slide_numbers}"
    )

    content: list[dict[str, Any]] = [{"type": "text", "text": intro}]
    for slide in slides:
        content.append({"type": "text", "text": f"スライド {slide['slide_number']}"})
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{slide['image_png_b64']}"},
        })
    content.append({"type": "text", "text": "スライドごとの編集指示をJSONのみで返してください。"})

    return {"system_prompt": _SLIDE_EDIT_PLAN_SYSTEM_PROMPT, "user_prompt": content}


_CHANGE_DESCRIPTION_SYSTEM_PROMPT = """
あなたは、修正前と修正後のプレゼンテーションスライド画像を見比べて、実際にどのような修正が施されたかを説明するアシスタントです。

【出力ルール】
1. 出力は必ずJSON形式のみとしてください。前置き・説明・コードブロックは禁止です。
2. 以下のスキーマに厳密に従ってください:
   {"description": "string"}
3. description には、修正前の画像と修正後の画像を実際に見比べて確認できた変更点（テキスト、レイアウト、強調箇所など）のみを、Markdown形式の箇条書きで具体的に日本語で記載してください。
4. 変更されていない箇所については触れないでください。
5. 推測ではなく、画像上で実際に確認できる変化のみを記載してください。
6. 文末表現は、あなた自身がその修正を行ったかのような能動的な言い切りの形（例:「〜に差し替えました。」「〜を変更しました。」「〜を追加しました」）で統一してください。「〜されている」「〜になっている」「〜が変更された」のような受け身・他人事の表現は使用しないでください。
"""


def build_change_description_prompt_package(
    slide_number: int,
    before_image_b64: str,
    after_image_b64: str,
) -> dict[str, Any]:
    """
    1枚のスライドについて、修正前後の画像を比較し実際の修正内容を説明するプロンプトパッケージを構築する
    （010_ai_reviewerと同一）

    Args
    -----------------
    - slide_number: int,            対象スライド番号
    - before_image_b64: str,        修正前スライド画像（PNG）のBase64文字列
    - after_image_b64: str,         修正後スライド画像（PNG）のBase64文字列

    Returns
    -----------------
    - package: dict[str, Any],      system_prompt と user_prompt を含むプロンプトパッケージ

    """
    content: list[dict[str, Any]] = [
        {"type": "text", "text": f"スライド {slide_number} の修正前後の画像を比較してください。"},
        {"type": "text", "text": "【修正前】"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{before_image_b64}"}},
        {"type": "text", "text": "【修正後】"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{after_image_b64}"}},
        {"type": "text", "text": "実際に施された修正内容をJSONのみで返してください。"},
    ]
    return {"system_prompt": _CHANGE_DESCRIPTION_SYSTEM_PROMPT, "user_prompt": content}
