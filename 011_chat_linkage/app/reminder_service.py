"""リマインド関連の共通ロジック。

手動UI(main.pyのHTTPエンドポイント)・自動応答(slash_command_watcher)の
両方から利用する純粋関数として切り出している。
"""

from __future__ import annotations

from datetime import datetime

from app import mattermost_service as mm
from app.agenda_service import filter_posts_by_reminder_score
from app.azure_ai_service import call_summarize_post_for_reminder

# リマインド作成時に、リアクション済みとみなす絵文字名
REMINDER_DONE_EMOJI = "sumi"


def build_mention_line(post_id: str, members: list[str]) -> str:
    """
    指定投稿へのリアクション状況をもとに、REMINDER_DONE_EMOJI未リアクションの
    メンバーへの@メンション文字列を組み立てる

    Args
    -----------------
    - post_id: str,        対象投稿のID
    - members: list[str],  settings.ini [channel_users] members のメンバー一覧

    Returns
    -----------------
    - mention_line: str,  "@user1 @user2 ..." 形式の文字列(全員リアクション済みなら空文字)

    """
    reactions = mm.get_post_reactions(post_id)
    reacted = {r["username"] for r in reactions if r["emoji_name"] == REMINDER_DONE_EMOJI}
    targets = [m for m in members if m not in reacted]
    return " ".join(f"@{m}" for m in targets)


def _escape_table_cell(text: str) -> str:
    """Markdown表のセル内で改行・パイプ文字が表崩れの原因にならないよう置換する"""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def build_reminder_list_message(settings: dict) -> str:
    """
    "/nightrain remind" コマンド用: settings.iniの[history]channel・read_dateで指定された
    対象チャンネルからリマインド候補投稿を抽出し、Markdown表形式の一覧メッセージを組み立てる。
    画面から作成する場合と異なり、挨拶文・メンションは付けずメインコンテンツのみを返す。

    Args
    -----------------
    - settings: dict,  load_settings()の戻り値

    Returns
    -----------------
    - message: str,  スレッド返信用の一覧メッセージ(対象投稿が無い場合はその旨のメッセージ)

    """
    channel_name = settings.get("channel", "")
    read_date = settings.get("read_date", 30)
    threshold = settings.get("slash_watch_reminder_threshold", 0.9)

    name_to_id = {c["name"]: c["id"] for c in mm.list_my_channels()}
    channel_id = name_to_id.get(channel_name)
    if channel_id is None:
        return f"settings.iniのhistory.channel「{channel_name}」が見つかりませんでした。"

    end_ts = int(datetime.now().timestamp() * 1000)
    start_ts = end_ts - read_date * 24 * 60 * 60 * 1000
    posts = mm.get_channel_posts_in_range(channel_id, start_ts, end_ts)
    candidates = filter_posts_by_reminder_score(posts, threshold)

    if not candidates:
        return "リマインドが必要な投稿は見つかりませんでした。"

    rows = ["| 投稿日時 | 元の投稿へのリンク | 投稿内容要約 |", "| --- | --- | --- |"]
    for post in candidates:
        date_str = datetime.fromtimestamp(post["create_at"] / 1000).strftime("%Y-%m-%d %H:%M")
        summary = call_summarize_post_for_reminder(post["message"])
        rows.append(
            f"| {date_str} | [投稿を見る]({post['url']}) | {_escape_table_cell(summary)} |"
        )

    return "\n".join(rows)
