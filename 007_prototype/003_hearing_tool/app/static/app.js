/* ヒアリング管理ツールの画面
 *
 * データは小さいので、最初にすべてのテーブルを受け取り、画面ごとに組み立てて表示する。
 * 書き込みのたびにデータを読み直す。
 */

// ------------------------------------------------------------------ 状態

/** サーバから受け取ったテーブルと設定 */
const state = { tables: {}, settings: {} };

/** 選択肢の一覧 */
const OPTIONS = {
  sessionStatus: ["準備中", "実施済み", "整理済み"],
  hypothesisStatus: ["未確認", "確認中", "確認済み", "否定", "保留"],
  visibility: ["聞き手のみ", "本人に見せる", "提案に使う"],
  priority: ["◎", "○"],
  asked: ["未", "聞いた", "省略"],
  certainty: ["数字あり", "本人に確認中", "印象のみ"],
  issueStatus: ["候補", "深掘り中", "提案候補", "見送り"],
  confirmation: ["本人の認識", "確認を依頼中", "確認済み"],
  termCategory: ["人名", "サービス", "部署", "その他"],
};

/** テーブルごとのIDの列 */
const ID_COLUMN = {
  persons: "person_id", sessions: "session_id", segments: "segment_id", hypotheses: "hypothesis_id",
  questions: "question_id", utterances: "utterance_id", issues: "issue_id", data_sources: "source_id",
  solutions: "solution_id", evaluations: "evaluation_id", criteria: "criterion_id", terms: "term_id",
};

/** テーブルの日本語名（ダイアログの見出しに使う） */
const TABLE_NAME = {
  persons: "対象者", sessions: "ヒアリングの回", segments: "タイムテーブルの区切り", hypotheses: "仮説",
  questions: "質問", issues: "課題カード", data_sources: "データ台帳", terms: "用語", utterances: "発言",
  solutions: "解決策の候補", criteria: "評価の観点",
};

/* 編集フォームの定義
 * type: text / textarea / tall（長文） / number / date / select / check（1か0） / ref（1つ選ぶ） / refs（複数選ぶ）
 * ref と refs は refTable の行から選ぶ。scope が "person" なら、同じ対象者の行だけを出す。
 */
const FORMS = {
  persons: [
    { key: "name", label: "名前", type: "text", required: true },
    { key: "role", label: "役割", type: "markdown" },
    { key: "note", label: "聞き手用のメモ（配慮すること）", type: "markdown" },
  ],
  sessions: [
    { key: "person_id", label: "対象者", type: "ref", refTable: "persons", required: true },
    { key: "round", label: "第何回", type: "number", required: true },
    { key: "held_on", label: "実施日", type: "date" },
    { key: "interviewers", label: "聞き手", type: "text" },
    { key: "duration_min", label: "予定の時間（分）", type: "number" },
    { key: "status", label: "状態", type: "select", options: OPTIONS.sessionStatus },
    { key: "purpose", label: "この回の目的", type: "markdown" },
    { key: "screen_summary", label: "当日画面に出す要約（本人に見せる）", type: "tall" },
    { key: "request_message", label: "事前の依頼文（本人に送る）", type: "tall" },
    { key: "audio_file", label: "音声ファイルの名前（data/audio 内）", type: "text" },
    { key: "memo", label: "聞き手用のメモ", type: "markdown", tall: true },
  ],
  segments: [
    { key: "order", label: "順番", type: "number" },
    { key: "start_min", label: "開始（分）", type: "number", required: true },
    { key: "end_min", label: "終了（分）", type: "number", required: true },
    { key: "title", label: "内容", type: "text", required: true },
    { key: "aim", label: "狙い", type: "text" },
    { key: "hypothesis_ids", label: "ひも付く仮説", type: "refs", refTable: "hypotheses", scope: "person" },
  ],
  hypotheses: [
    { key: "person_id", label: "対象者", type: "ref", refTable: "persons", required: true },
    { key: "session_id", label: "立てた回", type: "ref", refTable: "sessions", scope: "person" },
    { key: "label", label: "表示名（例：仮説1、補足）", type: "text", required: true },
    { key: "title", label: "見出し", type: "text", required: true },
    { key: "body", label: "内容", type: "markdown" },
    { key: "examples", label: "お聞きしたいことの例（1行に1つ）", type: "textarea" },
    { key: "status", label: "状態", type: "select", options: OPTIONS.hypothesisStatus },
    { key: "source", label: "根拠", type: "text" },
    { key: "visibility", label: "公開範囲", type: "select", options: OPTIONS.visibility },
  ],
  questions: [
    { key: "segment_id", label: "区切り", type: "ref", refTable: "segments", scope: "session" },
    { key: "order", label: "区切りの中での順番", type: "number" },
    { key: "label", label: "番号（例：Q16。なければ空欄）", type: "text" },
    { key: "priority", label: "優先度（◎は必ず聞く、○は時間があれば聞く）", type: "select", options: OPTIONS.priority },
    { key: "text", label: "質問", type: "textarea", required: true },
    { key: "check_point", label: "確認すること", type: "text" },
    { key: "is_data_question", label: "データの有無を聞く質問", type: "check" },
    { key: "est_min", label: "目安の時間（分）", type: "number", hint: "空欄なら◎は2分、○は1分として集計します。" },
    { key: "hypothesis_ids", label: "ひも付く仮説", type: "refs", refTable: "hypotheses", scope: "person" },
    { key: "asked", label: "聞いたかどうか", type: "select", options: OPTIONS.asked },
    { key: "answer_memo", label: "回答メモ", type: "markdown" },
  ],
  commonQuestions: [
    { key: "order", label: "順番", type: "number" },
    { key: "priority", label: "優先度", type: "select", options: OPTIONS.priority },
    { key: "text", label: "質問", type: "textarea", required: true },
    { key: "check_point", label: "確認すること", type: "text" },
    { key: "is_data_question", label: "データの有無を聞く質問", type: "check" },
    { key: "est_min", label: "目安の時間（分）", type: "number" },
  ],
  issues: [
    { key: "person_id", label: "対象者", type: "ref", refTable: "persons", required: true },
    { key: "title", label: "課題の名前", type: "text", required: true },
    { key: "theme", label: "テーマ（横断表示で、対象者をまたいでまとめる単位）", type: "text",
      suggest: () => state.tables.issues.map((i) => i.theme), hint: "例：時間の使い方、作業の引き渡し、定例の準備" },
    { key: "status", label: "状態", type: "select", options: OPTIONS.issueStatus },
    { key: "quote", label: "本人の負担感（発言のまま）", type: "textarea" },
    { key: "scene", label: "具体的な場面", type: "markdown" },
    { key: "frequency", label: "頻度", type: "text" },
    { key: "time_per", label: "1回あたりの時間", type: "text" },
    { key: "core_step", label: "負担の中心となる工程", type: "markdown" },
    { key: "judgment", label: "判断の材料と基準", type: "markdown" },
    { key: "workaround", label: "既存の工夫や自動化", type: "markdown" },
    { key: "impact", label: "問題が起きた場合の影響", type: "markdown" },
    { key: "certainty", label: "発言の確度", type: "select", options: OPTIONS.certainty },
    { key: "hypothesis_ids", label: "ひも付く仮説", type: "refs", refTable: "hypotheses", scope: "person" },
    { key: "session_ids", label: "話を聞いた回", type: "refs", refTable: "sessions", scope: "person" },
    { key: "visibility", label: "公開範囲", type: "select", options: OPTIONS.visibility },
  ],
  data_sources: [
    { key: "person_id", label: "対象者", type: "ref", refTable: "persons", required: true },
    { key: "name", label: "データの名前", type: "text", required: true },
    { key: "issue_ids", label: "ひも付く課題", type: "refs", refTable: "issues", scope: "person" },
    { key: "location", label: "場所", type: "text" },
    { key: "format", label: "形式", type: "text" },
    { key: "period", label: "期間", type: "text" },
    { key: "volume", label: "件数", type: "text" },
    { key: "has_result", label: "結果の記録の有無", type: "markdown" },
    { key: "restriction", label: "利用の制限", type: "markdown" },
    { key: "confirmation", label: "確認の状態", type: "select", options: OPTIONS.confirmation },
  ],
  solutions: [
    { key: "method", label: "手法（例：コストの異常検知）", type: "text", required: true },
    { key: "uses_genai", label: "生成AIを使う", type: "check" },
    { key: "issue_ids", label: "ひも付く課題", type: "refs", refTable: "issues" },
    { key: "required_data", label: "必要なデータ", type: "markdown" },
    { key: "concern", label: "懸念点", type: "markdown" },
  ],
  criteria: [
    { key: "order", label: "順番", type: "number" },
    { key: "criterion", label: "観点", type: "text", required: true, hint: "名前を変えると、入力済みの評価も新しい名前に移ります。" },
    { key: "question", label: "確認すること", type: "text" },
  ],
  utteranceLinks: [
    { key: "question_ids", label: "ひも付く質問", type: "refs", refTable: "questions", scope: "session" },
    { key: "hypothesis_ids", label: "ひも付く仮説", type: "refs", refTable: "hypotheses", scope: "person" },
    { key: "issue_ids", label: "ひも付く課題", type: "refs", refTable: "issues", scope: "person" },
  ],
  terms: [
    { key: "term", label: "用語", type: "text", required: true },
    { key: "category", label: "分類", type: "select", options: OPTIONS.termCategory },
    { key: "description", label: "説明", type: "textarea" },
    { key: "misrecognitions", label: "誤認識されやすい表記（; 区切り）", type: "text" },
  ],
};

// ------------------------------------------------------------------ 共通の処理

/**
 * 文字列を HTML に埋め込める形にする。
 * @param {*} value 任意の値
 * @returns {string} エスケープした文字列
 */
function h(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

/**
 * API を呼ぶ。
 * @param {string} method HTTP メソッド
 * @param {string} url 呼び先
 * @param {object} [body] 送る内容
 * @returns {Promise<object>} 受け取った JSON
 */
async function api(method, url, body) {
  // 送る内容があれば JSON にする
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  // 呼び出して、失敗ならサーバのメッセージを投げる
  const res = await fetch(url, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `エラーが発生しました（${res.status}）`);
  return data;
}

/**
 * 画面の右下にお知らせを出す。
 * @param {string} message 表示する文
 * @param {boolean} [isError] エラーなら true
 * @returns {void}
 */
function toast(message, isError = false) {
  const box = document.getElementById("toast");
  box.textContent = message;
  box.className = isError ? "toast error" : "toast";
  box.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { box.hidden = true; }, isError ? 6000 : 2500);
}

/**
 * すべてのデータを読み直す。
 * @returns {Promise<void>}
 */
async function reload() {
  const data = await api("GET", "/api/data");
  state.tables = data.tables;
  state.settings = data.settings;
  document.getElementById("user-label").textContent = `更新者：${state.settings.user_name}`;
}

/**
 * ";" 区切りのIDを一覧にする。
 * @param {string} value ";" 区切りの文字列
 * @returns {string[]} IDの一覧
 */
function ids(value) {
  return String(value || "").split(";").map((v) => v.trim()).filter(Boolean);
}

/**
 * order 列の数値順に並べる。
 * @param {object[]} rows 行の一覧
 * @returns {object[]} 並べた一覧
 */
function byOrder(rows) {
  const num = (v) => (v === "" || v == null || isNaN(Number(v)) ? 9999 : Number(v));
  return [...rows].sort((a, b) => num(a.order) - num(b.order));
}

/**
 * テーブルからIDで行を探す。
 * @param {string} table テーブル名
 * @param {string} id 行のID
 * @returns {object|undefined} 見つかった行
 */
function find(table, id) {
  return (state.tables[table] || []).find((r) => r[ID_COLUMN[table]] === id);
}

/**
 * 参照先の行の表示名を返す。
 * @param {string} table テーブル名
 * @param {object} row 行
 * @returns {string} 表示名
 */
function labelOf(table, row) {
  if (!row) return "（不明）";
  switch (table) {
    case "persons": return row.name;
    case "sessions": return `${(find("persons", row.person_id) || {}).name || ""} 第${row.round}回`;
    case "segments": return `${row.start_min}〜${row.end_min}分 ${row.title}`;
    case "hypotheses": return `${row.label}：${row.title}`;
    case "issues": return `${row.title}（${(find("persons", row.person_id) || {}).name || ""}）`;
    case "solutions": return row.method;
    case "criteria": return row.criterion;
    case "questions": return `${row.label || "-"} ${String(row.text || "").slice(0, 50)}`;
    case "utterances": return `${row.speaker || "（発言者なし）"}：${String(row.text || "").slice(0, 30)}`;
    default: return row.name || row.title || "";
  }
}

/**
 * 状態に応じた色のバッジを返す。
 * @param {string} text 状態の文字列
 * @returns {string} HTML
 */
function badge(text) {
  const ok = ["整理済み", "確認済み", "聞いた", "提案候補"];
  const warn = ["準備中", "未確認", "確認中", "確認を依頼中", "本人の認識", "深掘り中"];
  const cls = ok.includes(text) ? "ok" : warn.includes(text) ? "warn" : "";
  return text ? `<span class="badge ${cls}">${h(text)}</span>` : "";
}

/**
 * 回の対象者のIDを返す。
 * @param {string} sessionId 回のID
 * @returns {string} 対象者のID
 */
function personOfSession(sessionId) {
  return (find("sessions", sessionId) || {}).person_id || "";
}

// ------------------------------------------------------------------ ダイアログ

/**
 * ダイアログを開き、ボタンが押されるまで待つ。
 * @param {string} title 見出し
 * @param {string} bodyHtml 中身の HTML
 * @param {{label: string, value: string, primary?: boolean, danger?: boolean}[]} buttons ボタン
 * @param {(body: HTMLElement) => void} [onOpen] 開いた直後の処理
 * @returns {Promise<string>} 押されたボタンの value（閉じただけなら空文字）
 */
function openDialog(title, bodyHtml, buttons, onOpen) {
  const dialog = document.getElementById("dialog");
  document.getElementById("dialog-title").textContent = title;
  const body = document.getElementById("dialog-body");
  body.innerHTML = bodyHtml;
  document.getElementById("dialog-actions").innerHTML = buttons.map((b) => (
    `<button value="${h(b.value)}" class="${b.primary ? "primary" : ""} ${b.danger ? "danger" : ""}"
      ${b.value === "cancel" ? 'formnovalidate' : ""}>${h(b.label)}</button>`
  )).join("");
  if (onOpen) onOpen(body);
  dialog.showModal();
  return new Promise((resolve) => {
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "cancel" ? "" : dialog.returnValue), { once: true });
    dialog.returnValue = "";
  });
}

/**
 * 確認のダイアログを出す。
 * @param {string} message 確認する内容
 * @returns {Promise<boolean>} 「はい」なら true
 */
async function confirmDialog(message) {
  const result = await openDialog("確認", `<p class="pre">${h(message)}</p>`, [
    { label: "やめる", value: "cancel" }, { label: "実行する", value: "ok", danger: true },
  ]);
  return result === "ok";
}

/**
 * 参照の選択肢を返す。
 * @param {object} field フォームの項目の定義
 * @param {{person_id?: string, session_id?: string}} scope 絞り込みの条件
 * @returns {object[]} 選べる行の一覧
 */
function refChoices(field, scope) {
  let rows = state.tables[field.refTable] || [];
  // 同じ対象者、または同じ回の行に絞る
  if (field.scope === "person" && scope.person_id) rows = rows.filter((r) => r.person_id === scope.person_id);
  if (field.scope === "session" && scope.session_id) rows = rows.filter((r) => r.session_id === scope.session_id);
  if (field.refTable === "segments" || field.refTable === "sessions") rows = byOrder(rows);
  // 質問は、区切りの順、区切りの中の順に並べる
  if (field.refTable === "questions") {
    const segOrder = (q) => Number((find("segments", q.segment_id) || {}).start_min ?? 999);
    rows = byOrder(rows).sort((a, b) => segOrder(a) - segOrder(b));
  }
  return rows;
}

/**
 * フォームの項目の HTML を作る。
 * @param {object} field 項目の定義
 * @param {string} value 今の値
 * @param {object} scope 参照の絞り込みの条件
 * @returns {string} HTML
 */
function fieldHtml(field, value, scope) {
  const name = `f_${field.key}`;
  const req = field.required ? "required" : "";
  let input = "";
  switch (field.type) {
    case "textarea":
    case "tall":
      input = `<textarea name="${name}" class="${field.type === "tall" ? "tall" : ""}" ${req}>${h(value)}</textarea>`;
      break;
    case "markdown":
      // 記述とプレビューを切り替えられる入力欄
      input = `<div class="md-editor">
        <div class="md-tabs">
          <button type="button" class="md-tab active" data-md-tab="edit">記述</button>
          <button type="button" class="md-tab" data-md-tab="preview">プレビュー</button>
          <span class="hint">Markdown で書けます（表、見出し、太字、箇条書きなど）</span>
        </div>
        <textarea name="${name}" class="${field.tall ? "tall" : ""}" ${req}>${h(value)}</textarea>
        <div class="md-view md-box md-preview ${field.tall ? "tall" : ""}" hidden></div>
      </div>`;
      break;
    case "number":
      input = `<input type="number" step="any" name="${name}" value="${h(value)}" ${req}>`;
      break;
    case "date":
      input = `<input type="date" name="${name}" value="${h(value)}">`;
      break;
    case "select":
      input = `<select name="${name}">${field.options.map((o) => (
        `<option ${o === value ? "selected" : ""}>${h(o)}</option>`)).join("")}</select>`;
      break;
    case "check":
      return `<div class="field"><label><input type="checkbox" name="${name}" ${value === "1" ? "checked" : ""}>
        ${h(field.label)}</label></div>`;
    case "ref": {
      const rows = refChoices(field, scope);
      input = `<select name="${name}" ${req}><option value="">（なし）</option>${rows.map((r) => {
        const id = r[ID_COLUMN[field.refTable]];
        return `<option value="${h(id)}" ${id === value ? "selected" : ""}>${h(labelOf(field.refTable, r))}</option>`;
      }).join("")}</select>`;
      break;
    }
    case "refs": {
      const chosen = ids(value);
      const rows = refChoices(field, scope);
      input = rows.length ? `<div class="checks">${rows.map((r) => {
        const id = r[ID_COLUMN[field.refTable]];
        return `<label><input type="checkbox" name="${name}" value="${h(id)}" ${chosen.includes(id) ? "checked" : ""}>
          ${h(labelOf(field.refTable, r))}</label>`;
      }).join("")}</div>` : `<div class="hint">選べるものがありません。</div>`;
      break;
    }
    default: {
      // 候補があれば、入力欄の下に選択肢として出す
      const suggestions = field.suggest ? [...new Set(field.suggest().filter(Boolean))].sort() : [];
      const listId = suggestions.length ? `dl_${field.key}` : "";
      input = `<input type="text" name="${name}" value="${h(value)}" ${req} ${listId ? `list="${listId}"` : ""}>` +
        (listId ? `<datalist id="${listId}">${suggestions.map((s) => `<option value="${h(s)}">`).join("")}</datalist>` : "");
    }
  }
  const hint = field.hint ? `<div class="hint">${h(field.hint)}</div>` : "";
  return `<div class="field"><label class="name">${h(field.label)}${field.required ? " *" : ""}</label>${input}${hint}</div>`;
}

/**
 * フォームの入力値を集める。
 * @param {HTMLElement} body ダイアログの中身
 * @param {object[]} fields 項目の定義
 * @returns {object} 列ごとの値
 */
function collectValues(body, fields) {
  const values = {};
  for (const field of fields) {
    const name = `f_${field.key}`;
    if (field.type === "check") {
      values[field.key] = body.querySelector(`[name="${name}"]`).checked ? "1" : "0";
    } else if (field.type === "refs") {
      values[field.key] = [...body.querySelectorAll(`[name="${name}"]:checked`)].map((c) => c.value).join(";");
    } else {
      values[field.key] = body.querySelector(`[name="${name}"]`).value;
    }
  }
  return values;
}

/**
 * 行の追加・編集のダイアログを開き、保存する。
 * @param {string} table テーブル名
 * @param {object|null} row 編集する行。新規なら null
 * @param {object} [defaults] 新規のときの初期値（フォームにない列もそのまま保存する）
 * @param {string} [formKey] FORMS のキー。省略時はテーブル名
 * @returns {Promise<boolean>} 保存したら true
 */
async function editRow(table, row, defaults = {}, formKey = table) {
  // 初期値と絞り込みの条件を決める
  const fields = FORMS[formKey];
  const current = { ...defaults, ...(row || {}) };
  const scope = {
    person_id: current.person_id || personOfSession(current.session_id),
    session_id: current.session_id,
  };
  const title = `${TABLE_NAME[table] || table}を${row ? "編集" : "追加"}`;
  const html = fields.map((f) => fieldHtml(f, current[f.key] ?? "", scope)).join("") +
    (row ? `<p class="hint muted">最終更新：${h(row.updated_by)}（${h(row.updated_at)}）</p>` : "");

  // ダイアログを開き、保存が押されるまで待つ
  const result = await openDialog(title, html, [
    { label: "やめる", value: "cancel" }, { label: "保存", value: "save", primary: true },
  ]);
  if (result !== "save") return false;

  // 入力値を集めて保存する
  const values = { ...defaults, ...collectValues(document.getElementById("dialog-body"), fields) };
  try {
    if (row) await api("PUT", `/api/tables/${table}/${row[ID_COLUMN[table]]}`, { values });
    else await api("POST", `/api/tables/${table}`, { values });
    await reload();
    toast("保存しました。");
    return true;
  } catch (e) {
    toast(e.message, true);
    return false;
  }
}

/**
 * 行を削除する。
 * @param {string} table テーブル名
 * @param {object} row 削除する行
 * @param {string} [extra] 確認の文に足す説明
 * @returns {Promise<boolean>} 削除したら true
 */
async function deleteRow(table, row, extra = "") {
  const ok = await confirmDialog(`「${labelOf(table, row) || row.text || row.term || ""}」を削除します。${extra}`);
  if (!ok) return false;
  try {
    await api("DELETE", `/api/tables/${table}/${row[ID_COLUMN[table]]}`);
    await reload();
    toast("削除しました。");
    return true;
  } catch (e) {
    toast(e.message, true);
    return false;
  }
}

/**
 * Markdown を表示し、コピーや保存をできるようにする。
 * @param {string} title 見出し
 * @param {string} kind 出力の種類（plan / summary / request）
 * @param {string[]} sessionIds 回のID
 * @returns {Promise<void>}
 */
async function showMarkdown(title, kind, sessionIds) {
  const query = encodeURIComponent(sessionIds.join(";"));
  await showMarkdownFrom(title, `/api/export/${kind}?session_ids=${query}`);
}

/**
 * 指定の API が作った Markdown を表示し、コピーや保存をできるようにする。
 * @param {string} title 見出し
 * @param {string} url Markdown を返す API（"?" を含むこと。保存時は &save=true を付けて呼ぶ）
 * @returns {Promise<void>}
 */
async function showMarkdownFrom(title, url) {
  const { markdown } = await api("GET", url);
  const result = await openDialog(title, `<pre class="md">${h(markdown || "（内容がありません）")}</pre>`, [
    { label: "閉じる", value: "cancel" },
    { label: "コピー", value: "copy" },
    { label: "exports に保存", value: "save", primary: true },
  ]);
  if (result === "copy") {
    await navigator.clipboard.writeText(markdown);
    toast("コピーしました。");
  } else if (result === "save") {
    const saved = await api("GET", `${url}&save=true`);
    toast(`保存しました：exports/${saved.saved}`);
  }
}

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

// ------------------------------------------------------------------ 画面：文字起こしと推敲

/** 推敲画面の絞り込みの状態 */
const transcriptFilter = { unreviewedOnly: false, hideExcluded: false, text: "" };

/**
 * 発言者の候補を返す。
 * @param {object} session 回の行
 * @returns {string[]} 発言者の名前の一覧
 */
function speakerChoices(session) {
  const person = find("persons", session.person_id);
  const names = String(session.interviewers || "").split(/[、,;]/).map((s) => s.trim()).filter(Boolean);
  if (person) names.push(person.name);
  // すでに使われている発言者も候補に入れる
  state.tables.utterances.filter((u) => u.session_id === session.session_id && u.speaker)
    .forEach((u) => names.push(u.speaker));
  return [...new Set(names)];
}

/**
 * 用語集の誤認識の表記と、正しい用語の組を返す。
 * @returns {{wrong: string, right: string}[]} 組の一覧（長い表記から順）
 */
function misrecognitionPairs() {
  return state.tables.terms.flatMap((t) => ids(t.misrecognitions).map((w) => ({ wrong: w, right: t.term })))
    .sort((a, b) => b.wrong.length - a.wrong.length);
}

/**
 * 文字起こしと推敲の画面を表示する。
 * @param {HTMLElement} main 表示先
 * @param {string} sessionId 回のID
 * @returns {Promise<void>}
 */
async function renderTranscript(main, sessionId) {
  const session = find("sessions", sessionId);
  if (!session) { main.innerHTML = "<p>回が見つかりません。</p>"; return; }
  const person = find("persons", session.person_id) || { name: "（不明）" };
  const all = byOrder(state.tables.utterances.filter((u) => u.session_id === sessionId));
  const word = transcriptFilter.text.trim();
  const shown = all.filter((u) => (
    (!transcriptFilter.unreviewedOnly || u.review_status !== "推敲済み") &&
    (!transcriptFilter.hideExcluded || u.excluded !== "1") &&
    (!word || u.text.includes(word) || u.speaker.includes(word))));
  const speakers = speakerChoices(session);
  const pairs = misrecognitionPairs();
  const { files } = await api("GET", "/api/audio-files");
  const audioOk = files.some((f) => f.name === session.audio_file);

  // 回全体での誤認識の候補の件数
  const found = pairs.map((p) => ({ ...p, count: all.filter((u) => u.text.includes(p.wrong)).length })).filter((p) => p.count);

  main.innerHTML = `
    <div class="panel-head">
      <div><h1><a href="#/session/${sessionId}">${h(person.name)} 第${h(session.round)}回</a>　文字起こしと推敲</h1>
        <p class="sub">${all.length}件の発言（未推敲 ${all.filter((u) => u.review_status !== "推敲済み").length}件、対象外 ${all.filter((u) => u.excluded === "1").length}件）</p></div>
    </div>

    <div class="panel">
      <div class="panel-head"><h2>音声と文字起こし</h2></div>
      <div class="filters">
        <label>音声ファイル（data/audio）
          <select id="tr-audio"><option value="">（選ぶ）</option>${files.map((f) => (
            `<option value="${h(f.name)}" ${f.name === session.audio_file ? "selected" : ""}>${h(f.name)}（${f.size_mb}MB）</option>`)).join("")}</select></label>
        ${session.audio_file && !audioOk ? `<span class="warn-text">${h(session.audio_file)} が data/audio にありません。</span>` : ""}
      </div>
      <div id="tr-estimate" class="muted">見積もりを確認しています…</div>
    </div>

    ${audioOk ? `<div class="player-bar">
      <audio id="player" controls preload="metadata" src="/api/audio/${encodeURIComponent(session.audio_file)}"></audio>
      <label>速度 <select id="tr-rate">${[0.75, 1, 1.25, 1.5, 2].map((r) => `<option ${r === 1 ? "selected" : ""}>${r}</option>`).join("")}</select></label>
      <span class="muted">時刻を押すと、その位置から再生します（時刻は分けた音声の開始位置のため、目安です）。</span>
    </div>` : ""}

    ${found.length ? `<div class="panel"><h2>誤認識の候補（用語集から）</h2><div class="actions" style="margin-top:8px">${found.map((p) => (
      `<button data-replace-all="${h(p.wrong)}" data-right="${h(p.right)}">「${h(p.wrong)}」→「${h(p.right)}」（${p.count}件）をすべて置き換え</button>`)).join("")}</div></div>` : ""}

    <div class="panel">
      <div class="panel-head">
        <div class="filters">
          <label><input type="checkbox" id="tf-unreviewed" ${transcriptFilter.unreviewedOnly ? "checked" : ""}> 未推敲だけ</label>
          <label><input type="checkbox" id="tf-excluded" ${transcriptFilter.hideExcluded ? "checked" : ""}> 対象外を隠す</label>
          <input type="search" id="tf-text" placeholder="発言を検索" value="${h(transcriptFilter.text)}">
          <span class="muted">${shown.length}件を表示</span>
        </div>
        <div class="actions">
          <button id="tr-merge-speakers">続けて同じ発言者の発言をまとめる</button>
          <button id="tr-review-all">表示中をすべて推敲済みにする</button>
          <button id="tr-insert-top">先頭に発言を追加</button>
        </div>
      </div>
      <p class="hint muted">文章は入力欄から離れると保存します。「分割」は、入力欄で分けたい位置にカーソルを置いてから押します。</p>
      <div id="tr-rows">${shown.map((u) => utteranceRowHtml(u, speakers, pairs)).join("") || '<p class="muted">発言がありません。</p>'}</div>
    </div>`;

  // 見積もりの表示（Azure は呼ばない）
  renderEstimate(main.querySelector("#tr-estimate"), sessionId);

  // 音声ファイルの選択
  main.querySelector("#tr-audio").onchange = async (e) => {
    await api("PUT", `/api/tables/sessions/${sessionId}`, { values: { audio_file: e.target.value } });
    await reload();
    route();
  };
  const rate = main.querySelector("#tr-rate");
  if (rate) rate.onchange = (e) => { main.querySelector("#player").playbackRate = Number(e.target.value); };

  // 絞り込み
  main.querySelector("#tf-unreviewed").onchange = (e) => { transcriptFilter.unreviewedOnly = e.target.checked; route(); };
  main.querySelector("#tf-excluded").onchange = (e) => { transcriptFilter.hideExcluded = e.target.checked; route(); };
  main.querySelector("#tf-text").onchange = (e) => { transcriptFilter.text = e.target.value; route(); };

  // 回全体の操作
  main.querySelectorAll("[data-replace-all]").forEach((b) => {
    b.onclick = async () => {
      const r = await api("POST", `/api/sessions/${sessionId}/utterances/replace`, { wrong: b.dataset.replaceAll, right: b.dataset.right });
      await refreshKeepScroll(`${r.replaced}件の発言を置き換えました。`);
    };
  });
  main.querySelector("#tr-merge-speakers").onclick = async () => {
    if (!(await confirmDialog("続けて同じ発言者が話している発言を、1つにまとめます。発言者が空の発言はまとめません。"))) return;
    const r = await api("POST", `/api/sessions/${sessionId}/utterances/merge-speakers`);
    await refreshKeepScroll(`${r.merged}件をまとめました。`);
  };
  main.querySelector("#tr-review-all").onclick = async () => {
    if (!(await confirmDialog(`表示中の${shown.length}件を「推敲済み」にします。`))) return;
    const r = await api("POST", `/api/sessions/${sessionId}/utterances/bulk`,
      { values: { review_status: "推敲済み" }, utterance_ids: shown.map((u) => u.utterance_id) });
    await refreshKeepScroll(`${r.updated}件を推敲済みにしました。`);
  };
  main.querySelector("#tr-insert-top").onclick = async () => {
    await api("POST", `/api/sessions/${sessionId}/utterances/insert`, { utterance_id: "" });
    await refreshKeepScroll("先頭に発言を追加しました。");
  };

  bindUtteranceRows(main, sessionId, speakers, pairs);
}

/**
 * 発言1件の行の HTML を作る。
 * @param {object} u 発言の行
 * @param {string[]} speakers 発言者の候補
 * @param {{wrong: string, right: string}[]} pairs 誤認識の組
 * @returns {string} HTML
 */
function utteranceRowHtml(u, speakers, pairs) {
  const options = [...new Set([...speakers, u.speaker].filter(Boolean))];
  const links = [
    ...ids(u.question_ids).map((id) => (find("questions", id) || {}).label || "質問"),
    ...ids(u.hypothesis_ids).map((id) => (find("hypotheses", id) || {}).label || "仮説"),
    ...ids(u.issue_ids).map((id) => (find("issues", id) || {}).title || "課題"),
  ];
  return `
    <div class="tr-row ${u.excluded === "1" ? "excluded" : ""} ${u.review_status === "推敲済み" ? "reviewed" : ""}" data-u="${u.utterance_id}">
      <div class="tr-side">
        <div class="muted">#${h(u.order)}</div>
        ${u.start_sec !== "" ? `<button class="small" data-seek="${h(u.start_sec)}" title="この位置から再生">▶ ${mmss(u.start_sec)}</button>` : ""}
        <select data-speaker><option value="">（発言者）</option>${options.map((s) => (
          `<option ${s === u.speaker ? "selected" : ""}>${h(s)}</option>`)).join("")}<option value="__new">＋ 名前を入力</option></select>
      </div>
      <div class="tr-main">
        <textarea data-text rows="${Math.min(10, Math.max(2, Math.ceil(u.text.length / 60) + (u.text.match(/\n/g) || []).length))}">${h(u.text)}</textarea>
        <div class="tr-chips">${misrecognitionChips(u.text, pairs)}
          ${links.length ? `<span class="muted">ひも付け：${links.map((l) => `<span class="badge accent">${h(l)}</span>`).join(" ")}</span>` : ""}</div>
      </div>
      <div class="tr-tools">
        <label><input type="checkbox" data-reviewed ${u.review_status === "推敲済み" ? "checked" : ""}> 推敲済み</label>
        <label><input type="checkbox" data-excluded ${u.excluded === "1" ? "checked" : ""}> 対象外</label>
        <div class="actions">
          <button class="small" data-op="merge" title="1つ前の発言につなげる">↑結合</button>
          <button class="small" data-op="split">分割</button>
          <button class="small" data-op="insert" title="直後に空の発言を追加">＋下に追加</button>
          <button class="small" data-op="link">ひも付け</button>
          <button class="small danger" data-op="delete">削除</button>
        </div>
      </div>
    </div>`;
}

/**
 * 発言の中にある誤認識の候補を、置き換えボタンとして返す。
 * @param {string} text 発言
 * @param {{wrong: string, right: string}[]} pairs 誤認識の組
 * @returns {string} HTML
 */
function misrecognitionChips(text, pairs) {
  return pairs.filter((p) => text.includes(p.wrong)).map((p) => (
    `<button class="small chip" data-fix="${h(p.wrong)}" data-right="${h(p.right)}">「${h(p.wrong)}」→「${h(p.right)}」</button>`
  )).join("");
}

/**
 * データを読み直して画面を描き直し、スクロールの位置を戻す。
 * @param {string} [message] 表示するお知らせ
 * @returns {Promise<void>}
 */
async function refreshKeepScroll(message) {
  const y = window.scrollY;
  await reload();
  await route();
  window.scrollTo(0, y);
  if (message) toast(message);
}

/**
 * 発言の行の入力とボタンに動きを付ける。
 * @param {HTMLElement} root 行を含む要素
 * @param {string} sessionId 回のID
 * @param {string[]} speakers 発言者の候補
 * @param {{wrong: string, right: string}[]} pairs 誤認識の組
 * @returns {void}
 */
function bindUtteranceRows(root, sessionId, speakers, pairs) {
  // 1件の発言の値を保存し、手元のデータにも反映する
  const save = async (id, values) => {
    try {
      const row = await api("PUT", `/api/tables/utterances/${id}`, { values });
      Object.assign(find("utterances", id), row);
      return true;
    } catch (e) { toast(e.message, true); return false; }
  };

  root.querySelectorAll(".tr-row").forEach((el) => {
    const id = el.dataset.u;

    // 再生
    const seek = el.querySelector("[data-seek]");
    if (seek) {
      seek.onclick = () => {
        const player = document.getElementById("player");
        if (!player) { toast("音声ファイルが選ばれていません。", true); return; }
        player.currentTime = Number(seek.dataset.seek);
        player.play();
      };
    }

    // 発言者（「名前を入力」なら新しい名前を聞く）
    el.querySelector("[data-speaker]").onchange = async (e) => {
      let name = e.target.value;
      if (name === "__new") {
        name = (window.prompt("発言者の名前") || "").trim();
        if (!name) { e.target.value = find("utterances", id).speaker; return; }
        if (await save(id, { speaker: name })) await refreshKeepScroll();
        return;
      }
      await save(id, { speaker: name });
    };

    // 本文（入力欄から離れたら保存し、誤認識の候補を更新する）
    const textarea = el.querySelector("[data-text]");
    textarea.onchange = async () => {
      if (await save(id, { text: textarea.value })) {
        el.querySelector(".tr-chips").querySelectorAll(".chip").forEach((c) => c.remove());
        el.querySelector(".tr-chips").insertAdjacentHTML("afterbegin", misrecognitionChips(textarea.value, pairs));
        bindChips(el);
      }
    };

    // 推敲済みと対象外
    el.querySelector("[data-reviewed]").onchange = async (e) => {
      if (await save(id, { review_status: e.target.checked ? "推敲済み" : "未推敲" })) el.classList.toggle("reviewed", e.target.checked);
    };
    el.querySelector("[data-excluded]").onchange = async (e) => {
      if (await save(id, { excluded: e.target.checked ? "1" : "0" })) el.classList.toggle("excluded", e.target.checked);
    };

    // 誤認識の候補を、この発言だけ置き換える
    const bindChips = (rowEl) => {
      rowEl.querySelectorAll("[data-fix]").forEach((b) => {
        b.onclick = async () => {
          if (textarea.value !== find("utterances", id).text) await save(id, { text: textarea.value });
          await api("POST", `/api/sessions/${sessionId}/utterances/replace`,
            { wrong: b.dataset.fix, right: b.dataset.right, utterance_id: id });
          await refreshKeepScroll();
        };
      });
    };
    bindChips(el);

    // 結合、分割、追加、ひも付け、削除
    el.querySelectorAll("[data-op]").forEach((b) => {
      b.onclick = async () => {
        // 書きかけの本文があれば先に保存する
        if (textarea.value !== find("utterances", id).text && !(await save(id, { text: textarea.value }))) return;
        try {
          switch (b.dataset.op) {
            case "merge":
              await api("POST", `/api/sessions/${sessionId}/utterances/merge`, { utterance_id: id });
              await refreshKeepScroll("前の発言につなげました。");
              break;
            case "split":
              await api("POST", `/api/sessions/${sessionId}/utterances/split`,
                { utterance_id: id, position: textarea.selectionStart });
              await refreshKeepScroll("分割しました。");
              break;
            case "insert":
              await api("POST", `/api/sessions/${sessionId}/utterances/insert`, { utterance_id: id });
              await refreshKeepScroll("発言を追加しました。");
              break;
            case "link":
              if (await editRow("utterances", find("utterances", id), {}, "utteranceLinks")) await refreshKeepScroll();
              break;
            case "delete":
              if (await deleteRow("utterances", find("utterances", id))) await refreshKeepScroll();
              break;
          }
        } catch (e) { toast(e.message, true); }
      };
    });
  });
}

/**
 * 文字起こしの見積もりを表示し、実行できるようにする。
 * @param {HTMLElement} box 表示先
 * @param {string} sessionId 回のID
 * @returns {Promise<void>}
 */
async function renderEstimate(box, sessionId) {
  let est;
  try { est = await api("GET", `/api/sessions/${sessionId}/transcribe/estimate`); }
  catch (e) { box.innerHTML = `<span class="warn-text">${h(e.message)}</span>`; return; }

  // 実行中なら進み具合を表示する
  if (est.job.state === "running") { showJobProgress(box, sessionId); return; }

  // 準備ができていなければ理由を出す
  const problems = [];
  if (!est.audio_exists) problems.push("音声ファイルを選んでください。");
  if (!est.ffmpeg) problems.push("ffmpeg が見つかりません（requirements.txt のパッケージを入れ直してください）。");
  if (!est.azure_ok) problems.push(est.azure_message);
  const last = est.job.state === "error" || est.job.state === "done"
    ? `<p class="${est.job.state === "error" ? "warn-text" : ""}">前回の実行：${h(est.job.message)}</p>` : "";
  if (problems.length) { box.innerHTML = `${last}<ul>${problems.map((p) => `<li>${h(p)}</li>`).join("")}</ul>`; return; }

  box.innerHTML = `${last}
    <table class="est">
      <tr><th>音声の長さ</th><td>${mmss(est.duration_sec)}</td></tr>
      <tr><th>分ける数</th><td>${est.chunks}つ（約6分ずつ。済んでいる分 ${est.done_chunks}つ）</td></tr>
      <tr><th>Azure の呼び出し</th><td><b>${est.calls}回</b>（${h(est.model)}）</td></tr>
      <tr><th>料金の目安</th><td>約${est.cost_usd[0]}〜${est.cost_usd[1]}ドル（約${est.cost_jpy[0]}〜${est.cost_jpy[1]}円）。公式の単価は未確認の概算です</td></tr>
      <tr><th>時間の目安</th><td>約${mmss(est.est_sec)}</td></tr>
    </table>
    ${est.existing_utterances ? `<p class="warn-text">この回にはすでに${est.existing_utterances}件の発言があります。実行すると置き換えます（前の内容は data/backups に保存します）。</p>` : ""}
    <p class="muted">音声は日本国外（Azure のグローバルデプロイ）で処理されます。結果は文ごとの発言として保存され、発言者は空になります。</p>
    <div class="actions run-actions">
      <label><input type="checkbox" id="tr-prompt"> 用語集の用語をヒントとして渡す</label>
      <button class="primary" id="tr-start" ${est.calls === 0 && !est.done_chunks ? "disabled" : ""}>文字起こしを実行</button>
    </div>`;

  box.querySelector("#tr-start").onclick = async () => {
    const ok = await confirmDialog(
      `Azure の ${est.model} を${est.calls}回呼び出します。\n料金の目安：約${est.cost_jpy[0]}〜${est.cost_jpy[1]}円\n時間の目安：約${mmss(est.est_sec)}` +
      (est.existing_utterances ? `\n\n今の${est.existing_utterances}件の発言は置き換えます（バックアップを残します）。` : ""));
    if (!ok) return;
    try {
      await api("POST", `/api/sessions/${sessionId}/transcribe`, { confirm: true, use_prompt: box.querySelector("#tr-prompt").checked });
      showJobProgress(box, sessionId);
    } catch (e) { toast(e.message, true); }
  };
}

/**
 * 文字起こしの進み具合を2秒ごとに表示し、終わったら画面を描き直す。
 * @param {HTMLElement} box 表示先
 * @param {string} sessionId 回のID
 * @returns {void}
 */
function showJobProgress(box, sessionId) {
  const update = async () => {
    const job = await api("GET", `/api/sessions/${sessionId}/transcribe/status`);
    box.innerHTML = `<p><b>文字起こし中</b>（${job.done}/${job.total || "?"}）：${h(job.message)}</p>
      <p class="muted">この画面を離れても処理は続きます。</p>`;
    if (job.state !== "running") {
      clearInterval(timers.poll);
      timers.poll = null;
      toast(job.message, job.state === "error");
      await refreshKeepScroll();
    }
  };
  clearInterval(timers.poll);
  timers.poll = setInterval(update, 2000);
  update();
}

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

// ------------------------------------------------------------------ 画面の切り替え

/**
 * URL の # 以降に応じて画面を表示する。
 * @returns {Promise<void>}
 */
async function route() {
  const main = document.getElementById("main");
  const [, page, id] = (location.hash || "#/").split("/");

  // 前の画面のタイマーを止める
  clearInterval(timers.live);
  timers.live = null;
  if (page !== "transcript") { clearInterval(timers.poll); timers.poll = null; }

  // 本人向けの表示では、メニューなどを隠す
  document.body.classList.toggle("screen-mode", page === "screen");

  // 左のメニューの選択を合わせる
  const navKey = { "": "home", person: "home", session: "home", live: "home", transcript: "home" }[page] ?? page;
  document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === navKey));

  try {
    switch (page) {
      case "person": renderPerson(main, id); break;
      case "session": await renderSession(main, id); break;
      case "live": renderLive(main, id); break;
      case "screen": renderScreen(main, id); break;
      case "transcript": await renderTranscript(main, id); break;
      case "issues": renderIssues(main); break;
      case "data": renderSources(main); break;
      case "common": renderCommon(main); break;
      case "terms": renderTerms(main); break;
      case "io": renderIo(main); break;
      case "overview": await renderOverview(main); break;
      case "evaluation": await renderEvaluation(main); break;
      default: await renderHome(main);
    }
  } catch (e) {
    main.innerHTML = `<div class="notice">${h(e.message)}</div>`;
  }
}

// Markdown の入力欄の「記述」「プレビュー」の切り替え
document.addEventListener("click", (event) => {
  const tab = event.target.closest("[data-md-tab]");
  if (!tab) return;
  const editor = tab.closest(".md-editor");
  const textarea = editor.querySelector("textarea");
  const preview = editor.querySelector(".md-preview");
  const showPreview = tab.dataset.mdTab === "preview";

  // プレビューに切り替えるときは、今の記述を変換して表示する
  if (showPreview) preview.innerHTML = renderMarkdown(textarea.value) || '<p class="muted">（未入力）</p>';
  textarea.hidden = showPreview;
  preview.hidden = !showPreview;
  editor.querySelectorAll("[data-md-tab]").forEach((b) => b.classList.toggle("active", b === tab));
});

// 起動時にデータを読み込み、画面を表示する
window.addEventListener("hashchange", route);
reload().then(route).catch((e) => toast(e.message, true));
