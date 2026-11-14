/* ヒアリング管理ツールの画面：ホームのロードマップ
 *
 * 横軸を日付にして、マイルストーン（roadmap.csv の kind が「マイルストーン」）と、
 * 予定（kind が「予定」の行と、実施日が入ったヒアリングの回）を表示する。
 * 横にスクロールでき、横軸の細かさ（日、週、月）を切り替えられる。
 * ファイルをまたいで関数と定数を共有するため、index.html での読み込み順を変えないこと。
 */

// ------------------------------------------------------------------ ロードマップ

/** 横軸の細かさ。px は1日あたりの幅 */
const ROADMAP_SCALES = {
  day: { label: "日", px: 32 },
  week: { label: "週", px: 10 },
  month: { label: "月", px: 3.5 },
};

/** 1行の高さ（px） */
const ROADMAP_ROW_H = 28;

/** 1日のミリ秒 */
const DAY_MS = 86400000;

/** 曜日の表記 */
const WEEKDAYS = ["日", "月", "火", "水", "木", "金", "土"];

/**
 * 横軸の細かさの選択を読み込む（選んだことがない、または保存できない環境では「日」にする）。
 * @returns {string} ROADMAP_SCALES のキー
 */
function loadRoadmapScale() {
  try {
    const saved = localStorage.getItem("roadmap_scale");
    return ROADMAP_SCALES[saved] ? saved : "day";
  } catch {
    return "day";
  }
}

/**
 * 横軸の細かさの選択を保存する。
 * @param {string} scale ROADMAP_SCALES のキー
 * @returns {void}
 */
function saveRoadmapScale(scale) {
  try { localStorage.setItem("roadmap_scale", scale); } catch { /* 保存できなくても表示は続ける */ }
}

/**
 * "YYYY-MM-DD" を、1970-01-01 からの日数にする。
 * @param {string} text 日付の文字列
 * @returns {number|null} 日数。日付として読めなければ null
 */
function dayNumber(text) {
  const m = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(String(text || "").trim());
  if (!m) return null;
  return Math.round(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])) / DAY_MS);
}

/**
 * 日数を日付に戻す（年、月、日、曜日を取り出すため UTC で扱う）。
 * @param {number} day 1970-01-01 からの日数
 * @returns {Date} 日付
 */
function dateOfDay(day) {
  return new Date(day * DAY_MS);
}

/**
 * 今日の日数を返す（PC の時計の日付）。
 * @returns {number} 1970-01-01 からの日数
 */
function todayNumber() {
  const now = new Date();
  return Math.round(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()) / DAY_MS);
}

/**
 * 日付を「2026-11-20（金）」の形にする。
 * @param {number} day 1970-01-01 からの日数
 * @returns {string} 表示用の文字列
 */
function dayLabel(day) {
  const d = dateOfDay(day);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}（${WEEKDAYS[d.getUTCDay()]}）`;
}

/**
 * 表示する項目を集める。roadmap.csv の行と、実施日が入ったヒアリングの回をまとめる。
 * @returns {object[]} 項目の一覧（lane、day、title、status と、元の行の record または session を持つ）
 *   表示の段の番号は、layoutRoadmapRows が row に入れる（record と名前を分けること）
 */
function collectRoadmapItems() {
  const items = [];

  // 手で登録したマイルストーンと予定
  for (const row of state.tables.roadmap || []) {
    const day = dayNumber(row.date);
    if (day === null) continue;
    items.push({
      lane: row.kind === "マイルストーン" ? "milestone" : "schedule",
      day, title: row.title, status: row.status || "予定",
      person: (find("persons", row.person_id) || {}).name || "", note: row.note, record: row,
    });
  }

  // ヒアリングの回（実施日が入っているものだけ。実施済みと整理済みは完了として表示する）
  for (const session of state.tables.sessions || []) {
    const day = dayNumber(session.held_on);
    if (day === null) continue;
    const person = (find("persons", session.person_id) || {}).name || "";
    items.push({
      lane: "schedule", day, title: `${person} 第${session.round}回ヒアリング`,
      status: session.status === "準備中" ? "予定" : "完了", person, note: "", session,
    });
  }
  return items.sort((a, b) => a.day - b.day);
}

/**
 * 名前の表示幅のおおよその値を返す（重ならないように段を分けるために使う）。
 * @param {string} text 名前
 * @returns {number} 幅（px）
 */
function roadmapLabelWidth(text) {
  let width = 0;
  for (const c of String(text || "")) width += c.charCodeAt(0) < 128 ? 7 : 12.5;
  return width + 26;
}

/**
 * 項目を、名前が重ならないように段に割り当てる。
 * @param {object[]} items 同じ段（レーン）の項目。日付順に並んでいること
 * @param {number} start 表示の最初の日数
 * @param {number} px 1日あたりの幅
 * @returns {number} 使った段の数（1以上）
 */
function layoutRoadmapRows(items, start, px) {
  const rowEnds = [];
  for (const item of items) {
    // 項目の左端と右端の位置を計算する
    item.x = (item.day - start) * px + px / 2;
    const right = item.x + roadmapLabelWidth(item.title);

    // 左から重ならない最初の段に入れる。なければ段を増やす
    let row = rowEnds.findIndex((end) => end < item.x - 6);
    if (row === -1) { row = rowEnds.length; rowEnds.push(0); }
    rowEnds[row] = right;
    item.row = row;
  }
  return Math.max(1, rowEnds.length);
}

/**
 * 表示する期間を決める。項目と今日が入るようにし、月の初めから月の終わりまでにそろえる。
 * @param {object[]} items 項目の一覧
 * @returns {{start: number, end: number}} 最初と最後の日数
 */
function roadmapRange(items) {
  // 項目と今日を含め、前後に余裕を持たせる
  const today = todayNumber();
  const days = [today, ...items.map((i) => i.day)];
  const first = Math.min(today - 30, Math.min(...days) - 14);
  const last = Math.max(today + 120, Math.max(...days) + 45);

  // 月の初めと月の終わりにそろえる
  const f = dateOfDay(first);
  const l = dateOfDay(last);
  const start = Math.round(Date.UTC(f.getUTCFullYear(), f.getUTCMonth(), 1) / DAY_MS);
  const end = Math.round(Date.UTC(l.getUTCFullYear(), l.getUTCMonth() + 1, 1) / DAY_MS) - 1;
  return { start, end };
}

/**
 * 横軸の目盛り（上段は月、下段は日または週）の HTML を作る。
 * @param {number} start 最初の日数
 * @param {number} end 最後の日数
 * @param {string} scale 横軸の細かさ
 * @returns {{head: string, grid: string}} 見出しの HTML と、縦線の HTML
 */
function roadmapAxisHtml(start, end, scale) {
  const px = ROADMAP_SCALES[scale].px;
  const months = [];
  const ticks = [];
  const grid = [];

  for (let day = start; day <= end; day++) {
    const d = dateOfDay(day);
    const x = (day - start) * px;

    // 月の初め：上段に月の名前を出し、太い縦線を引く
    if (d.getUTCDate() === 1) {
      const next = Math.round(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1) / DAY_MS);
      const width = (Math.min(next, end + 1) - day) * px;
      const label = scale === "month" ? `${d.getUTCFullYear()}/${d.getUTCMonth() + 1}` : `${d.getUTCFullYear()}年${d.getUTCMonth() + 1}月`;
      months.push(`<div class="rm-month" style="left:${x}px;width:${width}px">${label}</div>`);
      grid.push(`<div class="rm-line month" style="left:${x}px"></div>`);
    }

    // 日の表示：日ごとに日付を出し、土日に色を付ける
    if (scale === "day") {
      const weekend = d.getUTCDay() === 0 || d.getUTCDay() === 6;
      ticks.push(`<div class="rm-tick ${weekend ? "weekend" : ""}" style="left:${x}px;width:${px}px">${d.getUTCDate()}</div>`);
      if (weekend) grid.push(`<div class="rm-weekend" style="left:${x}px;width:${px}px"></div>`);
      else if (d.getUTCDate() !== 1) grid.push(`<div class="rm-line" style="left:${x}px"></div>`);
    }

    // 週の表示：月曜日ごとに日付を出す
    if (scale === "week" && d.getUTCDay() === 1) {
      ticks.push(`<div class="rm-tick" style="left:${x}px;width:${px * 7}px">${d.getUTCMonth() + 1}/${d.getUTCDate()}</div>`);
      if (d.getUTCDate() !== 1) grid.push(`<div class="rm-line" style="left:${x}px"></div>`);
    }
  }

  const tickRow = ticks.length ? `<div class="rm-ticks">${ticks.join("")}</div>` : "";
  return { head: `<div class="rm-months">${months.join("")}</div>${tickRow}`, grid: grid.join("") };
}

/**
 * 1つの項目の HTML を作る。
 * @param {object} item 項目
 * @param {number} index 項目の番号（押したときに項目を探すため）
 * @returns {string} HTML
 */
function roadmapItemHtml(item, index) {
  // 種類と状態に応じて見た目を変える
  const kind = item.lane === "milestone" ? "milestone" : item.session ? "session" : "schedule";
  const status = item.status === "完了" ? "done" : item.status === "中止" ? "cancel" : "";

  // マウスを乗せたときの説明
  const tip = [dayLabel(item.day), item.title, `状態：${item.status}`,
    item.person ? `対象者：${item.person}` : "", item.session ? "（ヒアリングの回。押すと回の画面を開きます）" : ""]
    .filter(Boolean).join("\n");
  return `<button type="button" class="rm-item ${kind} ${status}" data-rm-index="${index}"
    style="left:${item.x}px;top:${item.row * ROADMAP_ROW_H + 6}px" title="${h(tip)}">
    <span class="rm-mark"></span><span class="rm-label">${h(item.title)}</span></button>`;
}

/**
 * ロードマップを表示する。
 * @param {HTMLElement} box 表示先（ホームのパネル）
 * @param {boolean} [keepScroll] true なら今のスクロール位置を保つ。false なら今日が見える位置にする
 * @returns {void}
 */
function renderRoadmap(box, keepScroll = false) {
  const scale = loadRoadmapScale();
  const px = ROADMAP_SCALES[scale].px;
  const oldScroll = box.querySelector(".rm-scroll")?.scrollLeft ?? 0;

  // 項目を集め、表示する期間と段の割り当てを決める
  const items = collectRoadmapItems();
  const { start, end } = roadmapRange(items);
  const width = (end - start + 1) * px;
  const lanes = [
    { key: "milestone", label: "マイルストーン" },
    { key: "schedule", label: "予定" },
  ].map((lane) => {
    const laneItems = items.filter((i) => i.lane === lane.key);
    return { ...lane, items: laneItems, rows: layoutRoadmapRows(laneItems, start, px) };
  });

  // 目盛りと、今日の線
  const axis = roadmapAxisHtml(start, end, scale);
  const todayX = (todayNumber() - start) * px + px / 2;

  // レーンごとの HTML（左端の見出しは、横にスクロールしても残す）
  const lanesHtml = lanes.map((lane) => `
    <div class="rm-lane">
      <div class="rm-lane-name">${lane.label}</div>
      <div class="rm-lane-body" style="width:${width}px;height:${lane.rows * ROADMAP_ROW_H + 12}px">
        ${lane.items.map((item) => roadmapItemHtml(item, items.indexOf(item))).join("")}
      </div>
    </div>`).join("");

  box.innerHTML = `
    <div class="panel-head">
      <h2>ロードマップ</h2>
      <div class="actions">
        <span class="rm-scales">${Object.entries(ROADMAP_SCALES).map(([key, s]) => (
          `<button type="button" class="small ${key === scale ? "on" : ""}" data-rm-scale="${key}">${s.label}</button>`)).join("")}</span>
        <button type="button" class="small" id="rm-today">今日へ</button>
        <button type="button" class="primary" id="rm-add">項目を追加</button>
      </div>
    </div>
    <div class="rm-legend muted">
      <span><i class="rm-mark milestone"></i>マイルストーン</span>
      <span><i class="rm-mark schedule"></i>予定</span>
      <span><i class="rm-mark session"></i>ヒアリングの実施日から自動反映</span>
      <span>薄い表示は完了、取り消し線は中止。項目を押すと編集できます。</span>
    </div>
    <div class="rm-scroll">
      <div class="rm-canvas" style="width:${width + 120}px">
        <div class="rm-head"><div class="rm-lane-name"></div><div class="rm-head-body" style="width:${width}px">${axis.head}
          <div class="rm-today-label" style="left:${todayX}px">今日</div></div></div>
        <div class="rm-body">
          <div class="rm-grid" style="width:${width}px">${axis.grid}<div class="rm-today" style="left:${todayX}px"></div></div>
          ${lanesHtml}
        </div>
      </div>
    </div>
    ${items.length ? "" : '<p class="muted">項目がまだありません。「項目を追加」から、マイルストーンや予定を登録してください。</p>'}`;

  // スクロールの位置：前の位置を保つか、今日が左から3分の1あたりに来るようにする
  const scroller = box.querySelector(".rm-scroll");
  const scrollToToday = () => { scroller.scrollLeft = Math.max(0, todayX - scroller.clientWidth / 3); };
  if (keepScroll) scroller.scrollLeft = oldScroll; else scrollToToday();

  // 横軸の細かさの切り替え（切り替えた後も今日が見えるようにする）
  box.querySelectorAll("[data-rm-scale]").forEach((b) => {
    b.onclick = () => { saveRoadmapScale(b.dataset.rmScale); renderRoadmap(box); };
  });
  box.querySelector("#rm-today").onclick = scrollToToday;

  // 項目の追加
  box.querySelector("#rm-add").onclick = async () => {
    if (await editRoadmapItem(null)) renderRoadmap(box, true);
  };

  // 項目を押したとき：ヒアリングの回は回の画面を開き、それ以外は編集する
  box.querySelectorAll("[data-rm-index]").forEach((b) => {
    b.onclick = async () => {
      const item = items[Number(b.dataset.rmIndex)];
      if (item.session) { location.hash = `#/session/${item.session.session_id}`; return; }
      if (await editRoadmapItem(item.record)) renderRoadmap(box, true);
    };
  });
}

/**
 * ロードマップの項目を追加、編集、削除するダイアログを開く。
 * @param {object|null} row 編集する行。追加なら null
 * @returns {Promise<boolean>} 保存または削除したら true
 */
async function editRoadmapItem(row) {
  // 入力欄を作る（追加のときは、種類を「予定」、日付を今日にしておく）
  const fields = FORMS.roadmap;
  const current = row || { kind: "予定", status: "予定", date: dayLabel(todayNumber()).slice(0, 10) };
  const html = fields.map((f) => fieldHtml(f, current[f.key] ?? "", {})).join("") +
    (row ? `<p class="hint muted">最終更新：${h(row.updated_by)}（${h(row.updated_at)}）</p>` : "");

  // ダイアログを開く（編集のときだけ削除のボタンを出す）
  const buttons = [{ label: "やめる", value: "cancel" }];
  if (row) buttons.push({ label: "削除", value: "delete", danger: true });
  buttons.push({ label: "保存", value: "save", primary: true });
  const result = await openDialog(`${TABLE_NAME.roadmap}を${row ? "編集" : "追加"}`, html, buttons);

  // 削除：確認してから消す
  if (result === "delete") return deleteRow("roadmap", row);
  if (result !== "save") return false;

  // 保存：入力値を集めて書き込み、データを読み直す
  const values = collectValues(document.getElementById("dialog-body"), fields);
  try {
    if (row) await api("PUT", `/api/tables/roadmap/${row.item_id}`, { values });
    else await api("POST", "/api/tables/roadmap", { values });
    await reload();
    toast("保存しました。");
    return true;
  } catch (e) {
    toast(e.message, true);
    return false;
  }
}
