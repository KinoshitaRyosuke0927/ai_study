"""ツールの設定（config.json）を読み込む。"""

import json
import sys
from pathlib import Path

# exe（PyInstaller）で動いているかどうか
FROZEN = getattr(sys, "frozen", False)

# ツールのルートフォルダ。config.json と data フォルダはここに置く
#   通常：003_hearing_tool フォルダ
#   exe：exe があるフォルダ
TOOL_ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent.parent

# 画面のファイルなど、プログラムに同梱するファイルの場所
#   exe では、展開先のフォルダ（_internal）になる
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", TOOL_ROOT))

# 設定ファイルと、その見本の場所
CONFIG_FILE = TOOL_ROOT / "config.json"
CONFIG_EXAMPLE_FILE = TOOL_ROOT / "config.example.json"
if not CONFIG_EXAMPLE_FILE.exists():
    CONFIG_EXAMPLE_FILE = RESOURCE_ROOT / "config.example.json"

# 設定ファイルがないときに使う値（exe では .env を exe と同じフォルダに置く）
DEFAULTS = {
    "user_name": "未設定",
    "data_dir": "./data",
    "azure_env_file": "./.env" if FROZEN else "../001_communication_helper/.env",
}


def load_config() -> dict:
    """設定を読み込む。

    config.json があればそれを、なければ見本の config.example.json を使う。
    どちらにもない項目は DEFAULTS の値で補う。

    Returns:
        dict: 設定。data_dir は絶対パスの Path に変換して "data_path" に入れる。
    """
    # 読み込むファイルを決める（本番の設定を優先する。メモ帳で保存した BOM 付きのファイルも読めるようにする）
    source = CONFIG_FILE if CONFIG_FILE.exists() else CONFIG_EXAMPLE_FILE

    # ファイルの内容を既定値に上書きする
    config = dict(DEFAULTS)
    if source.exists():
        config.update(json.loads(source.read_text(encoding="utf-8-sig")))

    # データの場所は、ツールのルートからの相対パスとして解決する
    data_path = Path(config["data_dir"])
    if not data_path.is_absolute():
        data_path = (TOOL_ROOT / data_path).resolve()
    config["data_path"] = data_path
    config["config_source"] = source.name if source.exists() else "(既定値)"
    return config


def ensure_config_file() -> bool:
    """config.json がなければ、既定値で作る（exe の初回起動用）。

    Returns:
        bool: 新しく作ったら True。
    """
    if CONFIG_FILE.exists():
        return False
    CONFIG_FILE.write_text(json.dumps(DEFAULTS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def save_user_name(user_name: str) -> None:
    """更新者の名前を config.json に保存する。

    Args:
        user_name: 各行の updated_by に記録する名前。

    Returns:
        None
    """
    # 今の設定を読み込む（config.json がなければ見本から作る）
    current = dict(DEFAULTS)
    source = CONFIG_FILE if CONFIG_FILE.exists() else CONFIG_EXAMPLE_FILE
    if source.exists():
        current.update(json.loads(source.read_text(encoding="utf-8-sig")))

    # 名前を書き換えて config.json に保存する
    current["user_name"] = user_name
    CONFIG_FILE.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
