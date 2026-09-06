// Mattermost 情報取得タブ: 投稿の取得表示 + アカウント別・チャンネル横断の AI 分析。

import { $, api, esc, _today } from "./core.js";
import { accountAnalysisCard } from "./components.js";

// 取得結果はページを離れても消さない(タブ切替は表示切替のみ。アプリ停止で消えるのは仕様どおり)
let mmResult = null;

export async function loadMattermostMeta() {
  const d = await api("/api/settings");
  const since = d.config.since_date;
  const nCh = (d.config.mattermost_channel_ids || []).length;
  $("#mmMeta").textContent = `対象チャンネル: ${nCh} 件(設定画面の「Mattermost 取得チャンネル」)`;
  $("#mmSince").textContent = since ? `(${since})` : "(未設定)";
  // 日付欄の初期値(未入力のときだけ補完する)
  if (!$("#mmCurrentLatest").value) $("#mmCurrentLatest").value = _today();
  if (!$("#mmRangeEnd").value) $("#mmRangeEnd").value = _today();
  if (!$("#mmRangeStart").value) $("#mmRangeStart").value = since || _today();
}
export async function fetchMattermost(mode) {
  const body = { mode };
  if (mode === "current") {
    body.latest_date = $("#mmCurrentLatest").value || null;
  } else {
    body.start_date = $("#mmRangeStart").value || null;
    body.end_date = $("#mmRangeEnd").value || null;
  }
  $("#mmStatus").innerHTML = '<span class="spinner"></span> 取得中...';
  $("#mmResultSummary").textContent = "";
  try {
    const r = await api("/api/mattermost/fetch", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    mmResult = r;
    renderMattermost(r);
  } catch (e) {
    $("#mmStatus").innerHTML = `<span style="color:var(--problem)">${esc(e.message)}</span>`;
    $("#mmResults").innerHTML = "";
    mmResult = null;
  }
}
function renderMattermostPost(p, isReply) {
  const reactions = (p.reactions || []).map((x) => `<span class="mm-reaction">:${esc(x.emoji)}: ×${x.count}</span>`).join("");
  const rootRef = p.root_excerpt ? `<div class="mm-root-ref">↳ スレッド元: ${esc(p.root_excerpt)}${p.root_excerpt.length >= 60 ? "…" : ""}</div>` : "";
  return `
    <div class="mm-post${isReply ? " reply" : ""}">
      ${rootRef}
      <div class="mm-post-head">
        <span class="mm-post-user">${esc(p.user)}</span>
        <span>${esc(p.created)}</span>
        ${isReply ? '<span class="mm-thread-tag">返信</span>' : ""}
      </div>
      <div class="mm-body">${esc(p.message) || '<span class="muted">(本文なし)</span>'}</div>
      ${reactions ? `<div class="mm-reactions">${reactions}</div>` : ""}
    </div>`;
}
function renderMattermost(r) {
  $("#mmStatus").textContent = "";
  $("#mmResultSummary").textContent = `期間 ${r.start} 〜 ${r.end} / ${r.channel_count} チャンネル / ${r.post_count} 投稿`;
  if (!r.channels.length || !r.post_count) {
    $("#mmResults").innerHTML = '<span class="muted">対象期間の投稿はありませんでした。</span>';
    return;
  }
  $("#mmResults").innerHTML = r.channels.map((ch) => {
    const rows = (ch.posts || []).map((p) => {
      const root = renderMattermostPost(p, false);
      const replies = (p.replies || []).map((rp) => renderMattermostPost(rp, true)).join("");
      return root + replies;
    }).join("");
    return `<div class="mm-channel"><h3>${esc(ch.channel_name)}(${ch.post_count})</h3>${rows || '<span class="muted">投稿なし</span>'}</div>`;
  }).join("");
}

// --- Mattermost 分析(アカウント別・チャンネル横断) ---
// 分析結果はタブを切り替えても保持(アプリ停止で消えるのは仕様どおり)
let mmAnalysis = null;
export async function analyzeMattermost() {
  $("#mmAnalyzeBtn").disabled = true;
  $("#mmCurrentBtn").disabled = true;
  $("#mmAnalysisStatus").innerHTML = '<span class="spinner"></span> 分析中...(投稿の蓄積 → チーム話題の抽出 → アカウントごとの分析を行うため時間がかかる場合があります)';
  $("#mmAnalysisSummary").textContent = "";
  try {
    const force = $("#mmForce").checked;
    const body = { mode: "current", latest_date: $("#mmCurrentLatest").value || null };
    const r = await api("/api/mattermost/analyze" + (force ? "?force=true" : ""), {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    mmAnalysis = r;
    renderMattermostAnalysis(r);
    const at = (r.saved_at || "").replace("T", " ").slice(0, 16);
    $("#mmAnalysisStatus").innerHTML = `<span class="muted">${r.cached ? "投稿に変化が無いため保存済みの結果を表示" : "分析して保存しました"}(analysis #${r.analysis_id} / ${esc(at)})。作り直す場合は「キャッシュを無視して再分析」。</span>`;
  } catch (e) {
    $("#mmAnalysisStatus").innerHTML = `<span style="color:var(--problem)">${esc(e.message)}</span>`;
    $("#mmAnalysisResults").innerHTML = "";
    $("#mmAnalysisTopics").innerHTML = "";
    mmAnalysis = null;
  } finally {
    $("#mmAnalyzeBtn").disabled = false;
    $("#mmCurrentBtn").disabled = false;
  }
}
export async function loadLatestMattermostAnalysis() {
  if (mmAnalysis) return;
  try {
    const r = await api("/api/mattermost/analysis/latest");
    if (!r.analysis_id) return;
    mmAnalysis = r;
    renderMattermostAnalysis(r);
    const at = (r.saved_at || "").replace("T", " ").slice(0, 16);
    $("#mmAnalysisStatus").innerHTML = `<span class="muted">保存済みの分析結果を表示しています(analysis #${r.analysis_id} / ${esc(at)})。</span>`;
  } catch (e) { /* 無ければ何もしない */ }
}
function renderMattermostAccount(a) {
  const s = a.stats || {};
  const chList = (s.channels || []).slice(0, 8).map((c) => esc(c)).join("、 ");
  return accountAnalysisCard({
    title: a.username,
    chips: [
      `投稿 ${s.post_count ?? 0}`, `返信 ${s.reply_count ?? 0}`, `スレ立 ${s.thread_started ?? 0}`,
      `被リアクション ${s.reactions_received ?? 0}`, `参加ch ${s.channel_count ?? 0}`, `活動 ${s.active_days ?? 0}日`,
    ],
    overview: a.overview, error: a.error, sections: a.sections,
    extraTop: chList ? `<div class="field-hint" style="margin:8px 12px">主な参加チャンネル: ${chList}</div>` : "",
    emptyText: "発言から分析できる内容がありませんでした。",
    refCount: (a.refs || []).length, refLabel: "投稿",
  });
}
function renderMattermostAnalysis(r) {
  $("#mmAnalysisStatus").textContent = "";
  const w = r.window || {};
  $("#mmAnalysisSummary").textContent =
    `期間 ${w.start ?? "-"} 〜 ${w.end ?? "-"} / ${r.account_count} アカウント / ${r.post_count ?? "-"} 投稿 / チャンク ${r.chunk_count ?? "-"}(埋め込み更新 ${r.embedded_chunks ?? 0})`;
  $("#mmAnalysisTopics").innerHTML = (r.topics || []).length
    ? `<span class="muted" style="font-size:12px">チーム内の主な話題:</span> ${(r.topics || []).map((t) => `<span class="badge">${esc(t)}</span>`).join(" ")}`
    : "";
  $("#mmAnalysisResults").innerHTML = (r.accounts || []).length
    ? r.accounts.map(renderMattermostAccount).join("")
    : '<span class="muted">分析対象のアカウントがありませんでした。</span>';
}
