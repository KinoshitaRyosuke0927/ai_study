/* ヒアリング管理ツールの画面：画面：課題カード、データ台帳、共通の質問、用語集、入出力と設定
 *
 * 元は app.js の一部。ファイルをまたいで関数と定数を共有するため、index.html での読み込み順を変えないこと。
 */

// ------------------------------------------------------------------ 画面：一覧

/**
 * 対象者で絞り込むプルダウンを作る。
 * @param {string} id 要素のID
 * @param {string} value 選んでいる対象者のID
 * @returns {string} HTML
 */
function personFilter(id, value) {
  return `<select id="${id}"><option value="">すべての対象者</option>${state.tables.persons.map((p) => (
    `<option value="${p.person_id}" ${p.person_id === value ? "selected" : ""}>${h(p.name)}</option>`)).join("")}</select>`;
}

/**
 * 選択肢で絞り込むプルダウンを作る。
 * @param {string} id 要素のID
 * @param {string} allLabel 「すべて」の表示
 * @param {string[]} options 選択肢
 * @param {string} value 選んでいる値
 * @returns {string} HTML
 */
function optionFilter(id, allLabel, options, value) {
  return `<select id="${id}"><option value="">${h(allLabel)}</option>${options.map((o) => (
    `<option ${o === value ? "selected" : ""}>${h(o)}</option>`)).join("")}</select>`;
}

/** 一覧画面の絞り込みの状態 */
const filters = { issuePerson: "", issueStatus: "", sourcePerson: "", sourceConfirm: "", termCategory: "", termText: "" };

/**
 * 課題カードの一覧を表示する。
 * @param {HTMLElement} main 表示先
 * @returns {void}
 */
function renderIssues(main) {
  const rows = state.tables.issues.filter((x) => (
    (!filters.issuePerson || x.person_id === filters.issuePerson) && (!filters.issueStatus || x.status === filters.issueStatus)));
  main.innerHTML = `
    <h1>課題カード</h1>
    <p class="sub">ヒアリングで見えた課題を、記録シートの項目で整理します。</p>
    <div class="panel">
      <div class="panel-head">
        <div class="filters">${personFilter("f-person", filters.issuePerson)}
          ${optionFilter("f-status", "すべての状態", OPTIONS.issueStatus, filters.issueStatus)}
          <span class="muted">${rows.length}件</span></div>
        <button class="primary" id="add-issue">課題を追加</button>
      </div>
      ${issueTable(rows, true)}
    </div>`;
  main.querySelector("#f-person").onchange = (e) => { filters.issuePerson = e.target.value; route(); };
  main.querySelector("#f-status").onchange = (e) => { filters.issueStatus = e.target.value; route(); };
  main.querySelector("#add-issue").onclick = async () => {
    if (await editRow("issues", null, { person_id: filters.issuePerson, status: "候補", visibility: "聞き手のみ" })) route();
  };
  bindRowButtons(main, "issue", "issues");
}

/**
 * データ台帳の一覧を表示する。
 * @param {HTMLElement} main 表示先
 * @returns {void}
 */
function renderSources(main) {
  const rows = state.tables.data_sources.filter((x) => (
    (!filters.sourcePerson || x.person_id === filters.sourcePerson) && (!filters.sourceConfirm || x.confirmation === filters.sourceConfirm)));
  main.innerHTML = `
    <h1>データ台帳</h1>
    <p class="sub">機械学習に使えそうなデータの場所、形式、量を記録します。聞き手が見られないデータは「本人の認識」として記録します。</p>
    <div class="panel">
      <div class="panel-head">
        <div class="filters">${personFilter("f-person", filters.sourcePerson)}
          ${optionFilter("f-confirm", "すべての確認状態", OPTIONS.confirmation, filters.sourceConfirm)}
          <span class="muted">${rows.length}件</span></div>
        <button class="primary" id="add-source">データを追加</button>
      </div>
      ${sourceTable(rows, true)}
    </div>`;
  main.querySelector("#f-person").onchange = (e) => { filters.sourcePerson = e.target.value; route(); };
  main.querySelector("#f-confirm").onchange = (e) => { filters.sourceConfirm = e.target.value; route(); };
  main.querySelector("#add-source").onclick = async () => {
    if (await editRow("data_sources", null, { person_id: filters.sourcePerson, confirmation: "本人の認識" })) route();
  };
  bindRowButtons(main, "source", "data_sources");
}

/**
 * 共通の質問の一覧を表示する。
 * @param {HTMLElement} main 表示先
 * @returns {void}
 */
function renderCommon(main) {
  const rows = byOrder(state.tables.questions.filter((q) => !q.session_id));
  main.innerHTML = `
    <h1>共通の質問</h1>
    <p class="sub">どの回にも追加できる質問の部品です。回の準備画面の「共通の質問から追加」で使います。</p>
    <div class="panel">
      <div class="panel-head"><span class="muted">${rows.length}件</span><button class="primary" id="add-common">質問を追加</button></div>
      ${rows.length ? `<table><tr><th></th><th>質問</th><th>確認すること</th><th>目安</th><th></th></tr>
      ${rows.map((q) => `<tr><td>${h(q.priority)}</td><td class="pre">${h(q.text)}</td>
        <td>${q.is_data_question === "1" ? '<span class="badge accent">データ</span> ' : ""}${h(q.check_point)}</td>
        <td class="num">${h(q.est_min)}</td>
        <td><div class="actions"><button class="small" data-edit-q="${q.question_id}">編集</button>
        <button class="small danger" data-del-q="${q.question_id}">削除</button></div></td></tr>`).join("")}</table>`
        : '<p class="muted">まだありません。</p>'}
    </div>`;
  main.querySelector("#add-common").onclick = async () => {
    if (await editRow("questions", null, { session_id: "", order: String(rows.length + 1), priority: "◎", asked: "未" }, "commonQuestions")) route();
  };
  bindRowButtons(main, "q", "questions", "commonQuestions");
}

/**
 * 用語集を表示する。
 * @param {HTMLElement} main 表示先
 * @returns {void}
 */
function renderTerms(main) {
  const word = filters.termText.trim();
  const rows = state.tables.terms.filter((x) => (
    (!filters.termCategory || x.category === filters.termCategory) &&
    (!word || [x.term, x.description, x.misrecognitions].some((v) => (v || "").includes(word)))));
  main.innerHTML = `
    <h1>用語集</h1>
    <p class="sub">人名やサービス名と、文字起こしで誤認識されやすい表記をまとめます。段階2の推敲で、誤認識の候補の表示に使います。</p>
    <div class="panel">
      <div class="panel-head">
        <div class="filters">${optionFilter("f-cat", "すべての分類", OPTIONS.termCategory, filters.termCategory)}
          <input type="search" id="f-text" placeholder="検索" value="${h(filters.termText)}">
          <span class="muted">${rows.length}件</span></div>
        <button class="primary" id="add-term">用語を追加</button>
      </div>
      <table><tr><th>用語</th><th>分類</th><th>説明</th><th>誤認識されやすい表記</th><th></th></tr>
      ${rows.map((x) => `<tr><td class="nowrap">${h(x.term)}</td><td class="nowrap">${h(x.category)}</td>
        <td>${h(x.description)}</td><td>${h(x.misrecognitions)}</td>
        <td><div class="actions"><button class="small" data-edit-term="${x.term_id}">編集</button>
        <button class="small danger" data-del-term="${x.term_id}">削除</button></div></td></tr>`).join("")}</table>
    </div>`;
  main.querySelector("#f-cat").onchange = (e) => { filters.termCategory = e.target.value; route(); };
  const search = main.querySelector("#f-text");
  search.onchange = (e) => { filters.termText = e.target.value; route(); };
  main.querySelector("#add-term").onclick = async () => { if (await editRow("terms", null, { category: "その他" })) route(); };
  bindRowButtons(main, "term", "terms");
}

// ------------------------------------------------------------------ 画面：入出力と設定

/**
 * 入出力と設定の画面を表示する。
 * @param {HTMLElement} main 表示先
 * @returns {void}
 */
function renderIo(main) {
  const rounds = [...new Set(state.tables.sessions.map((s) => s.round))].sort((a, b) => Number(a) - Number(b));
  main.innerHTML = `
    <h1>入出力と設定</h1>
    <p class="sub">資料の出力、ほかの聞き手とのデータの受け渡し、更新者の名前の設定を行います。</p>

    <div class="panel">
      <h2>Markdown の出力</h2>
      <p class="muted">同じ回の複数の対象者を、1つの進行資料にまとめて出力できます。要約と依頼文は、回の準備画面から1人ずつ出力します。</p>
      <div class="filters">
        <select id="io-round">${rounds.map((r) => `<option value="${h(r)}">第${h(r)}回</option>`).join("")}</select>
        <span id="io-sessions"></span>
        <button class="primary" id="io-plan">進行資料を出力</button>
      </div>
    </div>

    <div class="panel">
      <h2>データの書き出し</h2>
      <p class="muted">CSV を1つの ZIP にまとめます。ZIP は data/exports にも残ります。発言や個人の情報を含むので、渡す相手に注意してください。</p>
      <p class="muted">音声や動画は ZIP に含めません。ファイルを直接渡し、受け取った人は data/audio に置いてください。</p>
      <a class="button primary" href="/api/transfer/export">ZIP を書き出す</a>
    </div>

    <div class="panel">
      <h2>データの取り込み</h2>
      <p class="muted">ほかの聞き手が書き出した ZIP を取り込みます。同じ行は更新日時が新しいほうを残し、取り込む前に今のデータを data/backups に保存します。
        行の削除は取り込みでは反映されません。</p>
      <div class="filters"><input type="file" id="io-file" accept=".zip"><button id="io-preview">内容を確認</button></div>
      <div id="io-result"></div>
    </div>

    <div class="panel">
      <h2>設定</h2>
      <div class="filters">
        <label>更新者の名前 <input type="text" id="io-user" value="${h(state.settings.user_name)}"></label>
        <button id="io-save-user">保存</button>
      </div>
      <p class="muted">データの場所：${h(state.settings.data_path)}（設定ファイル：${h(state.settings.config_source)}）</p>
    </div>`;

  // 回を選んだら、その回の対象者を選べるようにする
  const showSessions = () => {
    const round = main.querySelector("#io-round").value;
    const sessions = state.tables.sessions.filter((s) => s.round === round);
    main.querySelector("#io-sessions").innerHTML = sessions.map((s) => (
      `<label><input type="checkbox" value="${s.session_id}" checked> ${h((find("persons", s.person_id) || {}).name)}</label>`)).join(" ");
  };
  if (rounds.length) {
    main.querySelector("#io-round").value = rounds[rounds.length - 1];
    showSessions();
  }
  main.querySelector("#io-round").onchange = showSessions;
  main.querySelector("#io-plan").onclick = () => {
    const chosen = [...main.querySelectorAll("#io-sessions input:checked")].map((c) => c.value);
    if (!chosen.length) { toast("対象者を選んでください。", true); return; }
    showMarkdown("進行資料（聞き手用）", "plan", chosen);
  };

  // 取り込む ZIP を確認する
  main.querySelector("#io-preview").onclick = async () => {
    const file = main.querySelector("#io-file").files[0];
    if (!file) { toast("ZIP を選んでください。", true); return; }
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/transfer/preview", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) { toast(data.detail || "確認に失敗しました。", true); return; }
    renderImportPreview(main.querySelector("#io-result"), data);
  };

  // 更新者の名前を保存する
  main.querySelector("#io-save-user").onclick = async () => {
    try {
      await api("PUT", "/api/settings", { user_name: main.querySelector("#io-user").value });
      await reload();
      toast("保存しました。");
    } catch (e) { toast(e.message, true); }
  };
}

/**
 * 取り込みの確認結果を表示し、実行できるようにする。
 * @param {HTMLElement} box 表示先
 * @param {object} data /api/transfer/preview の結果
 * @returns {void}
 */
function renderImportPreview(box, data) {
  const names = { ...TABLE_NAME, utterances: "文字起こしの発言", solutions: "解決策の候補", evaluations: "評価", criteria: "評価の観点" };
  const rows = Object.entries(data.tables);
  const updates = rows.flatMap(([table, r]) => r.update_examples.map((e) => ({ table, ...e })));
  box.innerHTML = `
    <h3>確認の結果</h3>
    <table><tr><th>データ</th><th>追加</th><th>上書き</th><th>そのまま（今のほうが新しいか同じ）</th></tr>
      ${rows.map(([table, r]) => `<tr><td>${h(names[table] || table)}</td><td class="num">${r.new}</td>
        <td class="num ${r.update ? "warn-text" : ""}">${r.update}</td><td class="num">${r.skip}</td></tr>`).join("")}
    </table>
    ${data.missing_audio.length ? `<div class="notice" style="margin-top:10px">次の音声ファイルが data/audio にありません。
      ファイルを受け取って置いてください（取り込みは置く前でも行えます）。<ul>${data.missing_audio.map((n) => (
        `<li>${h(n)}</li>`)).join("")}</ul></div>` : ""}
    ${updates.length ? `<h3>上書きされる行の例</h3><table><tr><th>データ</th><th>内容</th><th>今</th><th>取り込むほう</th></tr>
      ${updates.map((u) => `<tr><td>${h(names[u.table] || u.table)}</td><td>${h(u.label)}</td>
        <td>${h(u.local_by)}（${h(u.local_at)}）</td><td>${h(u.incoming_by)}（${h(u.incoming_at)}）</td></tr>`).join("")}</table>` : ""}
    <div class="actions" style="margin-top:10px"><button class="primary" id="io-apply">取り込む</button></div>`;
  box.querySelector("#io-apply").onclick = async () => {
    try {
      const result = await api("POST", "/api/transfer/apply", { token: data.token });
      await reload();
      box.innerHTML = `<div class="info">取り込みました。バックアップ：data/backups/${h(result.backup)}</div>`;
    } catch (e) { toast(e.message, true); }
  };
}

