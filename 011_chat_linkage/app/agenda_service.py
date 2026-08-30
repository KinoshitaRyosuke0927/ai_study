"""アジェンダ生成・GROWI公開に関する共通ロジック。

手動UI(main.pyのHTTPエンドポイント)・自動応答(slash_command_watcher)の
両方から利用する純粋関数として切り出している。
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from app import growi_service as growi
from app import mattermost_service as mm
from app.azure_ai_service import call_generate_agenda
from app.model.predict import predict_reminder_scores

# agenda_template.txt はユーザーが編集する運用のため、
# exe化(frozen)時はexeと同じ階層を参照する(main.pyと同一のパス解決)
if getattr(sys, "frozen", False):
    AGENDA_TEMPLATE_PATH = Path(sys.executable).resolve().parent / "agenda_template.txt"
else:
    AGENDA_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "agenda_template.txt"


def filter_posts_by_reminder_score(posts: list[dict], threshold: float) -> list[dict]:
    """学習済みモデルで各投稿のリマインド必要度をスコアリングし、
    フィルタ強度(threshold)以上のスコアを持つ投稿のみを返す。"""
    if not posts:
        return []
    scores = predict_reminder_scores([p["message"] for p in posts])
    return [post for post, score in zip(posts, scores) if score >= threshold]


def collect_mattermost_agenda_items(settings: dict, threshold: float | None = None) -> list[dict]:
    """
    settings.iniの growi.channel_list・history.read_date をもとに、対象Mattermostチャンネルの
    直近投稿を取得し、リマインド候補のみアジェンダ項目として抽出する
    (Mattermost投稿のみが対象。GROUPSESSIONは自動ログインの安全性の観点から対象外)

    Args
    -----------------
    - settings: dict,          load_settings()の戻り値
    - threshold: float | None, リマインド候補と判定するスコアのしきい値(省略時はsettingsの既定値)

    Returns
    -----------------
    - items: list[dict],  [{"message","username","source":"mattermost","url"}, ...]

    """
    threshold = threshold if threshold is not None else settings.get("slash_watch_reminder_threshold", 0.9)
    channel_names = settings.get("agenda_mattermost_channels", [])
    read_date = settings.get("read_date", 30)

    name_to_id = {c["name"]: c["id"] for c in mm.list_my_channels()}
    end_ts = int(datetime.now().timestamp() * 1000)
    start_ts = end_ts - read_date * 24 * 60 * 60 * 1000

    items = []
    for name in channel_names:
        channel_id = name_to_id.get(name)
        if channel_id is None:
            continue
        posts = mm.get_channel_posts_in_range(channel_id, start_ts, end_ts)
        for post in filter_posts_by_reminder_score(posts, threshold):
            items.append({
                "message": post["message"],
                "username": post["username"],
                "source": "mattermost",
                "url": post["url"],
            })
    return items


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

    now = datetime.now()
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


def build_and_publish_agenda(settings: dict) -> str:
    """
    "/nightrain agenda" コマンド用: 項目収集→AI生成→GROWI自動公開までを一括実行し、
    Mattermostへ返信するための結果メッセージを組み立てる

    Args
    -----------------
    - settings: dict,  load_settings()の戻り値

    Returns
    -----------------
    - message: str,  スレッド返信用のメッセージ(公開結果のURLを含む、
                      対象投稿が無い場合はその旨のメッセージ)

    """
    items = collect_mattermost_agenda_items(settings)
    if not items:
        return "直近の対象チャンネルにアジェンダ化できる投稿が見つかりませんでした。"

    agenda_text = render_agenda_document(items)
    now = datetime.now()
    # 自動生成した内容は未確認のまま第三者に公開されないよう、自分のみ閲覧可能な状態で公開する
    # (画面からの手動公開はユーザーが選択した公開範囲(既定は公開)のままとし、この既定はここでのみ上書きする)
    result = publish_agenda_document(settings, agenda_text, now.year, now.month, grant=growi.PAGE_GRANT_ONLY_ME)
    return f"AIMのアジェンダを作成しました: {result['url']}"
