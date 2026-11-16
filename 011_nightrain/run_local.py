"""開発時の動作確認用: 監視処理(app.watcher.poll_once)をローカルで1回だけ実行する。

本サービスはAzure上での運用のみを想定しており、このスクリプトは開発者の動作確認専用。
local.settings.json の "Values" を環境変数として読み込み、状態はBlobではなく
.local_state/ フォルダにJSONで保存する。

誤って本番チャンネルへ投稿しないよう、REMIND_DM_USERNAME(リマインドの投稿先をDMに差し替える設定)が
空の場合は実行しない。

使い方(011_nightrain ディレクトリで実行):
    python run_local.py --print-only --skip-ai --lookback-minutes 10080
        投稿もAI呼び出しもせず、7日分の投稿からリマインド対象を判定して、投稿予定のメッセージを表示する
    python run_local.py --lookback-minutes 1440
        直近1日分を対象に、AIで投稿内容を要約してDMへ投稿する

オプション:
    --print-only          Mattermostへ投稿せず、投稿予定のメッセージを画面に表示するだけにする
    --skip-ai             Azure OpenAIを呼ばず、固定の要約で代用する
    --lookback-minutes N  さかのぼって確認する時間(分)。POLL_OVERLAP_MINUTES を上書きする
    --reset-state         .local_state/ を削除し、初回実行の状態から始める
    --ignore-business-hours  営業日・営業時間(平日9:00-18:00、祝日・会社独自の休日を除く)の判定をせずに実行する
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
LOCAL_STATE_DIR = ROOT_DIR / ".local_state"


def _load_local_settings() -> None:
    """
    local.settings.json の "Values" を環境変数に設定する

    Args
    -----------------
    - なし

    Returns
    -----------------
    - None

    """
    path = ROOT_DIR / "local.settings.json"
    if not path.exists():
        raise SystemExit("local.settings.json がありません。local.settings.json.sample をコピーして作成してください。")
    values = json.loads(path.read_text(encoding="utf-8")).get("Values", {})
    for key, value in values.items():
        os.environ[key] = str(value)


def main() -> None:
    """コマンドライン引数を解釈し、監視処理を1回実行する"""
    parser = argparse.ArgumentParser(description="監視処理をローカルで1回実行する(開発用)")
    parser.add_argument("--print-only", action="store_true", help="投稿せず、メッセージを表示するだけにする")
    parser.add_argument("--skip-ai", action="store_true", help="Azure OpenAIを呼ばず、固定の要約で代用する")
    parser.add_argument("--lookback-minutes", type=int, help="さかのぼって確認する時間(分)")
    parser.add_argument("--reset-state", action="store_true", help=".local_state/ を削除してから実行する")
    parser.add_argument("--ignore-business-hours", action="store_true", help="営業日・営業時間の判定をせずに実行する")
    args = parser.parse_args()

    # Windowsのコンソールでも日本語のログが文字化けしないようにする
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)

    # 設定を読み込み、状態の保存先をローカルフォルダに切り替える
    _load_local_settings()
    os.environ["STATE_STORE_DIR"] = str(LOCAL_STATE_DIR)
    if args.lookback_minutes is not None:
        os.environ["POLL_OVERLAP_MINUTES"] = str(args.lookback_minutes)
    if args.reset_state and LOCAL_STATE_DIR.exists():
        shutil.rmtree(LOCAL_STATE_DIR)

    # 安全のため、投稿先がDMに差し替えられていない場合は実行しない
    dm_username = os.environ.get("REMIND_DM_USERNAME", "").strip()
    if not dm_username:
        raise SystemExit("REMIND_DM_USERNAME が空です。ローカル実行ではDMへの差し替えが必須です。")
    print(f"リマインドの投稿先: DM:{dm_username}" + ("(--print-only のため投稿しません)" if args.print_only else ""))

    # 設定の読み込み後にimportする(モジュールの読み込み時に環境変数を参照する箇所があるため)
    from app import mattermost_service as mm
    from app import state_store
    from app import watcher

    # --print-only: 投稿処理を画面への表示に差し替え、状態も保存しない
    # (保存すると、表示しただけの投稿が通知済み扱いになり、後で実際に投稿する確認ができなくなるため)
    if args.print_only:
        def _print_message(channel_id: str, message: str, props: dict | None = None) -> None:
            print("=" * 60)
            print(message)
            print("=" * 60)
        mm.post_message = _print_message
        state_store.save_state = lambda key, state: None

    # --skip-ai: AIによる要約を、固定の内容に差し替える
    summarize = None
    if args.skip_ai:
        def summarize(post_message: str, author_username: str, posted_at) -> dict:
            return {
                "kind": "request",
                "title": "(--skip-ai のため表題の作成を省略)",
                "task": "(--skip-ai のため作業の要約を省略)",
                "notes": "",
                "deadline": None,
                "deadline_time": None,
            }

    watcher.poll_once(summarize=summarize, ignore_business_hours=args.ignore_business_hours)


if __name__ == "__main__":
    main()
