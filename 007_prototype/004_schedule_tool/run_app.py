"""スケジュール確認ツールを起動し、ブラウザで画面を開く。

exe(PyInstaller)の入口として使う。通常の Python でも次のように起動できる:
    python run_app.py

引数:
    --port 番号     使うポート(既定は 8000)
    --no-browser    ブラウザを自動で開かない
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import webbrowser

import uvicorn

from app.config import CONFIG_FILE, FROZEN, ensure_config_file

# 他のツールと同じ 8000 番(同時に使う想定はないため)
DEFAULT_PORT = 8000


def port_in_use(port: int) -> bool:
    """
    ポートがすでに使われているか確かめる

    Args
    -----------------
    - port: int,  ポート番号

    Returns
    -----------------
    - in_use: bool,  使われていれば True

    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def open_browser_later(url: str) -> None:
    """
    サーバの起動を少し待ってから、ブラウザで画面を開く

    Args
    -----------------
    - url: str,  開くURL

    Returns
    -----------------
    - None

    """
    def worker() -> None:
        time.sleep(1.5)
        webbrowser.open(url)

    threading.Thread(target=worker, daemon=True).start()


def main() -> int:
    """
    ツールを起動する

    Args
    -----------------
    - なし

    Returns
    -----------------
    - code: int,  終了コード(0 は正常)

    """
    parser = argparse.ArgumentParser(description="スケジュール確認ツール")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"使うポート(既定は {DEFAULT_PORT})")
    parser.add_argument("--no-browser", action="store_true", help="ブラウザを自動で開かない")
    args = parser.parse_args()
    url = f"http://localhost:{args.port}"

    # 初回起動時は、exe(または run_app.py)と同じフォルダに config.json を作る
    if ensure_config_file():
        print(f"設定ファイルを作りました: {CONFIG_FILE}")

    # すでに起動しているときは、ブラウザで開くだけにする
    if port_in_use(args.port):
        print(f"ポート {args.port} はすでに使われています。ツールがすでに起動している可能性があります。")
        if not args.no_browser:
            webbrowser.open(url)
        if FROZEN:
            input("Enter キーで閉じます。")
        return 1

    # 画面のモジュールは config.json を作った後に読み込む
    from app.main import app

    print("スケジュール確認ツールを起動します。")
    print(f"  画面: {url}")
    print("  終了するときは、このウィンドウを閉じてください。")
    if not args.no_browser:
        open_browser_later(url)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
