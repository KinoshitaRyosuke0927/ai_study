// 設計書情報取得タブ: 設計書ファイルの取得表示 + AI による機能分析。

import { $, api, esc } from "./core.js";
import { analysisSavedNote } from "./components.js";

// 取得結果・分析結果はタブを切り替えても保持(アプリ停止で消えるのは仕様どおり)
let designResult = null;
let designAnalysis = null;
export async function loadDesignMeta() {
  try {
    const d = await api("/api/settings");
    const repo = d.config.github_repo;
    const path = d.config.github_design_path;
    $("#dsgMeta").textContent = (repo && path)
      ? `対象: ${repo} の ${path}(設定画面)`
      : "設定画面で「GitHub リポジトリ名称」と「設計書パス」を設定してください。";
  } catch (e) { /* ヒントのみ */ }
}
export async function fetchDesign() {
  $("#dsgFetchBtn").disabled = true;
  $("#dsgAnalyzeBtn").disabled = true;
  // 取得結果を表示するのでラベルを「取得結果」に戻す
  $("#dsgResultTitle").textContent = "取得結果";
  $("#dsgStatus").innerHTML = '<span class="spinner"></span> 取得中...';
  $("#dsgResultSummary").textContent = "";
  try {
    const r = await api("/api/design/fetch", { method: "POST" });
    designResult = r;
    renderDesign(r);
  } catch (e) {
    $("#dsgStatus").innerHTML = `<span style="color:var(--problem)">${esc(e.message)}</span>`;
    $("#dsgResults").innerHTML = "";
    designResult = null;
  } finally {
    $("#dsgFetchBtn").disabled = false;
    $("#dsgAnalyzeBtn").disabled = false;
  }
}
// 「機能分析」: 設計書を取得し、その内容から AI がアプリの機能一覧を分析する
export async function analyzeDesign() {
  $("#dsgFetchBtn").disabled = true;
  $("#dsgAnalyzeBtn").disabled = true;
  // 分析結果を表示するのでラベルを「分析結果」に変更する
  $("#dsgResultTitle").textContent = "分析結果";
  $("#dsgStatus").innerHTML = '<span class="spinner"></span> 機能を分析中...(全体の機能の洗い出し → 機能ごとに該当箇所へ絞り込んで詳細仕様を読み取るため時間がかかる場合があります)';
  $("#dsgResultSummary").textContent = "";
  try {
    const force = $("#dsgForce").checked;
    const r = await api("/api/design/analyze" + (force ? "?force=true" : ""), { method: "POST" });
    designAnalysis = r;
    renderDesignAnalysis(r);
    $("#dsgStatus").innerHTML = analysisSavedNote(r);
  } catch (e) {
    $("#dsgStatus").innerHTML = `<span style="color:var(--problem)">${esc(e.message)}</span>`;
    $("#dsgResults").innerHTML = "";
    designAnalysis = null;
  } finally {
    $("#dsgFetchBtn").disabled = false;
    $("#dsgAnalyzeBtn").disabled = false;
  }
}
// タブを開いたとき、まだ何も表示していなければ保存済みの最新分析結果を表示する
export async function loadLatestDesignAnalysis() {
  if (designAnalysis || designResult) return;
  try {
    const runs = await api("/api/analysis/runs?kind=design&limit=1");
    if (!runs.length) return;
    const r = await api("/api/analysis/runs/" + runs[0].id);
    designAnalysis = r;
    renderDesignAnalysis(r);
    $("#dsgStatus").innerHTML = analysisSavedNote({ ...r, cached: true });
  } catch (e) { /* 保存済みが無ければ何もしない */ }
}
function renderDesignFile(f) {
  let body;
  if (f.binary) {
    body = '<span class="muted">(バイナリまたはデコードできないため表示を省略しました)</span>';
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
function renderDesign(r) {
  $("#dsgStatus").textContent = "";
  $("#dsgResultTitle").textContent = "取得結果";
  const note = r.truncated ? `(上限 ${r.file_count} 件で打ち切り)` : "";
  $("#dsgResultSummary").textContent = `${esc(r.repo)}@${esc(r.branch)} / ${esc(r.path)} / ${r.file_count} ファイル${note}`;
  $("#dsgResults").innerHTML = (r.files || []).length
    ? r.files.map(renderDesignFile).join("")
    : '<span class="muted">ファイルがありません。</span>';
}
// 機能分析(2回目のやり取り)の結果を、機能ごとに詳細仕様として表示する
function renderDesignFeatureDetail(f) {
  // 概要
  const overview = f.overview
    ? `<div class="dsg-feat-overview">${esc(f.overview)}</div>` : "";
  // 詳細分析に失敗した機能はエラー文言を表示する
  const err = f.error ? `<div class="dsg-feat-error">${esc(f.error)}</div>` : "";
  // 2回目リクエストの絞り込み状況(動作確認用のバッジ)
  const mode = f.context_mode === "full"
    ? '<span class="badge">全文フォールバック</span>'
    : `<span class="badge">絞り込み ${(f.selected_section_ids || []).length} 節 / ${f.context_char_len || 0} 字</span>`;
  // 見出しごとの詳細仕様
  const secs = (f.sections || []).map((s) => `
    <div class="dsg-spec-sec">
      <h4>${esc(s.heading)}</h4>
      <div class="dsg-spec-body">${esc(s.body) || '<span class="muted">(記載なし)</span>'}</div>
    </div>`).join("");
  const noSec = (!f.error && !(f.sections || []).length)
    ? '<div class="muted" style="margin:0 12px 10px">詳細な仕様は設計書から読み取れませんでした。</div>' : "";
  return `<details class="dsg-file" open>
    <summary><span class="dsg-name">${esc(f.name)}</span>${mode}</summary>
    ${overview}${err}${secs}${noSec}
  </details>`;
}
function renderDesignAnalysis(r) {
  $("#dsgStatus").textContent = "";
  $("#dsgResultTitle").textContent = "分析結果";
  $("#dsgResultSummary").textContent =
    `${esc(r.repo)}@${esc(r.branch)} / ${esc(r.path)} / ${r.feature_count} 機能` +
    `(${r.analyzed_file_count} ファイル・全 ${r.section_count ?? "-"} 節 / 共通 ${r.common_section_count ?? "-"} 節)`;
  $("#dsgResults").innerHTML = (r.features || []).length
    ? r.features.map(renderDesignFeatureDetail).join("")
    : '<span class="muted">機能を抽出できませんでした。</span>';
}
