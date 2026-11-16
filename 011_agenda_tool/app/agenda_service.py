"""アジェンダ生成・GROWI公開に関する共通ロジック。

画面UI(main.pyのHTTPエンドポイント)から利用する関数をまとめている。
"""

from __future__ import annotations

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
    agenda_body = call_generate_agenda(items)

    if not AGENDA_TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"アジェンダのひな形ファイルが見つかりません({AGENDA_TEMPLATE_PATH.name})")

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

