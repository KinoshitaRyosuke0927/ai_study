-- ============================================================
-- AI学習ポータル データベースと接続ユーザの作成
--   MySQL の管理者(root など)で実行する。
--   実行前に 'CHANGE_ME' を接続ユーザのパスワードに書き換えること
--   (backend/.env の MYSQL_PASSWORD と同じ値にする)。
--   実行例: mysql -u root -p < 01_create_database.sql
-- ============================================================

-- データベース(日本語を扱うため utf8mb4)
CREATE DATABASE IF NOT EXISTS ai_learning_portal
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- アプリの接続ユーザ(既に存在する場合はパスワードを更新する)
CREATE USER IF NOT EXISTS 'ai_learning_portal'@'localhost' IDENTIFIED BY 'CHANGE_ME';
ALTER USER 'ai_learning_portal'@'localhost' IDENTIFIED BY 'CHANGE_ME';

-- 権限の付与
GRANT ALL PRIVILEGES ON ai_learning_portal.* TO 'ai_learning_portal'@'localhost';
FLUSH PRIVILEGES;
