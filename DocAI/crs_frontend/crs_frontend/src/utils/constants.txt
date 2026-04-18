// ============================================================
// アプリケーション共通定数
// ============================================================

// バックエンドAPIのベースURL
export const API_BASE_URL = 'http://localhost:5000';

// APIエンドポイント一覧
export const API_ENDPOINTS = {
  LOGIN:             `${API_BASE_URL}/login`,
  TASK_LIST:         `${API_BASE_URL}/task-list`,
  TASK_INQUIRY:      `${API_BASE_URL}/task-detail/inquiry`,
  TASK_READ:         `${API_BASE_URL}/task-detail/read`,
  TASK_CREATE:       `${API_BASE_URL}/task-detail/create`,
  TASK_UPDATE:       `${API_BASE_URL}/task-detail/update`,
  TASK_DELETE:       `${API_BASE_URL}/task-detail/delete`,
  TASK_TRANSLATE:    `${API_BASE_URL}/task-detail-translate`,
  FILE_FILTER:       `${API_BASE_URL}/file-filter`,
};

// タスクステータス名称（m_task_stateテーブルに対応）
export const TASK_STATE_NAMES = {
  1: '準備中',
  2: '翻訳中',
  3: '翻訳失敗',
  4: '翻訳済',
};

// タスクステータスID
export const TASK_STATE = {
  PREPARING:   1, // 準備中
  TRANSLATING: 2, // 翻訳中
  FAILED:      3, // 翻訳失敗
  DONE:        4, // 翻訳済
};

// 共通エラーメッセージ
export const SYSTEM_ERROR_MESSAGE =
  'システム内でエラーが発生しました。お手数ですがシステム管理者までお問い合わせください。';

// タスク状態の自動更新間隔（ミリ秒）
export const POLLING_INTERVAL_MS = 10000;
