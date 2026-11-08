/* ヒアリング管理ツールの画面：画面：横断表示、評価表と解決策
 *
 * 元は app.js の一部。ファイルをまたいで関数と定数を共有するため、index.html での読み込み順を変えないこと。
 */

// ------------------------------------------------------------------ 画面：横断表示

/**
 * 課題の要点の表を作る。
 * @param {object[]} rows analysis の課題の要点
 * @returns {string} HTML
 */
function briefIssueTable(rows) {
  if (!rows.length) return '<p class="muted">ありません。</p>';
  return `<table><tr><th>対象者</th><th>課題</th><th>状態</th><th>確度</th><th>公開範囲</th><th></th></tr>
    ${rows.map((i) => `<tr><td class="nowrap"><a href="#/person/${i.person_id}">${h(i.person)}</a></td>
      <td>${h(i.title)}</td><td>${badge(i.status)}</td><td class="nowrap">${h(i.certainty)}</td><td>${badge(i.visibility)}</td>
      <td><div class="actions"><button class="small" data-edit-issue="${i.issue_id}">編集</button></div></td></tr>`).join("")}</table>`;
}

/**
 * 件数の一覧をバッジで表示する。
 * @param {object} counts 値ごとの件数
 * @returns {string} HTML
 */
function countBadges(counts) {
  const entries = Object.entries(counts || {});
  return entries.length ? entries.map(([k, v]) => `${badge(k)} ${v}`).join("　") : '<span class="muted">なし</span>';
}

/**
 * 横断表示の画面を表示する。
 * @param {HTMLElement} main 表示先
 * @returns {Promise<void>}
 */
async function renderOverview(main) {
  const ov = await api("GET", "/api/overview");
  main.innerHTML = `
    <h1>横断表示</h1>
    <p class="sub">対象者をまたいで、課題とデータの状況を見ます。状態が「見送り」の課題は除いています。</p>

    <div class="panel">
      <h2>対象者ごとの状況</h2>
      <table><tr><th>対象者</th><th>実施した回</th><th>仮説</th><th>課題カード</th><th>データ（確認済み／全体）</th></tr>
      ${ov.persons.map((p) => `<tr><td class="nowrap"><a href="#/person/${p.person_id}">${h(p.name)}</a></td>
        <td class="num">${p.held_sessions}／${p.sessions}</td><td>${countBadges(p.hypotheses)}</td>
        <td>${countBadges(p.issues)}</td><td class="num">${p.sources_confirmed}／${p.sources_total}</td></tr>`).join("")}</table>
    </div>

    <div class="panel">
      <h2>テーマごとの課題</h2>
      <p class="muted">課題カードの「テーマ」でまとめています。複数の人の課題があるテーマは、ほかのメンバーにも展開できる可能性があります。</p>
      ${ov.themes.map((t) => `
        <div class="segment-head"><span class="title">${h(t.theme)}</span>
          ${t.person_count >= 2 ? `<span class="badge ok">${t.person_count}人に共通</span>` : `<span class="muted">${t.person_count}人</span>`}</div>
        ${briefIssueTable(t.issues)}`).join("") || '<p class="muted">テーマが付いた課題はまだありません。</p>'}
      <div class="segment-head"><span class="title muted">テーマが未設定の課題（${ov.no_theme.length}件）</span></div>
      <p class="hint muted">「編集」でテーマを付けると、上のテーマごとの一覧に移ります。入力欄には、使ったことのあるテーマが候補として出ます。</p>
      ${briefIssueTable(ov.no_theme)}
    </div>

    <div class="panel">
      <h2>複数の人の課題にひも付く解決策の候補</h2>
      <p class="muted">同じ名前の手法が、複数の人の課題にひも付いているものです。</p>
      ${ov.shared_solutions.length ? `<table><tr><th>手法</th><th>対象者</th><th>課題</th></tr>
        ${ov.shared_solutions.map((s) => `<tr><td>${h(s.method)}</td><td class="nowrap">${h(s.persons.join("、"))}</td>
          <td>${s.issues.map((i) => `${h(i.title)}（${h(i.person)}）`).join("<br>")}</td></tr>`).join("")}</table>`
        : '<p class="muted">ありません。</p>'}
    </div>

    <div class="grid two">
      <div class="panel">
        <h2>データがひも付いていない課題（${ov.issues_without_data.length}件）</h2>
        <p class="hint muted">機械学習の検討には、データの有無の確認が必要です。</p>
        ${ov.issues_without_data.length ? `<table><tr><th>対象者</th><th>課題</th><th></th></tr>
          ${ov.issues_without_data.map((i) => `<tr><td class="nowrap">${h(i.person)}</td><td>${h(i.title)}</td>
            <td><div class="actions"><button class="small" data-add-source-for="${i.issue_id}" data-person="${i.person_id}">データを追加</button></div></td></tr>`).join("")}</table>`
          : '<p class="muted">ありません。</p>'}
      </div>
      <div class="panel">
        <h2>確認済みでないデータ（${ov.unconfirmed_sources.length}件）</h2>
        ${ov.unconfirmed_sources.length ? `<table><tr><th>対象者</th><th>データ</th><th>場所</th><th>確認</th><th></th></tr>
          ${ov.unconfirmed_sources.map((d) => `<tr><td class="nowrap">${h(d.person)}</td><td>${h(d.name)}</td><td>${h(d.location)}</td>
            <td>${badge(d.confirmation)}</td><td><div class="actions"><button class="small" data-edit-source="${d.source_id}">編集</button></div></td></tr>`).join("")}</table>`
          : '<p class="muted">ありません。</p>'}
      </div>
    </div>`;

  bindRowButtons(main, "issue", "issues");
  bindRowButtons(main, "source", "data_sources");
  main.querySelectorAll("[data-add-source-for]").forEach((b) => {
    b.onclick = async () => {
      const defaults = { person_id: b.dataset.person, issue_ids: b.dataset.addSourceFor, confirmation: "本人の認識" };
      if (await editRow("data_sources", null, defaults)) route();
    };
  });
}

// ------------------------------------------------------------------ 画面：評価表と解決策

/** 評価表の絞り込みの状態 */
const evalFilter = { person: "", showDropped: false };

/**
 * 評価表と解決策の画面を表示する。
 * @param {HTMLElement} main 表示先
 * @returns {Promise<void>}
 */
async function renderEvaluation(main) {
  const matrix = await api("GET", "/api/evaluations/matrix");
  const rows = matrix.issues.filter((r) => (
    (!evalFilter.person || r.person_id === evalFilter.person) && (evalFilter.showDropped || r.status !== "見送り")));
  const criteria = matrix.criteria;
  const proposalCount = state.tables.issues.filter((i) => i.visibility === "提案に使う").length;
  const solutions = state.tables.solutions;

  main.innerHTML = `
    <h1>評価表と解決策</h1>
    <p class="sub">課題ごとに観点を評価し、提案の候補を絞ります。評価のセルを押すと、評価と理由を入力できます。</p>

    <div class="panel">
      <div class="panel-head">
        <div class="filters">${personFilter("ev-person", evalFilter.person)}
          <label><input type="checkbox" id="ev-dropped" ${evalFilter.showDropped ? "checked" : ""}> 見送りも表示</label>
          <span class="muted">${rows.length}件。合計点（◎3、○2、△1、×0）の高い順</span></div>
        <div class="actions"><button class="primary" id="ev-proposal">提案用の整理を出力</button></div>
      </div>
      ${rows.length ? `<div class="table-scroll"><table class="ev-table"><tr><th>課題</th><th>対象者</th>
        ${criteria.map((c) => `<th class="ev-head" title="${h(c.question)}">${h(c.criterion)}</th>`).join("")}
        <th>合計</th><th>手法</th><th>データ</th><th></th></tr>
        ${rows.map((r) => `<tr class="${r.status === "見送り" ? "dim" : ""}">
          <td>${h(r.title)} ${r.visibility === "提案に使う" ? '<span class="badge ok">提案に使う</span>' : ""}</td>
          <td class="nowrap">${h(r.person)}</td>
          ${criteria.map((c) => {
            const cell = r.cells[c.criterion] || {};
            return `<td class="ev-cell" data-issue="${r.issue_id}" data-criterion="${h(c.criterion)}" title="${h(cell.comment || "押して入力")}">
              ${h(cell.rating) || '<span class="muted">・</span>'}${cell.comment ? '<span class="ev-note">＊</span>' : ""}</td>`;
          }).join("")}
          <td class="num"><b>${r.score}</b><span class="muted">／${matrix.max_score}</span></td>
          <td class="num">${r.solutions || ""}</td><td class="num">${r.sources || ""}</td>
          <td><div class="actions"><button class="small" data-edit-issue="${r.issue_id}">課題を編集</button></div></td></tr>`).join("")}
      </table></div>` : '<p class="muted">課題がありません。</p>'}
      <p class="hint muted">＊は理由の入力あり（セルにマウスを置くと表示）。提案用の整理には、公開範囲が「提案に使う」の課題（今は${proposalCount}件）だけが入ります。</p>
    </div>

    <div class="panel">
      <div class="panel-head"><h2>解決策の候補（${solutions.length}件）</h2><button class="primary" id="add-solution">解決策の候補を追加</button></div>
      ${solutions.length ? `<table><tr><th>手法</th><th>生成AI</th><th>課題</th><th>必要なデータ</th><th>懸念点</th><th></th></tr>
        ${solutions.map((s) => `<tr><td>${h(s.method)}</td><td class="nowrap">${s.uses_genai === "1" ? '<span class="badge warn">使う</span>' : "使わない"}</td>
          <td>${ids(s.issue_ids).map((id) => h(labelOf("issues", find("issues", id)))).join("<br>")}</td>
          <td class="md-view">${renderMarkdown(s.required_data)}</td><td class="md-view">${renderMarkdown(s.concern)}</td>
          <td><div class="actions"><button class="small" data-edit-sol="${s.solution_id}">編集</button>
          <button class="small danger" data-del-sol="${s.solution_id}">削除</button></div></td></tr>`).join("")}</table>`
        : '<p class="muted">まだありません。</p>'}
    </div>

    <div class="panel">
      <div class="panel-head"><h2>評価の観点</h2><button class="primary" id="add-criterion">観点を追加</button></div>
      <table><tr><th>順番</th><th>観点</th><th>確認すること</th><th></th></tr>
      ${criteria.map((c) => `<tr><td class="num">${h(c.order)}</td><td>${h(c.criterion)}</td><td>${h(c.question)}</td>
        <td><div class="actions"><button class="small" data-edit-crit="${c.criterion_id}">編集</button>
        <button class="small danger" data-del-crit="${c.criterion_id}">削除</button></div></td></tr>`).join("")}</table>
      <p class="hint muted">観点を削除すると、その観点の評価もあわせて削除します。</p>
    </div>`;

  // 絞り込み
  main.querySelector("#ev-person").onchange = (e) => { evalFilter.person = e.target.value; route(); };
  main.querySelector("#ev-dropped").onchange = (e) => { evalFilter.showDropped = e.target.checked; route(); };

  // 評価のセルの入力
  main.querySelectorAll(".ev-cell").forEach((td) => {
    td.onclick = () => editEvaluationCell(td.dataset.issue, td.dataset.criterion, matrix);
  });

  // 提案用の整理の出力（名前を伏せるかを選ぶ）
  main.querySelector("#ev-proposal").onclick = async () => {
    const choice = await openDialog("提案用の整理を出力",
      `<p>公開範囲が「提案に使う」の課題（${proposalCount}件）を、評価、解決策の候補、データとあわせて出力します。本人の発言（負担感）は含めません。</p>`,
      [{ label: "やめる", value: "cancel" }, { label: "名前を出して出力", value: "named" },
        { label: "名前を伏せて出力", value: "anon", primary: true }]);
    if (!choice) return;
    await showMarkdownFrom("提案用の整理", `/api/export-proposal?anonymize=${choice === "anon"}`);
  };

  // 解決策の候補と観点の追加、編集、削除
  main.querySelector("#add-solution").onclick = async () => { if (await editRow("solutions", null, { uses_genai: "0" })) route(); };
  main.querySelector("#add-criterion").onclick = async () => {
    if (await editRow("criteria", null, { order: String(criteria.length + 1) })) route();
  };
  bindRowButtons(main, "issue", "issues");
  bindRowButtons(main, "sol", "solutions");
  bindRowButtons(main, "crit", "criteria");
}

/**
 * 評価表の1つのセルを入力するダイアログを開き、保存する。
 * @param {string} issueId 課題のID
 * @param {string} criterion 観点の名前
 * @param {object} matrix /api/evaluations/matrix の結果
 * @returns {Promise<void>}
 */
async function editEvaluationCell(issueId, criterion, matrix) {
  const row = matrix.issues.find((r) => r.issue_id === issueId);
  const crit = matrix.criteria.find((c) => c.criterion === criterion) || {};
  const cell = row.cells[criterion] || { rating: "", comment: "" };
  const html = `
    <p><b>${h(row.title)}</b>（${h(row.person)}）</p>
    <p class="muted">観点：${h(criterion)}${crit.question ? `　確認すること：${h(crit.question)}` : ""}</p>
    <div class="field"><label class="name">評価</label><div class="seg-buttons" id="ev-rating">
      ${["◎", "○", "△", "×", ""].map((r) => `<button type="button" data-rating="${r}" class="${cell.rating === r ? "on" : ""}">${r || "空欄"}</button>`).join("")}
    </div></div>
    <div class="field"><label class="name">理由</label><textarea id="ev-comment">${h(cell.comment)}</textarea></div>`;
  let rating = cell.rating;
  const result = await openDialog("評価を入力", html, [
    { label: "やめる", value: "cancel" }, { label: "保存", value: "save", primary: true },
  ], (body) => {
    // 評価のボタンを1つだけ選べるようにする
    body.querySelectorAll("[data-rating]").forEach((b) => {
      b.onclick = () => {
        rating = b.dataset.rating;
        body.querySelectorAll("[data-rating]").forEach((x) => x.classList.toggle("on", x === b));
      };
    });
  });
  if (result !== "save") return;
  try {
    await api("POST", "/api/evaluations/cell",
      { issue_id: issueId, criterion, rating, comment: document.getElementById("ev-comment").value });
    await reload();
    route();
  } catch (e) { toast(e.message, true); }
}

// 「本人向けの表示を開く」ボタン（どの画面からでも使う）
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-open-screen]");
  if (button) openScreen(button.dataset.openScreen);
});

