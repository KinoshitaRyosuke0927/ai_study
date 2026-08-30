"""Mattermostの特定チャンネル・DMをポーリングし、"/nightrain agenda"・"/nightrain remind"
投稿を検知して自動応答する。Azure Functionsのタイマートリガーから呼び出される想定。

Mattermost管理者権限(Bot作成・スラッシュコマンド登録・Outgoing Webhook設定)を使わず、
既存の個人アクセストークンのみで完結させるため、正式なスラッシュコマンド機能ではなく、
単なるメッセージ本文として"/nightrain agenda"・"/nightrain remind"の投稿をポーリングで検知する。
"""

from __future__ import annotations

import traceback
from datetime import datetime, timezone

from app import mattermost_service as mm
from app import state_store
from app.agenda_service import build_and_publish_agenda
from app.reminder_service import build_reminder_list_message
from app.settings_loader import load_settings

AGENDA_COMMAND = "/nightrain agenda"
REMIND_COMMAND = "/nightrain remind"


def poll_once(now: datetime | None = None) -> None:
    """
    1回分のポーリング処理。監視対象チャンネル/DMそれぞれについて新着投稿を取得し、
    "/nightrain agenda"・"/nightrain remind" にマッチする投稿を検出して応答する

    Args
    -----------------
    - now: datetime | None,  現在時刻(テスト用に注入可能。省略時は実行時刻)

    Returns
    -----------------
    - None

    """
    now = now or datetime.now(timezone.utc)
    settings = load_settings()
    targets = _resolve_watch_targets(settings)

    for target in targets:
        try:
            _process_target(target, settings, now)
        except Exception as exc:
            # 1つの監視対象で予期しない例外が起きても、他の監視対象の処理は継続する
            print(f"[エラー] 監視対象 {target['label']} の処理に失敗しました: {exc}")


def _resolve_watch_targets(settings: dict) -> list[dict]:
    """
    settings.iniのslash_watch設定から、監視対象チャンネルID一覧を解決する

    Args
    -----------------
    - settings: dict,  load_settings()の戻り値

    Returns
    -----------------
    - targets: list[dict],  [{"channel_id": str, "label": str}, ...]

    """
    targets = []

    # チャンネル名 -> チャンネルIDを解決する
    channels = mm.list_my_channels()
    name_to_id = {c["name"]: c["id"] for c in channels}
    for name in settings.get("slash_watch_channels", []):
        channel_id = name_to_id.get(name)
        if channel_id is None:
            print(f"[警告] slash_watch.watch_channels のチャンネル「{name}」が見つかりません")
            continue
        targets.append({"channel_id": channel_id, "label": name})

    # DM相手のユーザー名 -> DMチャンネルIDを解決する
    for username in settings.get("slash_watch_dm_users", []):
        try:
            channel_id = mm.get_direct_channel_id_by_username(username)
        except Exception as exc:
            print(f"[警告] slash_watch.watch_dm_users のユーザー「{username}」のDM解決に失敗しました: {exc}")
            continue
        targets.append({"channel_id": channel_id, "label": f"DM:{username}"})

    return targets


def _process_target(target: dict, settings: dict, now: datetime) -> None:
    """1つの監視対象(チャンネル/DM)について、新着投稿を取得しコマンドを検知・応答する"""
    channel_id = target["channel_id"]
    state = state_store.load_channel_state(channel_id)

    overlap_ms = settings.get("slash_watch_poll_overlap_minutes", 2) * 60 * 1000
    end_ts = int(now.timestamp() * 1000)
    if state["last_processed_at"] == 0:
        # 初回実行時は直近のオーバーラップ分のみさかのぼる(過去の大量投稿を誤検知しないため)
        start_ts = end_ts - overlap_ms
    else:
        start_ts = state["last_processed_at"] - overlap_ms

    # Mattermost APIへの取得に失敗した場合は、状態を更新せず今回の処理を打ち切る
    # (次回のポーリングで同じ期間を再取得することでリトライに相当する)
    try:
        posts = mm.get_channel_posts_in_range(channel_id, start_ts, end_ts)
    except Exception as exc:
        print(f"[エラー] {target['label']} の投稿取得に失敗しました: {exc}")
        return

    already_processed_ids = set(state["last_processed_post_ids"])
    max_create_at = state["last_processed_at"]
    processed_ids_at_max = list(state["last_processed_post_ids"])

    for post in posts:
        if post["id"] in already_processed_ids:
            continue

        command = post["message"].strip()
        if command == AGENDA_COMMAND:
            _safe_handle(_handle_agenda_command, post, settings)
        elif command == REMIND_COMMAND:
            _safe_handle(_handle_remind_command, post, settings)

        if post["create_at"] > max_create_at:
            max_create_at = post["create_at"]
            processed_ids_at_max = [post["id"]]
        elif post["create_at"] == max_create_at:
            processed_ids_at_max.append(post["id"])

    # コマンドに一致した投稿が無くても、取得に成功していれば状態は進める
    # (無関係な投稿を毎回スキャンし続けることを防ぐ)
    state_store.save_channel_state(channel_id, max_create_at, processed_ids_at_max)


def _safe_handle(handler, post: dict, settings: dict) -> None:
    """コマンドハンドラを実行し、失敗した場合はスレッドへエラー通知を試みる。
    個々のコマンド処理の失敗で他の投稿の処理を止めないための共通ラッパー。"""
    try:
        handler(post, settings)
    except Exception as exc:
        print(f"[エラー] {post['id']} の処理に失敗しました: {exc}")
        print(traceback.format_exc())
        try:
            mm.post_message(post["channel_id"], f"処理中にエラーが発生しました: {exc}", root_id=post["id"])
        except Exception:
            pass  # 通知自体の失敗はログのみで無視する


def _handle_agenda_command(post: dict, settings: dict) -> None:
    """"/nightrain agenda" 投稿を検知した際の処理"""
    result_message = build_and_publish_agenda(settings)
    mm.post_message(post["channel_id"], result_message, root_id=post["id"])


def _handle_remind_command(post: dict, settings: dict) -> None:
    """"/nightrain remind" 投稿を検知した際の処理"""
    result_message = build_reminder_list_message(settings)
    mm.post_message(post["channel_id"], result_message, root_id=post["id"])
