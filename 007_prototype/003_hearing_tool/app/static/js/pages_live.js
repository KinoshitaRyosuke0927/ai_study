/* ヒアリング管理ツールの画面：画面：当日の進行、本人向けの表示
 *
 * 元は app.js の一部。ファイルをまたいで関数と定数を共有するため、index.html での読み込み順を変えないこと。
 */

// ------------------------------------------------------------------ 画面：当日の進行

/** 画面を切り替えたときに止めるタイマー */
const timers = { live: null, poll: null };

/**
 * 秒を「分:秒」の文字列にする。
 * @param {number} sec 秒
 * @returns {string} 例 "12:05"
 */
function mmss(sec) {
  const s = Math.max(0, Math.floor(Number(sec) || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/**
 * ブラウザに保存した、進行のタイマーの状態を読む。
 * @param {string} sessionId 回のID
 * @returns {{startedAt: number|null, elapsedBefore: number}} 状態
 */
function loadTimer(sessionId) {
  try {
    const saved = JSON.parse(localStorage.getItem(`live_${sessionId}`) || "null");
    if (saved && typeof saved.elapsedBefore === "number") return saved;
  } catch (e) { /* 保存できない環境では毎回 0 から */ }
  return { startedAt: null, elapsedBefore: 0 };
}

/**
 * 進行のタイマーの状態をブラウザに保存する（画面を読み込み直しても続きから測れるように）。
 * @param {string} sessionId 回のID
 * @param {object} timer 状態
 * @returns {void}
 */
function saveTimer(sessionId, timer) {
  try { localStorage.setItem(`live_${sessionId}`, JSON.stringify(timer)); } catch (e) { /* 保存できなくても続ける */ }
}

/**
 * 経過時間（秒）を返す。
 * @param {object} timer タイマーの状態
 * @returns {number} 経過時間（秒）
 */
function elapsedSec(timer) {
  const running = timer.startedAt ? Date.now() - timer.startedAt : 0;
  return (timer.elapsedBefore + running) / 1000;
}

/**
 * 質問の目安の時間（分）を返す。
 * @param {object} q 質問の行
 * @returns {number} 目安の時間
 */
function estOf(q) {
  return q.est_min !== "" && q.est_min != null && !isNaN(Number(q.est_min)) ? Number(q.est_min) : (q.priority === "◎" ? 2 : 1);
}

/**
 * 当日の進行画面を表示する。
 * @param {HTMLElement} main 表示先
 * @param {string} sessionId 回のID
 * @returns {void}
 */
function renderLive(main, sessionId) {
  const session = find("sessions", sessionId);
  if (!session) { main.innerHTML = "<p>回が見つかりません。</p>"; return; }
  const person = find("persons", session.person_id) || { name: "（不明）" };
  const segments = byOrder(state.tables.segments.filter((s) => s.session_id === sessionId));
  const questionsOf = (segId) => byOrder(state.tables.questions.filter((q) => q.session_id === sessionId && q.segment_id === segId));
  const known = new Set(segments.map((g) => g.segment_id));
  const rest = byOrder(state.tables.questions.filter((q) => q.session_id === sessionId && !known.has(q.segment_id)));

  // 質問1件の表示
  const questionHtml = (q) => `
    <div class="live-q" data-q="${q.question_id}">
      <div class="live-q-head">
        <span class="prio">${h(q.priority)}</span>
        <span class="live-label">${h(q.label) || ""}</span>
        <span class="live-text">${h(q.text)}</span>
        <span class="skip-hint badge warn" hidden>省略候補</span>
        <div class="seg-buttons">${OPTIONS.asked.map((a) => (
          `<button type="button" data-asked="${a}" class="${q.asked === a ? "on" : ""}">${a}</button>`)).join("")}</div>
      </div>
      ${q.check_point ? `<div class="live-check">確認すること：${h(q.check_point)}${q.is_data_question === "1" ? ' <span class="badge accent">データ</span>' : ""}</div>` : ""}
      <textarea class="live-memo" placeholder="回答メモ（入力欄から離れると保存）">${h(q.answer_memo)}</textarea>
    </div>`;

  main.innerHTML = `
    <div class="live-bar">
      <div>
        <div class="live-title"><a href="#/session/${sessionId}">${h(person.name)} 第${h(session.round)}回</a>　当日の進行</div>
        <div class="live-now" id="live-now"></div>
      </div>
      <div class="live-clock"><span id="live-elapsed">0:00</span><small>／${h(session.duration_min || "-")}分</small></div>
      <div class="actions">
        <button class="primary" id="live-toggle">開始</button>
        <button id="live-reset">リセット</button>
        <button data-open-screen="${sessionId}">本人向けの表示を開く</button>
        <button id="live-finish">実施済みにする</button>
      </div>
    </div>
    <div class="notice" id="live-advice" hidden></div>
    ${segments.map((g) => `
      <div class="panel live-seg" data-seg="${g.segment_id}" data-start="${h(g.start_min)}" data-end="${h(g.end_min)}">
        <div class="panel-head">
          <h2>${h(g.start_min)}〜${h(g.end_min)}分　${h(g.title)}</h2>
          <span class="muted">${h(g.aim)}</span>
        </div>
        ${questionsOf(g.segment_id).map(questionHtml).join("") || '<p class="muted">質問はありません。</p>'}
      </div>`).join("")}
    ${rest.length ? `<div class="panel"><h2>区切りに入っていない質問</h2>${rest.map(questionHtml).join("")}</div>` : ""}
    <div class="panel"><h2>聞いていない◎の質問</h2><div id="live-left"></div></div>`;

  // タイマーの操作
  let timer = loadTimer(sessionId);
  const toggle = main.querySelector("#live-toggle");
  toggle.onclick = () => {
    if (timer.startedAt) timer = { startedAt: null, elapsedBefore: timer.elapsedBefore + Date.now() - timer.startedAt };
    else timer = { ...timer, startedAt: Date.now() };
    saveTimer(sessionId, timer);
    tick();
  };
  main.querySelector("#live-reset").onclick = async () => {
    if (!(await confirmDialog("経過時間を 0 に戻します。"))) return;
    timer = { startedAt: null, elapsedBefore: 0 };
    saveTimer(sessionId, timer);
    tick();
  };

  // 聞いたかどうかの切り替え（画面全体は描き直さず、その質問の表示だけを変える）
  main.querySelectorAll(".live-q").forEach((box) => {
    const id = box.dataset.q;
    box.querySelectorAll("[data-asked]").forEach((b) => {
      b.onclick = async () => {
        try {
          await api("PUT", `/api/tables/questions/${id}`, { values: { asked: b.dataset.asked } });
          find("questions", id).asked = b.dataset.asked;
          box.querySelectorAll("[data-asked]").forEach((x) => x.classList.toggle("on", x === b));
          tick();
        } catch (e) { toast(e.message, true); }
      };
    });
    // 回答メモは入力欄から離れたときに保存する
    box.querySelector(".live-memo").onchange = async (e) => {
      try {
        await api("PUT", `/api/tables/questions/${id}`, { values: { answer_memo: e.target.value } });
        find("questions", id).answer_memo = e.target.value;
        toast("メモを保存しました。");
      } catch (err) { toast(err.message, true); }
    };
  });

  // 実施済みにする（実施日が空なら今日の日付を入れる）
  main.querySelector("#live-finish").onclick = async () => {
    if (!(await confirmDialog("この回を「実施済み」にします。"))) return;
    const today = new Date();
    const ymd = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
    const values = { status: "実施済み" };
    if (!session.held_on) values.held_on = ymd;
    await api("PUT", `/api/tables/sessions/${sessionId}`, { values });
    await reload();
    toast("実施済みにしました。");
    location.hash = `#/session/${sessionId}`;
  };

  /**
   * 毎秒、経過時間、今の区切り、省略の候補を更新する。
   * @returns {void}
   */
  function tick() {
    const sec = elapsedSec(timer);
    const minute = sec / 60;
    main.querySelector("#live-elapsed").textContent = mmss(sec);
    toggle.textContent = timer.startedAt ? "一時停止" : (timer.elapsedBefore ? "再開" : "開始");

    // 今の区切りを決め、前後の区切りの見た目を変える
    let current = null;
    main.querySelectorAll(".live-seg").forEach((el) => {
      const start = Number(el.dataset.start), end = Number(el.dataset.end);
      const isNow = minute >= start && minute < end;
      el.classList.toggle("now", isNow);
      el.classList.toggle("past", minute >= end);
      if (isNow) current = el;
    });

    // 今の区切りの残り時間と、残っている◎の時間を比べる
    const advice = [];
    main.querySelectorAll(".skip-hint").forEach((x) => { x.hidden = true; });
    if (current) {
      const seg = find("segments", current.dataset.seg);
      const left = Number(current.dataset.end) - minute;
      const qs = questionsOf(current.dataset.seg);
      const mustLeft = qs.filter((q) => q.priority === "◎" && q.asked === "未").reduce((s, q) => s + estOf(q), 0);
      main.querySelector("#live-now").textContent = `今：${seg.title}（残り${mmss(left * 60)}）`;
      if (mustLeft > left) {
        advice.push(`この区切りの残り${mmss(left * 60)}に対し、聞いていない◎が約${mustLeft}分あります。○の質問は省略しましょう。`);
        qs.filter((q) => q.priority !== "◎" && q.asked === "未").forEach((q) => {
          const box = main.querySelector(`.live-q[data-q="${q.question_id}"] .skip-hint`);
          if (box) box.hidden = false;
        });
      }
    } else {
      main.querySelector("#live-now").textContent = sec ? "予定の時間を過ぎています。" : "「開始」を押すと時間を測ります。";
    }

    // 過ぎた区切りで聞いていない◎を知らせる
    const behind = segments.filter((g) => minute >= Number(g.end_min))
      .flatMap((g) => questionsOf(g.segment_id).filter((q) => q.priority === "◎" && q.asked === "未"));
    if (behind.length) advice.push(`過ぎた区切りに、聞いていない◎が${behind.length}件あります（${behind.map((q) => q.label || "番号なし").join("、")}）。`);
    const box = main.querySelector("#live-advice");
    box.hidden = !advice.length;
    box.innerHTML = advice.map((a) => `<div>${h(a)}</div>`).join("");

    // 聞いていない◎の一覧
    const left = state.tables.questions.filter((q) => q.session_id === sessionId && q.priority === "◎" && q.asked === "未");
    main.querySelector("#live-left").innerHTML = left.length
      ? `<ul>${byOrder(left).map((q) => `<li>${h(q.label ? q.label + "：" : "")}${h(q.text)}</li>`).join("")}</ul>`
      : '<p class="muted">すべて聞きました（または省略にしました）。</p>';
  }

  tick();
  timers.live = setInterval(tick, 1000);
}

// ------------------------------------------------------------------ 画面：本人向けの表示

/**
 * 本人向けの表示を、別のウィンドウで開く。
 * @param {string} sessionId 回のID
 * @returns {void}
 */
function openScreen(sessionId) {
  window.open(`/#/screen/${sessionId}`, `screen_${sessionId}`, "width=1100,height=800");
}

/**
 * 本人向けの表示を出す。聞き手用の情報は出さず、当日画面に出す要約だけを大きく表示する。
 * @param {HTMLElement} main 表示先
 * @param {string} sessionId 回のID
 * @returns {void}
 */
function renderScreen(main, sessionId) {
  const session = find("sessions", sessionId);
  main.innerHTML = session && session.screen_summary
    ? `<div class="screen-view"><pre>${h(session.screen_summary)}</pre></div>`
    : `<div class="screen-view"><p>表示する内容がありません。</p></div>`;
}

