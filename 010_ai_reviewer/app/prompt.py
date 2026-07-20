from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any


if getattr(sys, "frozen", False):
    _APP_ROOT = Path(sys.executable).resolve().parent
else:
    _APP_ROOT = Path(__file__).parent.parent

_CSV_PATH = _APP_ROOT / "review_point.csv"
_PP_CHECK_CSV_PATH = _APP_ROOT / "pp_check_points.csv"

# 観点設定APIで扱うCSVソース名とファイルパスの対応
CSV_SOURCES: dict[str, Path] = {
    "review_point": _CSV_PATH,
    "pp_check_points": _PP_CHECK_CSV_PATH,
}


def _read_csv_rows(csv_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """
    CSVファイルをヘッダーと行データに分けて読み込む（detail列が空の行は除外）

    Args
    -----------------
    - csv_path: Path,                       読み込み対象のCSVファイルパス

    Returns
    -----------------
    - fieldnames: list[str],                CSVのヘッダー列名リスト
    - rows: list[dict[str, str]],           行データのリスト

    """
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = [row for row in reader if (row.get("detail") or "").strip()]
    return fieldnames, rows


def _parse_apply_flag(value: str | None) -> bool:
    """
    CSVのapply_flag列の文字列("TRUE"/"FALSE")を真偽値に変換する
    """
    return (value or "").strip().upper() == "TRUE"


def _load_review_points_from_csv(csv_path: Path) -> dict[str, list[str]]:
    """
    指定したCSVファイルから、apply_flagがTRUEのレビュー観点のみを読み込み、perspective_type 別辞書に分けて返す

    Args
    -----------------
    - csv_path: Path,                   読み込み対象のCSVファイルパス

    Returns
    -----------------
    - by_type: dict[str, list[str]],    perspective_type をキーとするレビュー観点辞書

    """
    by_type: dict[str, list[str]] = {}
    _, rows = _read_csv_rows(csv_path)
    for row in rows:
        # apply_flagがFALSEの観点はレビュー対象から除外
        if not _parse_apply_flag(row.get("apply_flag")):
            continue
        ptype = (row.get("perspective_type") or "").strip()
        by_type.setdefault(ptype, []).append((row.get("detail") or "").strip())
    return by_type


def _load_review_points() -> dict[str, list[str]]:
    """
    review_point.csv と pp_check_points.csv からレビュー観点を読み込み、perspective_type 別辞書にまとめて返す

    Returns
    -----------------
    - by_type: dict[str, list[str]],    perspective_type をキーとするレビュー観点辞書

    """
    by_type: dict[str, list[str]] = {}
    for csv_path in (_CSV_PATH, _PP_CHECK_CSV_PATH):
        for ptype, details in _load_review_points_from_csv(csv_path).items():
            by_type.setdefault(ptype, []).extend(details)
    return by_type


def list_review_point_settings() -> list[dict[str, Any]]:
    """
    観点設定画面向けに、両方のCSVファイルの観点一覧（apply_flagの状態を含む）をまとめて返す

    Returns
    -----------------
    - settings: list[dict[str, Any]],   source / row_index / perspective_type / role / apply_flag / detail を持つ辞書のリスト

    """
    settings: list[dict[str, Any]] = []
    for source, csv_path in CSV_SOURCES.items():
        _, rows = _read_csv_rows(csv_path)
        for index, row in enumerate(rows):
            settings.append({
                "source": source,
                "row_index": index,
                "perspective_type": (row.get("perspective_type") or "").strip(),
                "role": (row.get("role") or "").strip() or None,
                "apply_flag": _parse_apply_flag(row.get("apply_flag")),
                "detail": (row.get("detail") or "").strip(),
            })
    return settings


def update_review_point_settings(updates: list[dict[str, Any]]) -> None:
    """
    観点設定のapply_flagをまとめて更新し、対象のCSVファイルへ書き戻す

    Args
    -----------------
    - updates: list[dict[str, Any]],   source / row_index / apply_flag を持つ更新内容のリスト

    """
    # source（CSVファイル）ごとに更新内容をまとめる
    updates_by_source: dict[str, dict[int, bool]] = {}
    for u in updates:
        source = u["source"]
        if source not in CSV_SOURCES:
            continue
        updates_by_source.setdefault(source, {})[u["row_index"]] = bool(u["apply_flag"])

    for source, index_map in updates_by_source.items():
        csv_path = CSV_SOURCES[source]
        fieldnames, rows = _read_csv_rows(csv_path)
        for index, apply_flag in index_map.items():
            if 0 <= index < len(rows):
                rows[index]["apply_flag"] = "TRUE" if apply_flag else "FALSE"
        with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


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


_SLIDE_EDIT_PLAN_SYSTEM_PROMPT = """
あなたは、プレゼンテーション資料全体のレビュー指摘を確認し、指摘事項がどのスライドに関係するかを判断した上で、
画像編集AI（元のスライド画像1枚を書き換えるimage-to-image編集モデル）向けの指示文をスライドごとに振り分けるアシスタントです。

画像編集AIは、元のスライド画像とテキストの指示だけを受け取り、画像そのものを直接書き換えます。レビュー指摘の文章をそのまま渡しても意図通りに編集されないため、画像編集に適した具体的な指示文を作成してください。

【出力ルール】
1. 出力は必ずJSON形式のみとしてください。前置き・説明・コードブロックは禁止です。
2. 以下のスキーマに厳密に従ってください:
   {"slide_plans": [{"slide_number": number, "instruction": "string または null"}]}
3. 提示されたすべてのスライド画像の内容を確認し、各指摘事項が実際にどのスライドの内容に関係するかを判断してください。指摘事項の文章に記載がなくても、画像の内容から判断して構いません。
4. 該当する指摘があるスライドについて、instruction には画像編集AIがそのまま実行できるレベルで、視覚的に何をどう変えるかを具体的に記述してください。
   - どのテキスト・見出し・数値・図表・レイアウトを、どう変更するかを明確に書く
   - 差し替えるべきテキストがある場合は、実際の日本語の文言をそのまま指示文中に含める
   - 元のスライドのデザイン・配色・フォント・レイアウトの雰囲気はできる限り維持し、指摘のあった箇所のみを変更するよう指示する
   - 「わかりやすくして」のような抽象的な表現は禁止し、誰が実行しても同じ結果になるよう具体化する
   - スライドの端から端まで要素を詰め込まず、上下左右に十分な余白を確保した、企画資料として読みやすいレイアウトを維持するよう明記する
   - 1枚のスライドに複数の指摘が該当する場合は、すべてを1つの指示文にまとめて記載してください
5. どの指摘事項にも該当しないスライドについては、instruction に null を設定してください（そのスライドは編集しません）。
6. 提示されたスライド番号すべてについて、1件ずつ必ず slide_plans に含めてください（該当なしの場合もnullで含める）。
"""

# 画像編集AIへの指示文に、AIの出力内容によらず必ず付加する余白確保のガイダンス
LAYOUT_GUIDANCE_SUFFIX = (
    "スライド全体に要素を詰め込みすぎないこと。上下左右に十分な余白（マージン）を確保し、"
    "文字や図表をスライドの端ギリギリまで配置しないこと。情報量を減らさず、"
    "余白を活かした読みやすいレイアウトに整えること。"
)


def build_slide_edit_plan_prompt_package(
    slides: list[dict[str, Any]],
    findings_text: str,
) -> dict[str, Any]:
    """
    全スライド画像と指摘事項から、資料全体を見渡してスライドごとの画像編集AI向け指示を一括で決定するプロンプトパッケージを構築する

    Args
    -----------------
    - slides: list[dict[str, Any]],   スライドデータ（slide_number, image_png_b64）のリスト
    - findings_text: str,             観点別レビュー結果（指摘事項）のテキスト

    Returns
    -----------------
    - package: dict[str, Any],        system_prompt と user_prompt を含むプロンプトパッケージ

    """
    slide_numbers = [slide["slide_number"] for slide in slides]
    intro = (
        f"{len(slides)}枚のスライドからなるプレゼンテーション資料全体に対する指摘事項は以下の通りです。\n\n"
        f"{findings_text}\n"
        "\n各スライドの画像を確認し、指摘事項がどのスライドに該当するかを判断した上で、"
        "スライドごとの画像編集AI向け指示をJSONのみで返してください。"
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
