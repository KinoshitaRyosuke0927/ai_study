// ============================================================
// ユーティリティ
// ============================================================

function showMessage(div, text, type) {
  div.textContent = text;
  div.className = `message ${type}`;
}

function hideMessage(div) {
  div.className = "message hidden";
}

function formatTimestamp(epochMs) {
  const d = new Date(epochMs);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const POST_PREVIEW_LENGTH = 40;

/** 一覧表示用に、投稿本文の先頭を切り詰めたプレビュー文字列を返す */
function truncateForPreview(text) {
  const singleLine = text.replace(/\s+/g, " ").trim();
  if (singleLine.length <= POST_PREVIEW_LENGTH) return singleLine;
  return `${singleLine.slice(0, POST_PREVIEW_LENGTH)}...`;
}


// ============================================================
// DOM 参照
// ============================================================

const filterStrengthSlider = document.getElementById("filter-strength-slider");
const filterStrengthValue  = document.getElementById("filter-strength-value");

const gsLoginOpenBtn       = document.getElementById("gs-login-open-btn");
const gsLoginModalOverlay  = document.getElementById("gs-login-modal-overlay");
const gsLoginUsernameInput = document.getElementById("gs-login-username");
const gsLoginPasswordInput = document.getElementById("gs-login-password");
const gsLoginBtn           = document.getElementById("gs-login-btn");
const gsLoginCancelBtn     = document.getElementById("gs-login-cancel-btn");
const gsLoginMessage       = document.getElementById("gs-login-message");

const agendaStartDateInput = document.getElementById("agenda-start-date");
const agendaEndDateInput   = document.getElementById("agenda-end-date");
const agendaFetchBtn       = document.getElementById("agenda-fetch-btn");
const agendaMessage        = document.getElementById("agenda-message");
const agendaPostList       = document.getElementById("agenda-post-list");
const agendaSortDateBtn     = document.getElementById("agenda-sort-date-btn");
const agendaSortUsernameBtn = document.getElementById("agenda-sort-username-btn");
const agendaSortSourceBtn   = document.getElementById("agenda-sort-source-btn");
const agendaViewAllBtn       = document.getElementById("agenda-view-all-btn");
const agendaViewCheckedBtn   = document.getElementById("agenda-view-checked-btn");
const agendaViewAllCount     = document.getElementById("agenda-view-all-count");
const agendaViewCheckedCount = document.getElementById("agenda-view-checked-count");
const agendaPostDetail     = document.getElementById("agenda-post-detail");
const agendaCreateBtn      = document.getElementById("agenda-create-btn");
const agendaDetailMessage  = document.getElementById("agenda-detail-message");
const agendaOutput         = document.getElementById("agenda-output");
const agendaOutputMessage  = document.getElementById("agenda-output-message");
const agendaPublishYearInput  = document.getElementById("agenda-publish-year");
const agendaPublishMonthInput = document.getElementById("agenda-publish-month");
const agendaPublishBtn        = document.getElementById("agenda-publish-btn");
const agendaPublishMessage    = document.getElementById("agenda-publish-message");
const agendaPublishGrantToggle = document.getElementById("agenda-publish-grant-toggle");

// ============================================================
// 状態管理
// ============================================================

let agendaFetchedPosts = [];
// アジェンダに含めるようチェックした投稿・記事のID。
// 「選択済みのみ」表示で一覧から隠れた項目のチェックも保持するため、DOMではなくここで管理する
let agendaCheckedIds = new Set();
// 一覧を「選択済みのみ」で表示しているかどうか
let agendaShowCheckedOnly = false;
// 詳細を表示中の投稿・記事のID(並び替え・表示切り替えで再描画した後も選択状態を残すため)
let agendaSelectedPostId = null;
let agendaChannelIds = [];
// 参加チャンネルの一覧(/api/channels の取得結果)。settings.ini のチャンネル名からIDを引くために使う
let joinedChannels = [];

// ============================================================
// チャンネル一覧の取得
// ============================================================

/** 参加チャンネルの一覧を取得し、joinedChannels に保持する */
async function loadChannels() {
  try {
    const res = await fetch("/api/channels");
    const data = await res.json();
    if (!res.ok) {
      showMessage(agendaMessage, `エラー: ${data.detail}`, "error");
      return;
    }
    joinedChannels = data;
  } catch (err) {
    showMessage(agendaMessage, `ネットワークエラー: ${err.message}`, "error");
  }
}

// ============================================================
// フィルタ強度
// ============================================================

filterStrengthSlider.addEventListener("input", () => {
  filterStrengthValue.textContent = filterStrengthSlider.value;
});

/** スライダーで設定されたフィルタ強度(0〜1)を返す */
function getFilterThreshold() {
  return filterStrengthSlider.value;
}

// ============================================================
// GROUPSESSION: ログイン(モーダル)
// ============================================================

function openGroupsessionLoginModal() {
  hideMessage(gsLoginMessage);
  gsLoginPasswordInput.value = "";
  gsLoginModalOverlay.classList.remove("hidden");
  gsLoginUsernameInput.focus();
}

function closeGroupsessionLoginModal() {
  gsLoginModalOverlay.classList.add("hidden");
}

/** GROUPSESSIONログイン状態を、ログインボタンの表示・新着記事取得ボタンの活性状態に反映する */
function updateGroupsessionLoginUi(loggedIn) {
  gsLoginOpenBtn.textContent = loggedIn ? "GROUPSESSIONログイン済" : "GROUPSESSIONログイン";
  gsLoginOpenBtn.classList.toggle("logged-in", loggedIn);
  agendaFetchBtn.disabled = !loggedIn;
}

async function loadGroupsessionLoginStatus() {
  try {
    const res = await fetch("/api/groupsession/login-status");
    const data = await res.json();
    updateGroupsessionLoginUi(Boolean(data.logged_in));
  } catch (err) {
    updateGroupsessionLoginUi(false);
  }
}

gsLoginOpenBtn.addEventListener("click", openGroupsessionLoginModal);
gsLoginCancelBtn.addEventListener("click", closeGroupsessionLoginModal);

gsLoginModalOverlay.addEventListener("click", (event) => {
  if (event.target === gsLoginModalOverlay) {
    closeGroupsessionLoginModal();
  }
});

gsLoginBtn.addEventListener("click", async () => {
  hideMessage(gsLoginMessage);

  const username = gsLoginUsernameInput.value.trim();
  const password = gsLoginPasswordInput.value;
  if (!username || !password) {
    showMessage(gsLoginMessage, "IDとパスワードを入力してください", "error");
    return;
  }

  gsLoginBtn.disabled = true;
  gsLoginBtn.textContent = "ログイン中...";

  try {
    const res = await fetch("/api/groupsession/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      showMessage(gsLoginMessage, `エラー: ${data.detail}`, "error");
      return;
    }
    gsLoginPasswordInput.value = "";
    updateGroupsessionLoginUi(true);
    closeGroupsessionLoginModal();
  } catch (err) {
    showMessage(gsLoginMessage, `ネットワークエラー: ${err.message}`, "error");
  } finally {
    gsLoginBtn.disabled = false;
    gsLoginBtn.textContent = "ログイン";
  }
});


// ============================================================
// アジェンダ: Mattermost履歴・GROUPSESSION新着記事の取得
// ============================================================

function resetAgendaDetail() {
  agendaSelectedPostId = null;
  hideMessage(agendaDetailMessage);
  agendaPostDetail.innerHTML = `<p class="post-detail-placeholder">左の一覧から投稿・記事を選択してください</p>`;
  updateAgendaCreateBtnState();
}

/**
 * 「アジェンダを作成」ボタンの表示(件数)と活性状態を、チェック済みの件数に合わせて更新する
 *
 * Args:
 *   label: string  ボタンの文言(省略時は「アジェンダを作成」。作成中は「作成中...」を渡す)
 */
function updateAgendaCreateBtnState(label = "アジェンダを作成") {
  // 作成中(処理待ち)の間は文言・非活性のまま変えない
  if (agendaCreateBtn.dataset.busy === "true") return;

  // チェック済みの件数をボタンの文言に添える(0件のときは件数を出さない)
  const count = agendaCheckedIds.size;
  agendaCreateBtn.textContent = count > 0 ? `${label}(${count}件)` : label;
  // 1件以上チェックしているときだけ活性化する
  agendaCreateBtn.disabled = count === 0;
}

/** 一覧の表示切り替えボタン(すべて / 選択済み)の件数・選択状態を更新する */
function updateAgendaViewToggle() {
  // 件数を更新する
  agendaViewAllCount.textContent = agendaFetchedPosts.length;
  agendaViewCheckedCount.textContent = agendaCheckedIds.size;

  // 今どちらの表示かをボタンの見た目に反映する
  agendaViewAllBtn.classList.toggle("active", !agendaShowCheckedOnly);
  agendaViewCheckedBtn.classList.toggle("active", agendaShowCheckedOnly);
  agendaViewAllBtn.setAttribute("aria-pressed", String(!agendaShowCheckedOnly));
  agendaViewCheckedBtn.setAttribute("aria-pressed", String(agendaShowCheckedOnly));
}

/**
 * 一覧の表示を切り替えて再描画する
 *
 * Args:
 *   checkedOnly: boolean  true のときチェックした投稿・記事のみを表示する
 */
function setAgendaViewMode(checkedOnly) {
  agendaShowCheckedOnly = checkedOnly;
  renderAgendaPostList();
}

agendaViewAllBtn.addEventListener("click", () => setAgendaViewMode(false));
agendaViewCheckedBtn.addEventListener("click", () => setAgendaViewMode(true));

/**
 * 一覧のチェックボックスが変更されたときに、チェック状態を保持して表示を更新する
 *
 * Args:
 *   postId: string    変更された投稿・記事のID
 *   checked: boolean  変更後のチェック状態
 */
function onAgendaItemCheckChange(postId, checked) {
  // チェック状態を保持する
  if (checked) {
    agendaCheckedIds.add(postId);
  } else {
    agendaCheckedIds.delete(postId);
  }

  // 「選択済み」表示でチェックを外した項目は一覧から消すため、再描画する
  if (agendaShowCheckedOnly) {
    renderAgendaPostList();
    return;
  }
  // 「すべて」表示では一覧はそのままで、件数とボタンだけ更新する
  updateAgendaViewToggle();
  updateAgendaCreateBtnState();
}

function selectAgendaPost(post, itemEl) {
  hideMessage(agendaDetailMessage);

  // 選択中の投稿・記事を記録し、一覧の強調表示を付け替える
  agendaSelectedPostId = post.id;
  agendaPostList.querySelectorAll(".post-list-item").forEach((el) => el.classList.remove("selected"));
  itemEl.classList.add("selected");

  if (post.source === "web") {
    const attachments = post.attachments || [];
    const attachmentsHtml = attachments.length
      ? `
        <div class="post-attachments">
          <h3>添付ファイル</h3>
          <ul class="attachment-list">
            ${attachments
              .map(
                (a) =>
                  `<li><a href="${a.url}" target="_blank" rel="noopener">${a.name}</a> <span class="attachment-size">${a.size}</span></li>`
              )
              .join("")}
          </ul>
          <p class="attachment-note">※ダウンロードにはブラウザでGROUPSESSIONにログイン済みである必要があります</p>
        </div>
      `
      : "";

    agendaPostDetail.innerHTML = `
      <div class="post-detail-header">
        <span class="post-username">${post.username}</span>
        <span class="post-time">${formatTimestamp(post.create_at)}</span>
      </div>
      <div class="post-detail-body post-detail-body-html">${post.detail_html || ""}</div>
      ${attachmentsHtml}
    `;
  } else {
    agendaPostDetail.innerHTML = `
      <div class="post-detail-header">
        <span class="post-username">${post.username}</span>
        <span class="post-time">${formatTimestamp(post.create_at)}</span>
      </div>
      <div class="post-detail-body"></div>
    `;
    agendaPostDetail.querySelector(".post-detail-body").textContent = post.message;
  }
}

function renderAgendaPostList() {
  agendaPostList.innerHTML = "";
  // 件数・ボタンの表示を先に更新する
  updateAgendaViewToggle();
  updateAgendaCreateBtnState();

  // 取得結果が0件の場合はその旨を表示する
  if (agendaFetchedPosts.length === 0) {
    agendaPostList.innerHTML = `<p class="post-list-placeholder">指定期間内の投稿・記事はありませんでした</p>`;
    return;
  }

  // 表示モードに応じて、一覧に出す投稿・記事を絞り込む
  const visiblePosts = agendaShowCheckedOnly
    ? agendaFetchedPosts.filter((post) => agendaCheckedIds.has(post.id))
    : agendaFetchedPosts;
  if (visiblePosts.length === 0) {
    agendaPostList.innerHTML = `<p class="post-list-placeholder">チェックした投稿・記事はありません。「すべて」に切り替えてチェックを入れてください</p>`;
    return;
  }

  visiblePosts.forEach((post) => {
    const item = document.createElement("div");
    item.className = "post-list-item agenda-list-item";
    item.dataset.postId = post.id;
    item.innerHTML = `
      <input type="checkbox" class="agenda-item-checkbox">
      <div class="post-list-item-main">
        <div class="post-list-item-header">
          <span class="post-username">${post.username}</span>
          <span class="post-source-badge post-source-badge-${post.source}">${
      post.source === "web" ? "GROUPSESSION" : "Mattermost"
    }</span>
          <span class="post-time">${formatTimestamp(post.create_at)}</span>
        </div>
        <div class="post-list-item-body"></div>
      </div>
    `;
    item.querySelector(".post-list-item-body").textContent = truncateForPreview(post.message);
    // 保持しているチェック状態・詳細表示中の状態を復元する
    const checkbox = item.querySelector(".agenda-item-checkbox");
    checkbox.checked = agendaCheckedIds.has(post.id);
    if (post.id === agendaSelectedPostId) {
      item.classList.add("selected");
    }
    item
      .querySelector(".post-list-item-main")
      .addEventListener("click", () => selectAgendaPost(post, item));
    checkbox.addEventListener("change", () => onAgendaItemCheckChange(post.id, checkbox.checked));
    agendaPostList.appendChild(item);
  });
}

/** agendaFetchedPosts を指定の比較関数で並び替えて再描画する */
function sortAgendaPosts(compareFn) {
  agendaFetchedPosts = [...agendaFetchedPosts].sort(compareFn);
  renderAgendaPostList();
}

agendaSortDateBtn.addEventListener("click", () => {
  sortAgendaPosts((a, b) => a.create_at - b.create_at);
});

agendaSortUsernameBtn.addEventListener("click", () => {
  sortAgendaPosts((a, b) => a.username.localeCompare(b.username, "ja"));
});

agendaSortSourceBtn.addEventListener("click", () => {
  // GROUPSESSION(web)を上、Mattermostを下にする(グループ内の順序は維持)
  sortAgendaPosts((a, b) => (a.source === "web" ? 0 : 1) - (b.source === "web" ? 0 : 1));
});

async function fetchAndRenderAgendaPosts() {
  hideMessage(agendaMessage);
  // 取得し直すと一覧が入れ替わるため、チェック状態と表示モードを初期状態に戻す
  agendaCheckedIds = new Set();
  agendaShowCheckedOnly = false;
  agendaFetchedPosts = [];
  updateAgendaViewToggle();
  resetAgendaDetail();

  const start = agendaStartDateInput.value;
  const end = agendaEndDateInput.value;
  if (agendaChannelIds.length === 0) {
    showMessage(agendaMessage, "settings.iniのchannel_listに取得対象のチャンネルが設定されていません", "error");
    return;
  }
  if (!start || !end) {
    showMessage(agendaMessage, "取得開始日・取得終了日を選択してください", "error");
    return;
  }

  agendaFetchBtn.disabled = true;
  agendaFetchBtn.textContent = "取得中...";
  agendaPostList.innerHTML = "";

  try {
    const [mattermostResults, groupsessionRes] = await Promise.all([
      Promise.all(
        agendaChannelIds.map((channelId) =>
          fetch(`/api/channels/${encodeURIComponent(channelId)}/posts?start=${start}&end=${end}&threshold=${getFilterThreshold()}`)
        )
      ),
      fetch(`/api/webpage/announcements?start=${start}&end=${end}&threshold=${getFilterThreshold()}`),
    ]);

    const mattermostData = [];
    for (const res of mattermostResults) {
      const data = await res.json();
      if (!res.ok) {
        showMessage(agendaMessage, `Mattermostの取得エラー: ${data.detail}`, "error");
        return;
      }
      mattermostData.push(...data);
    }

    const groupsessionData = await groupsessionRes.json();
    if (!groupsessionRes.ok) {
      showMessage(agendaMessage, `GROUPSESSIONの取得エラー: ${groupsessionData.detail}`, "error");
      return;
    }

    agendaFetchedPosts = [
      ...mattermostData.map((post) => ({ ...post, source: "mattermost" })),
      ...groupsessionData.map((post) => ({ ...post, source: "web" })),
    ].sort((a, b) => a.create_at - b.create_at);

    renderAgendaPostList();
  } catch (err) {
    showMessage(agendaMessage, `ネットワークエラー: ${err.message}`, "error");
  } finally {
    agendaFetchBtn.disabled = false;
    agendaFetchBtn.textContent = "履歴・新着記事を取得";
  }
}

agendaFetchBtn.addEventListener("click", fetchAndRenderAgendaPosts);

// ============================================================
// アジェンダの作成
// ============================================================

agendaCreateBtn.addEventListener("click", async () => {
  hideMessage(agendaOutputMessage);

  // チェック状態は agendaCheckedIds で保持している(「選択済み」表示で隠れた項目も含む)
  if (agendaCheckedIds.size === 0) {
    showMessage(agendaOutputMessage, "アジェンダに含める投稿・記事にチェックを入れてください", "error");
    return;
  }

  const items = agendaFetchedPosts
    .filter((post) => agendaCheckedIds.has(post.id))
    .map((post) => ({
      message: post.message,
      username: post.username,
      source: post.source,
      url: post.url || null,
    }));

  // 作成中は件数を添えた「作成中...」表示にし、完了まで文言・非活性を固定する
  updateAgendaCreateBtnState("作成中...");
  agendaCreateBtn.disabled = true;
  agendaCreateBtn.dataset.busy = "true";

  try {
    const res = await fetch("/api/agenda", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items }),
    });
    const data = await res.json();
    if (!res.ok) {
      showMessage(agendaOutputMessage, `エラー: ${data.detail}`, "error");
      return;
    }
    agendaOutput.value = data.agenda;
    showMessage(agendaOutputMessage, "部会アジェンダを作成しました。", "success");

    const now = new Date();
    agendaPublishYearInput.value = now.getFullYear();
    agendaPublishMonthInput.value = now.getMonth() + 1;
    agendaPublishBtn.disabled = false;
    hideMessage(agendaPublishMessage);
  } catch (err) {
    showMessage(agendaOutputMessage, `ネットワークエラー: ${err.message}`, "error");
  } finally {
    // 作成中の固定を解除し、現在のチェック件数に合わせて表示を戻す
    delete agendaCreateBtn.dataset.busy;
    updateAgendaCreateBtnState();
  }
});

// ============================================================
// アジェンダのwiki公開
// ============================================================

/**
 * wiki公開の成功メッセージを、公開ページへのリンクと「URLをコピー」ボタン付きで表示する
 *
 * Args:
 *   data: object   /api/agenda/publish の戻り値({ path, url, recreated })
 *   year: number   公開先の年
 *   month: number  公開先の月
 */
function showPublishSuccessMessage(data, year, month) {
  // メッセージ欄を空にして成功表示にする
  agendaPublishMessage.textContent = "";
  agendaPublishMessage.className = "message success publish-success";

  // 本文: 「wikiへ公開しました:」+ 公開ページへのリンク(新しいタブで開く)
  const text = document.createElement("span");
  text.textContent = "wikiへ公開しました: ";
  const link = document.createElement("a");
  link.href = data.url;
  link.target = "_blank";
  link.rel = "noopener";
  link.className = "publish-link";
  link.textContent = `「${year}年${month}月度アジェンダ」を開く ↗`;
  link.title = data.url;
  text.appendChild(link);
  agendaPublishMessage.appendChild(text);

  // URLをコピーするボタン(チャット等に貼り付ける用途)
  const copyBtn = document.createElement("button");
  copyBtn.type = "button";
  copyBtn.className = "btn copy-url-btn";
  copyBtn.textContent = "URLをコピー";
  copyBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(data.url);
      copyBtn.textContent = "コピーしました";
    } catch {
      copyBtn.textContent = "コピーできませんでした";
    }
    // 少し経ったら文言を元に戻す
    setTimeout(() => { copyBtn.textContent = "URLをコピー"; }, 2000);
  });
  agendaPublishMessage.appendChild(copyBtn);

  // 公開範囲の変更でページを作り直した場合は、URLが変わったことを知らせる
  if (data.recreated) {
    const note = document.createElement("p");
    note.className = "publish-note";
    note.textContent = "※公開範囲を変更したためページを作成し直しました。以前のURLは使えなくなっています。";
    agendaPublishMessage.appendChild(note);
  }
}

agendaPublishBtn.addEventListener("click", async () => {
  hideMessage(agendaPublishMessage);

  const agenda = agendaOutput.value.trim();
  const year = Number(agendaPublishYearInput.value);
  const month = Number(agendaPublishMonthInput.value);

  if (!agenda) {
    showMessage(agendaPublishMessage, "公開するアジェンダがありません", "error");
    return;
  }
  if (!year || !month) {
    showMessage(agendaPublishMessage, "公開先の年・月を入力してください", "error");
    return;
  }

  agendaPublishBtn.disabled = true;
  agendaPublishBtn.textContent = "公開中...";

  const grant = agendaPublishGrantToggle.checked ? "only_me" : "public";

  try {
    const res = await fetch("/api/agenda/publish", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agenda, year, month, grant }),
    });
    const data = await res.json();
    if (!res.ok) {
      showMessage(agendaPublishMessage, `エラー: ${data.detail}`, "error");
      return;
    }
    showPublishSuccessMessage(data, year, month);
  } catch (err) {
    showMessage(agendaPublishMessage, `ネットワークエラー: ${err.message}`, "error");
  } finally {
    agendaPublishBtn.disabled = false;
    agendaPublishBtn.textContent = "wikiへ公開";
  }
});


// ============================================================
// 初期化
// ============================================================

/** "YYYY-MM-DD" 形式の文字列を返す */
function toDateInputValue(date) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** チャンネル一覧(joinedChannels)から、表示名が一致するチャンネルのIDを返す */
function getChannelIdByName(name) {
  const matched = joinedChannels.find((channel) => channel.name.trim() === name.trim());
  return matched ? matched.id : null;
}

/** settings.ini の設定(Mattermost・GROUPSESSIONそれぞれの取得期間のうち長い方・取得対象チャンネル)をアジェンダタブに反映する */
async function applyAgendaSettings() {
  try {
    const res = await fetch("/api/settings");
    const settings = await res.json();

    const readDate = Math.max(settings.read_date || 30, settings.groupsession_read_date || 30);
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - (readDate - 1));
    agendaStartDateInput.value = toDateInputValue(start);
    agendaEndDateInput.value = toDateInputValue(end);

    const channelNames = settings.agenda_mattermost_channels || [];
    agendaChannelIds = [];
    channelNames.forEach((name) => {
      const channelId = getChannelIdByName(name);
      if (!channelId) {
        showMessage(agendaMessage, `settings.iniのチャンネル「${name}」が見つかりませんでした`, "error");
        return;
      }
      agendaChannelIds.push(channelId);
    });
  } catch (err) {
    showMessage(agendaMessage, `settings.iniの読み込みに失敗しました: ${err.message}`, "error");
  }
}

async function init() {
  await loadChannels();
  await applyAgendaSettings();
  await loadGroupsessionLoginStatus();
}

init();

// ============================================================
// 右パネル上下エリアの高さ調整(ドラッグリサイズ)
// ============================================================

const V_RESIZER_MIN_HEIGHT = 80;

function setupVerticalResizer(resizer) {
  const prevEl = document.getElementById(resizer.dataset.prev);
  const nextEl = document.getElementById(resizer.dataset.next);
  if (!prevEl || !nextEl) return;

  resizer.addEventListener("mousedown", (downEvent) => {
    downEvent.preventDefault();

    const startY = downEvent.clientY;
    const startPrevHeight = prevEl.getBoundingClientRect().height;
    const startNextHeight = nextEl.getBoundingClientRect().height;
    const totalHeight = startPrevHeight + startNextHeight;

    resizer.classList.add("resizing");
    document.body.classList.add("resizing-vertical");

    function onMouseMove(moveEvent) {
      const delta = moveEvent.clientY - startY;
      const newPrevHeight = Math.min(
        totalHeight - V_RESIZER_MIN_HEIGHT,
        Math.max(V_RESIZER_MIN_HEIGHT, startPrevHeight + delta)
      );
      const newNextHeight = totalHeight - newPrevHeight;

      // flex-shrink/flex-growを有効にしておくことで、ドラッグ後にウィンドウサイズが
      // 変わっても、指定した高さ(比率の基準)を保ちつつ利用可能な高さに追従できる
      // (0 0 に固定すると、ウィンドウを縮めた際に親要素からはみ出してしまう)
      prevEl.style.flex = `1 1 ${newPrevHeight}px`;
      nextEl.style.flex = `1 1 ${newNextHeight}px`;
    }

    function onMouseUp() {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
      resizer.classList.remove("resizing");
      document.body.classList.remove("resizing-vertical");
    }

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  });
}

document.querySelectorAll(".v-resizer").forEach(setupVerticalResizer);
