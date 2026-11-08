/* ヒアリング管理ツールの画面：ダイアログ、編集フォーム、Markdown の表示
 *
 * 元は app.js の一部。ファイルをまたいで関数と定数を共有するため、index.html での読み込み順を変えないこと。
 */

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

