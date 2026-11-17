"""アジェンダ生成・GROWI公開に関する共通ロジック。

画面UI(main.pyのHTTPエンドポイント)から利用する関数をまとめている。
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import growi_service as growi
from app.azure_ai_service import call_generate_agenda
from app.model.predict import predict_reminder_scores

# agenda_template.txt はユーザーが編集する運用のため、
# exe化(frozen)時はexeと同じ階層を参照する(main.pyと同一のパス解決)
if getattr(sys, "frozen", False):
    AGENDA_TEMPLATE_PATH = Path(sys.executable).resolve().parent / "agenda_template.txt"
else:
    AGENDA_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "agenda_template.txt"

# 過去アジェンダの手本(few-shot)。agenda_template.txt と同じ階層に置く
# (app/agenda_examples/collect_agenda_examples.py で作成する)
AGENDA_EXAMPLES_PATH = AGENDA_TEMPLATE_PATH.with_name("agenda_examples.json")
# 手本1件あたりの元の投稿・記事の本文の最大文字数(これより長い本文は先頭だけ使う)
MAX_EXAMPLE_MESSAGE_CHARS = 1500
# 手本全体の元の投稿・記事の本文の合計文字数の上限(超える分は古い手本から使わない)
MAX_EXAMPLES_TOTAL_CHARS = 40000

# アジェンダの年月・投稿日時の表示に使うタイムゾーン。
# 実行環境のタイムゾーン設定に依存せずJSTで扱う
# (exe配布時のWindowsにはIANAタイムゾーンDBが無い場合があるため、ZoneInfoではなく固定オフセットを使う)
JST = timezone(timedelta(hours=9), "JST")


def filter_posts_by_reminder_score(posts: list[dict], threshold: float) -> list[dict]:
    """学習済みモデルで各投稿のリマインド必要度をスコアリングし、
    フィルタ強度(threshold)以上のスコアを持つ投稿のみを返す。"""
    if not posts:
        return []
    scores = predict_reminder_scores([p["message"] for p in posts])
    return [post for post, score in zip(posts, scores) if score >= threshold]


# 箇条書きのネスト1段分のインデント(半角スペース4つ)
INDENT = "    "


def _escape_link_text(text: str) -> str:
    """
    Markdownリンクの表示文字列として使えるよう、角括弧をエスケープする

    Args
    -----------------
    - text: str,  リンクの表示文字列

    Returns
    -----------------
    - escaped: str,  "[" / "]" をバックスラッシュでエスケープした文字列

    """
    return text.replace("[", r"\[").replace("]", r"\]")


# AIの出力に含まれるMarkdownリンク
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")


def _strip_unknown_links(text: str, source_text: str) -> str:
    """
    AIが書いたMarkdownリンクのうち、元の投稿・記事に無いURLへのリンクを表示文字列だけにする
    (AIがURLを誤って生成・改変した場合に、誤ったリンクが公開されないようにする)

    Args
    -----------------
    - text: str,         AIが出力した文字列
    - source_text: str,  元の投稿・記事の本文(すべてを連結したもの)

    Returns
    -----------------
    - text: str,  元の投稿・記事に無いURLへのリンクを外した文字列

    """
    return _MARKDOWN_LINK_RE.sub(
        lambda m: m.group(0) if m.group(2) in source_text else m.group(1),
        text,
    )


def load_agenda_examples() -> list[dict]:
    """
    agenda_examples.json(過去アジェンダの手本)を読み込み、few-shotで渡す分を返す。
    新しいアジェンダほどよい手本のため、新しいものから文字数の上限まで採用する

    Args
    -----------------
    なし

    Returns
    -----------------
    - examples: list[dict],  手本の一覧(古い順)。ファイルが無い場合は空のリスト

    """
    # ファイルが無ければ手本なしで生成する
    if not AGENDA_EXAMPLES_PATH.exists():
        return []
    examples = json.loads(AGENDA_EXAMPLES_PATH.read_text(encoding="utf-8"))

    # 新しいページから順に、元の投稿・記事の本文の合計が上限を超えるまで採用する
    selected: list[dict] = []
    total_chars = 0
    for example in sorted(examples, key=lambda e: e["page"], reverse=True):
        items = []
        for item in example["items"]:
            # 長い本文は先頭だけにする(手本としては要約の仕方がわかれば十分なため)
            message = item["input"]["message"][:MAX_EXAMPLE_MESSAGE_CHARS]
            items.append({**item, "input": {**item["input"], "message": message}})
        page_chars = sum(len(item["input"]["message"]) for item in items)
        if selected and total_chars + page_chars > MAX_EXAMPLES_TOTAL_CHARS:
            break
        selected.append({**example, "items": items})
        total_chars += page_chars

    # 会話の後ろほど新しい手本になるよう、古い順に並べ直す
    return list(reversed(selected))


def build_agenda_body_markdown(agenda_items: list[dict], source_items: list[dict]) -> str:
    """
    AIが生成した構造化データ(JSON)から、「全体共有事項」欄のMarkdown箇条書きを組み立てる。
    元の投稿・記事へのリンクは、AIの出力した source_indexes をもとにここで付ける

    Args
    -----------------
    - agenda_items: list[dict],  call_generate_agenda() の戻り値(アジェンダの項目一覧)
    - source_items: list[dict],  AIに渡した投稿・記事一覧(各要素は "url" を持つ)

    Returns
    -----------------
    - agenda_body: str,  「全体共有事項」欄の文章(Markdown箇条書き)

    """
    # AIが本文中に書いたURLの確認用に、元の投稿・記事の本文をまとめておく
    source_text = "\n".join(item.get("message", "") for item in source_items)

    lines: list[str] = []
    for agenda_item in agenda_items:
        # 元の投稿・記事のURLを、AIが出力した index から引く(範囲外・重複の index は無視する)
        urls: list[str] = []
        for index in agenda_item.get("source_indexes", []):
            if isinstance(index, int) and 0 <= index < len(source_items):
                url = source_items[index].get("url")
                if url and url not in urls:
                    urls.append(url)

        # 見出し行: URLがあれば見出しを1件目のURLへのリンクにし、2件目以降は「関連」リンクとして後ろに添える
        title = agenda_item.get("title", "").strip()
        if urls:
            heading = f"- [{_escape_link_text(title)}]({urls[0]})"
            heading += "".join(f" ([関連{n}]({url}))" for n, url in enumerate(urls[1:], start=2))
        else:
            heading = f"- {_strip_unknown_links(title, source_text)}"
        # 見出しの後ろの一言(期限など)は、過去のアジェンダに合わせて全角スペースで区切る
        title_note = _strip_unknown_links(agenda_item.get("title_note", "").strip(), source_text)
        if title_note:
            heading += f"　{title_note}"
        lines.append(heading)

        # 補足情報: 本文の行と、その下に詳細を1段深くネストして記載する
        for detail in agenda_item.get("details", []):
            lines.append(f"{INDENT}- {_strip_unknown_links(detail.get('text', '').strip(), source_text)}")
            for child in detail.get("children", []):
                lines.append(f"{INDENT * 2}- {_strip_unknown_links(child.strip(), source_text)}")

    return "\n".join(lines)


def render_agenda_document(items: list[dict]) -> str:
    """
    AI生成した「全体共有事項」欄の文章を agenda_template.txt に埋め込んだ完成文を返す

    Args
    -----------------
    - items: list[dict],  アジェンダに含める投稿・記事一覧

    Returns
    -----------------
    - agenda: str,  agenda_template.txt に埋め込んだ完成文

    """
    # ひな形が無い場合はAIを呼ぶ前にエラーにする(無駄なAI呼び出しを避ける)
    if not AGENDA_TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"アジェンダのひな形ファイルが見つかりません({AGENDA_TEMPLATE_PATH.name})")

    # 過去アジェンダの手本を読み込み、AIで項目を構造化データとして生成する。
    # Markdownへの組み立て(リンクの付与を含む)はアプリ側で行う
    agenda_items = call_generate_agenda(items, load_agenda_examples())
    agenda_body = build_agenda_body_markdown(agenda_items, items)

    # ひな形に年月・本文を埋め込む
    now = datetime.now(JST)
    template = AGENDA_TEMPLATE_PATH.read_text(encoding="utf-8")
    return (
        template.replace("{{YEAR}}", str(now.year))
        .replace("{{MONTH}}", str(now.month))
        .replace("{{AGENDA_BODY}}", agenda_body)
    )


def publish_agenda_document(
    settings: dict, agenda_text: str, year: int, month: int, grant: int = growi.PAGE_GRANT_PUBLIC
) -> dict:
    """
    アジェンダ本文をGROWIに公開する

    Args
    -----------------
    - settings: dict,      load_settings()の戻り値
    - agenda_text: str,    公開するアジェンダ本文
    - year: int,           公開先ページの年
    - month: int,          公開先ページの月
    - grant: int,          GROWIページの公開範囲(既定は公開)

    Returns
    -----------------
    - result: dict,  {"path", "url", "recreated"}(growi_service.publish_agendaの戻り値)

    """
    root_path = settings.get("growi_root_path", "")
    if not root_path:
        raise ValueError("settings.iniにgrowiのroot_pathが設定されていません")
    return growi.publish_agenda(root_path, year, month, agenda_text, grant)

