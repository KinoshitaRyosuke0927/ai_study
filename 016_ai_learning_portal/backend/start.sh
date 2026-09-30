#!/bin/sh
# コンテナの起動スクリプト(Dockerfile の CMD から実行する)
#
# DB(Azure Database for MySQL)は、使われていない間は停止している。停止中でもアプリを起動し、
# 最初のアクセスで DB を起動できるよう、マイグレーションに失敗しても起動を続ける。
# スキーマの変更を含む版をデプロイするときは、先に DB を起動しておくこと(docs/azure_deploy.md)。

# マイグレーションを適用(DB に接続できなければスキップ)
alembic upgrade head || echo "[start] DB に接続できないため、マイグレーションをスキップしました"

# アプリを起動
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
