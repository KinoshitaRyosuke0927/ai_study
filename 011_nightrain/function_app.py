"""Azure Functions エントリポイント(チャット内容自動リマインドサービス)。

タイマートリガーで一定間隔ごとに app.watcher.poll_once() を呼び出し、
指定したMattermostチャンネル・GROUPSESSIONフォーラムの新着投稿からリマインド対象を見つけて、
指定のMattermostチャンネルへ確認を促すメッセージを投稿する。

実行間隔はアプリケーション設定 POLL_SCHEDULE(NCRONTAB形式。例: "0 */5 * * * *" = 5分ごと)で指定する。
Azure portal から値を変更すれば、再デプロイせずに間隔を変えられる(変更後にFunction Appが再起動される)。
"""

import logging
import os
import sys

import azure.functions as func

# Azure Functions(Linux Consumption)実行時、sys.pathにこのファイル自身のディレクトリが
# 含まれず "app" パッケージをインポートできない場合があるため、明示的に追加する。
# __file__ベースの解決はワーカーの読み込み方式によっては信頼できないため、
# Azure Functionsが実行時に設定するスクリプトルートの環境変数を優先して使う。
_script_root = os.environ.get("AzureWebJobsScriptRoot") or os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _script_root)

from app import watcher  # noqa: E402

app = func.FunctionApp()


@app.timer_trigger(
    schedule="%POLL_SCHEDULE%",
    arg_name="mytimer",
    run_on_startup=False,
    use_monitor=True,
)
def poll_and_remind(mytimer: func.TimerRequest) -> None:
    """POLL_SCHEDULEの間隔で実行され、監視対象の新着投稿をチェックしてリマインドを投稿する"""
    # 前回の実行が大きく遅れていた場合はログに残す(取りこぼしの調査用)
    if mytimer.past_due:
        logging.warning("タイマーの実行が予定より遅れています")
    watcher.poll_once()
