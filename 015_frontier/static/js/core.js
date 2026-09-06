// 共通ヘルパ: DOM 取得、fetch ラッパ、HTML エスケープ、日付整形。

// セレクタ 1 件 / 複数件
export const $ = (s) => document.querySelector(s);
export const $$ = (s) => Array.from(document.querySelectorAll(s));

// JSON API 呼び出し。!ok のときは detail をメッセージにした Error を投げる。
export const api = async (path, opts) => {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
};

// HTML 特殊文字のエスケープ(innerHTML へ差し込む前に必ず通す)
export const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// 今日(YYYY-MM-DD)
export function _today() { return new Date().toISOString().slice(0, 10); }

// ISO 日時 → "YYYY-MM-DD HH:MM"
export function _ymd(s) { return (s || "").replace("T", " ").slice(0, 16); }
