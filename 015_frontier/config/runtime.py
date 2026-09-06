"""実行時に参照する「データ取得に関する設定」の永続化と読み込み。

設定画面(/api/settings)で編集し、`acquisition_settings.json`(外出しファイル)へ
保存する。アプリ起動時にはキャッシュせず、**その設定を使う処理が実行されるたびに**
このモジュールの load_runtime_config() を呼んで最新値を読み込む。

- データ取得開始日: この日付の 0:00(アプリのタイムゾーン基準)以降のみ取得対象
- Mattermost 取得チャンネル / Trello 取得ボード: チェックした ID のみ取得対象
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

# ユーザーが手書きする settings.ini とは別のファイルに保存する
CONFIG_PATH = Path(__file__).resolve().parents[1] / "acquisition_settings.json"


def _as_str_list(value: object) -> list[str]:
    """JSON から読んだ値を文字列リストへ正規化する。"""
    if not isinstance(value, list):
        return []
    return [str(x).strip() for x in value if str(x).strip()]


@dataclass
class RuntimeConfig:
    """データ取得に関する実行時設定。"""

    # データ取得開始日(None なら未設定)
    since_date: date | None = None
    # 取得対象
    mattermost_channel_ids: list[str] = field(default_factory=list)
    trello_board_ids: list[str] = field(default_factory=list)
    github_repo: str = ""          # "owner/repo"。空なら .env の GITHUB_REPOS を使う
    github_design_path: str = ""   # github_repo からの相対パス。設計書フォルダ
    growi_page_path: str = ""      # "/projects/foo"。空なら .env の GROWI_TARGET_PATHS を使う

    def to_api_dict(self) -> dict:
        """フロントエンド / ファイル保存で使う辞書表現。"""
        return {
            "since_date": self.since_date.isoformat() if self.since_date else None,
            "mattermost_channel_ids": list(self.mattermost_channel_ids),
            "trello_board_ids": list(self.trello_board_ids),
            "github_repo": self.github_repo,
            "github_design_path": self.github_design_path,
            "growi_page_path": self.growi_page_path,
        }


def load_runtime_config() -> RuntimeConfig:
    """acquisition_settings.json を毎回読み込んで RuntimeConfig を返す。

    ファイルが無い / 壊れている場合はデフォルト値を返す(起動は妨げない)。
    """
    cfg = RuntimeConfig()
    if not CONFIG_PATH.exists():
        return cfg

    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning(
            "%s の読み込みに失敗しました。デフォルト値を使用します: %s", CONFIG_PATH.name, exc
        )
        return cfg
    if not isinstance(data, dict):
        return cfg

    # --- データ取得開始日 ---
    raw_since = (data.get("since_date") or "").strip() if isinstance(data.get("since_date"), str) else None
    if raw_since:
        try:
            cfg.since_date = date.fromisoformat(raw_since)
        except ValueError:
            logger.warning("since_date の形式が不正です(無視します): %r", raw_since)

    # --- 取得対象 ---
    cfg.mattermost_channel_ids = _as_str_list(data.get("mattermost_channel_ids"))
    cfg.trello_board_ids = _as_str_list(data.get("trello_board_ids"))
    if isinstance(data.get("github_repo"), str):
        cfg.github_repo = data["github_repo"].strip()
    if isinstance(data.get("github_design_path"), str):
        cfg.github_design_path = data["github_design_path"].strip()
    if isinstance(data.get("growi_page_path"), str):
        cfg.growi_page_path = data["growi_page_path"].strip()
    return cfg


def save_runtime_config(cfg: RuntimeConfig) -> None:
    """RuntimeConfig を acquisition_settings.json へ書き出す。"""
    CONFIG_PATH.write_text(
        json.dumps(cfg.to_api_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info("%s を保存しました", CONFIG_PATH.name)
