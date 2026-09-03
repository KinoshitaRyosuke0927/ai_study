-- Frontier スキーマ定義(MySQL 8.x / utf8mb4)
-- 起動時に CREATE TABLE IF NOT EXISTS で冪等に適用する。

CREATE TABLE IF NOT EXISTS events (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  week VARCHAR(10) NOT NULL,              -- ISO週 "2026-W36"
  source VARCHAR(20) NOT NULL,            -- mattermost / trello / growi / github / sample
  type VARCHAR(40) NOT NULL,              -- post / card_moved / pr_merged / page_updated / ...
  actor VARCHAR(255) NOT NULL,
  ts DATETIME NOT NULL,                   -- UTC
  ref VARCHAR(255) NOT NULL,              -- ソース内一意キー(投稿ID / カードID / SHA / ページID)
  payload JSON NOT NULL,
  event_uid VARCHAR(300) GENERATED ALWAYS AS (concat(source, ':', ref, ':', type)) STORED,
  UNIQUE KEY uq_event (event_uid),        -- 再実行時の二重取り込み防止
  INDEX idx_week_source (week, source)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS items (
  item_key VARCHAR(255) PRIMARY KEY,      -- 例: "trello:card:abc123", "github:pr:42"
  source VARCHAR(20) NOT NULL,
  type VARCHAR(40) NOT NULL,              -- card / issue / pr / page / thread
  title VARCHAR(1024) NOT NULL,
  status VARCHAR(40) NOT NULL,            -- open / done / merged / archived / ...
  assignee VARCHAR(255) NULL,
  first_week VARCHAR(10) NOT NULL,        -- 初検出週
  last_week VARCHAR(10) NOT NULL,         -- 最終確認週
  payload JSON NOT NULL
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- 週次断面(差分計算の本体)
CREATE TABLE IF NOT EXISTS week_items (
  week VARCHAR(10) NOT NULL,
  item_key VARCHAR(255) NOT NULL,
  status VARCHAR(40) NOT NULL,
  title VARCHAR(1024) NOT NULL,
  PRIMARY KEY (week, item_key)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS metrics (
  week VARCHAR(10) NOT NULL,
  name VARCHAR(60) NOT NULL,              -- mattermost_posts, github_prs_merged など
  value DOUBLE NOT NULL,
  PRIMARY KEY (week, name)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS reports (
  week VARCHAR(10) PRIMARY KEY,
  kpt JSON NOT NULL,                      -- keep / problem / try / done / learned
  risks JSON NOT NULL,                    -- 潜在問題リスト
  summary_md MEDIUMTEXT NOT NULL,         -- Markdown形式の週次サマリ
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS decisions (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  week VARCHAR(10) NOT NULL,
  summary TEXT NOT NULL,                  -- 決定事項
  rationale TEXT NULL,                    -- 理由・背景(暗黙知)
  participants JSON NULL,
  source_refs JSON NOT NULL               -- event_id や URL の配列
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS embeddings (
  chunk_id VARCHAR(300) PRIMARY KEY,      -- "{source}:{ref}:{chunk_no}"
  week VARCHAR(10) NOT NULL,
  source VARCHAR(20) NOT NULL,
  ref VARCHAR(255) NOT NULL,
  text MEDIUMTEXT NOT NULL,
  vec BLOB NOT NULL,                      -- float32配列
  model VARCHAR(100) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_week (week)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS runs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  started_at DATETIME NOT NULL,
  finished_at DATETIME NULL,
  status VARCHAR(20) NOT NULL,            -- running / success / error
  mode VARCHAR(10) NOT NULL,              -- manual / scheduled
  detail TEXT NULL                        -- エラー内容など
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
