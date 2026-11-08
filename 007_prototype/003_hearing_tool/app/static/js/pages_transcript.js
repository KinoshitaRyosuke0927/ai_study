/* ヒアリング管理ツールの画面：画面：文字起こしと推敲
 *
 * 元は app.js の一部。ファイルをまたいで関数と定数を共有するため、index.html での読み込み順を変えないこと。
 */

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

