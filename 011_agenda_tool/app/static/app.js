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
  agendaCreateBtn.disabled = true;
  hideMessage(agendaDetailMessage);
  agendaPostDetail.innerHTML = `<p class="post-detail-placeholder">左の一覧から投稿・記事を選択してください</p>`;
}

/** チェック済みの投稿・記事が1件以上あるかどうかで「アジェンダを作成」ボタンの活性状態を切り替える */
function updateAgendaCreateBtnState() {
  const hasChecked = agendaPostList.querySelector(".agenda-item-checkbox:checked") !== null;
  agendaCreateBtn.disabled = !hasChecked;
}

function selectAgendaPost(post, itemEl) {
  hideMessage(agendaDetailMessage);

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
  const checkedIds = new Set(
    Array.from(agendaPostList.querySelectorAll(".agenda-item-checkbox:checked")).map(
      (checkbox) => checkbox.closest(".agenda-list-item").dataset.postId
    )
  );

  agendaPostList.innerHTML = "";

  if (agendaFetchedPosts.length === 0) {
    agendaPostList.innerHTML = `<p class="post-list-placeholder">指定期間内の投稿・記事はありませんでした</p>`;
    updateAgendaCreateBtnState();
    return;
  }

  agendaFetchedPosts.forEach((post) => {
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
    if (checkedIds.has(post.id)) {
      item.querySelector(".agenda-item-checkbox").checked = true;
    }
    item
      .querySelector(".post-list-item-main")
      .addEventListener("click", () => selectAgendaPost(post, item));
    item
      .querySelector(".agenda-item-checkbox")
      .addEventListener("change", updateAgendaCreateBtnState);
    agendaPostList.appendChild(item);
  });

  updateAgendaCreateBtnState();
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

  const checkedIds = Array.from(
    agendaPostList.querySelectorAll(".agenda-item-checkbox:checked")
  ).map((checkbox) => checkbox.closest(".agenda-list-item").dataset.postId);

  if (checkedIds.length === 0) {
    showMessage(agendaOutputMessage, "アジェンダに含める投稿・記事にチェックを入れてください", "error");
    return;
  }

  const items = agendaFetchedPosts
    .filter((post) => checkedIds.includes(post.id))
    .map((post) => ({
      message: post.message,
      username: post.username,
      source: post.source,
      url: post.url || null,
    }));

  agendaCreateBtn.disabled = true;
  agendaCreateBtn.textContent = "作成中...";

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
    agendaCreateBtn.disabled = false;
    agendaCreateBtn.textContent = "アジェンダを作成";
  }
});

// ============================================================
// アジェンダのwiki公開
// ============================================================

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
    showMessage(agendaPublishMessage, `wikiへ公開しました: ${data.url}`, "success");
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
