#!/usr/bin/env bash
# ============================================================
# AI学習ポータル DB セットアップ(macOS / Linux / Git Bash)
#   1. データベースと接続ユーザを作成
#   2. テーブル定義とデータ(02_schema_and_data.sql)を登録
# 実行例(このフォルダで):
#   bash setup_db.sh                      # localhost:3306 に root で接続
#   MYSQL_HOST=db.example MYSQL_ROOT_USER=admin bash setup_db.sh
# ============================================================
set -euo pipefail

HOST="${MYSQL_HOST:-localhost}"
PORT="${MYSQL_PORT:-3306}"
ROOT_USER="${MYSQL_ROOT_USER:-root}"
HERE="$(cd "$(dirname "$0")" && pwd)"

# mysql コマンドの確認
command -v mysql >/dev/null || { echo "mysql コマンドが見つかりません。" >&2; exit 1; }

# パスワードの入力(画面には表示しない)
read -rsp "MySQL 管理者(${ROOT_USER})のパスワード: " ROOT_PW; echo
read -rsp "作成する接続ユーザ ai_learning_portal のパスワード: " APP_PW; echo
[ -n "$APP_PW" ] || { echo "接続ユーザのパスワードを入力してください。" >&2; exit 1; }

# 管理者パスワードは環境変数で渡す(コマンド履歴に残さない)
export MYSQL_PWD="$ROOT_PW"
COMMON=(-h "$HOST" -P "$PORT" -u "$ROOT_USER" --default-character-set=utf8mb4)
ESCAPED="${APP_PW//\\/\\\\}"
ESCAPED="${ESCAPED//\'/\'\'}"

# 1. データベースと接続ユーザを作成(01_create_database.sql と同じ内容)
mysql "${COMMON[@]}" <<SQL
CREATE DATABASE IF NOT EXISTS ai_learning_portal CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER IF NOT EXISTS 'ai_learning_portal'@'localhost' IDENTIFIED BY '${ESCAPED}';
ALTER USER 'ai_learning_portal'@'localhost' IDENTIFIED BY '${ESCAPED}';
GRANT ALL PRIVILEGES ON ai_learning_portal.* TO 'ai_learning_portal'@'localhost';
FLUSH PRIVILEGES;
SQL
echo "データベースと接続ユーザを作成しました。"

# 2. テーブル定義とデータを登録
mysql "${COMMON[@]}" ai_learning_portal < "$HERE/02_schema_and_data.sql"
echo "テーブル定義とデータを登録しました。"
unset MYSQL_PWD

echo
echo "次に backend/.env を作成し、MYSQL_PASSWORD に今入力した接続ユーザのパスワードを設定してください。"
