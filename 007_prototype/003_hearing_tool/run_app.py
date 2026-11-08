"""ヒアリング管理ツールを起動し、ブラウザで画面を開く。

exe（PyInstaller）の入口として使う。通常の Python でも次のように起動できる：
    .venv\\Scripts\\python.exe run_app.py

引数：
    --port 番号     使うポート（既定は 8000）
    --no-browser    ブラウザを自動で開かない
"""

import argparse
import socket
import sys
import threading
import time
import webbrowser

import uvicorn

from app.config import CONFIG_FILE, FROZEN, ensure_config_file, load_config
from app.main import app


def port_in_use(port: int) -> bool:
    """ポートがすでに使われているか確かめる。

    Args:
        port: ポート番号。

    Returns:
        bool: 使われていれば True。
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def open_browser_later(url: str) -> None:
    """サーバの起動を少し待ってから、ブラウザで画面を開く。

    Args:
        url: 開く URL。

    Returns:
        None
    """
    def worker() -> None:
        time.sleep(1.5)
        webbrowser.open(url)

    threading.Thread(target=worker, daemon=True).start()


def main() -> int:
    """ツールを起動する。

    Returns:
        int: 終了コード（0 は正常）。
    """
    parser = argparse.ArgumentParser(description="ヒアリング管理ツール")
    parser.add_argument("--port", type=int, default=8000, help="使うポート（既定は 8000）")
    parser.add_argument("--no-browser", action="store_true", help="ブラウザを自動で開かない")
    args = parser.parse_args()
    url = f"http://localhost:{args.port}"

    # exe の初回起動では、exe と同じフォルダに config.json を作る
    if FROZEN and ensure_config_file():
        print(f"設定ファイルを作りました：{CONFIG_FILE}")

    # すでに起動しているときは、ブラウザで開くだけにする
    if port_in_use(args.port):
        print(f"ポート {args.port} はすでに使われています。ツールがすでに起動している可能性があります。")
        if not args.no_browser:
            webbrowser.open(url)
        if FROZEN:
            input("Enter キーで閉じます。")
        return 1

    # 起動の案内を出し、ブラウザを開いてからサーバを動かす
    config = load_config()
    print("ヒアリング管理ツールを起動します。")
    print(f"  画面：{url}")
    print(f"  データの場所：{config['data_path']}")
    print("  終了するときは、このウィンドウを閉じてください。")
    if not args.no_browser:
        open_browser_later(url)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
