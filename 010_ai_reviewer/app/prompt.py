from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any


if getattr(sys, "frozen", False):
    _CSV_PATH = Path(sys.executable).resolve().parent / "review_point.csv"
else:
    _CSV_PATH = Path(__file__).parent.parent / "review_point.csv"


def _load_review_points() -> dict[str, list[str]]:
    """
    CSVからレビュー観点を読み込み、perspective_type 別辞書に分けて返す

    Returns
    -----------------
    - by_type: dict[str, list[str]],    perspective_type をキーとするレビュー観点辞書

    """
    by_type: dict[str, list[str]] = {}
    with _CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            detail = row.get("detail", "").strip()
            # 内容が空の行はスキップ
            if not detail:
                continue
            ptype = row.get("perspective_type", "").strip()
            by_type.setdefault(ptype, []).append(detail)
    return by_type


SYSTEM_PROMPT = """
あなたはプレゼンテーション資料のレビュー専門アシスタントです。
出力は必ずJSONのみで返してください。文章の前置きやコードブロックは禁止です。
各レビュー観点について、以下のルールに従って result フィールドを返してください:
- インプットの情報からは判断がつかない場合には、「判断ができません」とだけ返してください。他の文章を追加することは禁止です。
- レビューした結果、問題がない場合は「指摘事項はありません」とだけ返してください。無理に指摘事項を挙げることはせず、他の文章を追加することも禁止です。
- 問題がある場合のみ、具体的な指摘内容を返してください。
- この資料は企画会議にて発表することを想定しているため、厳しめにチェックしてください。
"""


def _build_slide_images_content(slides: list[dict]) -> list[dict[str, Any]]:
    """
    スライドごとの画像＋ラベルのコンテンツブロックを構築する

    Args
    -----------------
    - slides: list[dict],               スライドデータのリスト

    Returns
    -----------------
    - content: list[dict[str, Any]],    テキストと画像URLを交互に並べたコンテンツブロックリスト

    """
    content: list[dict[str, Any]] = []
    for slide in slides:
        # スライド番号と伝えたい内容からラベルを生成
        label = f"スライド {slide['slide_number']}"
        if slide.get("intended_message"):
            label += f" / 伝えたい内容: {slide['intended_message']}"
        content.append({"type": "text", "text": label})
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{slide['image_jpeg_b64']}"},
        })
    return content


_OVERALL_PER_TYPE_SUMMARIZE_SYSTEM_PROMPT = """
あなたはプレゼンテーション資料のレビュー専門アシスタントです。
出力は必ずJSONのみで返してください。文章の前置きやコードブロックは禁止です。
プレゼンテーション全体のレビュー結果（Q&A形式）を、自然な日本語文章にまとめてください。
- 「判断ができません」の結果がある場合は、判断するための情報が足りていない旨を記載してください。
- 「指摘事項はありません」の結果は無視し、まとめ文には含めないでください。
- 実際の指摘事項がある結果のみを対象に、まとめた文章を作成してください。複数文になっても構いません。
- 対象となる指摘事項が1件もない場合は summary に「特に指摘事項はありません」とだけ返してください。
- 回答はmarkdown形式の箇条書きで作成してください。
"""


def _build_overall_per_type_prompt_package(
    review_request: dict[str, Any],
    review_points: list[str],
) -> dict[str, Any]:
    """
    指定したレビュー観点セットでプレゼンテーション全体評価プロンプトパッケージを構築する

    Args
    -----------------
    - review_request: dict[str, Any],   スライドデータと全体意図メッセージを含むリクエスト辞書
    - review_points: list[str],         レビュー観点の文字列リスト

    Returns
    -----------------
    - package: dict[str, Any],          system_prompt と user_prompt を含むプロンプトパッケージ

    """
    slides = review_request["slides"]
    overall_msg = review_request.get("overall_intended_message", "")

    ## プロンプト本文を構築
    questions_text = "\n".join(f"- {p}" for p in review_points)
    schema = {
        "reviews": [{"question": p, "result": "string"} for p in review_points]
    }

    intro = f"{len(slides)}枚のスライドからなるプレゼンテーション全体を以下の観点でレビューしてください。"
    if overall_msg:
        intro += f"\nプレゼンテーション全体の意図: {overall_msg}"
    intro += f"\n\nレビュー観点:\n{questions_text}"
    intro += "\n\n以下のスキーマでJSONのみを返してください:\n" + json.dumps(schema, ensure_ascii=False, indent=2)

    ## コンテンツブロックを組み立て
    content: list[dict[str, Any]] = [{"type": "text", "text": intro}]
    content.extend(_build_slide_images_content(slides))
    content.append({"type": "text", "text": "プレゼンテーション全体を評価し、JSONのみで返してください。"})

    return {"system_prompt": SYSTEM_PROMPT, "user_prompt": content}


def build_overall_per_type_summarize_prompt_package(
    ptype_label: str,
    reviews: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    perspective_type のQ&Aレビュー結果をプレゼンテーション全体の集約文章に変換するプロンプトパッケージを構築する

    Args
    -----------------
    - ptype_label: str,                 観点カテゴリの日本語ラベル
    - reviews: list[dict[str, Any]],    question と result を持つレビュー結果リスト

    Returns
    -----------------
    - package: dict[str, Any],          system_prompt と user_prompt を含むプロンプトパッケージ

    """
    # Q&A形式のレビュー結果をテキストに変換
    reviews_text = "".join(
        f"  Q: {r['question']}\n  A: {r['result']}\n"
        for r in reviews
    )
    schema = {"summary": "string"}

    prompt = (
        f"観点カテゴリ「{ptype_label}」に関するプレゼンテーション全体のレビュー結果を、"
        "まとめた文章にしてください。\n"
        f"\nレビュー結果:{reviews_text}"
        "\n\n以下のスキーマでJSONのみを返してください:\n"
        + json.dumps(schema, ensure_ascii=False, indent=2)
    )

    return {
        "system_prompt": _OVERALL_PER_TYPE_SUMMARIZE_SYSTEM_PROMPT,
        "user_prompt": [{"type": "text", "text": prompt}],
    }


_REVISION_SUGGESTION_SYSTEM_PROMPT = """
あなたは、PowerPointスライドのレビュー結果をもとに、「元のスライドをどう直すべきか」を具体的に整理して返すアシスタントです。

目的は、レビュー指摘を単に言い換えることではなく、スライド作成者がそのまま修正作業に着手できるように、修正方針を構造化して返すことです。

以下のルールに厳密に従って出力してください。

【目的】
入力として与えられる
- スライドの内容
- スライドに対するレビュー指摘
をもとに、
- 何が問題か
- どう直すべきか
- どのような文言に差し替えるとよいか
- 修正後にどういう状態になるべきか
を、具体的で実務的な修正方針として返してください。

【出力ルール】
1. 出力は必ずJSON形式のみとしてください
2. JSONの外側に説明文、前置き、補足、Markdown記法、コードブロックを付けないでください
3. 必ず以下のキーをすべて含めてください
   - summary
   - issues
   - actions
   - example_text
   - expected_outcome
4. 情報が不足していても、キーは省略せず、空文字または空配列ではなく、推定可能な範囲で具体化してください
5. レビュー指摘の要約ではなく、「修正作業の指示」として記述してください
6. actions には、作業者がそのまま修正できるレベルで具体的に記載してください
7. example_text には、可能な限りスライドへそのまま流用できる文案を入れてください
8. expected_outcome には、「修正後にスライドがどう見えるべきか」を1文で明確に記載してください
9. 曖昧な表現を避けてください
   - 悪い例: わかりやすくする
   - 良い例: PoC対象と将来対応を表で分離し、優先順位が一目で分かる構成にする
10. 同じ内容を重複して書かないでください

【JSONスキーマ】
以下の構造・型に厳密に従ってください。

{
  "summary": "このスライドをどう修正すべきかを1〜2文で要約した文章",
  "issues": [
    "現状の問題点1",
    "現状の問題点2",
    "現状の問題点3"
  ],
  "actions": [
    {
      "type": "structure",
      "instruction": "構成変更に関する具体的な修正指示"
    },
    {
      "type": "content",
      "instruction": "内容追加・削除・整理に関する具体的な修正指示"
    },
    {
      "type": "expression",
      "instruction": "見出しや文言表現に関する具体的な修正指示"
    }
  ],
  "example_text": {
    "title": "修正後のスライドタイトル案",
    "lead": "修正後のスライド冒頭説明文案",
    "body": [
      "本文や箇条書きの差し替え文案1",
      "本文や箇条書きの差し替え文案2"
    ]
  },
  "expected_outcome": "修正後にどのようなスライドになっているべきか"
}

【各項目の記載ルール】
- summary:
  スライド全体として何を直すべきかを簡潔に要約する
- issues:
  現状の問題を、閲覧者視点で整理して列挙する
- actions:
  修正指示を記載する
  type は必ず次のいずれかを使う
  - structure: レイアウト、情報の並び、章立て、表の分割統合など
  - content: 情報の追加、削除、整理、優先順位付けなど
  - expression: 見出し、説明文、ラベル、表現の言い換えなど
- example_text:
  実際にスライドへ貼れる文案を入れる
  title は必須
  lead は必須
  body は2件以上入れる
- expected_outcome:
  閲覧者が見たときに、何が一目で伝わる状態になるかを書く

【判断基準】
修正方針は、次の観点で具体化してください。
- 何を残すべきか
- 何を分けるべきか
- 何を追加すべきか
- どこを簡潔にすべきか
- どの情報を先に見せるべきか
- 修正後に意思決定しやすくなるか

【禁止事項】
- 単なるレビュー指摘の焼き直し
- 抽象的で作業に落ちない助言
- 「適宜追加してください」「必要に応じて見直してください」だけで終わる記述
- JSON以外の形式での出力
- キー名の変更

以下に対象データを与えます。
この内容をもとに、上記ルールに従ってJSONのみを出力してください。

【スライド内容】
{{SLIDE_CONTENT}}

【レビュー指摘】
{{REVIEW_COMMENTS}}

"""


def build_revision_findings_text(perspectives: list[dict[str, Any]]) -> str:
    """
    観点別レビュー結果を、修正方針提案プロンプトに渡す指摘事項テキストに変換する

    Args
    -----------------
    - perspectives: list[dict[str, Any]],   type / label / summary を持つ観点別レビュー結果リスト

    Returns
    -----------------
    - findings_text: str,                   指摘事項のテキスト

    """
    return "".join(
        f"- {p.get('label') or p.get('type', '')}: {p.get('summary', '')}\n"
        for p in perspectives
    )


def build_revision_suggestion_prompt_package(
    slide: dict[str, Any],
    findings_text: str,
) -> dict[str, Any]:
    """
    1枚のスライドについて、レビュー指摘をもとに修正方針を提案するプロンプトパッケージを構築する

    Args
    -----------------
    - slide: dict[str, Any],            slide_number と image_jpeg_b64 を含むスライドデータ
    - findings_text: str,               観点別レビュー結果（指摘事項）のテキスト

    Returns
    -----------------
    - package: dict[str, Any],          system_prompt と user_prompt を含むプロンプトパッケージ

    """
    slide_content = f"スライド {slide['slide_number']}"

    # システムプロンプト内のプレースホルダーを実データで置換
    system_prompt = (
        _REVISION_SUGGESTION_SYSTEM_PROMPT
        .replace("{{SLIDE_CONTENT}}", slide_content)
        .replace("{{REVIEW_COMMENTS}}", findings_text)
    )

    ## コンテンツブロックを組み立て（対象スライドの画像を添付）
    content: list[dict[str, Any]] = [{"type": "text", "text": slide_content}]
    content.append({
        "type": "image_url",
        "image_url": {"url": f"data:image/jpeg;base64,{slide['image_jpeg_b64']}"},
    })
    content.append({"type": "text", "text": "上記スライドについて、修正方針をJSONのみで返してください。"})

    return {"system_prompt": system_prompt, "user_prompt": content}


def build_overall_per_type_prompt_packages_by_type(
    review_request: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    """
    perspective_type ごとのプロンプトパッケージリストを構築して返す

    Args
    -----------------
    - review_request: dict[str, Any],                   スライドデータと全体意図メッセージを含むリクエスト辞書

    Returns
    -----------------
    - packages: list[tuple[str, dict[str, Any]]],       (perspective_type, プロンプトパッケージ) のタプルリスト

    """
    by_type = _load_review_points()
    return [
        (ptype, _build_overall_per_type_prompt_package(review_request, points))
        for ptype, points in by_type.items()
    ]
