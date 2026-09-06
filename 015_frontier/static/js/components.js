// 複数タブで共有する描画パーツ。

import { esc } from "./core.js";

// mm / trello / 変更履歴 / アクティビティ 共通: アカウント分析 1 件のアコーディオンカード
export function accountAnalysisCard(o) {
  const chips = (o.chips || []).map((t) => `<span class="badge">${esc(t)}</span>`).join(" ");
  const overview = o.overview ? `<div class="dsg-feat-overview">${esc(o.overview)}</div>` : "";
  const err = o.error ? `<div class="dsg-feat-error">${esc(o.error)}</div>` : "";
  const secs = (o.sections || []).map((x) => `
    <div class="dsg-spec-sec">
      <h4>${esc(x.heading)}</h4>
      <div class="dsg-spec-body">${esc(x.body) || '<span class="muted">(記載なし)</span>'}</div>
    </div>`).join("");
  const noSec = (!o.error && !(o.sections || []).length)
    ? `<div class="muted" style="margin:0 12px 10px">${esc(o.emptyText || "分析できる内容がありませんでした。")}</div>` : "";
  const refNote = o.refCount
    ? `<div class="muted" style="margin:6px 12px 10px;font-size:12px">根拠にした${esc(o.refLabel || "記録")}: ${o.refCount} 件(トレーサビリティ用に保存)</div>` : "";
  return `<details class="dsg-file">
    <summary><span class="dsg-name">${esc(o.title)}</span> ${chips}</summary>
    ${overview}${o.extraTop || ""}${err}${secs}${noSec}${refNote}
  </details>`;
}

// 保存済み run のメタ情報(いつ保存 / キャッシュ再利用か)を1行で表す
export function analysisSavedNote(r) {
  const at = (r.saved_at || "").replace("T", " ").slice(0, 16);
  const src = r.cached ? "内容に変更が無いため保存済みの結果を表示" : "分析して保存しました";
  return `<span class="muted">${src}(run #${r.run_id} / ${esc(at)})。作り直す場合は「キャッシュを無視して再分析」。</span>`;
}
