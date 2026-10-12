"""アプリの起動スクリプト（exe 化のエントリポイント）。

PyInstaller はエントリスクリプトをパッケージ外のトップレベルスクリプトとして実行するため、
相対 import を使う backend/main.py を直接エントリにできない。ここから backend パッケージを import して起動する。

開発時も `python run.py` で起動できる（`python -m uvicorn backend.main:app --port 8000` と同じ）。
"""

import uvicorn

from backend.main import app

HOST = "127.0.0.1"
PORT = 8000


def main() -> None:
    """Web サーバを起動する。"""
    # http でマイクを使えるのは localhost だけなので、外部には公開せずローカルで待ち受ける
    print(f"コミュニケーション練習ツールを起動しました: http://localhost:{PORT}")
    print("終了するときは、このウィンドウを閉じてください。")
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
