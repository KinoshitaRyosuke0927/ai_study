/**
 * スケジュール確認ツールの画面処理
 *
 * 画面は「左: 条件」「中央: 空き時間の候補(一覧)」「右上: 期間の俯瞰」「右下: 選んだ日の詳細」の4つの領域に分け、
 * 画面全体はスクロールさせない(各領域の中だけスクロールする)。
 * 取得した予定はこの画面(ブラウザのメモリ上)にだけ保持し、保存はしない。
 */
"use strict";

const WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"];
// GROUPSESSION のタイトル色(cl_fontSchTitle○○ の○○)と、画面で使う色
const COLOR_MAP = {
  Blue: "#2563eb", Red: "#dc2626", Green: "#16a34a", Yellow: "#ca8a04", Black: "#334155",
  Navy: "#1e3a8a", Wine: "#9f1239", Cien: "#0891b2", Gray: "#6b7280", Marine: "#0f766e",
  Orange: "#ea580c", Pink: "#db2777", Purple: "#7c3aed", Brown: "#92400e",
};
const DEFAULT_COLOR = "#475569";

const state = {
  config: null,
  loggedIn: false,
  groupMembers: [],        // 選択中のマイグループのメンバー
  schedule: null,          // 取得した予定 {days, members, events}
  blockingKeys: new Set(), // 「埋まっている扱い」にした時刻なし予定
  candidates: [],          // 空き時間の候補
  selectedDate: null,      // 詳細を表示している日
  selectedCandidate: null, // 選んだ候補の番号(候補から日を選んだ場合)
  mode: "free",            // 表示中の画面("free": 空き時間 / "status": 業務状況)
};

const $ = (id) => document.getElementById(id);

// ======================================================================== 共通

/**
 * HTMLとして安全な文字列にする
 * @param {string} s 文字列
 * @returns {string} エスケープした文字列
 */
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/**
 * APIを呼び出す(エラー時はサーバのメッセージで例外にする)
 * @param {string} url URL
 * @param {object} [options] fetch のオプション
 * @returns {Promise<any>} 応答のJSON
 */
async function api(url, options = {}) {
  const res = await fetch(url, { headers: { "Content-Type": "application/json" }, cache: "no-store", ...options });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(typeof data.detail === "string" ? data.detail : `エラーが発生しました(HTTP ${res.status})`);
    err.status = res.status;
    throw err;
  }
  return data;
}

/**
 * メッセージ欄に表示する(text が空なら隠す)
 * @param {string} id 要素ID
 * @param {string} text 表示する文字
 * @param {"error"|"info"|"success"} type 種類
 */
function showMessage(id, text, type = "info") {
  const el = $(id);
  el.textContent = text || "";
  el.className = `message ${type}` + (text ? "" : " hidden");
}

/**
 * Date を "YYYY-MM-DD" にする(ローカル時刻)
 * @param {Date} d 日付
 * @returns {string} 日付の文字列
 */
function isoDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/**
 * "YYYY-MM-DD" を "11/24(火)" の形にする
 * @param {string} iso 日付
 * @returns {string} 表示用の日付
 */
function formatDate(iso) {
  const d = new Date(`${iso}T00:00:00`);
  return `${d.getMonth() + 1}/${d.getDate()}(${WEEKDAYS[(d.getDay() + 6) % 7]})`;
}

/**
 * メンバーIDから氏名を引く
 * @param {string} uid メンバーID
 * @returns {string} 氏名
 */
function memberName(uid) {
  const m = (state.schedule?.members || state.groupMembers).find((x) => x.uid === uid);
  return m ? m.name : uid;
}

// ======================================================================== ログイン

/** ログイン状態に合わせてボタン・入力欄の状態を切り替える */
function updateLoginUi() {
  const btn = $("login-open-btn");
  btn.textContent = state.loggedIn ? "GROUPSESSIONログイン済" : "GROUPSESSIONログイン";
  btn.classList.toggle("logged-in", state.loggedIn);
  $("group-select").disabled = !state.loggedIn;
  updateFetchButton();
}

/** ログインのモーダルを開く */
function openLogin() {
  showMessage("login-message", "");
  $("login-password").value = "";
  $("login-overlay").classList.remove("hidden");
  $("login-username").focus();
}

/** ログインのモーダルを閉じる */
function closeLogin() {
  $("login-overlay").classList.add("hidden");
  $("login-password").value = "";
}

/**
 * ログインする(成功したらマイグループの一覧を読み込む)
 * @param {Event} e 送信イベント
 */
async function submitLogin(e) {
  e.preventDefault();
  const btn = $("login-btn");
  btn.disabled = true;
  showMessage("login-message", "ログインしています…", "info");
  try {
    await api("/api/login", {
      method: "POST",
      body: JSON.stringify({ username: $("login-username").value, password: $("login-password").value }),
    });
    state.loggedIn = true;
    closeLogin();
    updateLoginUi();
    await loadGroups();
  } catch (err) {
    showMessage("login-message", err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

/**
 * セッション切れなどで401が返った場合に、ログインし直してもらう
 * @param {Error} err 発生したエラー
 * @returns {boolean} ログインし直しが必要だった場合 true
 */
function handleAuthError(err) {
  if (err.status !== 401) return false;
  state.loggedIn = false;
  updateLoginUi();
  openLogin();
  showMessage("login-message", err.message, "error");
  return true;
}

// ======================================================================== マイグループ・メンバー

/** マイグループの一覧を読み込み、前回のグループを選ぶ */
async function loadGroups() {
  const sel = $("group-select");
  sel.innerHTML = `<option value="">読み込み中…</option>`;
  try {
    const groups = await api("/api/groups");
    if (groups.length === 0) {
      sel.innerHTML = `<option value="">マイグループがありません</option>`;
      return;
    }
    sel.innerHTML = `<option value="">選択してください</option>` +
      groups.map((g) => `<option value="${esc(g.value)}">${esc(g.name)}</option>`).join("");
    // 前回選んだグループがあれば選んでおく
    if (groups.some((g) => g.value === state.config.last_group)) {
      sel.value = state.config.last_group;
      await loadMembers();
    }
  } catch (err) {
    if (!handleAuthError(err)) sel.innerHTML = `<option value="">読み込めませんでした</option>`;
    showMessage("fetch-message", err.message, "error");
  }
}

/** 選択したマイグループのメンバーを読み込み、チェックボックスを表示する */
async function loadMembers() {
  const group = $("group-select").value;
  const list = $("member-list");
  state.groupMembers = [];
  updateFetchButton();
  if (!group) {
    list.innerHTML = `<p class="placeholder">マイグループを選ぶと表示されます</p>`;
    return;
  }
  list.innerHTML = `<p class="placeholder">読み込み中…</p>`;
  try {
    state.groupMembers = await api(`/api/groups/${encodeURIComponent(group)}/members`);
    // 前回と同じグループなら前回のチェックを、違うグループなら全員をチェックする
    const lastIds = group === state.config.last_group ? new Set(state.config.last_member_ids) : null;
    list.innerHTML = state.groupMembers.map((m) => `
      <label class="member-item">
        <input type="checkbox" value="${esc(m.uid)}" ${!lastIds || lastIds.has(m.uid) ? "checked" : ""}>
        ${esc(m.name)}
      </label>`).join("") || `<p class="placeholder">メンバーがいません</p>`;
  } catch (err) {
    if (!handleAuthError(err)) list.innerHTML = `<p class="placeholder">読み込めませんでした</p>`;
    showMessage("fetch-message", err.message, "error");
  }
  updateFetchButton();
}

/**
 * チェックしたメンバーのID
 * @returns {string[]} メンバーID
 */
function checkedMemberIds() {
  return [...$("member-list").querySelectorAll("input[type=checkbox]:checked")].map((c) => c.value);
}

/**
 * メンバーのチェックをまとめて切り替える
 * @param {boolean} checked チェックするなら true
 */
function setAllMembers(checked) {
  $("member-list").querySelectorAll("input[type=checkbox]").forEach((c) => { c.checked = checked; });
  updateFetchButton();
}

// ======================================================================== 期間・取得

/**
 * 期間の週数を求める(サーバは開始日から7日ずつ取得する)
 * @returns {number|null} 週数(日付が不正なら null)
 */
function periodWeeks() {
  const s = $("start-date").value;
  const e = $("end-date").value;
  if (!s || !e || e < s) return null;
  const days = (new Date(`${e}T00:00:00`) - new Date(`${s}T00:00:00`)) / 86400000 + 1;
  return Math.ceil(days / 7);
}

/** 期間・メンバーの選択に合わせて、取得ボタンの状態と注意書きを更新する */
function updateFetchButton() {
  const weeks = periodWeeks();
  // 一度に取得できる週数は画面によって異なる(業務状況は長い期間を扱う)
  const max = state.config ? (state.mode === "status" ? state.config.max_weeks_status : state.config.max_weeks) : 8;
  const hint = $("period-hint");
  let ok = state.loggedIn && $("group-select").value && checkedMemberIds().length > 0;
  if (weeks === null) {
    hint.textContent = "終了日は開始日以降にしてください。";
    ok = false;
  } else if (weeks > max) {
    hint.textContent = `一度に取得できるのは${max}週間までです(現在 ${weeks}週間)。`;
    ok = false;
  } else {
    hint.textContent = `${weeks}週間分を取得します(最大${max}週間)。`;
  }
  $("member-all-btn").disabled = $("member-none-btn").disabled = state.groupMembers.length === 0;
  $("fetch-btn").disabled = !ok;
  updateSummaries();
}

/** 選択したメンバー・期間の予定を取得して表示する */
async function fetchSchedule() {
  const btn = $("fetch-btn");
  btn.disabled = true;
  btn.textContent = "取得中…";
  showMessage("fetch-message", "GROUPSESSIONから予定を取得しています(1週間ごとに取得するため、少し時間がかかります)…", "info");
  try {
    const memberIds = checkedMemberIds();
    const group = $("group-select").value;
    state.schedule = await api("/api/schedule", {
      method: "POST",
      body: JSON.stringify({ group, member_ids: memberIds, start: $("start-date").value, end: $("end-date").value, purpose: state.mode }),
    });
    // 次回用に選択を覚えておく(サーバ側でも config.json に保存済み)
    state.config.last_group = group;
    state.config.last_member_ids = memberIds;
    state.blockingKeys = new Set();
    state.selectedDate = null;
    state.selectedCandidate = null;
    buildRequiredOptions();
    showMessage("fetch-message", "");
    $("fetch-status").textContent =
      `${formatDate($("start-date").value)}〜${formatDate($("end-date").value)}・${state.schedule.members.length}人・予定 ${state.schedule.events.length}件を表示中`;
    renderAll();
    // 業務状況の画面(status.js)にも、予定を取得したことを知らせる
    if (typeof onScheduleLoaded === "function") onScheduleLoaded();
  } catch (err) {
    handleAuthError(err);
    showMessage("fetch-message", err.message, "error");
  } finally {
    btn.textContent = "予定を取得";
    updateFetchButton();
  }
}

// ======================================================================== 空き時間の条件

/** 参加できる人数の選択肢を、取得したメンバー数に合わせて作り直す */
function buildRequiredOptions() {
  const sel = $("cond-required");
  const n = state.schedule ? state.schedule.members.length : 0;
  const prev = sel.value;
  const options = [`<option value="all">全員${n ? `(${n}人)` : ""}</option>`];
  for (let k = n - 1; k >= 1; k--) options.push(`<option value="${k}">${k}人以上</option>`);
  sel.innerHTML = options.join("");
  if ([...sel.options].some((o) => o.value === prev)) sel.value = prev;
}

/**
 * 画面の入力から、空き時間の条件を作る
 * @returns {object} 条件(free_time.js の conditions)
 */
function readConditions() {
  const n = state.schedule ? state.schedule.members.length : 0;
  const req = $("cond-required").value;
  return {
    businessStart: $("cond-business-start").value || "09:00",
    businessEnd: $("cond-business-end").value || "18:00",
    lunchStart: $("cond-lunch-start").value || "12:00",
    lunchEnd: $("cond-lunch-end").value || "13:00",
    slotMinutes: Number($("cond-slot").value),
    minDurationMinutes: Number($("cond-duration").value),
    requiredCount: req === "all" ? n : Number(req),
    excludeHolidays: $("cond-exclude-holidays").checked,
  };
}

/** 設定の初期値を、空き時間の条件の入力欄に入れる */
function applyConfigToConditions() {
  const c = state.config;
  $("cond-business-start").value = c.business_start;
  $("cond-business-end").value = c.business_end;
  $("cond-lunch-start").value = c.lunch_start;
  $("cond-lunch-end").value = c.lunch_end;
  $("cond-slot").value = String(c.slot_minutes);
  $("cond-duration").value = String(c.min_duration_minutes);
  buildRequiredOptions();
}

/** 左の条件欄の、折りたたんだ時にも見える要約を更新する */
function updateSummaries() {
  const total = state.groupMembers.length;
  $("member-summary").textContent = total ? `${checkedMemberIds().length}/${total}人` : "";
  if (!$("cond-required").value) return;
  const c = readConditions();
  const req = $("cond-required").value === "all" ? "全員" : `${$("cond-required").value}人以上`;
  $("cond-summary").textContent = `${c.businessStart}〜${c.businessEnd}・${c.minDurationMinutes}分以上・${req}`;
}

// ======================================================================== 表示(共通)

/**
 * 表示する日(「土日・祝日を除く」がオンなら休日を除く)
 * @returns {object[]} 日付の一覧
 */
function visibleDays() {
  if (!state.schedule) return [];
  const exclude = $("cond-exclude-holidays").checked;
  return state.schedule.days.filter((d) => !(exclude && d.holiday));
}

/**
 * 表示する時刻の列(業務時間を刻みで区切る。昼休みの列は lunch=true)
 * @param {object} c 条件
 * @returns {{start:number,end:number,lunch:boolean}[]} 列の一覧
 */
function buildColumns(c) {
  const bs = FreeTime.toMinutes(c.businessStart);
  const be = FreeTime.toMinutes(c.businessEnd);
  const ls = FreeTime.toMinutes(c.lunchStart);
  const le = FreeTime.toMinutes(c.lunchEnd);
  const cols = [];
  for (let s = bs; s + c.slotMinutes <= be; s += c.slotMinutes) {
    cols.push({ start: s, end: s + c.slotMinutes, lunch: s < le && s + c.slotMinutes > ls });
  }
  return cols;
}

/**
 * 時刻の見出し(正時の列だけ数字を出す)
 * @param {object[]} cols 列
 * @returns {string} th の並び
 */
function hourHeads(cols) {
  return cols.map((col) => `<th>${col.start % 60 === 0 ? String(col.start / 60) : ""}</th>`).join("");
}

/**
 * 予定の色(タイトル色)を返す
 * @param {object} ev 予定
 * @returns {string} 色
 */
function eventColor(ev) {
  return COLOR_MAP[ev.color] || DEFAULT_COLOR;
}

/**
 * ツールチップに表示する予定の説明
 * @param {object} ev 予定
 * @returns {string} 説明(時刻・タイトル・メンバー・詳細)
 */
function eventTip(ev) {
  const time = ev.all_day
    ? (ev.start_date === ev.end_date ? "時刻なし" : `${formatDate(ev.start_date)}〜${formatDate(ev.end_date)}`)
    : `${ev.start_time}〜${ev.end_time}`;
  const extra = (ev.detail || []).filter((line) => line !== ev.title && !line.includes(ev.start_time || "\u0000"));
  return [`${time}  ${ev.title}`, `(${memberName(ev.uid)})`, ...extra].join("\n");
}

/** 候補・俯瞰・詳細・予定一覧をまとめて描き直す */
function renderAll() {
  updateSummaries();
  if (!state.schedule) return;
  const c = readConditions();
  if (FreeTime.toMinutes(c.businessEnd) <= FreeTime.toMinutes(c.businessStart)) {
    $("candidate-list").innerHTML = `<p class="empty">業務終了は業務開始より後の時刻にしてください。</p>`;
    return;
  }
  const ids = state.schedule.members.map((m) => m.uid);
  state.candidates = FreeTime.findCandidates(state.schedule.days, ids, state.schedule.events, c, state.blockingKeys);

  // 選択中の日が表示対象から外れた場合は、最初の候補の日(無ければ最初の日)を選ぶ
  const days = visibleDays();
  if (!days.some((d) => d.date === state.selectedDate)) {
    state.selectedDate = state.candidates[0]?.date || days[0]?.date || null;
    state.selectedCandidate = null;
  }
  // 条件の変更で候補が変わった場合、選んでいた候補の選択は外す
  const sel = state.candidates[state.selectedCandidate];
  if (!sel || sel.date !== state.selectedDate) state.selectedCandidate = null;

  renderCandidates(c, ids);
  renderOverview(c, ids);
  renderDetail(c, ids);
  renderAllEvents();
}

// ======================================================================== 表示(各領域)

/**
 * 空き時間の候補(一覧)を表示する
 * @param {object} c 条件
 * @param {string[]} ids 対象メンバーのID
 */
function renderCandidates(c, ids) {
  const list = $("candidate-list");
  $("candidate-count").textContent = state.candidates.length;
  $("candidate-summary").textContent = `${c.requiredCount === ids.length ? "全員" : `${c.requiredCount}人以上`}が通して空いている` +
    `${c.minDurationMinutes}分以上の時間帯です。クリックすると右下に詳細を表示します。`;
  if (state.candidates.length === 0) {
    list.innerHTML = `<p class="empty">条件に合う空き時間がありません。人数や必要な長さを変えてみてください。</p>`;
    return;
  }
  // 日付ごとにまとめて表示する
  const byDate = {};
  state.candidates.forEach((cd, i) => { (byDate[cd.date] ||= []).push([cd, i]); });
  list.innerHTML = Object.entries(byDate).map(([date, items]) => `
    <div class="candidate-day">
      <h3 data-date="${esc(date)}">${esc(formatDate(date))}</h3>
      ${items.map(([cd, i]) => {
        const missing = ids.filter((uid) => !cd.free.includes(uid));
        return `<div class="candidate ${missing.length ? "partial" : ""} ${state.selectedCandidate === i ? "selected" : ""}" data-index="${i}">
          <span class="candidate-time">${cd.start}〜${cd.end}</span>
          <span class="candidate-len">${cd.minutes >= 60 ? `${cd.minutes / 60}時間` : `${cd.minutes}分`}</span>
          <span class="candidate-members">${missing.length
            ? `${cd.free.length}人参加可(不可: ${esc(missing.map(memberName).join("、"))})`
            : "全員参加可"}</span>
        </div>`;
      }).join("")}
    </div>`).join("");
  list.querySelector(".candidate.selected")?.scrollIntoView({ block: "nearest" });
}

/**
 * 空いている割合に応じた、俯瞰のセルの色
 * @param {number} free 空いている人数
 * @param {number} total 対象の人数
 * @returns {string} 色
 */
function heatColor(free, total) {
  if (total > 0 && free === total) return "var(--free)";
  if (free === 0) return "var(--busy-bg)";
  // 一部空き: 全員空き(緑)と見分けやすいよう黄色系にし、空いている人が多いほど濃くする
  const ratio = free / total;
  return `hsl(${48 - ratio * 10}, 95%, ${90 - ratio * 25}%)`;
}

/**
 * 期間の俯瞰(日付×時刻のヒートマップ)を表示する
 * @param {object} c 条件
 * @param {string[]} ids 対象メンバーのID
 */
function renderOverview(c, ids) {
  const box = $("overview");
  const days = visibleDays();
  const cols = buildColumns(c);
  if (days.length === 0) {
    box.innerHTML = `<p class="empty">表示する日がありません。</p>`;
    return;
  }
  const rows = days.map((day) => {
    const slotMap = new Map(FreeTime.computeDaySlots(day.date, ids, state.schedule.events, c, state.blockingKeys).map((s) => [s.start, s]));
    const cells = cols.map((col) => {
      if (col.lunch) return `<td class="hm-cell lunch"></td>`;
      const s = slotMap.get(col.start);
      const tip = `${formatDate(day.date)} ${FreeTime.toHHMM(col.start)}〜  空き ${s.free.length}/${ids.length}人` +
        (s.busy.length ? `\n不可: ${s.busy.map(memberName).join("、")}` : "");
      return `<td class="hm-cell" style="background:${heatColor(s.free.length, ids.length)}" data-tip="${esc(tip)}"></td>`;
    }).join("");
    const cls = `hm-row${day.date === state.selectedDate ? " selected" : ""}${day.holiday ? " holiday" : ""}`;
    return `<tr class="${cls}" data-date="${esc(day.date)}"><th class="hm-date">${esc(formatDate(day.date))}</th>${cells}</tr>`;
  }).join("");
  box.innerHTML = `<table class="hm-table"><thead><tr><th class="hm-date"></th>${hourHeads(cols)}</tr></thead><tbody>${rows}</tbody></table>`;
  // 選択中の行が見える位置までスクロールする
  box.querySelector(".hm-row.selected")?.scrollIntoView({ block: "nearest" });
}

/**
 * 選んだ日の詳細(タイムライン・この日の予定)を表示する
 * @param {object} c 条件
 * @param {string[]} ids 対象メンバーのID
 */
function renderDetail(c, ids) {
  const date = state.selectedDate;
  const days = visibleDays();
  const idx = days.findIndex((d) => d.date === date);
  $("prev-day-btn").disabled = idx <= 0;
  $("next-day-btn").disabled = idx < 0 || idx >= days.length - 1;
  if (!date || idx < 0) {
    $("detail-title").textContent = "日の詳細";
    $("timeline").innerHTML = `<p class="empty">表示する日がありません。</p>`;
    $("tab-day-events").innerHTML = "";
    return;
  }
  const day = days[idx];
  $("detail-title").textContent = `${formatDate(date)}${day.holiday ? "(休日)" : ""} の詳細`;

  const cols = buildColumns(c);
  const members = state.schedule.members;
  const slotMap = new Map(FreeTime.computeDaySlots(date, ids, state.schedule.events, c, state.blockingKeys).map((s) => [s.start, s]));
  const dayEvents = state.schedule.events.filter((ev) => ev.start_date <= date && ev.end_date >= date);
  const sel = state.selectedCandidate !== null ? state.candidates[state.selectedCandidate] : null;
  // 選んだ候補の時間帯の列に印を付ける
  const mark = (col) => (sel && FreeTime.toMinutes(sel.start) <= col.start && FreeTime.toMinutes(sel.end) >= col.end ? " in-cand" : "");

  // 空いている人数の行
  const freeRow = `<tr class="tl-free-row"><th class="tl-name">空き人数</th><td class="tl-allday"></td>${cols.map((col) => {
    if (col.lunch) return `<td class="tl-cell lunch"></td>`;
    const s = slotMap.get(col.start);
    const cls = s.free.length === ids.length ? "all-free" : s.free.length > 0 ? "some-free" : "none-free";
    return `<td class="tl-cell ${cls}${mark(col)}" data-tip="${esc(`${FreeTime.toHHMM(col.start)}〜 空き ${s.free.length}/${ids.length}人`)}">${s.free.length}</td>`;
  }).join("")}</tr>`;

  // メンバーごとの行(時刻なし予定はチップ、時刻あり予定は色の帯)
  const rows = members.map((m) => {
    const mine = dayEvents.filter((ev) => ev.uid === m.uid);
    const chips = mine.filter((ev) => ev.all_day).map((ev) => {
      const key = FreeTime.eventKey(ev);
      return `<span class="chip ${state.blockingKeys.has(key) ? "blocking" : ""}" style="background:${eventColor(ev)}"
        data-key="${esc(key)}" data-tip="${esc(eventTip(ev) + "\n(クリックで「埋まっている扱い」を切り替え)")}">${esc(ev.title || "(無題)")}</span>`;
    }).join("");
    const timed = mine.filter((ev) => !ev.all_day);
    const cells = cols.map((col) => {
      const hits = timed.filter((ev) => FreeTime.toMinutes(ev.start_time) < col.end && FreeTime.toMinutes(ev.end_time) > col.start);
      if (hits.length) {
        return `<td class="tl-cell busy${mark(col)}" style="background:${eventColor(hits[0])}" data-tip="${esc(hits.map(eventTip).join("\n\n"))}"></td>`;
      }
      return `<td class="tl-cell${col.lunch ? " lunch" : ""}${mark(col)}"></td>`;
    }).join("");
    return `<tr><th class="tl-name" title="${esc(m.name)}">${esc(m.name)}</th><td class="tl-allday">${chips}</td>${cells}</tr>`;
  }).join("");

  $("timeline").innerHTML = `<table class="tl-table">
    <thead><tr><th class="tl-name"></th><th class="tl-allday">終日</th>${hourHeads(cols)}</tr></thead>
    <tbody>${freeRow}${rows}</tbody></table>`;
  $("tab-day-events").innerHTML = eventTable(dayEvents, false);
}

/**
 * 予定の一覧表を作る
 * @param {object[]} events 予定
 * @param {boolean} withDate 日付の列を出すなら true
 * @returns {string} 表のHTML
 */
function eventTable(events, withDate) {
  if (events.length === 0) return `<p class="empty">予定がありません。</p>`;
  const order = new Map(state.schedule.members.map((m, i) => [m.uid, i]));
  const sorted = [...events].sort((a, b) =>
    (withDate ? a.start_date.localeCompare(b.start_date) : 0) || (order.get(a.uid) - order.get(b.uid)) ||
    (a.start_time || "").localeCompare(b.start_time || ""));
  return `<table class="ev-table">
    <thead><tr>${withDate ? `<th class="date-col">日付</th>` : ""}<th class="name-col">メンバー</th><th class="time-col">時刻</th><th>予定</th></tr></thead>
    <tbody>${sorted.map((ev) => `<tr>
      ${withDate ? `<td class="date-col">${esc(formatDate(ev.start_date))}${ev.end_date !== ev.start_date ? `〜${esc(formatDate(ev.end_date))}` : ""}</td>` : ""}
      <td class="name-col">${esc(memberName(ev.uid))}</td>
      <td class="time-col">${ev.all_day ? (ev.end_date !== ev.start_date ? "期間予定" : "時刻なし") : `${ev.start_time}〜${ev.end_time}`}</td>
      <td><span class="dot" style="background:${eventColor(ev)}"></span><span data-tip="${esc(eventTip(ev))}">${esc(ev.title || "(無題)")}</span></td>
    </tr>`).join("")}</tbody></table>`;
}

/** 全期間の予定一覧を表示する */
function renderAllEvents() {
  $("event-count").textContent = state.schedule.events.length;
  $("tab-all-events").innerHTML = eventTable(state.schedule.events, true);
}

// ======================================================================== 日の選択・タブ・ツールチップ

/**
 * 日を選んで詳細を表示する(全期間の予定を表示中なら、タイムラインに切り替える)
 * @param {string} date 日付
 * @param {number|null} candidateIndex 選んだ候補の番号(候補から選んだ場合)
 */
function selectDay(date, candidateIndex = null) {
  state.selectedDate = date;
  state.selectedCandidate = candidateIndex;
  if (document.querySelector(".tab.active")?.dataset.tab === "all-events") switchTab("timeline");
  renderAll();
}

/**
 * 前後の日に移動する
 * @param {number} delta -1 で前の日、1 で次の日
 */
function moveDay(delta) {
  const days = visibleDays();
  const next = days[days.findIndex((d) => d.date === state.selectedDate) + delta];
  if (next) selectDay(next.date);
}

/**
 * 詳細のタブを切り替える
 * @param {string} name タブの名前(timeline / day-events / all-events)
 */
function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${name}`));
}

/** data-tip を持つ要素にマウスを乗せたとき、ツールチップを表示する */
function setupTooltip() {
  const tip = $("tooltip");
  document.addEventListener("mouseover", (e) => {
    const el = e.target.closest("[data-tip]");
    if (!el) { tip.classList.add("hidden"); return; }
    tip.textContent = el.dataset.tip;
    tip.classList.remove("hidden");
  });
  document.addEventListener("mousemove", (e) => {
    if (tip.classList.contains("hidden")) return;
    const x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
    const y = e.clientY + 16 + tip.offsetHeight > window.innerHeight ? e.clientY - tip.offsetHeight - 10 : e.clientY + 16;
    tip.style.left = `${x}px`;
    tip.style.top = `${y}px`;
  });
}

// ======================================================================== 仕切り(俯瞰と詳細の高さ)

const RESIZER_STORAGE_KEY = "schedule_tool.overview_height";
// 俯瞰・詳細それぞれに最低限残す高さ(px)
const MIN_PANE_HEIGHT = 90;

/**
 * 俯瞰の高さを指定する(詳細と俯瞰がそれぞれ最低限の高さを保てる範囲に収める)
 * @param {number|null} height 高さ(px)。null なら中身に合わせた既定の高さに戻す
 */
function setOverviewHeight(height) {
  const overview = document.querySelector(".overview");
  if (height === null) {
    overview.style.height = "";
    overview.classList.remove("sized");
    return;
  }
  const right = document.querySelector(".right");
  const max = right.clientHeight - $("right-resizer").offsetHeight - MIN_PANE_HEIGHT;
  overview.style.height = `${Math.round(Math.max(MIN_PANE_HEIGHT, Math.min(height, max)))}px`;
  overview.classList.add("sized");
}

/** 俯瞰と詳細の間の仕切りを、ドラッグで上下に動かせるようにする */
function setupResizer() {
  const resizer = $("right-resizer");
  const overview = document.querySelector(".overview");

  // 前回の高さを復元する(ブラウザに覚えさせるのは高さだけ。使えない環境では既定の高さのまま)
  try {
    const saved = Number(localStorage.getItem(RESIZER_STORAGE_KEY));
    if (saved > 0) setOverviewHeight(saved);
  } catch (_) { /* 保存領域が使えない場合は何もしない */ }

  resizer.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    const startY = e.clientY;
    const startHeight = overview.getBoundingClientRect().height;
    resizer.setPointerCapture(e.pointerId);
    resizer.classList.add("dragging");
    document.body.classList.add("resizing");

    // ドラッグ中は、動かした分だけ俯瞰の高さを変える
    const onMove = (ev) => setOverviewHeight(startHeight + ev.clientY - startY);
    const onUp = () => {
      resizer.removeEventListener("pointermove", onMove);
      resizer.removeEventListener("pointerup", onUp);
      resizer.classList.remove("dragging");
      document.body.classList.remove("resizing");
      try { localStorage.setItem(RESIZER_STORAGE_KEY, String(overview.getBoundingClientRect().height)); } catch (_) { /* 無視 */ }
    };
    resizer.addEventListener("pointermove", onMove);
    resizer.addEventListener("pointerup", onUp);
  });

  // ダブルクリックで既定の高さに戻す
  resizer.addEventListener("dblclick", () => {
    setOverviewHeight(null);
    try { localStorage.removeItem(RESIZER_STORAGE_KEY); } catch (_) { /* 無視 */ }
  });

  // ウィンドウの大きさが変わったら、指定した高さが収まるように直す
  window.addEventListener("resize", () => {
    if (overview.classList.contains("sized")) setOverviewHeight(overview.getBoundingClientRect().height);
  });
}

// ======================================================================== 初期化

/** 画面を初期化する(設定・ログイン状態を読み込み、イベントを登録する) */
async function init() {
  setupTooltip();
  setupResizer();

  // 期間の初期値: 今日から2週間
  const today = new Date();
  const end = new Date(today);
  end.setDate(end.getDate() + 13);
  $("start-date").value = isoDate(today);
  $("end-date").value = isoDate(end);

  // ボタン・入力欄のイベント
  $("login-open-btn").addEventListener("click", openLogin);
  $("login-cancel-btn").addEventListener("click", closeLogin);
  $("login-form").addEventListener("submit", submitLogin);
  $("group-select").addEventListener("change", loadMembers);
  $("member-list").addEventListener("change", updateFetchButton);
  // 「全員」「解除」は見出し(summary)の中にあるため、折りたたみが切り替わらないようにする
  $("member-all-btn").addEventListener("click", (e) => { e.preventDefault(); setAllMembers(true); });
  $("member-none-btn").addEventListener("click", (e) => { e.preventDefault(); setAllMembers(false); });
  $("start-date").addEventListener("change", updateFetchButton);
  $("end-date").addEventListener("change", updateFetchButton);
  $("fetch-btn").addEventListener("click", fetchSchedule);
  $("prev-day-btn").addEventListener("click", () => moveDay(-1));
  $("next-day-btn").addEventListener("click", () => moveDay(1));
  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => switchTab(t.dataset.tab)));
  ["cond-business-start", "cond-business-end", "cond-lunch-start", "cond-lunch-end", "cond-slot",
    "cond-duration", "cond-required", "cond-exclude-holidays"].forEach((id) => $(id).addEventListener("change", renderAll));

  // 候補のクリック → その日・その時間帯を詳細に表示する(日付の見出しのクリックはその日を表示)
  $("candidate-list").addEventListener("click", (e) => {
    const item = e.target.closest(".candidate");
    if (item) {
      const i = Number(item.dataset.index);
      selectDay(state.candidates[i].date, i);
      return;
    }
    const head = e.target.closest("h3[data-date]");
    if (head) selectDay(head.dataset.date);
  });
  // 俯瞰の行のクリック → その日を詳細に表示する
  $("overview").addEventListener("click", (e) => {
    const row = e.target.closest(".hm-row");
    if (row) selectDay(row.dataset.date);
  });
  // 時刻なし予定のチップのクリックで「埋まっている扱い」を切り替える
  $("timeline").addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    const key = chip.dataset.key;
    if (state.blockingKeys.has(key)) state.blockingKeys.delete(key);
    else state.blockingKeys.add(key);
    renderAll();
  });
  // 左右の矢印キーで前後の日に移動する(入力欄にいる時・業務状況の画面では除く)
  document.addEventListener("keydown", (e) => {
    if (!state.schedule || state.mode !== "free" || e.target.closest("input, select, textarea")) return;
    if (e.key === "ArrowLeft") moveDay(-1);
    if (e.key === "ArrowRight") moveDay(1);
  });

  // 設定とログイン状態を読み込む(ログイン済みならマイグループを読み込む)
  state.config = await api("/api/config");
  // ラベルの保存・学習を使えるか(配布版では使えないので、関係するボタンを隠す)
  document.body.dataset.labeling = state.config.labeling_enabled ? "on" : "off";
  applyConfigToConditions();
  state.loggedIn = (await api("/api/login-status")).logged_in;
  updateLoginUi();
  if (state.loggedIn) await loadGroups();
  else openLogin();
}

init().catch((err) => showMessage("fetch-message", err.message, "error"));
