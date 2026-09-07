// 暗黙知共有タブ: 抽出結果の一覧表示と★評価(クリックで即時保存)。
// 表示フィルタ(評価/ソース)はチップクリックで表示/非表示を切り替える(クライアント側で絞り込み)。
// 抽出の実行は「抽出実行」ボタン(POST /api/tacit/extract)。

import { $, $$, api, esc } from "./core.js";

export const SOURCE_LABEL = { mattermost: "Mattermost", trello: "Trello", github: "GitHub" };
const RATING_VALUES = ["unrated", "1", "2", "3", "4", "5"];
const SOURCE_VALUES = ["mattermost", "trello", "github"];

let tacitAllItems = [];  // サーバから取得した全アイテム(未フィルタ)
let tacitLoaded = false;
// フィルタの状態(すべて表示中の値の集合)。チップの「active」状態と対応する。
let activeRatings = new Set(RATING_VALUES);
let activeSources = new Set(SOURCE_VALUES);

function ratingBucket(item) {
  return item.rating == null ? "unrated" : String(item.rating);
}

// フィルタ対象のチップが無い値(例: rating=0)は絞り込みの影響を受けず常に表示する
function tacitVisible(item) {
  const rb = ratingBucket(item);
  if (RATING_VALUES.includes(rb) && !activeRatings.has(rb)) return false;
  if (SOURCE_VALUES.includes(item.source) && !activeSources.has(item.source)) return false;
  return true;
}

// ソースごとに出典(どこから抽出したか)を短い文字列にする
function tacitContextLine(item) {
  const d = item.source_detail || {};
  if (item.source === "mattermost") {
    return `#${d.channel_name || d.channel_id || "?"} ${d.username || d.user_id || ""}`;
  }
  if (item.source === "trello") {
    const who = d.username ? ` / ${d.username}` : "";
    return `「${d.list_name || ""}」${d.card_name || ""}${who}`;
  }
  if (item.source === "github") {
    return `PR #${d.pr_number ?? "?"} ${d.title || ""} / ${d.actor || ""}`;
  }
  return "";
}

function tacitStarsHtml(item) {
  let s = "";
  for (let i = 1; i <= 5; i++) {
    const on = item.rating != null && i <= item.rating;
    s += `<span class="kpt-star ${on ? "on" : ""}" data-id="${item.id}" data-n="${i}" `
      + `title="評価 ${i}(同じ★をもう一度クリックで未評価に戻す)">★</span>`;
  }
  let label = item.rating == null ? "未評価" : `評価 ${item.rating}`;
  // 未評価かつ学習済みモデルによる予測値がある場合は、あくまで参考値として添える
  if (item.rating == null && item.predicted_rating != null) {
    label += ` / AI予測 ★${item.predicted_rating.toFixed(1)}`;
  }
  return `<span class="kpt-stars">${s}</span> <span class="muted" style="font-size:11px">${label}</span>`;
}

function tacitItemHtml(item) {
  return `<div class="kpt-item">
    <div class="kpt-head">
      <div class="t">${esc(item.title)}</div>
      ${tacitStarsHtml(item)}
    </div>
    <div class="d">${esc(item.content)}</div>
    <div class="e">
      <span class="badge">${esc(SOURCE_LABEL[item.source] || item.source)}</span>
      <span class="muted" style="font-size:12px">${esc(tacitContextLine(item))}</span>
    </div>
  </div>`;
}

function renderTacitList() {
  const visible = tacitAllItems.filter(tacitVisible);
  $("#tacitResults").innerHTML = tacitAllItems.length
    ? (visible.length
      ? visible.map(tacitItemHtml).join("")
      : '<div class="muted">条件に一致する項目がありません。フィルタを見直してください。</div>')
    : '<div class="muted">まだ抽出結果がありません。「抽出実行」を押してください。</div>';

  $$("#tacitResults .kpt-star").forEach((el) => {
    el.addEventListener("click", () => rateTacitItem(Number(el.dataset.id), Number(el.dataset.n)));
  });
}

// ★クリック: 同じ★の再クリックで未評価(null)に戻す。押した瞬間に保存する。
async function rateTacitItem(id, n) {
  const item = tacitAllItems.find((x) => x.id === id);
  if (!item) return;
  const nextRating = item.rating === n ? null : n;
  try {
    const updated = await api(`/api/tacit/items/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rating: nextRating }),
    });
    Object.assign(item, updated);
    renderTacitList();
  } catch (e) {
    $("#tacitStatus").innerHTML = `<span style="color:var(--problem)">${esc(e.message)}</span>`;
  }
}

// フィルタチップのクリック配線(表示中/非表示中の切り替え。1 度だけ配線すればよい)
function wireTacitFilters() {
  $$("#tacitFilters .tacit-filter-chip").forEach((el) => {
    el.addEventListener("click", () => {
      const group = el.dataset.group === "rating" ? activeRatings : activeSources;
      const value = el.dataset.value;
      if (group.has(value)) {
        group.delete(value);
        el.classList.remove("active");
      } else {
        group.add(value);
        el.classList.add("active");
      }
      renderTacitList();
    });
  });
}

export async function loadTacitItems() {
  try {
    const r = await api("/api/tacit/items");
    tacitAllItems = r.items || [];
    renderTacitList();
  } catch (e) {
    $("#tacitResults").innerHTML = `<span style="color:var(--problem)">${esc(e.message)}</span>`;
  }
}

export async function loadLatestTacit() {
  if (tacitLoaded) return;
  tacitLoaded = true;
  wireTacitFilters();
  await loadTacitItems();
  pollTacitTraining();
}

export async function extractTacit() {
  $("#tacitExtractBtn").disabled = true;
  $("#tacitStatus").textContent = "抽出中...";
  try {
    const r = await api("/api/tacit/extract", { method: "POST" });
    const st = r.stats || {};
    const sum = (obj) => Object.values(obj || {}).reduce((a, b) => a + b, 0);
    $("#tacitStatus").textContent =
      `完了: ${sum(st.scanned)}件走査 / ${sum(st.extracted)}件抽出(新規登録 ${r.inserted_count ?? 0}件)`;
    await loadTacitItems();
  } catch (e) {
    $("#tacitStatus").innerHTML = `<span style="color:var(--problem)">${esc(e.message)}</span>`;
  } finally {
    $("#tacitExtractBtn").disabled = false;
  }
}

// --- 評価値の学習(バックグラウンドタスク。run の状態をポーリングして確認する) ---
let tacitTrainPolling = null;

function tacitTrainStatusText(run) {
  if (!run || !run.id) return "";
  if (run.status === "running") return "学習中...";
  if (run.status === "error") return `学習エラー: ${run.detail || ""}`;
  if (run.status === "success") {
    const m = run.metrics || {};
    const acc = m.val_mae != null
      ? `検証MAE ${m.val_mae.toFixed(2)}(${m.val_count}件)`
      : (m.train_mae != null ? `学習データMAE ${m.train_mae.toFixed(2)}(参考値)` : "");
    return `学習完了: ${run.training_item_count}件で学習${acc ? " / " + acc : ""}`;
  }
  return "";
}

// 学習中の run があれば完了まで定期的に確認する(タブ再表示時にも呼ばれる)
export async function pollTacitTraining() {
  clearTimeout(tacitTrainPolling);
  try {
    const run = await api("/api/tacit/train/latest");
    $("#tacitTrainStatus").textContent = tacitTrainStatusText(run);
    $("#tacitTrainBtn").disabled = run.status === "running";
    if (run.status === "running") {
      tacitTrainPolling = setTimeout(() => pollTacitTraining().catch(() => {}), 3000);
    } else if (run.status === "success") {
      // 学習完了直後は未評価アイテムの predicted_rating が更新されているので再取得する
      await loadTacitItems();
    }
  } catch (e) { /* ネットワーク断など。次回タブ表示で再取得 */ }
}

export async function trainTacit() {
  $("#tacitTrainBtn").disabled = true;
  $("#tacitTrainStatus").textContent = "学習を開始しています...";
  try {
    await api("/api/tacit/train", { method: "POST" });
    pollTacitTraining();
  } catch (e) {
    $("#tacitTrainBtn").disabled = false;
    $("#tacitTrainStatus").innerHTML = `<span style="color:var(--problem)">${esc(e.message)}</span>`;
  }
}
