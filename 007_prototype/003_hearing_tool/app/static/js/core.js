/* ヒアリング管理ツールの画面：状態、選択肢、フォームの定義、共通の処理（最初に読み込む）
 *
 * データは小さいので、最初にすべてのテーブルを受け取り、画面ごとに組み立てて表示する。
 * 書き込みのたびにデータを読み直す。
 * ファイルをまたいで関数と定数を共有するため、index.html での読み込み順を変えないこと。
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

