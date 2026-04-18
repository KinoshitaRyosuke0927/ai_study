// ============================================================
// アプリケーション共通ヘルパー関数
// ============================================================

/**
 * 日付文字列を「yyyy/mm/dd hh:mm:ss」形式にフォーマットする
 * @param {string|null} dateString - ISO形式などの日付文字列
 * @returns {string} フォーマット済み日付文字列。入力がない場合は空文字
 */
export const formatDateTime = (dateString) => {
  if (!dateString) return '';
  const date = new Date(dateString);
  const year    = date.getFullYear();
  const month   = String(date.getMonth() + 1).padStart(2, '0');
  const day     = String(date.getDate()).padStart(2, '0');
  const hours   = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  const seconds = String(date.getSeconds()).padStart(2, '0');
  return `${year}/${month}/${day} ${hours}:${minutes}:${seconds}`;
};

/**
 * タスク名を自動生成する（「新しいタスク_yyyymmddhhmmss」形式）
 * @returns {string} 生成されたタスク名
 */
export const generateTaskName = () => {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return `新しいタスク_${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
};
