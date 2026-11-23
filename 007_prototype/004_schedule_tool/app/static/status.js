/**
 * 業務状況(出社割合)の画面処理
 *
 * - 1人×1日×30分の枠ごとに「オフィス / オフィス外 / 休み」を表示・修正(ラベル付け)する
 * - 出社割合 = オフィスの枠の数 ÷ 枠の数(勤務時間8時間固定。休日は0)
 * - 保存するのはラベル(メンバー・日付・枠ごとの値)だけで、予定名などの予定の内容は保存しない
 *   (学習するときは、サーバがラベルのある日の予定を GROUPSESSION から読み込み直して使う)
 *
 * app.js の state / $ / esc / api / formatDate / memberName / eventColor / showMessage などを使う。
 */
"use strict";

const LABEL_NAMES = { office: "オフィス", outside: "オフィス外", off: "休み" };
const SOURCE_NAMES = { label: "ラベル", model: "モデル推定", rule: "ルール判定", holiday: "休日", edit: "未保存の修正" };

const st = {
  slots: [],             // 枠の開始時刻
  results: new Map(),    // "uid|date" → {labels, ratio, source}(サーバの判定結果)
  edits: new Map(),      // "uid|date" → labels(画面で修正し、まだ保存していないもの)
  selectedDate: null,    // ラベル付けをしている日
  brush: "office",       // 塗る値
  painting: false,       // ドラッグで塗っている途中か
  stale: false,          // 空き時間の画面で取得し直した後、まだ判定し直していない
};

// ======================================================================== 共通

/**
 * "uid|date" のキー
 * @param {string} uid メンバーID
 * @param {string} date 日付
 * @returns {string} キー
 */
function skey(uid, date) {
  return `${uid}|${date}`;
}

/**
 * 今表示しているラベル(未保存の修正があればそれ、無ければサーバの判定結果)
 * @param {string} uid メンバーID
 * @param {string} date 日付
 * @returns {string[]|null} 枠ごとのラベル
 */
function currentLabels(uid, date) {
  const key = skey(uid, date);
  return st.edits.get(key) || st.results.get(key)?.labels || null;
}

/**
 * 判定方法(未保存の修正があれば "edit")
 * @param {string} uid メンバーID
 * @param {string} date 日付
 * @returns {string} label / model / rule / holiday / edit
 */
function currentSource(uid, date) {
  const key = skey(uid, date);
  return st.edits.has(key) ? "edit" : (st.results.get(key)?.source || "");
}

/**
 * 出社割合(オフィスの枠の数 ÷ 枠の数)
 * @param {string[]|null} labels 枠ごとのラベル
 * @returns {number} 0〜1
 */
function ratioOf(labels) {
  if (!labels || labels.length === 0) return 0;
  return labels.filter((v) => v === "office").length / labels.length;
}

/**
 * その人のその日の予定
 * @param {string} uid メンバーID
 * @param {string} date 日付
 * @returns {object[]} 予定
 */
function dayEventsOf(uid, date) {
  return state.schedule.events.filter((ev) => ev.uid === uid && ev.start_date <= date && ev.end_date >= date);
}

/**
 * ラベル付けの対象の日(休日を除く)
 * @returns {object[]} 日付
 */
function workDays() {
  return state.schedule ? state.schedule.days.filter((d) => !d.holiday) : [];
}

/**
 * 予定の時刻と枠が重なるか
 * @param {object} ev 予定
 * @param {string} slot 枠の開始時刻
 * @returns {boolean} 重なれば true
 */
function overlapsSlot(ev, slot) {
  if (ev.all_day || !ev.start_time) return false;
  const s = FreeTime.toMinutes(slot);
  return FreeTime.toMinutes(ev.start_time) < s + 30 && FreeTime.toMinutes(ev.end_time) > s;
}

// ======================================================================== 判定・表示

/** 保存済みのラベル数とモデルの情報を表示する */
async function loadStatusSummary() {
  try {
    const s = await api("/api/status/summary");
    const m = s.model;
    const metric = m && m.metrics
      ? `<div class="metric">精度(日付で分けた検証): 枠の正解率 ${(m.metrics.slot_accuracy * 100).toFixed(1)}% / 出社割合の平均誤差 ±${m.metrics.ratio_mae.toFixed(3)}</div>`
      : "";
    // 配布版(ラベル保存・学習なし)では、保存済みのラベル数は出さない
    const labelLine = state.config?.labeling_enabled
      ? `<div>保存済みのラベル: <b>${s.label_count}</b>件(1人×1日)</div>` : "";
    $("status-summary").innerHTML = `
      ${labelLine}
      <div>モデル: ${m ? `${esc(m.trained_at.replace("T", " "))} に ${m.n_days}件で学習` : "未学習(ルールで判定中)"}</div>
      ${metric}`;
    $("train-btn").disabled = s.label_count < s.min_train_days;
    $("train-btn").title = s.label_count < s.min_train_days ? `学習には${s.min_train_days}件以上のラベルが必要です` : "";
  } catch (err) {
    $("status-summary").innerHTML = `<p class="placeholder">${esc(err.message)}</p>`;
  }
}

/** サーバで業務状況を判定し直して表示する(保存済みラベル > モデル > ルール) */
async function refreshEstimate() {
  if (!state.schedule) return;
  st.stale = false;
  try {
    // 予定は判定に使うだけで、サーバでは保存しない
    const { members, days: allDays, events } = state.schedule;
    const res = await api("/api/status/estimate", {
      method: "POST",
      body: JSON.stringify({ members, days: allDays, events }),
    });
    st.slots = res.slots;
    st.results = new Map(res.results.map((r) => [skey(r.uid, r.date), r]));
    // 選んでいる日が期間外なら、最初の平日を選ぶ
    const days = workDays();
    if (!days.some((d) => d.date === st.selectedDate)) st.selectedDate = days[0]?.date || null;
    renderStatus();
  } catch (err) {
    showMessage("label-message", err.message, "error");
  }
}

/** 業務状況の画面全体を描き直す */
function renderStatus() {
  renderRatioTable();
  renderLabelGrid();
  $("export-btn").disabled = !state.schedule || st.results.size === 0;
}

/**
 * 出社割合に応じたセルの色
 * @param {number} r 出社割合
 * @returns {string} CSS(背景色と文字色)
 */
function ratioStyle(r) {
  return `background:hsl(217, 85%, ${96 - r * 46}%);color:${r > 0.55 ? "#fff" : "var(--text)"}`;
}

/** 出社割合の表(行=日付、列=メンバー)を表示する */
function renderRatioTable() {
  const box = $("ratio-table");
  if (!state.schedule || st.results.size === 0) return;
  const members = state.schedule.members;
  const head = `<tr><th class="rt-date">日付</th>${members.map((m) => `<th title="${esc(m.name)}">${esc(m.name)}</th>`).join("")}<th>平均</th></tr>`;
  const sums = members.map(() => 0);
  let workCount = 0;

  const rows = state.schedule.days.map((d) => {
    const ratios = members.map((m) => ratioOf(currentLabels(m.uid, d.date)));
    if (!d.holiday) { workCount += 1; ratios.forEach((r, i) => { sums[i] += r; }); }
    const cells = members.map((m, i) => {
      const src = currentSource(m.uid, d.date);
      const r = ratios[i];
      return `<td class="src-${src}" style="${d.holiday ? "" : ratioStyle(r)}"
        data-tip="${esc(`${formatDate(d.date)} ${m.name}\n出社割合 ${r.toFixed(2)}(${SOURCE_NAMES[src] || ""})`)}">${d.holiday ? "休" : r.toFixed(2)}</td>`;
    }).join("");
    const avg = ratios.reduce((a, b) => a + b, 0) / (ratios.length || 1);
    const cls = `rt-row${d.date === st.selectedDate ? " selected" : ""}${d.holiday ? " holiday" : ""}`;
    return `<tr class="${cls}" data-date="${esc(d.date)}"><th class="rt-date">${esc(formatDate(d.date))}</th>${cells}<td class="rt-avg">${d.holiday ? "" : avg.toFixed(2)}</td></tr>`;
  }).join("");

  // 平日の平均(メンバーごと)
  const foot = `<tr><th class="rt-date">平日平均</th>${sums.map((s) => `<td class="rt-avg">${workCount ? (s / workCount).toFixed(2) : "-"}</td>`).join("")}<td class="rt-avg"></td></tr>`;
  box.innerHTML = `<table class="ratio-table"><thead>${head}</thead><tbody>${rows}${foot}</tbody></table>`;
  box.querySelector("tr.selected")?.scrollIntoView({ block: "nearest" });
}

/** 選んだ日のラベル付けの表を表示する */
function renderLabelGrid() {
  const grid = $("label-grid");
  const date = st.selectedDate;
  const days = workDays();
  const idx = days.findIndex((d) => d.date === date);
  $("status-prev-btn").disabled = idx <= 0;
  $("status-next-btn").disabled = idx < 0 || idx >= days.length - 1;
  $("label-save-btn").disabled = !date;
  if (!state.schedule || !date) {
    $("label-title").textContent = "ラベル付け";
    grid.innerHTML = `<p class="empty">予定を取得すると、日ごとのラベルが表示されます。</p>`;
    $("label-delete-btn").disabled = true;
    return;
  }
  $("label-title").textContent = `${formatDate(date)} のラベル`;
  const members = state.schedule.members;
  $("label-delete-btn").disabled = !members.some((m) => st.results.get(skey(m.uid, date))?.source === "label");

  // 見出し(正時だけ時刻を出す)
  const heads = st.slots.map((s) => `<th>${s.endsWith(":00") ? String(Number(s.slice(0, 2))) : ""}</th>`).join("");
  const rows = members.map((m) => {
    const labels = currentLabels(m.uid, date) || st.slots.map(() => "office");
    const src = currentSource(m.uid, date);
    const evs = dayEventsOf(m.uid, date);
    const chips = evs.filter((ev) => ev.all_day).map((ev) =>
      `<span class="chip" style="background:${eventColor(ev)}" data-tip="${esc(statusEventTip(ev))}">${esc(ev.title || "(無題)")}</span>`).join("");
    const labelCells = labels.map((v, i) =>
      `<td class="lg-cell ${v}" data-uid="${esc(m.uid)}" data-i="${i}" data-tip="${esc(`${st.slots[i]}〜 ${LABEL_NAMES[v]}`)}"></td>`).join("");
    const eventCells = st.slots.map((s) => {
      const hits = evs.filter((ev) => overlapsSlot(ev, s));
      return hits.length
        ? `<td class="ev-on" style="background:${eventColor(hits[0])}" data-tip="${esc(hits.map(statusEventTip).join("\n\n"))}"></td>`
        : "<td></td>";
    }).join("");
    return `
      <tr class="lg-label-row">
        <th class="lg-name" rowspan="2" title="${esc(m.name)}">${esc(m.name)}
          <span class="lg-source ${src === "edit" ? "lg-unsaved" : ""}">${esc(SOURCE_NAMES[src] || "")}</span></th>
        <td class="lg-allday" rowspan="2">${chips}</td>
        ${labelCells}
        <td class="lg-ratio" rowspan="2">${ratioOf(labels).toFixed(2)}</td>
        <td class="lg-actions" rowspan="2">
          <button type="button" data-fill="office" data-uid="${esc(m.uid)}" title="1日オフィス">オ</button><button type="button" data-fill="outside" data-uid="${esc(m.uid)}" title="1日オフィス外">外</button><button type="button" data-fill="off" data-uid="${esc(m.uid)}" title="1日休み">休</button>
        </td>
      </tr>
      <tr class="lg-event-row lg-row-sep">${eventCells}</tr>`;
  }).join("");
  grid.innerHTML = `<table class="lg-table">
    <thead><tr><th class="lg-name"></th><th class="lg-allday">終日</th>${heads}<th class="lg-ratio">割合</th><th class="lg-actions">1日分</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

/**
 * ラベル付けの画面で表示する予定の説明(時刻と予定名)
 * @param {object} ev 予定
 * @returns {string} 説明
 */
function statusEventTip(ev) {
  const time = ev.all_day
    ? (ev.start_date === ev.end_date ? "時刻なし" : `${formatDate(ev.start_date)}〜${formatDate(ev.end_date)}`)
    : `${ev.start_time}〜${ev.end_time}`;
  return `${time}  ${ev.title || "(無題)"}`;
}

// ======================================================================== ラベルの編集

/**
 * 枠を「塗る値」で塗る(画面のセルだけを書き換え、表全体の描き直しは塗り終わってから)
 * @param {HTMLElement} cell 枠のセル
 */
function paintCell(cell) {
  const uid = cell.dataset.uid;
  const i = Number(cell.dataset.i);
  const key = skey(uid, st.selectedDate);
  const labels = [...(currentLabels(uid, st.selectedDate) || st.slots.map(() => "office"))];
  if (labels[i] === st.brush) return;
  labels[i] = st.brush;
  st.edits.set(key, labels);
  cell.className = `lg-cell ${st.brush}`;
}

/**
 * 1日分をまとめて塗る
 * @param {string} uid メンバーID
 * @param {string} value ラベル
 */
function fillDay(uid, value) {
  st.edits.set(skey(uid, st.selectedDate), st.slots.map(() => value));
  renderStatus();
}

/** 選んだ日のラベルを保存する(全員分。予定の内容は送らない) */
async function saveDayLabels() {
  const date = st.selectedDate;
  if (!state.schedule || !date) return;

  // 全員分のラベルを送る(学習のときに予定を読み込み直せるよう、マイグループも記録する)
  const group = $("group-select").value;
  const records = state.schedule.members.map((m) => ({
    uid: m.uid,
    name: m.name,
    group,
    date,
    slots: st.slots,
    labels: currentLabels(m.uid, date) || st.slots.map(() => "office"),
  }));
  const btn = $("label-save-btn");
  btn.disabled = true;
  try {
    const res = await api("/api/status/labels", { method: "POST", body: JSON.stringify({ records }) });
    state.schedule.members.forEach((m) => st.edits.delete(skey(m.uid, date)));
    showMessage("label-message", `${formatDate(date)} のラベルを${res.saved}件保存しました(保存済み 合計${res.total}件)。`, "success");
    await refreshEstimate();
    await loadStatusSummary();
  } catch (err) {
    showMessage("label-message", err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

/** 選んだ日の保存済みラベルを削除する */
async function deleteDayLabels() {
  const date = st.selectedDate;
  if (!date || !window.confirm(`${formatDate(date)} の保存済みラベルを削除します。よろしいですか?`)) return;
  try {
    const keys = state.schedule.members.map((m) => ({ uid: m.uid, date }));
    const res = await api("/api/status/labels/delete", { method: "POST", body: JSON.stringify({ keys }) });
    showMessage("label-message", `${res.deleted}件のラベルを削除しました。`, "info");
    await refreshEstimate();
    await loadStatusSummary();
  } catch (err) {
    showMessage("label-message", err.message, "error");
  }
}

/**
 * ラベル付けをする日を選ぶ
 * @param {string} date 日付
 */
function selectStatusDate(date) {
  const day = state.schedule.days.find((d) => d.date === date);
  if (day && day.holiday) {
    showMessage("label-message", "休日は出社割合0として扱うため、ラベル付けは不要です。", "info");
    return;
  }
  st.selectedDate = date;
  showMessage("label-message", "");
  renderStatus();
}

/**
 * 前後の平日に移動する
 * @param {number} delta -1 で前、1 で次
 */
function moveStatusDay(delta) {
  const days = workDays();
  const next = days[days.findIndex((d) => d.date === st.selectedDate) + delta];
  if (next) selectStatusDate(next.date);
}

// ======================================================================== 学習・出力

/**
 * 保存したラベルでモデルを学習する
 * (サーバが、ラベルのある日の予定を GROUPSESSION から読み込み直して学習する。ログインが必要)
 */
async function trainModel() {
  const btn = $("train-btn");
  btn.disabled = true;
  showMessage("train-message", "ラベルのある日の予定を GROUPSESSION から読み込んで学習しています…(半年分で1分ほどかかります)", "info");
  try {
    // グループが記録されていない古いラベルには、今選んでいるマイグループを使う
    const info = await api("/api/status/train", {
      method: "POST",
      body: JSON.stringify({ group: $("group-select").value }),
    });
    const m = info.metrics;
    const skipped = info.skipped ? `(メンバーが見つからず使えなかったラベル ${info.skipped}件)` : "";
    showMessage("train-message", `学習しました(${info.n_days}件)${skipped}。` +
      (m ? `枠の正解率 ${(m.slot_accuracy * 100).toFixed(1)}%、出社割合の平均誤差 ±${m.ratio_mae.toFixed(3)}` : ""), "success");
    await loadStatusSummary();
    await refreshEstimate();
  } catch (err) {
    // ログインが切れていればログインし直してもらう
    if (!handleAuthError(err)) showMessage("train-message", err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

/**
 * CSVの1項目を書き出す形にする(カンマ・引用符・改行を含むときだけ "" で囲む)
 * @param {string|number} v 値
 * @returns {string} CSVの項目
 */
function csvField(v) {
  const s = String(v);
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/**
 * CSVの見出しに使うメンバー名(苗字のみ)を作る
 * 氏名を空白(半角・全角)で区切った最初の部分を苗字とする。空白がない名前はそのまま使う。
 * 同じ苗字の人が複数いる場合は、区別できるようにその人たちだけ氏名のままにする。
 * @param {Array<{name: string}>} members メンバー一覧
 * @returns {string[]} 見出しに使う名前(members と同じ順)
 */
function surnameHeaders(members) {
  // 1. 氏名から苗字を取り出す
  const surnames = members.map((m) => m.name.trim().split(/[\s　]+/)[0] || m.name);
  // 2. 苗字ごとの人数を数える
  const counts = {};
  surnames.forEach((s) => { counts[s] = (counts[s] || 0) + 1; });
  // 3. 重複する苗字だけ氏名に戻す
  return surnames.map((s, i) => (counts[s] > 1 ? members[i].name : s));
}

/**
 * 出社割合をCSVで出力する(全日付・全メンバー。予定名は含めない)
 * 形式: 1行目が「date,苗字…」、2行目以降が「2026/11/01,1,0.5,…」(行=日付、列=メンバー)
 */
function exportRatioCsv() {
  // 見出し行: date + メンバーの苗字(画面の列と同じ順)
  const members = state.schedule.members;
  const rows = [["date", ...surnameHeaders(members)]];
  state.schedule.days.forEach((d) => {
    // 日付は「2026/11/01」の形(yyyy/mm/dd、月・日は0埋め)
    const row = [d.date.replace(/-/g, "/")];
    members.forEach((m) => {
      // 休日は0、それ以外は「オフィス枠数 / 16」を余分な0なしで出す(例: 1, 0.5, 0.875)
      const r = d.holiday ? 0 : ratioOf(currentLabels(m.uid, d.date));
      row.push(String(Number(r.toFixed(4))));
    });
    rows.push(row);
  });
  const csv = rows.map((r) => r.map(csvField).join(",")).join("\r\n") + "\r\n";
  // Excel で文字化けしないよう、先頭に BOM を付ける
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `出社割合_${state.schedule.days[0].date}_${state.schedule.days[state.schedule.days.length - 1].date}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// ======================================================================== 画面の切り替え・初期化

/**
 * 画面(空き時間 / 業務状況)を切り替える
 * @param {string} mode free / status
 */
function setMode(mode) {
  state.mode = mode;
  document.body.dataset.mode = mode;
  document.querySelectorAll(".mode-btn").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
  updateFetchButton();
  if (mode === "status") {
    loadStatusSummary();
    if (state.schedule && (st.stale || st.results.size === 0)) refreshEstimate();
  }
}

/** 予定を取得し直したとき(app.js から呼ばれる) */
function onScheduleLoaded() {
  st.edits = new Map();
  st.results = new Map();
  st.selectedDate = null;
  if (state.mode === "status") refreshEstimate();
  else st.stale = true;
}

/** 業務状況の画面のイベントを登録する */
function initStatus() {
  document.querySelectorAll(".mode-btn").forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode)));
  document.querySelectorAll(".brush").forEach((b) => b.addEventListener("click", () => {
    st.brush = b.dataset.brush;
    document.querySelectorAll(".brush").forEach((x) => x.classList.toggle("active", x === b));
  }));

  // ラベルの枠: クリック・ドラッグで塗る(塗り終わったら表全体を描き直す)
  const grid = $("label-grid");
  grid.addEventListener("pointerdown", (e) => {
    const cell = e.target.closest(".lg-cell");
    if (!cell) return;
    e.preventDefault();
    st.painting = true;
    paintCell(cell);
  });
  grid.addEventListener("pointerover", (e) => {
    if (!st.painting) return;
    const cell = e.target.closest(".lg-cell");
    if (cell) paintCell(cell);
  });
  document.addEventListener("pointerup", () => {
    if (!st.painting) return;
    st.painting = false;
    renderStatus();
  });
  grid.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-fill]");
    if (btn) fillDay(btn.dataset.uid, btn.dataset.fill);
  });

  $("ratio-table").addEventListener("click", (e) => {
    const row = e.target.closest("tr.rt-row");
    if (row) selectStatusDate(row.dataset.date);
  });
  $("status-prev-btn").addEventListener("click", () => moveStatusDay(-1));
  $("status-next-btn").addEventListener("click", () => moveStatusDay(1));
  $("label-save-btn").addEventListener("click", saveDayLabels);
  $("label-delete-btn").addEventListener("click", deleteDayLabels);
  $("train-btn").addEventListener("click", trainModel);
  $("export-btn").addEventListener("click", exportRatioCsv);

  // 未保存の修正があるまま閉じようとしたら確認する(ラベルを保存できる場合のみ)
  window.addEventListener("beforeunload", (e) => {
    if (state.config?.labeling_enabled && st.edits.size > 0) { e.preventDefault(); e.returnValue = ""; }
  });
}

initStatus();
