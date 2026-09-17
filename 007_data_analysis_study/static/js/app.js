/* データサイエンス基礎ドリル - フロントエンド（ブラウザ内実行対応） */
"use strict";

const state = {
  course: null, lessons: [], progress: {}, lesson: null, code: {},
  pyodide: null, pyodidePromise: null,
};

const PYODIDE_BASE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));

/* ---------- 共通 ---------- */
async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" }, ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`APIエラー ${res.status}: ${text}`);
  }
  return res.json();
}

function esc(str) {
  return String(str ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

let toastTimer = null;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("on");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("on"), 2200);
}

function setRuntimeBadge(text) {
  [document.querySelector("#runtimeBadge"), document.querySelector("#headerRuntime")]
    .forEach((b) => {
      if (!b) return;
      b.textContent = text;
      b.classList.toggle("server", text !== "ブラウザ実行");
    });
}

/* ================= Pyodide（ブラウザ内実行） ================= */
async function ensurePyodide() {
  if (state.pyodide) return state.pyodide;
  if (state.pyodidePromise) return state.pyodidePromise;
  state.pyodidePromise = (async () => {
    try {
      if (!window.loadPyodide) {
        await new Promise((res, rej) => {
          const s = document.createElement("script");
          s.src = PYODIDE_BASE + "pyodide.js";
          s.onload = res; s.onerror = rej;
          document.head.appendChild(s);
        });
      }
      const py = await window.loadPyodide({ indexURL: PYODIDE_BASE });
      state.pyodide = py;
      setRuntimeBadge("ブラウザ実行");
      console.log("[pyodide] ready");
      return py;
    } catch (e) {
      console.warn("[pyodide] 読み込み失敗 → サーバー実行に切替", e);
      state.pyodide = null;
      state.pyodidePromise = null;
      setRuntimeBadge("サーバー実行");
      return null;
    }
  })();
  return state.pyodidePromise;
}

async function ensurePackages(py, drill) {
  const need = [];
  if ((drill.requires || []).includes("pandas") || (drill.data_files || []).length) need.push("pandas");
  if (drill.type === "viz") need.push("matplotlib");
  if (need.length) {
    toast("データ分析ライブラリを読み込み中…（初回のみ数秒）");
    await py.loadPackage([...new Set(need)]);
  }
}

async function preloadData(py, drill) {
  const files = drill.data_files || [];
  if (!files.length) return;
  const cwd = String(py.runPython("import os; os.getcwd()"));
  for (const f of files) {
    const r = await fetch("/data/" + f);
    if (!r.ok) throw new Error("データ取得失敗: " + f);
    const text = await r.text();
    py.FS.writeFile(cwd + "/" + f, text);
  }
}

function runInBrowser(py, code) {
  let out = "", err = "";
  py.setStdout({ batched: (s) => { out += s + "\n"; } });
  py.setStderr({ batched: (s) => { err += s + "\n"; } });
  const t0 = performance.now();
  try {
    py.runPython(code);
    return { ok: true, stdout: out, stderr: err, elapsed_ms: Math.round(performance.now() - t0) };
  } catch (e) {
    const msg = (e && e.message) ? String(e.message) : String(e);
    return { ok: false, stdout: out, stderr: err + msg + "\n", error: true,
             elapsed_ms: Math.round(performance.now() - t0) };
  }
}

function captureCharts(py) {
  try {
    const list = py.runPython(`
import io as _io, base64 as _b, matplotlib.pyplot as _plt
_ims = []
for _n in _plt.get_fignums():
    _bf = _io.BytesIO()
    _plt.figure(_n).savefig(_bf, format="png", bbox_inches="tight")
    _ims.append("data:image/png;base64," + _b.b64encode(_bf.getvalue()).decode())
_ims
`);
    const arr = (list && list.toJs) ? list.toJs() : (list || []);
    return Array.from(arr);
  } catch (e) {
    return [];
  }
}

function buildFullCodeLocal(starter, learnerCode) {
  return starter.replace("____", learnerCode);
}

async function prepBrowserRun(drill) {
  const py = await ensurePyodide();
  if (!py) return null;
  try {
    await ensurePackages(py, drill);
    await preloadData(py, drill);
    return py;
  } catch (e) {
    console.warn("[pyodide] 準備失敗 → サーバー実行に切替", e);
    return null;
  }
}

function currentDrill(drillId) {
  return (state.lesson && state.lesson.drills.find((d) => d.id === drillId)) || null;
}

/* ---------- データ取得 ---------- */
async function loadAll() {
  const [course, lessonsData, progress] = await Promise.all([
    api("/api/course"), api("/api/lessons"), api("/api/progress"),
  ]);
  state.course = course;
  state.lessons = lessonsData.lessons;
  state.progress = progress;
  renderSidebar();
  renderTopProgress(lessonsData.total_done, lessonsData.total_drills);
}

function refreshStats() {
  return api("/api/lessons").then((data) => {
    state.lessons = data.lessons;
    renderSidebar();
    renderTopProgress(data.total_done, data.total_drills);
    if (state.lesson && state.lesson.status === "open") renderLessonStats();
  }).catch((e) => console.error(e));
}

/* ---------- 目次 ---------- */
function chapterGroups() {
  const groups = [];
  const order = [];
  state.lessons.forEach((l) => { if (!order.includes(l.chapter)) order.push(l.chapter); });
  order.forEach((cn) => {
    groups.push({ chapter: cn, title: (state.lessons.find((l) => l.chapter === cn) || {}).chapter_title || "",
                  items: state.lessons.filter((l) => l.chapter === cn) });
  });
  return groups;
}

function renderSidebar() {
  const nav = $("#lessonNav");
  if (!nav) return;
  const current = state.lesson ? state.lesson.id : null;
  let html = "";
  chapterGroups().forEach((g) => {
    const open = g.items.filter((l) => l.status === "open");
    const doneCh = open.length && open.every((l) => l.drill_count && l.drill_done >= l.drill_count);
    const badge = doneCh ? '<span class="chapter-badge">完了</span>'
      : `<span class="chapter-badge">${open.filter((l) => l.drill_count && l.drill_done >= l.drill_count).length}/${open.length} 章達成</span>`;
    html += `<div class="side-nav-chapter"><div class="chapter-head">
      <span class="chapter-num">第${g.chapter}章</span><span>${esc(g.title)}</span>${badge}</div>`;
    g.items.forEach((l) => {
      if (l.status === "open") {
        let marks = "";
        for (let i = 0; i < l.drill_count; i++)
          marks += `<span class="mark-chip${i < l.drill_done ? " done" : ""}"></span>`;
        html += `<a class="lesson-link ${current === l.id ? "active" : ""}" href="#/lessons/${l.id}">
          <span class="l-num">${l.chapter}-${l.order}</span><span class="l-title">${esc(l.title)}</span>
          <span class="l-marks">${marks}</span></a>`;
      } else {
        html += `<a class="lesson-link locked" href="#/lessons/${l.id}"><span class="l-num">${l.chapter}-${l.order}</span>
          <span class="l-title">${esc(l.title)}</span><span class="soon">準備中</span></a>`;
      }
    });
    html += `</div>`;
  });
  html += `<div class="side-note">1ドリルは3〜5分。<br>解けたら目次の○が埋まります。<br>
    <span id="runtimeBadge" class="runtime-badge">サーバー実行</span>（コードはブラウザ内で動くこともあります）</div>`;
  nav.innerHTML = html;
  setRuntimeBadge(state.pyodide ? "ブラウザ実行" : "サーバー実行");
}

function renderTopProgress(done, total) {
  $("#courseProgressLabel").textContent = `${done}/${total} 問`;
  $("#courseProgressFill").style.width = (total ? Math.round((done / total) * 100) : 0) + "%";
}

/* ---------- トップ ---------- */
function renderOverview() {
  const c = state.course;
  const totalDrills = state.lessons.reduce((s, l) => s + l.drill_count, 0);
  const totalDone = state.lessons.reduce((s, l) => s + l.drill_done, 0);
  const chapterCards = chapterGroups().map((g) => {
    const open = g.items.filter((l) => l.status === "open");
    const drills = open.reduce((s, l) => s + l.drill_count, 0);
    const done = open.reduce((s, l) => s + l.drill_done, 0);
    const pct = drills ? Math.round((done / drills) * 100) : 0;
    const soon = open.length === 0
      ? `<span class="ch-meta">準備中</span>`
      : `<span class="ch-meta">${drills}問 / 約${open.reduce((s, l) => s + l.minutes, 0)}分</span>
         <div class="ch-prog"><div class="bar"><i style="width:${pct}%"></i></div><span>${done}/${drills} 問</span></div>`;
    return `<div class="chapter-card ${open.length === 0 ? "soon" : ""}">
      <div class="ch-top"><span class="ch-num">第${g.chapter}章</span><span class="ch-title">${esc(g.title)}</span></div>${soon}</div>`;
  }).join("");

  const first = state.lessons.find((l) => l.status === "open");
  const main = document.createElement("main");
  main.id = "main"; main.className = "main";
  main.innerHTML = `
    <section class="hero">
      <span class="kicker">ハンズオン ドリル式 入門コース</span>
      <h1>${esc(c.title)}</h1>
      <p class="sub">${esc(c.subtitle)}。${esc(c.target)}。<br>「読む」より「解く」。3〜5分のドリルを繰り返して、
      <strong>データサイエンティストの第一歩</strong>を固めます。約${Math.round(c.total_minutes / 60)}時間で完走を目指します。</p>
    </section>
    <div class="howto">
      <div class="step"><div class="s-no">STEP 1</div><h3>短い解説を読む</h3><p>要点だけ先に頭に入れます。</p></div>
      <div class="step"><div class="s-no">STEP 2</div><h3>ドリルを解く</h3><p>コードはブラウザ内 or サーバーで即実行。環境構築は不要です。</p></div>
      <div class="step"><div class="s-no">STEP 3</div><h3>答え合わせ</h3><p>赤ペン判定＋図の確認。間違えたらヒントで再挑戦。</p></div>
    </div>
    <h2 class="section-cap">カリキュラム <span class="cap-en">CURRICULUM</span></h2>
    <div class="chapter-grid">${chapterCards}</div>
    ${first ? `<a class="start-btn" href="#/lessons/${first.id}">ドリルを始める <span class="b-arrow">→</span></a>` : ""}`;
  swapMain(main);
}

/* ---------- レッスン ---------- */
function swapMain(el) {
  const old = $("#main");
  old.replaceWith(el);
  $("#tocToggle").setAttribute("aria-expanded", "false");
  document.body.classList.remove("toc-open");
}

async function renderLesson(lessonId) {
  const lesson = await api(`/api/lessons/${lessonId}`);
  state.lesson = lesson;
  state.code = {};
  renderSidebar();

  const main = document.createElement("main");
  main.id = "main"; main.className = "main";
  main.innerHTML = buildLessonHeader(lesson);
  if (lesson.status === "open") {
    main.insertAdjacentHTML("beforeend", buildContentBlocks(lesson));
    lesson.drills.forEach((d, i) => main.insertAdjacentHTML("beforeend", buildDrillHTML(d, i)));
    main.insertAdjacentHTML("beforeend", buildPager(lesson.id));
  } else {
    main.insertAdjacentHTML("beforeend", `<div class="locked-note"><strong>このレッスンは準備中です。</strong><br>
      実装済みの章から順に進めてください。</div>`);
  }
  swapMain(main);
  attachHandlers(lesson);
  $(".main").focus();
}

function buildLessonHeader(lesson) {
  const isOpen = lesson.status === "open";
  const drills = isOpen ? lesson.drills : [];
  const doneN = drills.filter((d) => state.progress[d.id]?.completed).length;
  const marks = drills.map((d) => {
    const p = state.progress[d.id];
    const cls = p?.completed ? "done" : (p && p.attempts > 0 ? "tried" : "");
    const sym = p?.completed ? "〇" : (p && p.attempts > 0 ? "✕" : "・");
    return `<span class="score-ring ${cls}">${sym}</span>`;
  }).join("");
  return `
    <section class="lesson-head">
      <div class="crumb">第${lesson.chapter}章　›　${esc(lesson.chapter_title)}</div>
      <h2 class="lesson-title">${esc(lesson.title)}</h2>
      <div class="lesson-meta">
        <span class="m">⏱ 約 ${lesson.minutes}分</span>
        <span class="m">✎ ドリル ${drills.length}問</span>
        ${isOpen ? `<span class="m">✔ 達成 ${doneN}/${drills.length}</span>` : ""}
      </div>
      ${isOpen ? `<div class="score-strip"><span class="ss-label">答え合わせ</span><span class="score-rings">${marks}</span></div>` : ""}
    </section>`;
}

function renderLessonStats() {
  const anchor = $("#main .lesson-head");
  if (!anchor || !state.lesson) return;
  const lesson = state.lesson;
  const doneN = lesson.drills.filter((d) => state.progress[d.id]?.completed).length;
  const marks = lesson.drills.map((d) => {
    const p = state.progress[d.id];
    const cls = p?.completed ? "done" : (p && p.attempts > 0 ? "tried" : "");
    const sym = p?.completed ? "〇" : (p && p.attempts > 0 ? "✕" : "・");
    return `<span class="score-ring ${cls}">${sym}</span>`;
  }).join("");
  const m = $$(".lesson-meta .m", anchor)[2];
  if (m) m.innerHTML = `✔ 達成 ${doneN}/${lesson.drills.length}`;
  const rings = $(".score-strip .score-rings", anchor);
  if (rings) rings.innerHTML = marks;
}

function buildContentBlocks(lesson) {
  const explain = (lesson.explanation || []).map((p) => `<p>${p}</p>`).join("");
  const keys = (lesson.keypoints || []).map((k) => `<li>${k}</li>`).join("");
  const example = lesson.example
    ? `<div class="code-card"><div class="cc-head"><span class="dot"><i></i><i></i><i></i></span>sample.py</div>
        <pre class="pre-code">${esc(lesson.example)}</pre></div>
       <div class="code-card"><div class="cc-head"><span class="dot"><i></i><i></i><i></i></span>実行結果</div>
        <pre class="pre-code pre-out">${esc(lesson.example_output)}</pre></div>` : "";
  return `
    <section class="block"><h3 class="b-title"><span class="b-tag">POINT</span> ここを押さえる</h3>${explain}</section>
    ${keys ? `<section class="block"><h3 class="b-title"><span class="b-tag">CHECK</span> キーポイント</h3><ul class="keypoints">${keys}</ul></section>` : ""}
    ${example ? `<section class="block"><h3 class="b-title"><span class="b-tag">SAMPLE</span> 動きを見る</h3><div class="code-pair">${example}</div></section>` : ""}`;
}

function buildDrillHTML(d, i) {
  const p = state.progress[d.id];
  const statusCls = p?.completed ? "done" : (p && p.attempts > 0 ? "tried" : "todo");
  const statusTxt = p?.completed ? "合格" : (p && p.attempts > 0 ? "再挑戦" : "未着手");
  const borderCls = p?.completed ? "done-border" : "";
  let body = "";

  if (d.type === "code_gap" || d.type === "viz") {
    const starter = state.code[d.id] ?? d.starter;
    const note = d.type === "viz"
      ? `<div class="viz-note">このドリルは「グラフを描く」ドリルです。実行して、下のコンソールに図が表示されるか確かめましょう。</div>` : "";
    body = `${note}
      <div class="hint" id="hint-${d.id}"><button type="button" class="hint-btn">ヒントを見る</button>
        <div class="hint-body">${esc(d.hint || "ヒントはまだありません。")}</div></div>
      <div class="editor">
        <div class="ed-bar"><span>main.py</span><span>Ctrl+Enter で採点</span></div>
        <textarea data-drill="${d.id}" spellcheck="false" autocomplete="off" autocapitalize="off">${esc(starter)}</textarea>
      </div>
      <div class="drill-actions">
        <button type="button" class="btn btn-ghost act-run" data-drill="${d.id}">▶ 実行する</button>
        <button type="button" class="btn btn-primary act-submit" data-drill="${d.id}">○ 採点する</button>
      </div>
      <div class="console" id="console-${d.id}" aria-live="polite"></div>
      <div class="feedback" id="fb-${d.id}" aria-live="polite"></div>`;
  } else if (d.type === "quiz") {
    body = `<div class="quiz-choices" id="quiz-${d.id}">
      <div class="quiz-choice-holder">
      ${d.choices.map((c, ci) =>
        `<button type="button" class="btn-quiz-choice" data-drill="${d.id}" data-answer="${ci}">
           <span class="choice-label">${String.fromCharCode(65 + ci)}</span>${esc(c)}
         </button>`).join("")}
      </div></div>
      <div class="feedback" id="fb-${d.id}" aria-live="polite"></div>`;
  } else if (d.type === "report") {
    body = `
      <div class="report-note">1)〜3) を1文ずつ書いて提出してください。提出した時点でこのドリルは「合格」になります。</div>
      <textarea class="report-ta" data-report="${d.id}" placeholder="${esc(d.placeholder || "")}" spellcheck="false"></textarea>
      <div class="drill-actions"><button type="button" class="btn btn-primary act-report" data-drill="${d.id}">提出する</button></div>
      <div class="feedback" id="fb-${d.id}" aria-live="polite"></div>`;
  }

  return `
    <section class="drill ${borderCls}" id="drill-${d.id}">
      <div class="drill-head">
        <span class="drill-no">ドリル ${i + 1}</span>
        <span class="drill-title">${esc(d.title)}</span>
        <span class="drill-status ${statusCls}" id="status-${d.id}">${statusTxt}</span>
      </div>
      <div class="drill-question">${renderQuestion(d.question)}</div>
      ${body}
    </section>`;
}

function renderQuestion(q) {
  const parts = String(q).split(/```/);
  return parts.map((part, idx) => {
    if (idx % 2 === 1) return `<pre><code>${esc(part.trim())}</code></pre>`;
    return part.split("\n").map((line) => {
      const t = line.trim();
      return t ? `<p>${esc(t)}</p>` : "";
    }).join("");
  }).join("");
}

function buildPager(lessonId) {
  const open = state.lessons.filter((l) => l.status === "open");
  const idx = open.findIndex((l) => l.id === lessonId);
  const prev = idx > 0 ? open[idx - 1] : null;
  const next = idx < open.length - 1 ? open[idx + 1] : null;
  return `<nav class="pager">
    ${prev ? `<a href="#/lessons/${prev.id}">← 前へ<br><small>${esc(prev.title)}</small></a>` : "<span></span>"}
    ${next ? `<a class="next" href="#/lessons/${next.id}">次へ →<br><small>${esc(next.title)}</small></a>` : ""}
  </nav>`;
}

/* ---------- ドリル操作 ---------- */
function attachHandlers(lesson) {
  const main = $("#main");
  main.addEventListener("click", async (e) => {
    const runBtn = e.target.closest(".act-run");
    const subBtn = e.target.closest(".act-submit");
    const repBtn = e.target.closest(".act-report");
    const hintBtn = e.target.closest(".hint-btn");
    const quizBtn = e.target.closest(".btn-quiz-choice");
    if (hintBtn) {
      const holder = hintBtn.closest(".hint");
      holder.classList.toggle("on");
      hintBtn.textContent = holder.classList.contains("on") ? "ヒントを閉じる" : "ヒントを見る";
      return;
    }
    if (runBtn) { const id = runBtn.dataset.drill; runBtn.disabled = true; await runDrill(lesson.id, id); runBtn.disabled = false; return; }
    if (subBtn) { const id = subBtn.dataset.drill; subBtn.disabled = true; await submitDrill(lesson.id, id); subBtn.disabled = false; return; }
    if (quizBtn) { const id = quizBtn.dataset.drill; quizBtn.disabled = true; await answerQuiz(lesson.id, id, Number(quizBtn.dataset.answer)); quizBtn.disabled = false; return; }
    if (repBtn) {
      const id = repBtn.dataset.drill;
      repBtn.disabled = true;
      await submitReport(lesson.id, id);
      repBtn.disabled = false;
    }
  });

  main.addEventListener("input", (e) => {
    if (e.target.matches("textarea[data-drill]")) state.code[e.target.dataset.drill] = e.target.value;
  });
  main.addEventListener("keydown", (e) => {
    const ta = e.target;
    if (!ta.matches || !ta.matches("textarea[data-drill]")) return;
    if (e.key === "Tab") {
      e.preventDefault();
      const { selectionStart: s, selectionEnd: en, value } = ta;
      const next = value.slice(0, s) + "    " + value.slice(en);
      ta.value = next;
      state.code[ta.dataset.drill] = next;
      ta.setSelectionRange(s + 4, s + 4);
    } else if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      const btn = $(`.act-submit[data-drill="${ta.dataset.drill}"]`);
      if (btn && !btn.disabled) btn.click();
    }
  });
}

function getCode(drillId) {
  const ta = $(`textarea[data-drill="${drillId}"]`);
  if (ta) { state.code[drillId] = ta.value; return ta.value; }
  return state.code[drillId] ?? "";
}

function renderConsole(drillId, res, charts = []) {
  const con = $(`#console-${drillId}`);
  if (!con) return;
  con.classList.add("on");
  const err = res.stderr || "";
  const t = res.elapsed_ms != null ? `　実行時間: ${res.elapsed_ms}ms` : "";
  let html = `<div class="con-bar"><span>▶ console</span><span style="margin-left:auto">${t}</span>
    ${res.runtime ? `<span style="color:#7CC7B0">${esc(res.runtime)}</span>` : ""}</div>`;
  if (res.stdout && res.stdout.length) html += `<pre>${esc(res.stdout)}</pre>`;
  if (err && err.length) html += `<pre class="err">${esc(err)}</pre>`;
  if (!res.stdout && !err) html += `<pre>（出力はありませんでした）</pre>`;
  if ((res.chart_url || charts.length) ) {
    html += `<div class="charts">${[...(res.chart_url ? [res.chart_url] : []), ...charts]
      .map((c, i) => `<figure><img src="${esc(c)}" alt="作成したグラフ"><figcaption>作成した図 ${i + 1}</figcaption></figure>`).join("")}</div>`;
  }
  con.innerHTML = html;
}

function renderFeedback(drillId, res) {
  const fb = $(`#fb-${drillId}`);
  const statusEl = $(`#status-${drillId}`);
  if (!fb || !statusEl) return;
  fb.className = `feedback on ${res.passed ? "pass" : "fail"}`;
  let html = `<div class="fb-verdict"><span class="stamp">${res.passed ? "正解" : "不合格"}</span> ${esc(res.message)}</div>`;
  if (res.kind === "mismatch") {
    html += `<div class="diff-grid">
      <div class="diff-box got"><div class="db-head">あなたの出力</div><pre>${esc(res.got || "(空)")}</pre></div>
      <div class="diff-box exp"><div class="db-head">期待される出力</div><pre>${esc(res.expected || "(空)")}</pre></div>
    </div>`;
  }
  if (res.kind === "error" && res.stderr) html += `<div class="inline-err">【エラーの内容】\n${esc(res.stderr)}</div>`;
  fb.innerHTML = html;
  statusEl.className = `drill-status ${res.passed ? "done" : "tried"}`;
  statusEl.textContent = res.passed ? "合格" : "再挑戦";
  if (res.passed) toast("正解！ドリルに○が付きました 🎉");
}

/* ---------- 実行・採点 ---------- */
async function runDrill(lessonId, drillId) {
  const drill = currentDrill(drillId);
  const code = getCode(drillId);
  try {
    const py = await prepBrowserRun(drill);
    if (py) {
      const res = runInBrowser(py, buildFullCodeLocal(drill.starter, code));
      const charts = drill.type === "viz" ? captureCharts(py) : [];
      renderConsole(drillId, { ...res, runtime: "ブラウザ実行" }, charts);
      return;
    }
  } catch (e) { console.warn(e); }
  const res = await api(`/api/lessons/${lessonId}/drills/${drillId}/run`, {
    method: "POST", body: JSON.stringify({ code }),
  });
  renderConsole(drillId, { ...res, runtime: "サーバー実行" });
}

async function submitDrill(lessonId, drillId) {
  const drill = currentDrill(drillId);
  const code = getCode(drillId);
  if (code.trim() === "" || !/\S/.test(code.replace(/_/g, ""))) {
    toast("空欄を埋めてから採点してください");
    return;
  }
  try {
    const py = await prepBrowserRun(drill);
    if (py) {
      const res = runInBrowser(py, buildFullCodeLocal(drill.starter, code));
      const charts = drill.type === "viz" ? captureCharts(py) : [];
      renderConsole(drillId, { ...res, runtime: "ブラウザ実行" }, charts);
      let grade;
      if (drill.type === "viz") {
        grade = await api(`/api/lessons/${lessonId}/drills/${drillId}/viz_check`, {
          method: "POST", body: JSON.stringify({ code, ran_ok: res.ok, chart_count: charts.length }),
        });
      } else {
        grade = await api(`/api/lessons/${lessonId}/drills/${drillId}/grade`, {
          method: "POST", body: JSON.stringify({ code, stdout: res.stdout }),
        });
      }
      renderFeedback(drillId, grade);
      await refreshStats();
      return;
    }
  } catch (e) { console.warn(e); }
  // フォールバック: サーバーで実行・採点
  const res = await api(`/api/lessons/${lessonId}/drills/${drillId}/submit`, {
    method: "POST", body: JSON.stringify({ code }),
  });
  renderConsole(drillId, { ...res, runtime: "サーバー実行" });
  renderFeedback(drillId, res);
  await refreshStats();
}

async function answerQuiz(lessonId, drillId, answer) {
  try {
    const res = await api(`/api/lessons/${lessonId}/drills/${drillId}/quiz`, {
      method: "POST", body: JSON.stringify({ answer_index: answer }),
    });
    const holder = $(`#quiz-${drillId}`);
    $$(".btn-quiz-choice", holder).forEach((b) => {
      const idx = Number(b.dataset.answer);
      b.classList.remove("correct", "wrong");
      if (idx === res.answer_index) b.classList.add(res.passed ? "correct" : "wrong");
      b.disabled = res.passed;
    });
    renderFeedback(drillId, { passed: res.passed, message: res.feedback, kind: "quiz" });
  } catch (err) { toast("回答の判定に失敗しました"); console.error(err); }
}

async function submitReport(lessonId, drillId) {
  const ta = $(`textarea[data-report="${drillId}"]`);
  const text = ta ? ta.value : "";
  if (!text.trim()) { toast("レポートを1行以上書いてください"); return; }
  try {
    const res = await api(`/api/lessons/${lessonId}/drills/${drillId}/report`, {
      method: "POST", body: JSON.stringify({ text }),
    });
    const fb = $(`#fb-${drillId}`);
    const statusEl = $(`#status-${drillId}`);
    fb.className = "feedback on pass";
    fb.innerHTML = `<div class="fb-verdict"><span class="stamp">提出</span> ${esc(res.message)}</div>`;
    statusEl.className = "drill-status done";
    statusEl.textContent = "合格";
    toast("提出しました 🎉");
    await refreshStats();
  } catch (err) { toast("提出に失敗しました"); console.error(err); }
}

/* ---------- ルーティング / 起動 ---------- */
function route() {
  const hash = location.hash || "#/";
  if (hash.startsWith("#/lessons/")) {
    const id = hash.slice("#/lessons/".length);
    renderLesson(id).catch((e) => { console.error(e); renderOverview(); });
  } else {
    renderOverview();
  }
}

async function boot() {
  $("#lessonNav").innerHTML = '<div class="skeleton" style="height:520px"></div>';
  $("#main").innerHTML = '<div class="skeleton" style="height:420px"></div>';
  await loadAll();
  window.addEventListener("hashchange", route);
  $("#tocToggle").addEventListener("click", () => {
    const open = document.body.classList.toggle("toc-open");
    $("#tocToggle").setAttribute("aria-expanded", open ? "true" : "false");
  });
  route();
}

document.addEventListener("DOMContentLoaded", boot);
