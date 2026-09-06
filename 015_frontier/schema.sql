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

-- ------------------------------------------------------------------
-- 設計書分析 / コード分析の結果(方式D: メタは列 / 本体は JSON / トレーサビリティは専用テーブル)
-- ------------------------------------------------------------------

-- 分析 1 回ぶん
CREATE TABLE IF NOT EXISTS analysis_runs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  kind VARCHAR(10) NOT NULL,              -- design / code
  repo VARCHAR(255) NOT NULL,             -- owner/repo
  branch VARCHAR(255) NOT NULL,
  tree_sha VARCHAR(64) NULL,              -- 取得時点のツリー SHA(リポジトリ状態の目印)
  content_hash CHAR(64) NOT NULL,         -- 分析対象ファイル内容の SHA-256(同一入力の判定=キャッシュキー)
  model VARCHAR(100) NOT NULL,
  params JSON NOT NULL,                   -- 上限値・fallback 閾値など再現用パラメータ
  stats JSON NOT NULL,                    -- トークン使用量・ファイル数・セクション数など
  status VARCHAR(20) NOT NULL,            -- success / error
  detail TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_kind_repo_created (kind, repo, created_at),
  INDEX idx_kind_hash (kind, content_hash)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- 分析結果の機能単位(画面表示・差分機能・RAG が参照する本体)
CREATE TABLE IF NOT EXISTS analysis_features (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  run_id BIGINT NOT NULL,
  ordinal INT NOT NULL,                   -- 実行内の並び順
  name VARCHAR(512) NOT NULL,             -- 機能の名称
  overview MEDIUMTEXT NULL,               -- 機能の概要
  context_mode VARCHAR(20) NOT NULL,      -- narrowed / full / fallback
  meta JSON NOT NULL,                     -- context_char_len / selected_* / error など画面表示用メタ
  sections JSON NOT NULL,                 -- [{heading, body}] 詳細仕様
  INDEX idx_run (run_id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- 機能が参照している設計書セクション / コードシンボル(トレーサビリティ。RAG の出典引き当てに使う)
CREATE TABLE IF NOT EXISTS analysis_feature_refs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  run_id BIGINT NOT NULL,
  feature_id BIGINT NOT NULL,
  ref_kind VARCHAR(20) NOT NULL,          -- design_section / code_symbol / code_file
  file_path VARCHAR(512) NOT NULL,        -- 設計書ファイル / ソースファイルのパス
  locator VARCHAR(512) NOT NULL,          -- section_id / "path::symbol" / path
  heading VARCHAR(1024) NULL,             -- design: 見出しパス
  symbol_name VARCHAR(255) NULL,          -- code: 関数/クラス名
  start_line INT NULL,                    -- code: 開始行
  end_line INT NULL,                      -- code: 終了行
  extra JSON NULL,
  INDEX idx_feature (feature_id),
  INDEX idx_run_kind (run_id, ref_kind),
  INDEX idx_path (file_path)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- ------------------------------------------------------------------
-- 実装差分解析(設計書分析 と コード分析 の突き合わせ結果)
-- ------------------------------------------------------------------

-- 差分解析 1 回ぶん
CREATE TABLE IF NOT EXISTS spec_code_diffs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  repo VARCHAR(255) NOT NULL,
  design_run_id BIGINT NOT NULL,          -- 突き合わせに使った設計書分析 run
  code_run_id BIGINT NOT NULL,            -- 突き合わせに使ったコード分析 run
  model VARCHAR(100) NOT NULL,
  stats JSON NOT NULL,                    -- ペア数・トークンなど
  diff_count INT NOT NULL,                -- 相違点の件数(ダッシュボード表示用)
  status VARCHAR(20) NOT NULL,            -- success / error
  detail TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_repo_created (repo, created_at)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- 相違点 1 件
CREATE TABLE IF NOT EXISTS spec_code_diff_items (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  diff_id BIGINT NOT NULL,
  ordinal INT NOT NULL,
  feature_name VARCHAR(512) NOT NULL,     -- 突き合わせた機能名(代表)
  design_feature_id BIGINT NULL,          -- analysis_features.id(設計書側)
  code_feature_id BIGINT NULL,            -- analysis_features.id(コード側)
  verdict VARCHAR(20) NOT NULL,           -- conflict / design_only / code_only
  severity VARCHAR(10) NOT NULL,          -- high / mid / low
  summary VARCHAR(1024) NOT NULL,         -- 相違点の要約
  design_state MEDIUMTEXT NULL,           -- 設計書ではどうなっているか
  code_state MEDIUMTEXT NULL,             -- コードではどうなっているか
  evidence JSON NOT NULL,                 -- {design:[refs], code:[refs]} トレーサビリティ
  INDEX idx_diff (diff_id),
  INDEX idx_verdict (diff_id, verdict)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- ------------------------------------------------------------------
-- Mattermost 情報の蓄積 → アカウント横断分析 / RAG
-- 「現在情報取得」の結果を post_id で冪等に蓄積し(mm_posts)、
-- アカウント単位でチャンネル横断の分析(mm_account_analyses)を行う。
-- 会話はスレッド単位でチャンク化(mm_chunks)し、埋め込みは既存 embeddings
-- テーブルへ source='mattermost' で書く(既存 RAG がそのまま拾う)。
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mm_channels (
  channel_id VARCHAR(40) PRIMARY KEY,
  name VARCHAR(255) NOT NULL DEFAULT '',
  display_name VARCHAR(255) NOT NULL DEFAULT '',
  first_seen_at DATETIME NULL,
  last_seen_at DATETIME NULL
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS mm_users (
  user_id VARCHAR(40) PRIMARY KEY,
  username VARCHAR(255) NOT NULL DEFAULT '',
  first_seen_at DATETIME NULL,
  last_seen_at DATETIME NULL
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS mm_posts (
  post_id VARCHAR(40) PRIMARY KEY,        -- ★ dedup キー(期間が重複取得されても増えない)
  channel_id VARCHAR(40) NOT NULL,
  user_id VARCHAR(40) NOT NULL,
  root_id VARCHAR(40) NOT NULL DEFAULT '',
  is_reply TINYINT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL,           -- UTC
  week VARCHAR(10) NOT NULL,              -- "2026-W36"(既存の週次と揃える)
  message MEDIUMTEXT NOT NULL,
  reactions JSON NOT NULL,                -- {emoji: count}
  reaction_count INT NOT NULL DEFAULT 0,
  ingest_run_id BIGINT NULL,
  INDEX idx_mm_posts_ch_time (channel_id, created_at),
  INDEX idx_mm_posts_user_time (user_id, created_at),
  INDEX idx_mm_posts_root (root_id),
  INDEX idx_mm_posts_week (week)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS mm_ingest_runs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  mode VARCHAR(10) NOT NULL,              -- current / range
  window_start DATE NULL,
  window_end DATE NULL,
  channel_ids JSON NOT NULL,
  content_hash CHAR(64) NOT NULL,         -- (channel群 + 期間 + post_id/message/reactions) の SHA-256
  post_count INT NOT NULL,
  channel_count INT NOT NULL,
  user_count INT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_mm_ingest_hash (content_hash)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS mm_chunks (
  chunk_id VARCHAR(120) PRIMARY KEY,      -- "mm:<channel_id>:<root_id or post_id>"
  channel_id VARCHAR(40) NOT NULL,
  root_id VARCHAR(40) NOT NULL DEFAULT '',
  week VARCHAR(10) NOT NULL,
  start_at DATETIME NOT NULL,
  end_at DATETIME NOT NULL,
  participants JSON NOT NULL,             -- user_id[]
  post_ids JSON NOT NULL,
  text MEDIUMTEXT NOT NULL,               -- "username: message" を連結
  content_hash CHAR(64) NOT NULL,         -- 投稿集合が変わったら埋め込みを再生成
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_mm_chunks_ch (channel_id),
  INDEX idx_mm_chunks_week (week)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS mm_account_analyses (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  ingest_run_id BIGINT NOT NULL,
  window_start DATE NULL,
  window_end DATE NULL,
  channel_ids JSON NOT NULL,
  content_hash CHAR(64) NOT NULL,
  model VARCHAR(100) NOT NULL,
  topics JSON NOT NULL,                   -- チーム内の主な話題(1 段目の出力)
  stats JSON NOT NULL,                    -- アカウント数・投稿数・トークンなど
  status VARCHAR(20) NOT NULL,            -- success / error
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_mm_an_hash (content_hash),
  INDEX idx_mm_an_created (created_at)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS mm_account_analysis_items (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  analysis_id BIGINT NOT NULL,
  ordinal INT NOT NULL,
  user_id VARCHAR(40) NOT NULL,
  username VARCHAR(255) NOT NULL,
  overview MEDIUMTEXT NULL,
  stats JSON NOT NULL,                    -- 投稿数/返信数/参加channel数/活動日数/被リアクション等
  sections JSON NOT NULL,                 -- [{heading, body}]
  INDEX idx_mm_ai_analysis (analysis_id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- 分析が根拠にした投稿(トレーサビリティ / RAG の出典引き当て)
CREATE TABLE IF NOT EXISTS mm_account_analysis_refs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  analysis_id BIGINT NOT NULL,
  item_id BIGINT NOT NULL,
  post_id VARCHAR(40) NOT NULL,
  channel_id VARCHAR(40) NOT NULL,
  created_at DATETIME NULL,
  excerpt VARCHAR(500) NOT NULL DEFAULT '',
  INDEX idx_mm_ar_item (item_id),
  INDEX idx_mm_ar_post (post_id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- ------------------------------------------------------------------
-- Trello 情報の蓄積 → アカウント横断分析 / RAG(Mattermost と同型)
-- ボード/カード/アカウントを整理して蓄積し、アカウント単位でボード横断の
-- 活動(担当・コメント・操作)を分析する。カード 1 枚 = 1 チャンクで RAG 化。
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tr_boards (
  board_id VARCHAR(40) PRIMARY KEY,
  name VARCHAR(512) NOT NULL DEFAULT '',
  url VARCHAR(512) NOT NULL DEFAULT '',
  first_seen_at DATETIME NULL,
  last_seen_at DATETIME NULL
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS tr_members (
  username VARCHAR(255) PRIMARY KEY,
  full_name VARCHAR(255) NOT NULL DEFAULT '',
  first_seen_at DATETIME NULL,
  last_seen_at DATETIME NULL
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS tr_lists (
  list_id VARCHAR(40) PRIMARY KEY,
  board_id VARCHAR(40) NOT NULL,
  name VARCHAR(512) NOT NULL DEFAULT '',
  INDEX idx_tr_lists_board (board_id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS tr_cards (
  card_id VARCHAR(40) PRIMARY KEY,
  board_id VARCHAR(40) NOT NULL,
  list_id VARCHAR(40) NOT NULL DEFAULT '',
  list_name VARCHAR(512) NOT NULL DEFAULT '',
  name VARCHAR(1024) NOT NULL DEFAULT '',
  description MEDIUMTEXT NOT NULL,
  labels JSON NOT NULL,
  due DATETIME NULL,
  due_complete TINYINT NOT NULL DEFAULT 0,
  member_usernames JSON NOT NULL,
  checklists JSON NOT NULL,
  url VARCHAR(512) NOT NULL DEFAULT '',
  content_hash CHAR(64) NOT NULL,
  snapshot_at DATETIME NOT NULL,
  ingest_run_id BIGINT NULL,
  INDEX idx_tr_cards_board (board_id),
  INDEX idx_tr_cards_list (list_id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS tr_card_members (
  card_id VARCHAR(40) NOT NULL,
  username VARCHAR(255) NOT NULL,
  PRIMARY KEY (card_id, username),
  INDEX idx_tr_cm_user (username)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS tr_activity (
  activity_id VARCHAR(40) PRIMARY KEY,    -- Trello action id(安定)
  card_id VARCHAR(40) NOT NULL,
  board_id VARCHAR(40) NOT NULL,
  username VARCHAR(255) NOT NULL DEFAULT '',
  kind VARCHAR(12) NOT NULL,              -- comment / activity
  text MEDIUMTEXT NOT NULL,
  created_at DATETIME NULL,
  ingest_run_id BIGINT NULL,
  INDEX idx_tr_act_user (username, created_at),
  INDEX idx_tr_act_card (card_id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS tr_ingest_runs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  board_ids JSON NOT NULL,
  content_hash CHAR(64) NOT NULL,
  board_count INT NOT NULL,
  list_count INT NOT NULL,
  card_count INT NOT NULL,
  activity_count INT NOT NULL,
  member_count INT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_tr_ingest_hash (content_hash)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS tr_chunks (
  chunk_id VARCHAR(120) PRIMARY KEY,      -- "trello:<card_id>"
  board_id VARCHAR(40) NOT NULL,
  card_id VARCHAR(40) NOT NULL,
  list_name VARCHAR(512) NOT NULL DEFAULT '',
  week VARCHAR(10) NOT NULL,
  participants JSON NOT NULL,             -- username[]
  text MEDIUMTEXT NOT NULL,
  content_hash CHAR(64) NOT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_tr_chunks_board (board_id),
  INDEX idx_tr_chunks_week (week)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS tr_account_analyses (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  ingest_run_id BIGINT NOT NULL,
  board_ids JSON NOT NULL,
  content_hash CHAR(64) NOT NULL,
  model VARCHAR(100) NOT NULL,
  themes JSON NOT NULL,                   -- チームの作業テーマ(1 段目の出力)
  stats JSON NOT NULL,
  status VARCHAR(20) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_tr_an_hash (content_hash),
  INDEX idx_tr_an_created (created_at)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS tr_account_analysis_items (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  analysis_id BIGINT NOT NULL,
  ordinal INT NOT NULL,
  username VARCHAR(255) NOT NULL,
  full_name VARCHAR(255) NOT NULL DEFAULT '',
  overview MEDIUMTEXT NULL,
  stats JSON NOT NULL,
  sections JSON NOT NULL,
  INDEX idx_tr_ai_analysis (analysis_id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- 分析が根拠にしたカード / コメント(トレーサビリティ / RAG の出典引き当て)
CREATE TABLE IF NOT EXISTS tr_account_analysis_refs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  analysis_id BIGINT NOT NULL,
  item_id BIGINT NOT NULL,
  ref_kind VARCHAR(12) NOT NULL,          -- card / comment / activity
  card_id VARCHAR(40) NOT NULL,
  board_id VARCHAR(40) NOT NULL,
  created_at DATETIME NULL,
  excerpt VARCHAR(500) NOT NULL DEFAULT '',
  INDEX idx_tr_ar_item (item_id),
  INDEX idx_tr_ar_card (card_id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- ------------------------------------------------------------------
-- コード変更履歴(コミットをファイル単位・ユーザ単位で蓄積 → 分析 / RAG)
-- 情報量を抑えるため patch 本体は保存せず、ハンク見出し + 打ち切り抜粋のみ保持。
-- カード/投稿と同じく 1 コミット = 1 チャンク、加えて 1 ファイル = 1 ロールアップチャンク。
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gh_users (
  login VARCHAR(255) PRIMARY KEY,
  name VARCHAR(255) NOT NULL DEFAULT '',
  email VARCHAR(255) NOT NULL DEFAULT '',
  first_seen_at DATETIME NULL,
  last_seen_at DATETIME NULL
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS gh_commits (
  sha VARCHAR(40) PRIMARY KEY,
  repo VARCHAR(255) NOT NULL,
  branch VARCHAR(255) NOT NULL DEFAULT '',
  author_login VARCHAR(255) NOT NULL DEFAULT '',
  author_name VARCHAR(255) NOT NULL DEFAULT '',
  author_email VARCHAR(255) NOT NULL DEFAULT '',
  committed_at DATETIME NULL,
  week VARCHAR(10) NOT NULL DEFAULT '',
  message MEDIUMTEXT NOT NULL,
  files_changed INT NOT NULL DEFAULT 0,
  additions INT NOT NULL DEFAULT 0,
  deletions INT NOT NULL DEFAULT 0,
  is_merge TINYINT NOT NULL DEFAULT 0,
  ingest_run_id BIGINT NULL,
  INDEX idx_gh_commits_repo_time (repo, committed_at),
  INDEX idx_gh_commits_author (author_login, committed_at),
  INDEX idx_gh_commits_week (week)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS gh_commit_files (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  sha VARCHAR(40) NOT NULL,
  path VARCHAR(512) NOT NULL,
  previous_path VARCHAR(512) NULL,
  status VARCHAR(12) NOT NULL DEFAULT '',
  additions INT NOT NULL DEFAULT 0,
  deletions INT NOT NULL DEFAULT 0,
  hunk_headers JSON NOT NULL,
  patch_excerpt MEDIUMTEXT NULL,
  is_binary TINYINT NOT NULL DEFAULT 0,
  truncated TINYINT NOT NULL DEFAULT 0,
  is_source TINYINT NOT NULL DEFAULT 0,
  UNIQUE KEY uq_gh_cf (sha, path),
  INDEX idx_gh_cf_path (path)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS gh_files (
  path VARCHAR(512) PRIMARY KEY,
  repo VARCHAR(255) NOT NULL,
  change_count INT NOT NULL DEFAULT 0,
  additions INT NOT NULL DEFAULT 0,
  deletions INT NOT NULL DEFAULT 0,
  author_logins JSON NOT NULL,
  first_change_at DATETIME NULL,
  last_change_at DATETIME NULL,
  INDEX idx_gh_files_repo (repo)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS gh_history_ingest_runs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  repo VARCHAR(255) NOT NULL,
  branch VARCHAR(255) NOT NULL DEFAULT '',
  since_date DATE NULL,
  base_sha VARCHAR(40) NULL,
  head_sha VARCHAR(40) NULL,
  commit_count INT NOT NULL DEFAULT 0,
  file_change_count INT NOT NULL DEFAULT 0,
  content_hash CHAR(64) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_gh_hir_repo (repo, created_at),
  INDEX idx_gh_hir_hash (content_hash)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS gh_change_chunks (
  chunk_id VARCHAR(120) PRIMARY KEY,      -- "ghchange:<sha>" / "ghfile:<sha1(path)>"
  kind VARCHAR(8) NOT NULL,               -- commit / file
  repo VARCHAR(255) NOT NULL,
  sha VARCHAR(40) NULL,
  path VARCHAR(512) NULL,
  week VARCHAR(10) NOT NULL,
  participants JSON NOT NULL,
  text MEDIUMTEXT NOT NULL,
  content_hash CHAR(64) NOT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_gh_chunks_repo (repo),
  INDEX idx_gh_chunks_week (week)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS gh_author_analyses (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  ingest_run_id BIGINT NOT NULL,
  repo VARCHAR(255) NOT NULL,
  head_sha VARCHAR(40) NULL,
  content_hash CHAR(64) NOT NULL,
  model VARCHAR(100) NOT NULL,
  themes JSON NOT NULL,
  stats JSON NOT NULL,
  status VARCHAR(20) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_gh_aa_hash (content_hash),
  INDEX idx_gh_aa_created (created_at)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS gh_author_analysis_items (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  analysis_id BIGINT NOT NULL,
  ordinal INT NOT NULL,
  author VARCHAR(255) NOT NULL,
  author_name VARCHAR(255) NOT NULL DEFAULT '',
  overview MEDIUMTEXT NULL,
  stats JSON NOT NULL,
  sections JSON NOT NULL,
  INDEX idx_gh_ai_analysis (analysis_id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS gh_author_analysis_refs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  analysis_id BIGINT NOT NULL,
  item_id BIGINT NOT NULL,
  sha VARCHAR(40) NOT NULL,
  created_at DATETIME NULL,
  excerpt VARCHAR(500) NOT NULL DEFAULT '',
  INDEX idx_gh_ar_item (item_id),
  INDEX idx_gh_ar_sha (sha)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- ------------------------------------------------------------------
-- GitHub 情報取得(ブランチ活動 + PR + コメント/レビュー)の蓄積
-- 「誰が・いつ・どのような操作/コメントをしたか」を gh_activity に記録する。
-- 分析は行わない。PR / ブランチ単位でチャンク化し RAG(source='github_activity')。
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gh_branches (
  repo VARCHAR(255) NOT NULL,
  name VARCHAR(255) NOT NULL,
  is_protected TINYINT NOT NULL DEFAULT 0,
  commit_count INT NOT NULL DEFAULT 0,
  last_activity_at DATETIME NULL,
  last_author VARCHAR(255) NOT NULL DEFAULT '',
  ingest_run_id BIGINT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (repo, name)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS gh_pull_requests (
  repo VARCHAR(255) NOT NULL,
  number INT NOT NULL,
  title VARCHAR(1024) NOT NULL DEFAULT '',
  state VARCHAR(12) NOT NULL DEFAULT '',
  merged TINYINT NOT NULL DEFAULT 0,
  author VARCHAR(255) NOT NULL DEFAULT '',
  created_at DATETIME NULL,
  closed_at DATETIME NULL,
  merged_at DATETIME NULL,
  merged_by VARCHAR(255) NOT NULL DEFAULT '',
  comment_count INT NOT NULL DEFAULT 0,
  url VARCHAR(512) NOT NULL DEFAULT '',
  ingest_run_id BIGINT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (repo, number),
  INDEX idx_gh_pr_repo_upd (repo, updated_at)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS gh_activity (
  event_id VARCHAR(96) PRIMARY KEY,       -- "commit:<sha>" / "pr_opened:<n>" / "pr_comment:<id>" ...
  repo VARCHAR(255) NOT NULL,
  kind VARCHAR(16) NOT NULL,              -- commit / pr_opened / pr_merged / pr_closed / pr_comment / pr_review
  actor VARCHAR(255) NOT NULL DEFAULT '',
  occurred_at DATETIME NULL,
  week VARCHAR(10) NOT NULL DEFAULT '',
  pr_number INT NULL,
  branch VARCHAR(255) NULL,
  sha VARCHAR(40) NULL,
  title VARCHAR(1024) NOT NULL DEFAULT '',
  summary VARCHAR(512) NOT NULL DEFAULT '',
  body MEDIUMTEXT NOT NULL,
  url VARCHAR(512) NOT NULL DEFAULT '',
  ingest_run_id BIGINT NULL,
  INDEX idx_gh_act_repo_time (repo, occurred_at),
  INDEX idx_gh_act_actor (actor, occurred_at),
  INDEX idx_gh_act_pr (pr_number),
  INDEX idx_gh_act_kind (repo, kind)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS gh_activity_ingest_runs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  repo VARCHAR(255) NOT NULL,
  branch_count INT NOT NULL DEFAULT 0,
  pr_count INT NOT NULL DEFAULT 0,
  activity_count INT NOT NULL DEFAULT 0,
  content_hash CHAR(64) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_gh_air_repo (repo, created_at),
  INDEX idx_gh_air_hash (content_hash)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS gh_activity_chunks (
  chunk_id VARCHAR(120) PRIMARY KEY,      -- "ghpr:<repo>:<n>" / "ghbranch:<sha1(repo/name)>"
  kind VARCHAR(8) NOT NULL,               -- pr / branch
  repo VARCHAR(255) NOT NULL,
  pr_number INT NULL,
  branch VARCHAR(255) NULL,
  week VARCHAR(10) NOT NULL DEFAULT '',
  participants JSON NOT NULL,
  text MEDIUMTEXT NOT NULL,
  content_hash CHAR(64) NOT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_gh_ac_repo (repo),
  INDEX idx_gh_ac_week (week)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
