// 変更履歴取得タブ: コミット履歴のユーザ別/ファイル別集計 + アカウント別の AI 分析。

import { $, api, esc, _ymd } from "./core.js";
import { accountAnalysisCard } from "./components.js";

let changelogSummary = null;
let changelogAnalysis = null;
export async function loadChangelogMeta() {
  try {
    const d = await api("/api/settings");
    const repo = d.config.github_repo;
    const since = d.config.since_date;
    $("#clMeta").textContent = repo
      ? `対象: ${repo}(既定ブランチ)/ 取得開始日 ${since || "(未設定)"}`
      : "設定画面で「GitHub リポジトリ名称」を設定してください。";
  } catch (e) { /* ヒントのみ */ }
}
function renderChangelogSummary(r) {
  $("#clStatus").textContent = "";
  $("#clSummary").textContent =
    `${esc(r.repo || "")}@${esc(r.branch || "-")} / 蓄積コミット ${r.commit_count ?? 0} / ユーザ ${(r.users || []).length} / ファイル上位 ${(r.files || []).length}`
    + (r.head_sha ? ` / HEAD ${esc(String(r.head_sha).slice(0, 7))}` : "");
  const users = (r.users || []).map((u) => `<tr>
      <td>${esc(u.author)}${u.author_name && u.author_name !== u.author ? ` <span class="muted">(${esc(u.author_name)})</span>` : ""}</td>
      <td class="num">${u.commit_count}</td>
      <td class="num" style="color:#16a34a">+${u.additions}</td>
      <td class="num" style="color:#dc2626">-${u.deletions}</td>
      <td class="num">${u.files_touched}</td>
      <td>${esc(_ymd(u.first_at))}</td><td>${esc(_ymd(u.last_at))}</td>
    </tr>`).join("");
  const files = (r.files || []).map((f) => `<tr>
      <td style="word-break:break-all">${esc(f.path)}</td>
      <td class="num">${f.change_count}</td>
      <td class="num" style="color:#16a34a">+${f.additions}</td>
      <td class="num" style="color:#dc2626">-${f.deletions}</td>
      <td>${(f.authors || []).slice(0, 5).map(esc).join("、 ")}</td>
      <td>${esc(_ymd(f.last_at))}</td>
    </tr>`).join("");
  $("#clUsers").innerHTML = users
    ? `<h3>ユーザごと</h3><div style="overflow-x:auto"><table class="sd-table">
        <thead><tr><th>ユーザ</th><th class="num">コミット</th><th class="num">追加</th><th class="num">削除</th><th class="num">ファイル</th><th>初回</th><th>最終</th></tr></thead>
        <tbody>${users}</tbody></table></div>`
    : '<span class="muted">まだ変更履歴が蓄積されていません。「取得」を実行してください。</span>';
  $("#clFiles").innerHTML = files
    ? `<h3 style="margin-top:16px">ファイルごと(変更回数 上位)</h3><div style="overflow-x:auto"><table class="sd-table">
        <thead><tr><th>ファイル</th><th class="num">変更回数</th><th class="num">追加</th><th class="num">削除</th><th>変更者</th><th>最終変更</th></tr></thead>
        <tbody>${files}</tbody></table></div>`
    : "";
}
export async function loadChangelogSummary() {
  if (changelogSummary) return;
  try {
    const r = await api("/api/changelog/summary");
    if (!r.commit_count) return;
    changelogSummary = r;
    renderChangelogSummary(r);
  } catch (e) { /* 無ければ何もしない */ }
}
export async function fetchChangelog() {
  $("#clFetchBtn").disabled = true;
  $("#clAnalyzeBtn").disabled = true;
  $("#clStatus").innerHTML = '<span class="spinner"></span> 変更履歴を取得中...(コミットごとにファイル変更を取得するため時間がかかる場合があります)';
  try {
    const qs = [];
    if ($("#clFull").checked) qs.push("full=true");
    if ($("#clForceFetch").checked) qs.push("force=true");
    const r = await api("/api/changelog/fetch" + (qs.length ? "?" + qs.join("&") : ""), { method: "POST" });
    changelogSummary = r;
    renderChangelogSummary(r);
    const note = r.truncated ? `(上限のため ${r.detail_commits} 件まで取得)` : "";
    $("#clStatus").innerHTML = `<span class="muted">新規コミット ${r.new_commits} 件 / ファイル変更 ${r.ingested_file_changes} 件 を蓄積、チャンク ${r.chunk_count}(埋め込み更新 ${r.embedded_chunks})${note}。</span>`;
  } catch (e) {
    $("#clStatus").innerHTML = `<span style="color:var(--problem)">${esc(e.message)}</span>`;
  } finally {
    $("#clFetchBtn").disabled = false;
    $("#clAnalyzeBtn").disabled = false;
  }
}
function renderChangelogAccount(a) {
  const s = a.stats || {};
  const topFiles = (s.top_files || []).slice(0, 8).map((f) => esc(f)).join("、 ");
  return accountAnalysisCard({
    title: a.full_name && a.full_name !== a.username ? `${a.username}(${a.full_name})` : a.username,
    chips: [
      `コミット ${s.commit_count ?? 0}`, `+${s.additions ?? 0}`, `-${s.deletions ?? 0}`,
      `変更ファイル ${s.files_touched ?? 0}`,
    ],
    overview: a.overview, error: a.error, sections: a.sections,
    extraTop: topFiles ? `<div class="field-hint" style="margin:8px 12px">よく触るファイル: ${topFiles}</div>` : "",
    emptyText: "コミット履歴から分析できる内容がありませんでした。",
    refCount: (a.refs || []).length, refLabel: "コミット",
  });
}
function renderChangelogAnalysis(r) {
  $("#clAnalysisStatus").textContent = "";
  $("#clAnalysisSummary").textContent =
    `${r.account_count} アカウント / コミット ${r.commit_count ?? "-"}`;
  $("#clAnalysisTopics").innerHTML = (r.themes || []).length
    ? `<span class="muted" style="font-size:12px">リポジトリの作業テーマ:</span> ${(r.themes || []).map((t) => `<span class="badge">${esc(t)}</span>`).join(" ")}`
    : "";
  $("#clAnalysisResults").innerHTML = (r.accounts || []).length
    ? r.accounts.map(renderChangelogAccount).join("")
    : '<span class="muted">分析対象のアカウントがありませんでした。</span>';
}
export async function analyzeChangelog() {
  $("#clAnalyzeBtn").disabled = true;
  $("#clFetchBtn").disabled = true;
  $("#clAnalysisStatus").innerHTML = '<span class="spinner"></span> 分析中...(作業テーマの抽出 → アカウントごとの分析を行うため時間がかかる場合があります)';
  $("#clAnalysisSummary").textContent = "";
  try {
    const force = $("#clForce").checked;
    const r = await api("/api/changelog/analyze" + (force ? "?force=true" : ""), { method: "POST" });
    changelogAnalysis = r;
    renderChangelogAnalysis(r);
    $("#clAnalysisStatus").innerHTML = `<span class="muted">${r.cached ? "履歴に変化が無いため保存済みの結果を表示" : "分析して保存しました"}(analysis #${r.analysis_id} / ${esc(_ymd(r.saved_at))})。</span>`;
  } catch (e) {
    $("#clAnalysisStatus").innerHTML = `<span style="color:var(--problem)">${esc(e.message)}</span>`;
    $("#clAnalysisResults").innerHTML = "";
    $("#clAnalysisTopics").innerHTML = "";
    changelogAnalysis = null;
  } finally {
    $("#clAnalyzeBtn").disabled = false;
    $("#clFetchBtn").disabled = false;
  }
}
export async function loadLatestChangelogAnalysis() {
  if (changelogAnalysis) return;
  try {
    const r = await api("/api/changelog/analysis/latest");
    if (!r.analysis_id) return;
    changelogAnalysis = r;
    renderChangelogAnalysis(r);
    $("#clAnalysisStatus").innerHTML = `<span class="muted">保存済みの分析結果を表示しています(analysis #${r.analysis_id} / ${esc(_ymd(r.saved_at))})。</span>`;
  } catch (e) { /* 無ければ何もしない */ }
}
