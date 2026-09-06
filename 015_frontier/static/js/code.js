// コード情報取得タブ: リポジトリ全体のソース取得表示 + AI による機能分析。

import { $, api, esc } from "./core.js";
import { analysisSavedNote } from "./components.js";

// 取得結果・分析結果はタブを切り替えても保持(アプリ停止で消えるのは仕様どおり)
let codeResult = null;
let codeAnalysis = null;
export async function loadCodeMeta() {
  try {
    const d = await api("/api/settings");
    const repo = d.config.github_repo;
    $("#codeMeta").textContent = repo
      ? `対象: ${repo} のリポジトリ全体(設定画面の「GitHub リポジトリ名称」)`
      : "設定画面で「GitHub リポジトリ名称」を設定してください。";
  } catch (e) { /* ヒントのみ */ }
}
export async function fetchCode() {
  $("#codeFetchBtn").disabled = true;
  $("#codeAnalyzeBtn").disabled = true;
  // 取得結果を表示するのでラベルを「取得結果」に戻す
  $("#codeResultTitle").textContent = "取得結果";
  $("#codeStatus").innerHTML = '<span class="spinner"></span> 取得中...(リポジトリ全体のため時間がかかる場合があります)';
  $("#codeResultSummary").textContent = "";
  try {
    const r = await api("/api/code/fetch", { method: "POST" });
    codeResult = r;
    renderCode(r);
  } catch (e) {
    $("#codeStatus").innerHTML = `<span style="color:var(--problem)">${esc(e.message)}</span>`;
    $("#codeResults").innerHTML = "";
    codeResult = null;
  } finally {
    $("#codeFetchBtn").disabled = false;
    $("#codeAnalyzeBtn").disabled = false;
  }
}
// 「機能分析」: コードを取得し、コード構造から AI がアプリの機能一覧を分析する
export async function analyzeCode() {
  $("#codeFetchBtn").disabled = true;
  $("#codeAnalyzeBtn").disabled = true;
  // 分析結果を表示するのでラベルを「分析結果」に変更する
  $("#codeResultTitle").textContent = "分析結果";
  $("#codeStatus").innerHTML = '<span class="spinner"></span> 機能を分析中...(コードの取得 → 機能の洗い出し → 機能ごとに該当する関数/クラスへ絞り込んで詳細仕様を分析するため時間がかかる場合があります)';
  $("#codeResultSummary").textContent = "";
  try {
    const force = $("#codeForce").checked;
    const r = await api("/api/code/analyze" + (force ? "?force=true" : ""), { method: "POST" });
    codeAnalysis = r;
    renderCodeAnalysis(r);
    $("#codeStatus").innerHTML = analysisSavedNote(r);
  } catch (e) {
    $("#codeStatus").innerHTML = `<span style="color:var(--problem)">${esc(e.message)}</span>`;
    $("#codeResults").innerHTML = "";
    codeAnalysis = null;
  } finally {
    $("#codeFetchBtn").disabled = false;
    $("#codeAnalyzeBtn").disabled = false;
  }
}
// タブを開いたとき、まだ何も表示していなければ保存済みの最新分析結果を表示する
export async function loadLatestCodeAnalysis() {
  if (codeAnalysis || codeResult) return;
  try {
    const runs = await api("/api/analysis/runs?kind=code&limit=1");
    if (!runs.length) return;
    const r = await api("/api/analysis/runs/" + runs[0].id);
    codeAnalysis = r;
    renderCodeAnalysis(r);
    $("#codeStatus").innerHTML = analysisSavedNote({ ...r, cached: true });
  } catch (e) { /* 保存済みが無ければ何もしない */ }
}
function renderCodeFile(f) {
  let body;
  if (f.binary) {
    body = '<span class="muted">(バイナリ・上限超過などのため表示を省略しました)</span>';
  } else {
    body = `<pre class="gw-body">${esc(f.content) || '<span class="muted">(空ファイル)</span>'}</pre>`;
    if (f.truncated) body += '<div class="muted" style="margin:0 12px 10px">※ 大きいファイルのため先頭のみ表示しています。</div>';
  }
  return `<details class="dsg-file">
    <summary>
      <span class="dsg-name">${esc(f.name)}</span>
      <span class="dsg-size">${f.size} bytes</span>
    </summary>
    ${body}
  </details>`;
}
function renderCode(r) {
  $("#codeStatus").textContent = "";
  $("#codeResultTitle").textContent = "取得結果";
  const note = r.truncated ? `(上限 ${r.file_count} 件で打ち切り)` : "";
  $("#codeResultSummary").textContent = `${esc(r.repo)}@${esc(r.branch)} / ${esc(r.path)} / ${r.file_count} ファイル${note}`;
  $("#codeResults").innerHTML = (r.files || []).length
    ? r.files.map(renderCodeFile).join("")
    : '<span class="muted">ファイルがありません。</span>';
}
// 機能分析(2回目のやり取り)の結果を、機能ごとに詳細仕様として表示する
function renderCodeFeatureDetail(f) {
  const overview = f.overview
    ? `<div class="dsg-feat-overview">${esc(f.overview)}</div>` : "";
  const err = f.error ? `<div class="dsg-feat-error">${esc(f.error)}</div>` : "";
  // 2回目リクエストの絞り込み状況(動作確認用のバッジ)
  const mode = f.context_mode === "fallback"
    ? '<span class="badge">コアセットにフォールバック</span>'
    : `<span class="badge">絞り込み ${(f.selected_symbols || []).length} 定義 / ${(f.selected_paths || []).length} ファイル / ${f.context_char_len || 0} 字</span>`;
  const secs = (f.sections || []).map((s) => `
    <div class="dsg-spec-sec">
      <h4>${esc(s.heading)}</h4>
      <div class="dsg-spec-body">${esc(s.body) || '<span class="muted">(記載なし)</span>'}</div>
    </div>`).join("");
  const noSec = (!f.error && !(f.sections || []).length)
    ? '<div class="muted" style="margin:0 12px 10px">詳細な仕様はコードから読み取れませんでした。</div>' : "";
  return `<details class="dsg-file" open>
    <summary><span class="dsg-name">${esc(f.name)}</span>${mode}</summary>
    ${overview}${err}${secs}${noSec}
  </details>`;
}
function renderCodeAnalysis(r) {
  $("#codeStatus").textContent = "";
  $("#codeResultTitle").textContent = "分析結果";
  $("#codeResultSummary").textContent =
    `${esc(r.repo)}@${esc(r.branch)} / ${r.feature_count} 機能` +
    `(${r.analyzed_file_count} / ${r.file_count ?? "-"} ファイル・${r.symbol_count ?? "-"} 定義を走査 / コア ${r.core_file_count ?? "-"} ファイル)`;
  $("#codeResults").innerHTML = (r.features || []).length
    ? r.features.map(renderCodeFeatureDetail).join("")
    : '<span class="muted">機能を抽出できませんでした。</span>';
}
