"""settings.ini の読み込みロジック。

main.py(FastAPI)・agenda_service.py から利用するため、
FastAPI等の重い依存を持ち込まない独立したモジュールとして切り出している。
"""

from __future__ import annotations

import configparser
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
# settings.ini はユーザーが編集する運用のため、exe化(frozen)時はexeと同じ階層を参照する
if getattr(sys, "frozen", False):
    SETTINGS_PATH = Path(sys.executable).resolve().parent / "settings.ini"
else:
    SETTINGS_PATH = APP_DIR.parent / "settings.ini"


def _split_csv(raw: str) -> list[str]:
    """
    カンマ区切りの設定値を、前後の空白を除いたリストに変換する(空要素は除く)

    Args
    -----------------
    - raw: str,  カンマ区切りの設定値

    Returns
    -----------------
    - values: list[str],  分割した値の一覧

    """
    return [v.strip() for v in raw.split(",") if v.strip()]


def load_settings() -> dict:
    """
    settings.ini を読み込んで辞書で返す

    Args
    -----------------
    - なし

    Returns
    -----------------
    - settings: dict,  画面・アジェンダ生成で使う設定値(ファイルがない場合は空辞書)

    """
    # 設定ファイルが無い場合は空の設定で起動する(画面側で未設定エラーを表示する)
    config = configparser.ConfigParser()
    if not SETTINGS_PATH.exists():
        print("[警告] settings.ini が見つかりません。")
        return {}
    config.read(SETTINGS_PATH, encoding="utf-8")

    # GROUPSESSIONの取得対象フォーラムID(数値のリストに変換する)
    forum_sids = [int(s) for s in _split_csv(config.get("groupsession", "forum_sid", fallback=""))]

    return {
        # Mattermost履歴の取得期間(日数)。アジェンダの取得期間の初期値に使う
        "read_date": config.getint("history", "read_date", fallback=30),
        "groupsession_forum_sids": forum_sids,
        # GROUPSESSION新着記事の取得期間(日数)。Mattermost側と長い方をアジェンダの取得期間の初期値に使う
        "groupsession_read_date": config.getint("groupsession", "read_date", fallback=30),
        "agenda_mattermost_channels": _split_csv(config.get("growi", "channel_list", fallback="")),
        "growi_root_path": config.get("growi", "root_path", fallback=""),
    }
