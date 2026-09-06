// GitHub 情報取得タブ: ブランチ活動 + PR/コメントの取得表示、DB登録(誰が何をしたか)。

import { $, api, esc } from "./core.js";

// 取得結果はタブを切り替えても保持(アプリ停止で消えるのは仕様どおり)
let githubResult = null;
export async function loadGithubMeta() {
  try {
    const d = await api("/api/settings");
    const repo = d.config.github_repo;
    $("#ghMeta").textContent = repo
      ? `対象リポジトリ: ${repo}(設定画面)`
      : "設定画面で「GitHub リポジトリ名称」を設定してください。";
  } catch (e) { /* ヒントのみ */ }
}
export async function fetchGithub() {
  $("#ghFetchBtn").disabled = true;
  $("#ghStatus").innerHTML = '<span class="spinner"></span> 取得中...(PR のコメント取得に時間がかかる場合があります)';
  $("#ghResultSummary").textContent = "";
  try {
    const r = await api("/api/github/fetch", { method: "POST" });
    githubResult = r;
    renderGithub(r);
  } catch (e) {
    $("#ghStatus").innerHTML = `<span style="color:var(--problem)">${esc(e.message)}</span>`;
    $("#ghResults").innerHTML = "";
    githubResult = null;
  } finally {
    $("#ghFetchBtn").disabled = false;
  }
}
function renderGithubBranch(b) {
  const rows = (b.commits || []).map((c) =>
    `<div class="gh-row"><span class="when">${esc(c.date || "")}</span><span class="who">${esc(c.author)}</span><span class="msg">${esc(c.message)} <span class="gh-sub">(${esc(c.sha)})</span></span></div>`).join("");
  return `<details class="gh-item">
    <summary>
      <span class="gh-name">${esc(b.name)}</span>
      ${b.protected ? '<span class="gh-badge prot">protected</span>' : ""}
      <span class="gh-sub">最終更新 ${esc(b.last_activity || "-")} / ${esc(b.last_author || "-")} ・ コミット ${b.commit_count} 件</span>
    </summary>
    <div class="gh-body">${rows || '<span class="muted">コミットなし</span>'}</div>
  </details>`;
}
function renderGithubPr(p) {
  const badge = p.state === "open"
    ? '<span class="gh-badge open">OPEN</span>'
    : (p.merged ? '<span class="gh-badge merged">MERGED</span>' : '<span class="gh-badge closed">CLOSED</span>');
  const comments = (p.comments || []).map((c) =>
    `<div class="gh-comment${c.kind === "review" ? " review" : ""}"><span class="who">${esc(c.author)}</span> <span class="when">${esc(c.date || "")}</span><div class="text">${esc(c.text) || '<span class="muted">(本文なし)</span>'}</div></div>`).join("");
  const meta = `
    <div class="gh-meta">
      状態: ${p.state === "open" ? "open" : "close"}${p.merged ? "(マージ済み)" : ""}
      ・ 作成者: ${esc(p.author || "-")} (${esc(p.created || "-")})
      ${p.merged ? ` ・ マージ実行者: ${esc(p.merged_by || (p.detail_loaded ? "不明" : "未取得"))} (${esc(p.merged_at || "-")})` : ""}
      ${!p.merged && p.closed ? ` ・ クローズ: ${esc(p.closed)}` : ""}
    </div>`;
  const body = p.detail_loaded
    ? meta + (comments || '<span class="muted">コメントなし</span>')
    : meta + '<span class="muted">この PR のコメント / マージ実行者は未取得です(直近30件のみ取得)。</span>';
  return `<details class="gh-item">
    <summary>
      <span class="gh-name">#${p.number} ${esc(p.title)}</span>
      ${badge}
      <span class="gh-sub">${esc(p.author || "")}</span>
    </summary>
    <div class="gh-body">${body}</div>
  </details>`;
}
function renderGithub(r) {
  $("#ghStatus").textContent = "";
  $("#ghResultSummary").textContent = `${esc(r.repo)} / ブランチ ${r.branch_count} / PR ${r.pr_count}(詳細取得 ${r.pr_detail_count} 件)`;
  const branchNote = r.branches_truncated ? `(上限 ${r.branch_count} 件で打ち切り)` : "";
  const prNote = r.prs_truncated ? `(上限 ${r.pr_count} 件で打ち切り)` : "";
  $("#ghResults").innerHTML = `
    <div class="gh-section">
      <h3>ブランチ(${r.branch_count})${branchNote}</h3>
      ${(r.branches || []).map(renderGithubBranch).join("") || '<span class="muted">ブランチなし</span>'}
    </div>
    <div class="gh-section">
      <h3>プルリクエスト(${r.pr_count})${prNote}</h3>
      ${(r.pull_requests || []).map(renderGithubPr).join("") || '<span class="muted">PR なし</span>'}
    </div>`;
}

// --- GitHub 活動の DB 登録(誰が何をしたか) ---
let githubActivity = null;
const GH_KIND_COLS = [
  ["commit", "コミット"], ["pr_opened", "PR作成"], ["pr_merged", "マージ"],
  ["pr_closed", "PRクローズ"], ["pr_comment", "コメント"], ["pr_review", "レビュー"],
];
function renderGithubActivity(r) {
  $("#ghActStatus").textContent = "";
  $("#ghActSummary").textContent =
    `${esc(r.repo || "")} / ブランチ ${r.branch_count ?? "-"} / PR ${r.pr_count ?? "-"} / 活動 ${r.activity_total ?? 0} 件`
    + (r.last_run_at ? ` / 最終登録 ${esc((r.last_run_at || "").replace("T", " ").slice(0, 16))}` : "");
  const tally = (r.by_actor || []).map((a) => `<tr>
      <td>${esc(a.actor)}</td>
      ${GH_KIND_COLS.map(([k]) => `<td class="num">${a[k] || 0}</td>`).join("")}
      <td class="num"><b>${a.total}</b></td>
    </tr>`).join("");
  $("#ghActByActor").innerHTML = tally
    ? `<h3>アカウント別</h3><div style="overflow-x:auto"><table class="sd-table">
        <thead><tr><th>ユーザ</th>${GH_KIND_COLS.map(([, l]) => `<th class="num">${l}</th>`).join("")}<th class="num">計</th></tr></thead>
        <tbody>${tally}</tbody></table></div>`
    : '<span class="muted">まだ活動が登録されていません。「DB登録」を実行してください。</span>';
  const log = (r.activities || []).map((a) => `<tr>
      <td>${esc((a.occurred_at || "").replace("T", " ").slice(0, 16))}</td>
      <td>${esc(a.actor || "(不明)")}</td>
      <td><span class="badge">${esc(a.kind_label)}</span></td>
      <td>${a.pr_number != null ? `PR #${a.pr_number}` : (a.branch ? esc(a.branch) : "")}</td>
      <td style="word-break:break-word">${esc(a.summary)}${a.body_excerpt ? " — " + esc(a.body_excerpt) : (a.title && a.pr_number != null ? " — " + esc(a.title) : "")}</td>
    </tr>`).join("");
  $("#ghActLog").innerHTML = log
    ? `<h3 style="margin-top:16px">アクティビティ(新しい順・最大 ${(r.activities || []).length} 件)</h3><div style="overflow-x:auto"><table class="sd-table">
        <thead><tr><th style="width:130px">日時</th><th>ユーザ</th><th>操作</th><th>対象</th><th>内容</th></tr></thead>
        <tbody>${log}</tbody></table></div>`
    : "";
}
export async function loadGithubActivity() {
  if (githubActivity) return;
  try {
    const r = await api("/api/github/activity/summary");
    if (!r.activity_total) return;
    githubActivity = r;
    renderGithubActivity(r);
  } catch (e) { /* 無ければ何もしない */ }
}
export async function ingestGithub() {
  $("#ghIngestBtn").disabled = true;
  $("#ghFetchBtn").disabled = true;
  $("#ghActStatus").innerHTML = '<span class="spinner"></span> DB 登録中...(ブランチ活動と PR/コメントを取得して記録します)';
  $("#ghActSummary").textContent = "";
  try {
    const force = $("#ghForce").checked;
    const r = await api("/api/github/ingest" + (force ? "?force=true" : ""), { method: "POST" });
    githubActivity = r;
    renderGithubActivity(r);
    $("#ghActStatus").innerHTML = `<span class="muted">${r.ingested ? `登録しました(活動 ${r.activity_total} 件 / チャンク ${r.chunk_count}・埋め込み更新 ${r.embedded_chunks})` : "変化が無いため登録済みの内容を表示"}。</span>`;
  } catch (e) {
    $("#ghActStatus").innerHTML = `<span style="color:var(--problem)">${esc(e.message)}</span>`;
    githubActivity = null;
  } finally {
    $("#ghIngestBtn").disabled = false;
    $("#ghFetchBtn").disabled = false;
  }
}
