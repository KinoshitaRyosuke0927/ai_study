"""Azure Functions エントリポイント。

5分間隔のタイマートリガーで、Mattermostの特定チャンネル・DMに投稿された
"/nightrain agenda"・"/nightrain remind" をポーリングで検知し、自動応答する(app.slash_command_watcher)。

画面UI(app.main、手動操作用のFastAPIアプリ)はセキュリティ上の理由からAzure上には配置せず、
PyInstallerでのexe配布のみで提供する。このFunction Appはポーリング専用。
"""

import os
import sys

import azure.functions as func

# Azure Functions(Linux Consumption)実行時、sys.pathにこのファイル自身のディレクトリが
# 含まれず "app" パッケージをインポートできない場合があるため、明示的に追加する。
# __file__ベースの解決はワーカーの読み込み方式によっては信頼できないため、
# Azure Functionsが実行時に設定するスクリプトルートの環境変数を優先して使う。
_script_root = os.environ.get("AzureWebJobsScriptRoot") or os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _script_root)

from app import slash_command_watcher

app = func.FunctionApp()


@app.timer_trigger(
    schedule="0 */5 * * * *",
    arg_name="mytimer",
    run_on_startup=False,
    use_monitor=True,
)
def poll_slash_commands(mytimer: func.TimerRequest) -> None:
    """5分ごとに実行され、settings.iniのslash_watchで指定された監視対象をポーリングする"""
    slash_command_watcher.poll_once()
