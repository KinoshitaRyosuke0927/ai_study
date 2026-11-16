"""サービスの設定値の読み込み。

設定はすべて Azure Functions のアプリケーション設定(=環境変数)で管理し、
変更する場合は Azure portal の「環境変数」画面などから値を書き換える運用とする
(パッケージ内に設定ファイルは持たない)。設定項目の一覧は README.md を参照。
"""

from __future__ import annotations

import os

# Azure OpenAI のデプロイ名の既定値(011_agenda_tool のアジェンダ生成と同じモデル)
DEFAULT_AZURE_OPENAI_DEPLOYMENT = "gpt-5.4-mini"


def get_required(name: str) -> str:
    """
    必須の設定値を取得する(未設定・空文字の場合はエラー)

    Args
    -----------------
    - name: str,  設定名(環境変数名)

    Returns
    -----------------
    - value: str,  設定値

    """
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"アプリケーション設定 {name} が設定されていません")
    return value


def get_str(name: str, default: str = "") -> str:
    """任意の文字列の設定値を取得する(未設定の場合は既定値)"""
    return os.environ.get(name, "").strip() or default


def get_list(name: str) -> list[str]:
    """
    カンマ区切りの設定値をリストで取得する(前後の空白・空要素は除く)

    Args
    -----------------
    - name: str,  設定名(環境変数名)

    Returns
    -----------------
    - values: list[str],  分割した値の一覧(未設定の場合は空リスト)

    """
    return [v.strip() for v in os.environ.get(name, "").split(",") if v.strip()]


def get_int(name: str, default: int) -> int:
    """整数の設定値を取得する(未設定の場合は既定値、数値でない場合はエラー)"""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"アプリケーション設定 {name} は整数で指定してください(現在値: {raw})") from exc


def get_float(name: str, default: float) -> float:
    """小数の設定値を取得する(未設定の場合は既定値、数値でない場合はエラー)"""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise RuntimeError(f"アプリケーション設定 {name} は数値で指定してください(現在値: {raw})") from exc


def load_watch_settings() -> dict:
    """
    監視・リマインド処理で使う設定値をまとめて読み込む

    Args
    -----------------
    - なし

    Returns
    -----------------
    - settings: dict,  監視対象・通知先・しきい値などの設定値

    """
    # GROUPSESSIONのフォーラムIDは数値として扱う
    forum_sids_raw = get_list("WATCH_GROUPSESSION_FORUM_SIDS")
    try:
        forum_sids = [int(s) for s in forum_sids_raw]
    except ValueError as exc:
        raise RuntimeError(
            f"アプリケーション設定 WATCH_GROUPSESSION_FORUM_SIDS は数値をカンマ区切りで指定してください(現在値: {forum_sids_raw})"
        ) from exc

    return {
        # 監視対象のMattermostチャンネル(表示名)
        "watch_channels": get_list("WATCH_MATTERMOST_CHANNELS"),
        # 監視対象のGROUPSESSIONフォーラムID
        "watch_forum_sids": forum_sids,
        # リマインドの投稿先チャンネル(表示名)
        "remind_channel": get_str("REMIND_CHANNEL"),
        # 動作確認用: 設定するとリマインドの投稿先をこのユーザーとのDMに差し替える
        "remind_dm_username": get_str("REMIND_DM_USERNAME"),
        # リマインド投稿の先頭に付けるメンション(未設定なら "@channel"。"none" を指定すると付けない)
        "remind_mention": "" if get_str("REMIND_MENTION").lower() == "none" else get_str("REMIND_MENTION", "@channel"),
        # リマインド対象とみなすモデルスコアのしきい値
        "threshold": get_float("REMINDER_THRESHOLD", 0.7),
        # ポーリング間隔に対する取りこぼし防止の重なり幅(分)
        "overlap_minutes": get_int("POLL_OVERLAP_MINUTES", 2),
        # 通知済みIDを記録しておく日数(これより古い記録は削除する)
        "notified_retention_days": get_int("NOTIFIED_RETENTION_DAYS", 30),
        # 1件のリマインド作成・投稿に失敗した場合に再試行する回数
        "max_retry_count": get_int("MAX_RETRY_COUNT", 3),
    }
