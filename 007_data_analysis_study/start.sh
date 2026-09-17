#!/usr/bin/env bash
# 起動スクリプト: 初回は venv 作成 + 依存インストール、その後サーバ起動
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "[setup] Python 仮想環境を作成します..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
echo "[setup] 依存関係をインストールします..."
pip install -q -r requirements.txt

PORT="${PORT:-8777}"
echo "[start] http://localhost:${PORT} で起動します（Ctrl+C で停止）"
exec uvicorn backend.main:app --reload --host 0.0.0.0 --port "${PORT}"
