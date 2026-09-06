// KPT分析タブ: カードの整理(列移動・並び替え)・重要度(★)づけと保存。
// 分析の実行は「定期実行設定」画面。

import { $, $$, api, esc } from "./core.js";
import { loadKptCard } from "./dashboard.js";

export const KPT_SOURCE_LABEL = {
  mattermost: "Mattermost", trello: "Trello", github: "GitHub",
  changelog: "変更履歴", spec_diff: "実装差分",
};
const KPT_COLS = [
  { kind: "keep", label: "Keep(続けること)" },
  { kind: "problem", label: "Problem(課題)" },
  { kind: "try", label: "Try(次に試すこと)" },
];
let kptLoaded = false;          // 初回ロード済みか(タブ再表示で読み直さない)
let kptAnalysisId = null;
let kptAvailableSources = [];
let kptCards = [];              // [{cid, kind, importance, title, detail, evidence, sources}]
let kptDirty = false;           // 未保存の編集があるか
let kptDragCid = null;          // ドラッグ中のカード cid
let kptCidSeq = 0;

// サーバ応答から画面用のカード配列を作る(列ごとの表示順を保持)
function kptSetCardsFromResponse(r) {
  kptAnalysisId = r.analysis_id;
  kptAvailableSources = (r.stats || {}).available_sources || [];
  kptCards = [];
  for (const { kind } of KPT_COLS) {
    for (const it of (r[kind] || [])) {
      kptCards.push({
        cid: "c" + (++kptCidSeq),
        kind,
        importance: Math.max(0, Math.min(5, it.importance || 0)),
        title: it.title || "",
        detail: it.detail || "",
        evidence: it.evidence || "",  // 画面には出さないが保存時に送り返す
        sources: it.sources || [],
      });
    }
  }
  kptDirty = false;
}

function kptStarsHtml(card) {
  let s = "";
  for (let i = 1; i <= 5; i++) {
    s += `<span class="kpt-star ${i <= card.importance ? "on" : ""}" `
      + `data-cid="${card.cid}" data-n="${i}" title="重要度 ${i}(同じ★をもう一度クリックで 0)">★</span>`;
  }
  return `<span class="kpt-stars">${s}</span>`;
}

function kptCardHtml(card) {
  const badges = (card.sources || [])
    .map((x) => `<span class="badge">${esc(KPT_SOURCE_LABEL[x] || x)}</span>`).join(" ");
  const detail = card.detail ? `<div class="d">${esc(card.detail)}</div>` : "";
  return `<div class="kpt-item draggable" draggable="true" data-cid="${card.cid}">
    <div class="kpt-head">
      <div class="t">${esc(card.title)}</div>
      ${kptStarsHtml(card)}
    </div>
    ${detail}
    ${badges ? `<div class="e">${badges}</div>` : ""}
  </div>`;
}

function renderKptBoard() {
  // 列ごとの件数をサマリに反映
  const counts = { keep: 0, problem: 0, try: 0 };
  kptCards.forEach((c) => { if (counts[c.kind] != null) counts[c.kind]++; });
  $("#kptSummary").textContent =
    `Keep ${counts.keep} / Problem ${counts.problem} / Try ${counts.try}`
    + (kptAvailableSources.length
      ? ` / 対象ソース: ${kptAvailableSources.map((s) => KPT_SOURCE_LABEL[s] || s).join("、 ")}` : "");

  const grid = KPT_COLS.map(({ kind, label }) => {
    const cards = kptCards.filter((c) => c.kind === kind);
    const body = cards.length
      ? cards.map(kptCardHtml).join("")
      : '<div class="kpt-col-empty">ここにドラッグ</div>';
    return `<div class="kpt-col ${kind}" data-kind="${kind}"><h3>${label}</h3>${body}</div>`;
  }).join("");
  $("#kptResults").innerHTML = `<div class="kpt-grid">${grid}</div>`;

  wireKptBoard();
  $("#kptSaveBtn").disabled = !kptDirty || !kptAnalysisId;
  $("#kptSaveStatus").textContent = kptDirty ? "未保存の変更があります" : "";
}

// ★クリックとドラッグ&ドロップのハンドラを毎回貼り直す
function wireKptBoard() {
  $$("#kptResults .kpt-star").forEach((el) => {
    el.addEventListener("click", () => {
      const card = kptCards.find((c) => c.cid === el.dataset.cid);
      if (!card) return;
      const n = Number(el.dataset.n);
      card.importance = (card.importance === n) ? 0 : n;  // 同じ★の再クリックで 0
      kptDirty = true;
      renderKptBoard();
    });
  });

  $$("#kptResults .kpt-item").forEach((el) => {
    el.addEventListener("dragstart", (e) => {
      kptDragCid = el.dataset.cid;
      el.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", el.dataset.cid);
    });
    el.addEventListener("dragend", () => {
      kptDragCid = null;
      $$("#kptResults .dragging").forEach((x) => x.classList.remove("dragging"));
      $$("#kptResults .drop-hint").forEach((x) => x.classList.remove("drop-hint"));
    });
  });

  $$("#kptResults .kpt-col").forEach((col) => {
    col.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      col.classList.add("drop-hint");
    });
    col.addEventListener("dragleave", (e) => {
      if (!col.contains(e.relatedTarget)) col.classList.remove("drop-hint");
    });
    col.addEventListener("drop", (e) => {
      e.preventDefault();
      col.classList.remove("drop-hint");
      if (!kptDragCid) return;
      const beforeEl = kptDragAfterElement(col, e.clientY);
      kptMoveCard(kptDragCid, col.dataset.kind, beforeEl ? beforeEl.dataset.cid : null);
    });
  });
}

// 列内で、カーソル位置の直後にくるカード要素(なければ null = 末尾)
function kptDragAfterElement(col, y) {
  const els = Array.from(col.querySelectorAll(".kpt-item:not(.dragging)"));
  for (const el of els) {
    const box = el.getBoundingClientRect();
    if (y < box.top + box.height / 2) return el;
  }
  return null;
}

// カードを別の列 / 別の位置へ移動し、再描画する
function kptMoveCard(cid, toKind, beforeCid) {
  const idx = kptCards.findIndex((c) => c.cid === cid);
  if (idx < 0) return;
  const [card] = kptCards.splice(idx, 1);
  card.kind = toKind;
  if (beforeCid) {
    const bIdx = kptCards.findIndex((c) => c.cid === beforeCid);
    kptCards.splice(bIdx < 0 ? kptCards.length : bIdx, 0, card);
  } else {
    // 移動先の列の最後尾へ
    let lastIdx = -1;
    kptCards.forEach((c, i) => { if (c.kind === toKind) lastIdx = i; });
    kptCards.splice(lastIdx + 1, 0, card);
  }
  kptDirty = true;
  renderKptBoard();
}

// 現在の画面状態(列・並び順・重要度)を DB に保存する
export async function saveKpt() {
  if (!kptAnalysisId || !kptDirty) return;
  const items = [];
  for (const { kind } of KPT_COLS) {
    for (const c of kptCards.filter((x) => x.kind === kind)) {
      items.push({
        kind, title: c.title, detail: c.detail, evidence: c.evidence,
        sources: c.sources, importance: c.importance,
      });
    }
  }
  $("#kptSaveBtn").disabled = true;
  $("#kptSaveStatus").textContent = "保存中...";
  try {
    const r = await api(`/api/kpt/runs/${kptAnalysisId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items }),
    });
    kptSetCardsFromResponse(r);
    renderKptBoard();
    loadKptCard().catch(() => {});  // ダッシュボードのカードも更新
    $("#kptSaveStatus").textContent = `保存しました(${new Date().toLocaleTimeString()})`;
  } catch (e) {
    $("#kptSaveStatus").innerHTML = `<span style="color:var(--problem)">${esc(e.message)}</span>`;
    $("#kptSaveBtn").disabled = false;
  }
}

export async function loadLatestKpt() {
  if (kptLoaded) return;
  try {
    const r = await api("/api/kpt/latest");
    if (!r.analysis_id) {
      $("#kptStatus").innerHTML = '<span class="muted">まだ分析結果がありません。「定期実行設定」画面から実行してください。</span>';
      return;
    }
    kptLoaded = true;
    kptSetCardsFromResponse(r);
    renderKptBoard();
    $("#kptStatus").innerHTML =
      `<span class="muted">analysis #${r.analysis_id} / ${esc((r.saved_at || "").replace("T", " ").slice(0, 16))}</span>`;
  } catch (e) { /* 無ければ何もしない */ }
}
