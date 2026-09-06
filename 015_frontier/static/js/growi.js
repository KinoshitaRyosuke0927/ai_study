// wiki(GROWI)情報取得タブ: 参照ページ配下の記事内容・更新履歴・コメント表示。

import { $, api, esc } from "./core.js";

// 取得結果はタブを切り替えても保持(アプリ停止で消えるのは仕様どおり)
let growiResult = null;
export async function loadGrowiMeta() {
  try {
    const d = await api("/api/settings");
    const p = d.config.growi_page_path;
    $("#growiMeta").textContent = p
      ? `参照する Wiki のページ: ${p}(設定画面)`
      : "設定画面で「参照する Wiki のページ」を設定してください。";
  } catch (e) { /* ヒントのみなので無視 */ }
}
export async function loadGrowiPages() {
  $("#growiStatus").innerHTML = '<span class="spinner"></span> ページ一覧を取得中...';
  try {
    const d = await api("/api/growi/pages");
    const sel = $("#growiPageSelect");
    const keep = sel.value;
    sel.innerHTML = (d.pages || []).length
      ? d.pages.map((p) => `<option value="${esc(p.id)}">${esc(p.name || p.path)}</option>`).join("")
      : '<option value="">(配下にページがありません)</option>';
    if (keep && (d.pages || []).some((p) => p.id === keep)) sel.value = keep;
    $("#growiStatus").textContent = `${d.base_path} 配下: ${d.page_count} ページ`;
  } catch (e) {
    $("#growiStatus").innerHTML = `<span style="color:var(--problem)">${esc(e.message)}</span>`;
  }
}
export async function fetchGrowi() {
  const pageId = $("#growiPageSelect").value;
  if (!pageId) { $("#growiStatus").innerHTML = '<span style="color:var(--problem)">ページを選択してください</span>'; return; }
  $("#growiStatus").innerHTML = '<span class="spinner"></span> 取得中...';
  $("#growiResultSummary").textContent = "";
  try {
    const r = await api("/api/growi/fetch", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ page_id: pageId }),
    });
    growiResult = r;
    renderGrowi(r);
  } catch (e) {
    $("#growiStatus").innerHTML = `<span style="color:var(--problem)">${esc(e.message)}</span>`;
    $("#growiResults").innerHTML = "";
    growiResult = null;
  }
}
function renderGrowi(r) {
  $("#growiStatus").textContent = "";
  $("#growiResultSummary").textContent = `更新履歴 ${r.revision_count} 件 / コメント ${r.comment_count} 件`;
  const revs = (r.revisions || []).map((v) =>
    `<div class="gw-row"><span class="who">${esc(v.author)}</span><span class="when">${esc(v.date || "")}</span></div>`).join("");
  const comments = (r.comments || []).map((c) =>
    `<div class="gw-comment${c.reply ? " reply" : ""}"><span class="who">${esc(c.author)}</span><span class="when">${esc(c.date || "")}</span><div class="text">${esc(c.text)}</div></div>`).join("");
  $("#growiResults").innerHTML = `
    <div class="gw-head">
      <div class="p">${esc(r.path)}</div>
      作成: ${esc(r.creator)} (${esc(r.created_at || "-")}) / 最終更新: ${esc(r.last_updater)} (${esc(r.updated_at || "-")})
    </div>
    <div class="gw-section">
      <h3>記事内容</h3>
      <div class="gw-body">${esc(r.body) || '<span class="muted">(本文なし)</span>'}</div>
    </div>
    <div class="gw-section">
      <h3>更新履歴(${r.revision_count} 件)</h3>
      ${revs || '<span class="muted">なし</span>'}
    </div>
    <div class="gw-section">
      <h3>コメント(${r.comment_count} 件)</h3>
      ${comments || '<span class="muted">なし</span>'}
    </div>`;
}
