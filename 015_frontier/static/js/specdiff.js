// 実装差分解析タブ(表示のみ。解析の実行は「定期実行設定」)。

import { $, $$, api, esc } from "./core.js";
import { selectTab } from "./nav.js";

// 解析結果はタブを切り替えても保持(アプリ停止で消えるのは仕様どおり)
let specDiffResult = null;
const VERDICT_LABEL = {
  conflict: "食い違い",
  design_only: "未実装(設計書のみ)",
  code_only: "設計書に記載なし(実装のみ)",
};
export async function loadLatestSpecDiff() {
  if (specDiffResult) return;
  try {
    const r = await api("/api/spec-diff/latest");
    if (!r.diff_id) {
      $("#specDiffStatus").innerHTML = '<span class="muted">まだ解析結果がありません。「定期実行設定」画面から実行してください。</span>';
      return;
    }
    specDiffResult = r;
    renderSpecDiff(r);
    $("#specDiffStatus").innerHTML = `<span class="muted">保存済みの解析結果を表示しています(diff #${r.diff_id} / ${esc((r.created_at || "").replace("T", " ").slice(0, 16))})。</span>`;
  } catch (e) { /* 無ければ何もしない */ }
}
// ダッシュボードの機能名クリック: 差分画面へ遷移し、その機能だけアコーディオンを開く
export async function openSpecDiffFeature(name) {
  selectTab("specdiff");
  if (!specDiffResult) await loadLatestSpecDiff();
  if (!specDiffResult) return;
  // 全アコーディオンを閉じた状態に戻してから、対象だけ開く
  renderSpecDiff(specDiffResult);
  requestAnimationFrame(() => {
    let target = null;
    $$("#specDiffResults details[data-feature]").forEach((d) => {
      const match = d.dataset.feature === name;
      d.open = match;
      if (match) target = d;
    });
    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}
// 参照元(トレーサビリティ)を、設計書 / コードで左右に分けて表示する
function renderSpecDiffEvidence(ev) {
  const d = (ev.design || []).map((x) =>
    `<span class="badge">${esc(x.file_path)}${x.heading ? " / " + esc(x.heading) : ""}</span>`).join(" ");
  const c = (ev.code || []).map((x) =>
    `<span class="badge">${esc(x.file_path)}${x.symbol_name ? "::" + esc(x.symbol_name) : ""}${x.start_line ? " L" + x.start_line + "-" + x.end_line : ""}</span>`).join(" ");
  if (!d && !c) return "";
  return `<div class="row" style="margin-top:6px;gap:10px">
    <div style="flex:1 1 300px"><div class="muted" style="font-size:12px">参照元(設計書)</div>${d || '<span class="muted">-</span>'}</div>
    <div style="flex:1 1 300px"><div class="muted" style="font-size:12px">参照元(コード)</div>${c || '<span class="muted">-</span>'}</div>
  </div>`;
}
function renderSpecDiffItem(it) {
  return `<div class="kpt-item">
    <span class="badge sev-${esc(it.severity)}">${esc(it.severity)}</span>
    <span class="badge">${esc(VERDICT_LABEL[it.verdict] || it.verdict)}</span>
    <div class="t" style="margin-top:6px">${esc(it.summary)}</div>
    <div class="row" style="margin-top:6px;gap:10px">
      <div style="flex:1 1 300px"><div class="muted" style="font-size:12px">設計書</div><div class="dsg-spec-body">${esc(it.design_state) || '<span class="muted">-</span>'}</div></div>
      <div style="flex:1 1 300px"><div class="muted" style="font-size:12px">コード</div><div class="dsg-spec-body">${esc(it.code_state) || '<span class="muted">-</span>'}</div></div>
    </div>
    ${renderSpecDiffEvidence(it.evidence || {})}
  </div>`;
}
// 機能ごとに、その機能の差分をまとめてアコーディオン表示する
function renderSpecDiffGroup(g) {
  const sev = { high: 0, mid: 0, low: 0 };
  g.items.forEach((it) => { if (sev[it.severity] != null) sev[it.severity]++; });
  const tally = ["high", "mid", "low"].filter((k) => sev[k])
    .map((k) => `<span class="badge sev-${k}">${k} ${sev[k]}</span>`).join(" ");
  return `<details class="dsg-file" data-feature="${esc(g.name)}">
    <summary>
      <span class="dsg-name">${esc(g.name)}</span>
      <span class="muted">差分 ${g.items.length} 件</span>
      ${tally}
    </summary>
    <div style="padding:6px 12px 10px">
      ${g.items.map(renderSpecDiffItem).join("")}
    </div>
  </details>`;
}
function renderSpecDiff(r) {
  $("#specDiffStatus").textContent = "";
  const items = r.items || [];
  const sc = r.severity_counts || { high: 0, mid: 0, low: 0 };
  $("#specDiffSummary").textContent =
    `相違 ${r.diff_count} 件(High ${sc.high} / Mid ${sc.mid} / Low ${sc.low})`;
  if (!items.length) {
    $("#specDiffResults").innerHTML = '<span class="muted">相違点は検出されませんでした。</span>';
    return;
  }
  // 機能ごとにまとめる(出現順を維持)
  const groups = [];
  const idx = new Map();
  items.forEach((it) => {
    const key = it.feature_name || "(機能名なし)";
    if (!idx.has(key)) { idx.set(key, groups.length); groups.push({ name: key, items: [] }); }
    groups[idx.get(key)].items.push(it);
  });
  $("#specDiffResults").innerHTML = groups.map(renderSpecDiffGroup).join("");
}
