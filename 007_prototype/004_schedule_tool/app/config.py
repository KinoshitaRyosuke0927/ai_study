"""ツールの設定(config.json)の読み込みと、前回の選択(グループ・メンバー)の保存を行う。

config.json に保存するのは接続先・画面の初期値・前回選んだグループとメンバーのIDだけで、
予定の内容は保存しない。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# exe(PyInstaller)で動いているかどうか
FROZEN = getattr(sys, "frozen", False)

# ツールのルートフォルダ(config.json を置く場所)
#   通常: 004_schedule_tool フォルダ / exe: exe があるフォルダ
TOOL_ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent.parent

# 画面のファイルなど、プログラムに同梱するファイルの場所(exe では _internal フォルダ)
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", TOOL_ROOT))

CONFIG_FILE = TOOL_ROOT / "config.json"
# 業務状況のラベル(予定名は含まない)と学習したモデルの保存先
DATA_DIR = TOOL_ROOT / "data"

# 設定の既定値(config.json に無い項目はこの値を使う)
DEFAULTS: dict = {
    # GROUPSESSION のURL(末尾の / は不要)
    "groupsession_base_url": "https://gs.jbdcl.com/gsession",
    # 空き時間の判定条件の初期値
    "business_start": "09:00",
    "business_end": "18:00",
    "slot_minutes": 30,
    "lunch_start": "12:00",
    "lunch_end": "13:00",
    "min_duration_minutes": 60,
    # 一度に取得できる最大の週数(GROUPSESSIONへの負荷と待ち時間を抑えるため)
    "max_weeks": 8,
    # 業務状況の画面で一度に取得できる最大の週数(ラベル付け・出社割合の出力は長い期間を扱うため)
    "max_weeks_status": 26,
    # 業務状況のラベル保存・削除とモデルの学習を使えるようにするか
    #   false(既定・配布版): 学習済みモデルでの推定とCSV出力だけ使える(ボタンを隠し、APIも受け付けない)
    #   true(管理者): ラベル付け・学習ができる
    "labeling_enabled": False,
    # 前回選んだマイグループとメンバー(IDのみ)
    "last_group": "",
    "last_member_ids": [],
}

# 画面から変更して保存してよい項目
SAVABLE_KEYS = {"last_group", "last_member_ids"}


def load_config() -> dict:
    """
    config.json を読み込み、無い項目を既定値で補って返す

    Args
    -----------------
    - なし

    Returns
    -----------------
    - config: dict,  設定値

    """
    # 既定値に、config.json の内容を上書きする(メモ帳で保存した BOM 付きのファイルも読めるようにする)
    config = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            config.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig")))
        except json.JSONDecodeError:
            print(f"[警告] {CONFIG_FILE.name} の形式が正しくないため、既定値で起動します。")
    config["groupsession_base_url"] = str(config["groupsession_base_url"]).rstrip("/")
    return config


def ensure_config_file() -> bool:
    """
    config.json が無ければ既定値で作る(初回起動用)

    Args
    -----------------
    - なし

    Returns
    -----------------
    - created: bool,  新しく作った場合 True

    """
    if CONFIG_FILE.exists():
        return False
    CONFIG_FILE.write_text(json.dumps(DEFAULTS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def save_selection(values: dict) -> dict:
    """
    前回の選択(グループ・メンバーのID)を config.json に保存する

    Args
    -----------------
    - values: dict,  保存する値(SAVABLE_KEYS に含まれる項目のみ反映する)

    Returns
    -----------------
    - config: dict,  保存後の設定値

    """
    # 今の config.json の内容を読み込む(無ければ既定値から作る)
    current = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            current.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig")))
        except json.JSONDecodeError:
            pass

    # 保存してよい項目だけを上書きして書き戻す
    for key in SAVABLE_KEYS & values.keys():
        current[key] = values[key]
    CONFIG_FILE.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return load_config()
