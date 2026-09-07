// 定期実行設定タブ: パイプラインの即時実行とフロー図の進捗ポーリング。

import { $, api, esc } from "./core.js";

let plPolling = null;
const PL_ICON = { pending: "○", success: "✓", error: "✕" };
const PL_COLOR = { pending: "var(--muted)", success: "var(--keep)", error: "var(--problem)" };
function plResultText(s) {
  const r = s.result || {};
  if (s.step_key === "spec_diff") return `相違 ${r.diff_count ?? "-"} 件`;
  if (s.step_key === "user_activity") return `メンバー ${r.member_count ?? "-"} / その他 ${r.other_count ?? "-"}`;
  if (s.step_key === "github") return r.ingested ? `活動 ${r.activity_total ?? "-"} 件を登録` : "変化なし";
  if (s.step_key === "tacit_extract") return `新規 ${r.inserted_count ?? 0} 件登録(走査 ${r.extracted_total ?? 0} 件抽出)`;
  if (s.step_key === "tacit_train") return r.cached ? "評価内容に変更なし(スキップ)" : `${r.training_item_count ?? "-"} 件で学習`;
  const tail = r.feature_count != null ? ` / ${r.feature_count} 機能` : (r.account_count != null ? ` / ${r.account_count} 名` : "");
  return (r.cached ? "キャッシュ再利用" : "実行") + tail;
}
function plStepBox(s) {
  const icon = s.status === "running"
    ? '<span class="spinner"></span>'
    : `<span style="color:${PL_COLOR[s.status] || "var(--muted)"};font-weight:700">${PL_ICON[s.status] || "○"}</span>`;
  const dur = s.duration_sec != null ? ` <span class="muted" style="font-weight:400">${s.duration_sec}s</span>` : "";
  let info = "";
  if (s.status === "error") info = `<div class="pl-err">${esc((s.error || "").slice(0, 240))}</div>`;
  else if (s.status === "success") info = `<div class="muted" style="font-size:11px;margin-top:4px">${esc(plResultText(s))}</div>`;
  return `<div class="pl-step pl-${s.status}"><div class="pl-step-hd">${icon} ${esc(s.label)}${dur}</div>${info}</div>`;
}
function renderPipelineFlow(run) {
  if (!run || !run.id || !(run.steps || []).length) {
    $("#plFlow").innerHTML = '<span class="muted">まだ実行されていません。</span>';
    $("#plMeta").textContent = "";
    $("#plRunBtn").disabled = false;
    return;
  }
  $("#plRunBtn").disabled = run.status === "running";
  const at = (t) => (t || "").replace("T", " ").slice(0, 16);
  $("#plMeta").textContent =
    `run #${run.id} / ${run.status} / 開始 ${at(run.started_at)}` + (run.finished_at ? ` / 終了 ${at(run.finished_at)}` : "");
  const p1 = run.steps.filter((s) => s.phase === "parallel");
  const p2 = run.steps.filter((s) => s.phase === "sequential");
  const p3 = run.steps.filter((s) => s.phase === "final");
  $("#plFlow").innerHTML = `
    <div class="pl-phase-label">フェーズ1: 情報取得・分析(並列)</div>
    <div class="pl-grid">${p1.map(plStepBox).join("")}</div>
    <div class="pl-phase-label" style="margin-top:16px">フェーズ2: 解析(並列)</div>
    <div class="pl-grid">${p2.map(plStepBox).join("")}</div>
    ${p3.length ? `
    <div class="pl-phase-label" style="margin-top:16px">フェーズ3: 評価値学習(フェーズ2完了後)</div>
    <div class="pl-grid">${p3.map(plStepBox).join("")}</div>` : ""}`;
}
export async function pollPipeline() {
  clearTimeout(plPolling);
  try {
    const r = await api("/api/pipeline/latest");
    renderPipelineFlow(r.id ? r : null);
    if (r.id && r.status === "running") {
      plPolling = setTimeout(() => pollPipeline().catch(() => {}), 2500);
    }
  } catch (e) { /* ネットワーク断など。次回タブ表示で再取得 */ }
}
export async function runPipeline() {
  $("#plRunBtn").disabled = true;
  $("#plStatus").innerHTML = '<span class="spinner"></span> 実行を開始しています...';
  try {
    const force = $("#plForce").checked;
    const r = await api("/api/pipeline/run" + (force ? "?force=true" : ""), { method: "POST" });
    $("#plStatus").innerHTML = `<span class="muted">実行を開始しました(run #${r.run_id})。進捗は下のフロー図で確認できます。</span>`;
    pollPipeline();
  } catch (e) {
    $("#plRunBtn").disabled = false;
    $("#plStatus").innerHTML = `<span style="color:var(--problem)">${esc(e.message)}</span>`;
  }
}
