// Trello 情報取得タブ: ボードの取得表示 + アカウント別・ボード横断の AI 分析。

import { $, api, esc } from "./core.js";
import { accountAnalysisCard } from "./components.js";

// --- Trello 分析(アカウント別・ボード横断) ---
let trelloAnalysis = null;
export async function analyzeTrello() {
  $("#trelloAnalyzeBtn").disabled = true;
  $("#trelloFetchBtn").disabled = true;
  $("#trelloAnalysisStatus").innerHTML = '<span class="spinner"></span> 分析中...(カードの蓄積 → 作業テーマの抽出 → アカウントごとの分析を行うため時間がかかる場合があります)';
  $("#trelloAnalysisSummary").textContent = "";
  try {
    const force = $("#trelloForce").checked;
    const r = await api("/api/trello/analyze" + (force ? "?force=true" : ""), { method: "POST" });
    trelloAnalysis = r;
    renderTrelloAnalysis(r);
    const at = (r.saved_at || "").replace("T", " ").slice(0, 16);
    $("#trelloAnalysisStatus").innerHTML = `<span class="muted">${r.cached ? "カード/活動に変化が無いため保存済みの結果を表示" : "分析して保存しました"}(analysis #${r.analysis_id} / ${esc(at)})。作り直す場合は「キャッシュを無視して再分析」。</span>`;
  } catch (e) {
    $("#trelloAnalysisStatus").innerHTML = `<span style="color:var(--problem)">${esc(e.message)}</span>`;
    $("#trelloAnalysisResults").innerHTML = "";
    $("#trelloAnalysisTopics").innerHTML = "";
    trelloAnalysis = null;
  } finally {
    $("#trelloAnalyzeBtn").disabled = false;
    $("#trelloFetchBtn").disabled = false;
  }
}
export async function loadLatestTrelloAnalysis() {
  if (trelloAnalysis) return;
  try {
    const r = await api("/api/trello/analysis/latest");
    if (!r.analysis_id) return;
    trelloAnalysis = r;
    renderTrelloAnalysis(r);
    const at = (r.saved_at || "").replace("T", " ").slice(0, 16);
    $("#trelloAnalysisStatus").innerHTML = `<span class="muted">保存済みの分析結果を表示しています(analysis #${r.analysis_id} / ${esc(at)})。</span>`;
  } catch (e) { /* 無ければ何もしない */ }
}
function renderTrelloAccount(a) {
  const s = a.stats || {};
  const bdList = (s.boards || []).slice(0, 8).map((b) => esc(b)).join("、 ");
  return accountAnalysisCard({
    title: a.full_name ? `${a.username}(${a.full_name})` : a.username,
    chips: [
      `コメント ${s.comment_count ?? 0}`, `操作 ${s.action_count ?? 0}`, `担当カード ${s.assigned_cards ?? 0}`,
      `関与ボード ${s.board_count ?? 0}`, `関与リスト ${s.list_count ?? 0}`,
    ],
    overview: a.overview, error: a.error, sections: a.sections,
    extraTop: bdList ? `<div class="field-hint" style="margin:8px 12px">関与ボード: ${bdList}</div>` : "",
    emptyText: "活動から分析できる内容がありませんでした。",
    refCount: (a.refs || []).length, refLabel: "カード・コメント",
  });
}
function renderTrelloAnalysis(r) {
  $("#trelloAnalysisStatus").textContent = "";
  $("#trelloAnalysisSummary").textContent =
    `${r.board_count ?? (r.board_ids || []).length} ボード / ${r.account_count} アカウント / カード ${r.card_count ?? "-"} / 活動 ${r.activity_count ?? "-"} / チャンク ${r.chunk_count ?? "-"}(埋め込み更新 ${r.embedded_chunks ?? 0})`;
  $("#trelloAnalysisTopics").innerHTML = (r.themes || []).length
    ? `<span class="muted" style="font-size:12px">チームの作業テーマ:</span> ${(r.themes || []).map((t) => `<span class="badge">${esc(t)}</span>`).join(" ")}`
    : "";
  $("#trelloAnalysisResults").innerHTML = (r.accounts || []).length
    ? r.accounts.map(renderTrelloAccount).join("")
    : '<span class="muted">分析対象のアカウントがありませんでした。</span>';
}

// --- Trello 情報取得 ---
// 取得結果はタブを切り替えても保持(アプリ停止で消えるのは仕様どおり)
let trelloResult = null;
export async function loadTrelloBoards() {
  const sel = $("#trelloBoardSelect");
  const keep = sel.value;
  let d;
  try {
    d = await api("/api/trello/boards");
  } catch (e) {
    $("#trelloMeta").innerHTML = `<span style="color:var(--problem)">${esc(e.message)}</span>`;
    return;
  }
  const boards = d.boards || [];
  sel.innerHTML = boards.length
    ? boards.map((b) => `<option value="${esc(b.id)}">${esc(b.name)}</option>`).join("")
    : '<option value="">(設定画面でボードを選択してください)</option>';
  if (keep && boards.some((b) => b.id === keep)) sel.value = keep;
  $("#trelloMeta").textContent = d.error
    ? d.error
    : `対象は設定画面の「Trello 取得ボード」で選択したボード(${boards.length} 件)です。`;
}
export async function fetchTrello() {
  const boardId = $("#trelloBoardSelect").value;
  if (!boardId) { $("#trelloStatus").innerHTML = '<span style="color:var(--problem)">ボードを選択してください</span>'; return; }
  $("#trelloStatus").innerHTML = '<span class="spinner"></span> 取得中...';
  $("#trelloResultSummary").textContent = "";
  try {
    const r = await api("/api/trello/fetch", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ board_id: boardId }),
    });
    trelloResult = r;
    renderTrello(r);
  } catch (e) {
    $("#trelloStatus").innerHTML = `<span style="color:var(--problem)">${esc(e.message)}</span>`;
    $("#trelloResults").innerHTML = "";
    trelloResult = null;
  }
}
function renderTrelloCard(c) {
  // ラベル・カバーはどちらも色チップだが、チップ内の種別タグ(ラベル/カバー)で区別する
  const labels = (c.labels || []).map((l) =>
    `<span class="tr-chip tr-lc-${esc(l.color || "none")}"><span class="kind">ラベル</span>${esc(l.name || "(名称なし)")}</span>`).join("");
  const cover = c.cover
    ? `<span class="tr-chip tr-lc-${esc(c.cover)}"><span class="kind">カバー</span>${esc(c.cover)}</span>`
    : "";
  const due = c.due ? `<span class="tr-due${c.due_complete ? " done" : ""}">期限 ${esc(c.due)}${c.due_complete ? " ✓" : ""}</span>` : "";
  const summaryChips = [labels, cover, due].filter(Boolean).join(" ");

  const members = (c.members || []).length
    ? `<div class="tr-row"><span class="k">メンバー:</span> ${(c.members || []).map(esc).join("、 ")}</div>` : "";
  const desc = c.desc ? `<div class="tr-desc">${esc(c.desc)}</div>` : "";
  const checklists = (c.checklists || []).map((cl) => `
    <div class="tr-checklist">
      <span class="cl-name">${esc(cl.name || "チェックリスト")}(${cl.done}/${cl.total})</span>
      ${(cl.items || []).map((it) => `<div class="tr-check-item${it.checked ? " done" : ""}">${it.checked ? "☑" : "☐"} ${esc(it.name)}</div>`).join("")}
    </div>`).join("");
  const acts = (c.activity || []).map((a) => {
    if (a.kind === "comment") {
      return `<div class="tr-act-row comment"><span class="who">${esc(a.user)}</span> <span class="when">${esc(a.date || "")}</span>\n${esc(a.text)}</div>`;
    }
    return `<div class="tr-act-row"><span class="who">${esc(a.user)}</span> <span class="when">${esc(a.date || "")}</span> ${esc(a.summary)}</div>`;
  }).join("");
  const activity = (c.activity || []).length
    ? `<details class="tr-activity"><summary>コメントとアクティビティ(${c.activity.length}件)</summary>${acts}</details>`
    : "";
  const body = `${members}${desc}${checklists}${activity}` || '<div class="muted">詳細情報なし</div>';
  return `<details class="tr-card">
    <summary><span class="tr-card-name">${esc(c.name)}</span>${summaryChips}</summary>
    <div class="tr-card-body">${body}</div>
  </details>`;
}
function renderTrello(r) {
  $("#trelloStatus").textContent = "";
  $("#trelloResultSummary").textContent = `${esc(r.board_name)} / ${r.list_count} リスト / ${r.card_count} カード`;
  if (!r.lists.length) {
    $("#trelloResults").innerHTML = '<span class="muted">リストがありません。</span>';
    return;
  }
  $("#trelloResults").innerHTML = r.lists.map((lst) => `
    <div class="tr-list">
      <h3>${esc(lst.name)}(${lst.card_count})</h3>
      ${(lst.cards || []).map(renderTrelloCard).join("") || '<span class="muted">カードなし</span>'}
    </div>`).join("");
}
