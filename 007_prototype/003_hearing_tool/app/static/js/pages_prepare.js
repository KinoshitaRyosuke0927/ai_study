/* ヒアリング管理ツールの画面：画面：ホーム、対象者、回の準備
 *
 * 元は app.js の一部。ファイルをまたいで関数と定数を共有するため、index.html での読み込み順を変えないこと。
 */

// ------------------------------------------------------------------ 画面：ホーム

/**
 * ホーム画面を表示する。
 * @param {HTMLElement} main 表示先
 * @returns {Promise<void>}
 */
async function renderHome(main) {
  const home = await api("GET", "/api/home");

  // 次にやること
  const todos = home.todos.length ? `<ul>${home.todos.map((t) => {
    const link = t.session_id ? `#/session/${t.session_id}` : `#/person/${t.person_id}`;
    return `<li><span class="badge">${h(t.kind)}</span> <a href="${link}">${h(t.text)}</a></li>`;
  }).join("")}</ul>` : `<p class="muted">今のところありません。</p>`;

  // 対象者ごとのカード
  const cards = home.persons.map((p) => `
    <div class="panel">
      <div class="panel-head"><h2><a href="#/person/${p.person_id}">${h(p.name)}</a></h2></div>
      <div class="muted md-view">${renderMarkdown(p.role)}</div>
      <table>
        <tr><th>回</th><th>実施日</th><th>状態</th></tr>
        ${p.sessions.map((s) => `<tr>
          <td><a href="#/session/${s.session_id}">第${h(s.round)}回</a></td>
          <td>${h(s.held_on) || '<span class="muted">未定</span>'}</td><td>${badge(s.status)}</td></tr>`).join("")}
      </table>
      <div class="stats" style="margin-top:10px">
        <div class="stat"><b>${p.open_hypotheses}</b><span>未確認の仮説</span></div>
        <div class="stat"><b>${p.issues}</b><span>課題カード</span></div>
        <div class="stat"><b>${p.open_data_sources}</b><span>確認待ちのデータ</span></div>
      </div>
    </div>`).join("");

  main.innerHTML = `
    <h1>ホーム</h1>
    <p class="sub">対象者ごとの状況と、次にやることの一覧です。</p>
    <div class="panel"><h2>次にやること</h2>${todos}</div>
    <div class="panel-head"><h2>対象者</h2><button class="primary" id="add-person">対象者を追加</button></div>
    <div class="grid">${cards || '<p class="muted">対象者がいません。</p>'}</div>`;
  main.querySelector("#add-person").onclick = async () => { if (await editRow("persons", null)) route(); };
}

// ------------------------------------------------------------------ 画面：対象者

/**
 * 対象者の画面を表示する。
 * @param {HTMLElement} main 表示先
 * @param {string} personId 対象者のID
 * @returns {void}
 */
function renderPerson(main, personId) {
  const person = find("persons", personId);
  if (!person) { main.innerHTML = "<p>対象者が見つかりません。</p>"; return; }
  const sessions = state.tables.sessions.filter((s) => s.person_id === personId)
    .sort((a, b) => Number(a.round) - Number(b.round));
  const hyps = state.tables.hypotheses.filter((x) => x.person_id === personId)
    .sort((a, b) => a.label.localeCompare(b.label, "ja"));
  const issues = state.tables.issues.filter((x) => x.person_id === personId);
  const sources = state.tables.data_sources.filter((x) => x.person_id === personId);

  main.innerHTML = `
    <div class="panel-head">
      <div><h1>${h(person.name)}</h1><div class="sub md-view">${renderMarkdown(person.role)}</div></div>
      <div class="actions"><button id="edit-person">編集</button><button class="danger" id="del-person">削除</button></div>
    </div>
    ${person.note ? `<div class="info md-view">${renderMarkdown(person.note)}</div>` : ""}

    <div class="panel">
      <div class="panel-head"><h2>ヒアリングの回</h2><button class="primary" id="add-session">回を追加</button></div>
      <table><tr><th>回</th><th>実施日</th><th>状態</th><th>聞き手</th><th>質問</th><th>目的</th></tr>
      ${sessions.map((s) => {
        const qs = state.tables.questions.filter((q) => q.session_id === s.session_id);
        return `<tr><td class="nowrap"><a href="#/session/${s.session_id}">第${h(s.round)}回</a></td>
          <td class="nowrap">${h(s.held_on) || '<span class="muted">未定</span>'}</td><td>${badge(s.status)}</td>
          <td>${h(s.interviewers)}</td><td class="num">${qs.length}</td>
          <td class="muted">${h((s.purpose || "").slice(0, 60))}</td></tr>`;
      }).join("")}</table>
    </div>

    <div class="panel">
      <div class="panel-head"><h2>課題の仮説</h2><button class="primary" id="add-hyp">仮説を追加</button></div>
      <table><tr><th>表示名</th><th>見出し</th><th>立てた回</th><th>状態</th><th>公開範囲</th><th></th></tr>
      ${hyps.map((x) => `<tr><td class="nowrap">${h(x.label)}</td><td>${h(x.title)}</td>
        <td class="nowrap">${x.session_id ? `第${h((find("sessions", x.session_id) || {}).round)}回` : ""}</td>
        <td>${badge(x.status)}</td><td>${badge(x.visibility)}</td>
        <td><div class="actions"><button class="small" data-edit-hyp="${x.hypothesis_id}">編集</button>
        <button class="small danger" data-del-hyp="${x.hypothesis_id}">削除</button></div></td></tr>`).join("")}</table>
    </div>

    <div class="panel">
      <div class="panel-head"><h2>課題カード</h2><button class="primary" id="add-issue">課題を追加</button></div>
      ${issueTable(issues, false)}
    </div>

    <div class="panel">
      <div class="panel-head"><h2>データ台帳</h2><button class="primary" id="add-source">データを追加</button></div>
      ${sourceTable(sources, false)}
    </div>`;

  // ボタンの動き
  main.querySelector("#edit-person").onclick = async () => { if (await editRow("persons", person)) route(); };
  main.querySelector("#del-person").onclick = async () => { if (await deleteRow("persons", person)) location.hash = "#/"; };
  main.querySelector("#add-session").onclick = async () => {
    const nextRound = Math.max(0, ...sessions.map((s) => Number(s.round) || 0)) + 1;
    if (await editRow("sessions", null, { person_id: personId, round: String(nextRound), status: "準備中", duration_min: "30" })) route();
  };
  main.querySelector("#add-hyp").onclick = async () => {
    if (await editRow("hypotheses", null, { person_id: personId, status: "未確認", visibility: "聞き手のみ" })) route();
  };
  main.querySelector("#add-issue").onclick = async () => {
    if (await editRow("issues", null, { person_id: personId, status: "候補", visibility: "聞き手のみ" })) route();
  };
  main.querySelector("#add-source").onclick = async () => {
    if (await editRow("data_sources", null, { person_id: personId, confirmation: "本人の認識" })) route();
  };
  bindRowButtons(main, "hyp", "hypotheses");
  bindRowButtons(main, "issue", "issues");
  bindRowButtons(main, "source", "data_sources");
}

/**
 * 一覧の「編集」「削除」ボタンに動きを付ける。
 * @param {HTMLElement} root 一覧を含む要素
 * @param {string} prefix data 属性の名前（data-edit-<prefix>、data-del-<prefix>）
 * @param {string} table テーブル名
 * @param {string} [formKey] FORMS のキー
 * @returns {void}
 */
function bindRowButtons(root, prefix, table, formKey) {
  root.querySelectorAll(`[data-edit-${prefix}]`).forEach((b) => {
    b.onclick = async () => { if (await editRow(table, find(table, b.dataset[`edit${cap(prefix)}`]), {}, formKey)) route(); };
  });
  root.querySelectorAll(`[data-del-${prefix}]`).forEach((b) => {
    b.onclick = async () => { if (await deleteRow(table, find(table, b.dataset[`del${cap(prefix)}`]))) route(); };
  });
}

/**
 * 先頭の文字を大文字にする（data 属性の名前の変換に使う）。
 * @param {string} s 文字列
 * @returns {string} 変換した文字列
 */
function cap(s) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/**
 * 課題カードの表を作る。
 * @param {object[]} issues 課題カードの行
 * @param {boolean} withPerson 対象者の列を出すなら true
 * @returns {string} HTML
 */
function issueTable(issues, withPerson) {
  if (!issues.length) return '<p class="muted">まだありません。</p>';
  return `<table><tr>${withPerson ? "<th>対象者</th>" : ""}<th>課題</th><th>テーマ</th><th>状態</th><th>確度</th><th>頻度</th>
    <th>1回の時間</th><th>仮説</th><th>データ</th><th></th></tr>
    ${issues.map((x) => {
      const hypLabels = ids(x.hypothesis_ids).map((id) => (find("hypotheses", id) || {}).label).filter(Boolean).join("、");
      const srcCount = state.tables.data_sources.filter((d) => ids(d.issue_ids).includes(x.issue_id)).length;
      const solCount = state.tables.solutions.filter((s) => ids(s.issue_ids).includes(x.issue_id)).length;
      return `<tr>${withPerson ? `<td class="nowrap"><a href="#/person/${x.person_id}">${h((find("persons", x.person_id) || {}).name)}</a></td>` : ""}
        <td>${h(x.title)}${solCount ? ` <span class="badge accent" title="評価表と解決策の画面で確認できます">候補の手法 ${solCount}</span>` : ""}</td>
        <td class="nowrap">${h(x.theme)}</td><td>${badge(x.status)}</td><td class="nowrap">${h(x.certainty)}</td><td>${h(x.frequency)}</td><td>${h(x.time_per)}</td>
        <td class="nowrap">${h(hypLabels)}</td><td class="num">${srcCount || ""}</td>
        <td><div class="actions"><button class="small" data-edit-issue="${x.issue_id}">編集</button>
        <button class="small danger" data-del-issue="${x.issue_id}">削除</button></div></td></tr>`;
    }).join("")}</table>`;
}

/**
 * データ台帳の表を作る。
 * @param {object[]} sources データ台帳の行
 * @param {boolean} withPerson 対象者の列を出すなら true
 * @returns {string} HTML
 */
function sourceTable(sources, withPerson) {
  if (!sources.length) return '<p class="muted">まだありません。</p>';
  return `<table><tr>${withPerson ? "<th>対象者</th>" : ""}<th>データ</th><th>場所</th><th>形式</th><th>期間</th>
    <th>件数</th><th>利用の制限</th><th>確認</th><th></th></tr>
    ${sources.map((x) => `<tr>${withPerson ? `<td class="nowrap"><a href="#/person/${x.person_id}">${h((find("persons", x.person_id) || {}).name)}</a></td>` : ""}
      <td>${h(x.name)}</td><td>${h(x.location)}</td><td>${h(x.format)}</td><td>${h(x.period)}</td>
      <td>${h(x.volume)}</td><td class="md-view">${renderMarkdown(x.restriction)}</td><td>${badge(x.confirmation)}</td>
      <td><div class="actions"><button class="small" data-edit-source="${x.source_id}">編集</button>
      <button class="small danger" data-del-source="${x.source_id}">削除</button></div></td></tr>`).join("")}</table>`;
}

// ------------------------------------------------------------------ 画面：回の準備

/**
 * 回の準備画面を表示する。
 * @param {HTMLElement} main 表示先
 * @param {string} sessionId 回のID
 * @returns {Promise<void>}
 */
async function renderSession(main, sessionId) {
  const session = find("sessions", sessionId);
  if (!session) { main.innerHTML = "<p>回が見つかりません。</p>"; return; }
  const person = find("persons", session.person_id) || { name: "（不明）" };
  const analysis = await api("GET", `/api/sessions/${sessionId}/analysis`);
  const segments = byOrder(state.tables.segments.filter((s) => s.session_id === sessionId));
  const questions = state.tables.questions.filter((q) => q.session_id === sessionId);
  const utterances = state.tables.utterances.filter((u) => u.session_id === sessionId);
  const segStats = Object.fromEntries(analysis.segments.map((s) => [s.segment_id, s]));
  const t = analysis.totals;

  // 警告と引き継ぎの候補
  const warnings = analysis.warnings.length
    ? `<div class="notice"><b>時間配分の警告</b><ul>${analysis.warnings.map((w) => `<li>${h(w)}</li>`).join("")}</ul></div>` : "";
  const carry = analysis.carryover;
  const carryHtml = (carry.questions.length || carry.hypotheses.length) ? `
    <div class="panel">
      <h2>前回からの引き継ぎの候補</h2>
      ${carry.questions.length ? `<h3>前回聞いたことになっていない◎の質問</h3>
        <div class="checks" id="carry-questions">${carry.questions.map((q) => `<label>
          <input type="checkbox" value="${q.question_id}"> ${h(q.label ? q.label + "：" : "")}${h(q.text)}
          <span class="muted">（第${h(q.round)}回・${h(q.asked)}）</span></label>`).join("")}</div>
        <div class="actions" style="margin-top:8px">${segmentSelect("carry-segment", segments)}
          <button id="carry-add">選んだ質問をこの回に追加</button></div>` : ""}
      ${carry.hypotheses.length ? `<h3>この回でまだ扱っていない仮説</h3><ul>${carry.hypotheses.map((x) => (
        `<li>${h(x.label)}：${h(x.title)} ${badge(x.status)}</li>`)).join("")}</ul>
        <p class="hint muted">区切りか質問にひも付けると、候補から消えます。</p>` : ""}
    </div>` : "";

  // 区切りごとの質問
  const questionBlocks = segments.map((g) => {
    const st = segStats[g.segment_id] || {};
    const inSeg = byOrder(questions.filter((q) => q.segment_id === g.segment_id));
    const over = st.warnings && st.warnings.length;
    return `
      <div class="segment-head">
        <span class="title">${h(g.start_min)}〜${h(g.end_min)}分　${h(g.title)}</span>
        <span class="${over ? "warn-text" : "muted"}">◎${st.must_count ?? 0}件（${st.must_min ?? 0}分）／○${st.optional_count ?? 0}件
          ／区切り${st.length_min ?? 0}分
          <button class="small" data-add-q="${g.segment_id}">質問を追加</button></span>
      </div>
      ${questionTable(inSeg)}`;
  }).join("");
  const known = new Set(segments.map((g) => g.segment_id));
  const rest = byOrder(questions.filter((q) => !known.has(q.segment_id)));

  main.innerHTML = `
    <div class="panel-head">
      <div>
        <h1><a href="#/person/${session.person_id}">${h(person.name)}</a> 第${h(session.round)}回 ${badge(session.status)}</h1>
        <p class="sub">実施日：${h(session.held_on) || "未定"}　聞き手：${h(session.interviewers)}　予定：${h(session.duration_min)}分</p>
      </div>
      <div class="actions">
        <a class="button primary" href="#/live/${sessionId}">当日の進行</a>
        <a class="button" href="#/transcript/${sessionId}">文字起こしと推敲</a>
        <button id="edit-session">基本情報を編集</button>
        <button id="md-plan">進行資料を出力</button>
        <button class="danger" id="del-session">回を削除</button>
      </div>
    </div>
    ${session.purpose ? `<div class="info md-view">${renderMarkdown(session.purpose)}</div>` : ""}
    ${warnings}
    ${carryHtml}

    <div class="panel">
      <div class="panel-head"><h2>タイムテーブル</h2><button class="primary" id="add-segment">区切りを追加</button></div>
      <div class="stats">
        <div class="stat"><b>${t.planned_min}</b><span>分／予定${t.duration_min}分</span></div>
        <div class="stat"><b>${t.must_count}</b><span>件の◎（${t.must_min}分）</span></div>
        <div class="stat"><b>${t.optional_count}</b><span>件の○</span></div>
        <div class="stat"><b>${t.all_min}</b><span>分（すべての質問）</span></div>
      </div>
      <table><tr><th>時間</th><th>内容</th><th>狙い</th><th>仮説</th><th>◎</th><th>○</th><th>◎の時間</th><th></th></tr>
      ${segments.map((g) => {
        const st = segStats[g.segment_id] || {};
        const hyp = ids(g.hypothesis_ids).map((id) => (find("hypotheses", id) || {}).label).filter(Boolean).join("、");
        const over = st.warnings && st.warnings.length;
        return `<tr><td class="nowrap">${h(g.start_min)}〜${h(g.end_min)}分</td><td>${h(g.title)}</td>
          <td class="muted">${h(g.aim)}</td><td class="nowrap">${h(hyp)}</td>
          <td class="num">${st.must_count ?? 0}</td><td class="num">${st.optional_count ?? 0}</td>
          <td class="num ${over ? "warn-text" : ""}">${st.must_min ?? 0}／${st.length_min ?? 0}分</td>
          <td><div class="actions"><button class="small" data-edit-seg="${g.segment_id}">編集</button>
          <button class="small danger" data-del-seg="${g.segment_id}">削除</button></div></td></tr>`;
      }).join("")}</table>
    </div>

    <div class="panel">
      <div class="panel-head"><h2>質問</h2>
        <div class="actions"><button id="add-common">共通の質問から追加</button></div></div>
      <p class="hint muted">◎／○をクリックすると優先度を切り替えます。↑↓で区切りの中の順番を入れ替えます。</p>
      ${questionBlocks}
      ${rest.length ? `<div class="segment-head"><span class="title warn-text">区切りに入っていない質問</span></div>${questionTable(rest)}` : ""}
    </div>

    <div class="grid two">
      <div class="panel">
        <div class="panel-head"><h2>当日画面に出す要約</h2>
          <div class="actions"><button class="small" data-edit-field="screen_summary">編集</button>
          <button class="small" id="md-summary">出力</button>
          <button class="small" data-open-screen="${sessionId}">本人向けの表示を開く</button></div></div>
        <p class="hint muted">対象者に見せる内容です。聞き手用のメモや仮説を書かないでください。</p>
        <pre class="md">${h(session.screen_summary) || "（未入力）"}</pre>
      </div>
      <div class="panel">
        <div class="panel-head"><h2>事前の依頼文</h2>
          <div class="actions"><button class="small" data-edit-field="request_message">編集</button>
          <button class="small" id="md-request">出力</button></div></div>
        <p class="hint muted">対象者に送る内容です。</p>
        <pre class="md">${h(session.request_message) || "（未入力）"}</pre>
      </div>
    </div>

    <div class="panel">
      <div class="panel-head"><h2>聞き手用のメモ</h2><button class="small" data-edit-field="memo">編集</button></div>
      ${session.memo ? `<div class="md-view md-box">${renderMarkdown(session.memo)}</div>` : '<p class="muted">（未入力）</p>'}
    </div>

    <div class="panel">
      <div class="panel-head"><h2>文字起こし</h2><a class="button" href="#/transcript/${sessionId}">文字起こしと推敲を開く</a></div>
      <div class="stats">
        <div class="stat"><b>${utterances.length}</b><span>件の発言</span></div>
        <div class="stat"><b>${utterances.filter((u) => u.review_status !== "推敲済み").length}</b><span>件が未推敲</span></div>
        <div class="stat"><span>音声：${h(session.audio_file) || "未設定"}</span></div>
      </div>
    </div>`;

  // 基本情報、出力、削除
  main.querySelector("#edit-session").onclick = async () => { if (await editRow("sessions", session)) route(); };
  main.querySelector("#md-plan").onclick = () => showMarkdown("進行資料（聞き手用）", "plan", [sessionId]);
  main.querySelector("#md-summary").onclick = () => showMarkdown("当日画面に出す要約", "summary", [sessionId]);
  main.querySelector("#md-request").onclick = () => showMarkdown("事前の依頼文", "request", [sessionId]);
  main.querySelector("#del-session").onclick = async () => {
    if (await deleteRow("sessions", session, "\nこの回の区切り、質問、文字起こしもあわせて削除します。")) location.hash = `#/person/${session.person_id}`;
  };

  // 要約、依頼文、メモを1項目だけ編集する
  main.querySelectorAll("[data-edit-field]").forEach((b) => {
    b.onclick = async () => {
      const key = b.dataset.editField;
      const field = FORMS.sessions.find((f) => f.key === key);
      FORMS._single = [field];
      if (await editRow("sessions", session, {}, "_single")) route();
    };
  });

  // 区切りの追加、編集、削除
  main.querySelector("#add-segment").onclick = async () => {
    const last = segments[segments.length - 1];
    const defaults = { session_id: sessionId, order: String(segments.length + 1), start_min: last ? last.end_min : "0" };
    if (await editRow("segments", null, defaults)) route();
  };
  bindRowButtons(main, "seg", "segments");

  // 質問の追加、編集、削除、優先度の切り替え、並べ替え
  main.querySelectorAll("[data-add-q]").forEach((b) => {
    b.onclick = async () => {
      const segId = b.dataset.addQ;
      const count = questions.filter((q) => q.segment_id === segId).length;
      const seg = find("segments", segId) || {};
      const defaults = { session_id: sessionId, segment_id: segId, order: String(count + 1), priority: "○",
        asked: "未", hypothesis_ids: seg.hypothesis_ids || "" };
      if (await editRow("questions", null, defaults)) route();
    };
  });
  bindQuestionButtons(main, questions);

  // 共通の質問から追加
  main.querySelector("#add-common").onclick = () => addFromCommon(sessionId, segments);

  // 前回の質問の引き継ぎ
  const carryButton = main.querySelector("#carry-add");
  if (carryButton) {
    carryButton.onclick = async () => {
      const chosen = [...main.querySelectorAll("#carry-questions input:checked")].map((c) => c.value);
      if (!chosen.length) { toast("質問を選んでください。", true); return; }
      await api("POST", `/api/sessions/${sessionId}/copy-questions`,
        { question_ids: chosen, segment_id: main.querySelector("#carry-segment").value });
      await reload();
      toast(`${chosen.length}件の質問を追加しました。`);
      route();
    };
  }
}

/**
 * 区切りを選ぶプルダウンを作る。
 * @param {string} id 要素のID
 * @param {object[]} segments 区切りの一覧
 * @returns {string} HTML
 */
function segmentSelect(id, segments) {
  return `<select id="${id}"><option value="">（区切りなし）</option>${segments.map((g) => (
    `<option value="${g.segment_id}">${h(g.start_min)}〜${h(g.end_min)}分 ${h(g.title)}</option>`)).join("")}</select>`;
}

/**
 * 質問の表を作る。
 * @param {object[]} rows 質問の行（並べ替え済み）
 * @returns {string} HTML
 */
function questionTable(rows) {
  if (!rows.length) return '<p class="muted">質問がありません。</p>';
  return `<table><tr><th></th><th>No.</th><th>質問</th><th>確認すること</th><th>目安</th><th>聞いた</th><th></th></tr>
    ${rows.map((q, i) => `<tr class="${q.asked === "省略" ? "dim" : ""}">
      <td><span class="prio" data-prio="${q.question_id}" title="クリックで切り替え">${h(q.priority || "○")}</span></td>
      <td class="nowrap">${h(q.label) || "-"}</td>
      <td class="pre">${h(q.text)}${q.answer_memo ? `<div class="muted md-view">メモ：${renderMarkdown(q.answer_memo)}</div>` : ""}</td>
      <td>${q.is_data_question === "1" ? '<span class="badge accent">データ</span> ' : ""}${h(q.check_point)}</td>
      <td class="num">${q.est_min ? h(q.est_min) + "分" : '<span class="muted">' + (q.priority === "◎" ? 2 : 1) + "分</span>"}</td>
      <td>${badge(q.asked)}</td>
      <td><div class="actions">
        <button class="icon" data-move="${q.question_id}" data-dir="-1" ${i === 0 ? "disabled" : ""}>↑</button>
        <button class="icon" data-move="${q.question_id}" data-dir="1" ${i === rows.length - 1 ? "disabled" : ""}>↓</button>
        <button class="small" data-edit-q="${q.question_id}">編集</button>
        <button class="small danger" data-del-q="${q.question_id}">削除</button></div></td></tr>`).join("")}</table>`;
}

/**
 * 質問の表のボタンに動きを付ける。
 * @param {HTMLElement} root 表を含む要素
 * @param {object[]} questions この回の質問
 * @returns {void}
 */
function bindQuestionButtons(root, questions) {
  bindRowButtons(root, "q", "questions");

  // 優先度の切り替え
  root.querySelectorAll("[data-prio]").forEach((el) => {
    el.onclick = async () => {
      const q = find("questions", el.dataset.prio);
      await api("PUT", `/api/tables/questions/${q.question_id}`, { values: { priority: q.priority === "◎" ? "○" : "◎" } });
      await reload();
      route();
    };
  });

  // 区切りの中での並べ替え（順番を振り直してから隣と入れ替える）
  root.querySelectorAll("[data-move]").forEach((b) => {
    b.onclick = async () => {
      const q = find("questions", b.dataset.move);
      const list = byOrder(questions.filter((x) => x.segment_id === q.segment_id));
      const i = list.findIndex((x) => x.question_id === q.question_id);
      const j = i + Number(b.dataset.dir);
      if (j < 0 || j >= list.length) return;
      [list[i], list[j]] = [list[j], list[i]];
      // 順番が変わる行だけを保存する
      for (const [k, row] of list.entries()) {
        if (row.order !== String(k + 1)) {
          await api("PUT", `/api/tables/questions/${row.question_id}`, { values: { order: String(k + 1) } });
        }
      }
      await reload();
      route();
    };
  });
}

/**
 * 共通の質問を選んで、回に追加する。
 * @param {string} sessionId 回のID
 * @param {object[]} segments この回の区切り
 * @returns {Promise<void>}
 */
async function addFromCommon(sessionId, segments) {
  const common = byOrder(state.tables.questions.filter((q) => !q.session_id));
  if (!common.length) { toast("共通の質問がありません。「共通の質問」の画面で追加してください。", true); return; }
  const html = `
    <div class="field"><label class="name">追加する区切り</label>${segmentSelect("common-segment", segments)}</div>
    <div class="checks" style="max-height:340px">${common.map((q) => `<label>
      <input type="checkbox" value="${q.question_id}"> ${h(q.priority)} ${h(q.text)}</label>`).join("")}</div>`;
  let segmentId = "";
  let chosen = [];
  const result = await openDialog("共通の質問から追加", html, [
    { label: "やめる", value: "cancel" }, { label: "追加", value: "add", primary: true },
  ], (body) => {
    // ダイアログが閉じる前に選択を控えておく
    body.addEventListener("change", () => {
      segmentId = body.querySelector("#common-segment").value;
      chosen = [...body.querySelectorAll(".checks input:checked")].map((c) => c.value);
    });
  });
  if (result !== "add" || !chosen.length) return;
  await api("POST", `/api/sessions/${sessionId}/copy-questions`, { question_ids: chosen, segment_id: segmentId });
  await reload();
  toast(`${chosen.length}件の質問を追加しました。`);
  route();
}

