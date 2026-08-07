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

const channelSelect  = document.getElementById("channel-select");
const startDateInput = document.getElementById("start-date");
const endDateInput   = document.getElementById("end-date");
const fetchPostsBtn  = document.getElementById("fetch-posts-btn");
const postsMessage   = document.getElementById("posts-message");

const postList = document.getElementById("post-list");

const postDetail   = document.getElementById("post-detail");
const reminderBtn  = document.getElementById("reminder-btn");
const reminderMessage = document.getElementById("reminder-message");

const dmSection         = document.getElementById("dm-section");
const dmTargetUsername = document.getElementById("dm-target-username");
const dmInput           = document.getElementById("dm-input");
const dmSubmitBtn       = document.getElementById("dm-submit-btn");
const dmMessage         = document.getElementById("dm-message");

const tabBtnMattermost   = document.getElementById("tab-btn-mattermost");
const tabBtnGroupsession = document.getElementById("tab-btn-groupsession");
const tabMattermost      = document.getElementById("tab-mattermost");
const tabGroupsession    = document.getElementById("tab-groupsession");

const dmSlotMattermost   = document.getElementById("dm-slot-mattermost");
const dmSlotGroupsession = document.getElementById("dm-slot-groupsession");

const gsStartDateInput = document.getElementById("gs-start-date");
const gsEndDateInput   = document.getElementById("gs-end-date");
const gsFetchBtn      = document.getElementById("gs-fetch-btn");
const gsMessage       = document.getElementById("gs-message");
const gsPostList      = document.getElementById("gs-post-list");
const gsPostDetail    = document.getElementById("gs-post-detail");
const gsReminderBtn   = document.getElementById("gs-reminder-btn");
const gsReminderMessage = document.getElementById("gs-reminder-message");

const tabBtnAgenda = document.getElementById("tab-btn-agenda");
const tabAgenda     = document.getElementById("tab-agenda");

const agendaStartDateInput = document.getElementById("agenda-start-date");
const agendaEndDateInput   = document.getElementById("agenda-end-date");
const agendaFetchBtn       = document.getElementById("agenda-fetch-btn");
const agendaMessage        = document.getElementById("agenda-message");
const agendaPostList       = document.getElementById("agenda-post-list");
const agendaPostDetail     = document.getElementById("agenda-post-detail");
const agendaCreateBtn      = document.getElementById("agenda-create-btn");
const agendaDetailMessage  = document.getElementById("agenda-detail-message");
const agendaOutput         = document.getElementById("agenda-output");
const agendaOutputMessage  = document.getElementById("agenda-output-message");
const agendaPublishYearInput  = document.getElementById("agenda-publish-year");
const agendaPublishMonthInput = document.getElementById("agenda-publish-month");
const agendaPublishBtn        = document.getElementById("agenda-publish-btn");
const agendaPublishMessage    = document.getElementById("agenda-publish-message");

// ============================================================
// 状態管理
// ============================================================

let fetchedPosts = [];
let selectedPostId = null;
let selectedPostMessage = null;
let selectedPostUsername = null;

let gsSelectedPostMessage = null;
let gsSelectedPostUsername = null;
let gsSelectedPostUrl = null;

let agendaFetchedPosts = [];

// ============================================================
// タブ切り替え
// ============================================================

function switchTab(tabName) {
  const isMattermost = tabName === "mattermost";
  const isGroupsession = tabName === "groupsession";
  const isAgenda = tabName === "agenda";

  tabBtnMattermost.classList.toggle("active", isMattermost);
  tabBtnGroupsession.classList.toggle("active", isGroupsession);
  tabBtnAgenda.classList.toggle("active", isAgenda);
  tabMattermost.classList.toggle("active", isMattermost);
  tabGroupsession.classList.toggle("active", isGroupsession);
  tabAgenda.classList.toggle("active", isAgenda);

  // DM投稿エリアは共通なので、選択中タブの右パネル下半分へ実体を移動する
  // (アジェンダタブにはDM投稿エリアが無いため、その場合は移動しない)
  if (isMattermost) {
    dmSlotMattermost.appendChild(dmSection);
  } else if (isGroupsession) {
    dmSlotGroupsession.appendChild(dmSection);
  }
}

tabBtnMattermost.addEventListener("click", () => switchTab("mattermost"));
tabBtnGroupsession.addEventListener("click", () => switchTab("groupsession"));
tabBtnAgenda.addEventListener("click", () => switchTab("agenda"));

// ============================================================
// チャンネル一覧の取得
// ============================================================

async function loadChannels() {
  try {
    const res = await fetch("/api/channels");
    const data = await res.json();
    if (!res.ok) {
      showMessage(postsMessage, `エラー: ${data.detail}`, "error");
      return;
    }

    if (data.length === 0) {
      channelSelect.innerHTML = `<option value="">参加チャンネルがありません</option>`;
      return;
    }

    channelSelect.innerHTML = `<option value="">選択してください</option>`;

    const groupsByTeam = new Map();
    data.forEach((channel) => {
      if (!groupsByTeam.has(channel.team_name)) {
        groupsByTeam.set(channel.team_name, []);
      }
      groupsByTeam.get(channel.team_name).push(channel);
    });

    groupsByTeam.forEach((channels, teamName) => {
      const group = document.createElement("optgroup");
      group.label = teamName;
      channels.forEach((channel) => {
        const option = document.createElement("option");
        option.value = channel.id;
        option.textContent = channel.name;
        group.appendChild(option);
      });
      channelSelect.appendChild(group);
    });
  } catch (err) {
    showMessage(postsMessage, `ネットワークエラー: ${err.message}`, "error");
  }
}

channelSelect.addEventListener("change", () => {
  fetchPostsBtn.disabled = !channelSelect.value;
});

// ============================================================
// 履歴の取得
// ============================================================

async function fetchAndRenderPosts() {
  hideMessage(postsMessage);
  postList.innerHTML = "";
  resetPostDetail();

  const channelId = channelSelect.value;
  const start = startDateInput.value;
  const end = endDateInput.value;
  if (!channelId) {
    showMessage(postsMessage, "チャンネルを選択してください", "error");
    return;
  }
  if (!start || !end) {
    showMessage(postsMessage, "取得開始日・取得終了日を選択してください", "error");
    return;
  }

  fetchPostsBtn.disabled = true;
  fetchPostsBtn.textContent = "取得中...";

  try {
    const res = await fetch(
      `/api/channels/${encodeURIComponent(channelId)}/posts?start=${start}&end=${end}`
    );
    const data = await res.json();
    if (!res.ok) {
      showMessage(postsMessage, `エラー: ${data.detail}`, "error");
      return;
    }

    fetchedPosts = data;

    if (data.length === 0) {
      postList.innerHTML = `<p class="post-list-placeholder">指定期間内の投稿はありませんでした</p>`;
      return;
    }

    data.forEach((post) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "post-list-item";
      item.dataset.postId = post.id;
      item.innerHTML = `
        <div class="post-list-item-header">
          <span class="post-username">${post.username}</span>
          <span class="post-time">${formatTimestamp(post.create_at)}</span>
        </div>
        <div class="post-list-item-body"></div>
      `;
      item.querySelector(".post-list-item-body").textContent = truncateForPreview(post.message);
      item.addEventListener("click", () => selectPost(post, item));
      postList.appendChild(item);
    });
  } catch (err) {
    showMessage(postsMessage, `ネットワークエラー: ${err.message}`, "error");
  } finally {
    fetchPostsBtn.disabled = false;
    fetchPostsBtn.textContent = "履歴を取得";
  }
}

fetchPostsBtn.addEventListener("click", fetchAndRenderPosts);

// ============================================================
// 投稿の選択・詳細表示（リアクション含む）
// ============================================================

function resetPostDetail() {
  selectedPostId = null;
  selectedPostMessage = null;
  selectedPostUsername = null;
  reminderBtn.disabled = true;
  hideMessage(reminderMessage);
  postDetail.innerHTML = `<p class="post-detail-placeholder">左の一覧から投稿を選択してください</p>`;
}

async function selectPost(post, itemEl) {
  selectedPostId = post.id;
  selectedPostMessage = post.message;
  selectedPostUsername = post.username;
  reminderBtn.disabled = false;
  hideMessage(reminderMessage);

  document.querySelectorAll(".post-list-item").forEach((el) => el.classList.remove("selected"));
  itemEl.classList.add("selected");

  postDetail.innerHTML = `
    <div class="post-detail-header">
      <span class="post-username">${post.username}</span>
      <span class="post-time">${formatTimestamp(post.create_at)}</span>
    </div>
    <div class="post-detail-body"></div>
    <div class="post-reactions">
      <h3>リアクション</h3>
      <p class="post-reactions-loading">読み込み中...</p>
    </div>
  `;
  postDetail.querySelector(".post-detail-body").textContent = post.message;

  const reactionsEl = postDetail.querySelector(".post-reactions");
  try {
    const res = await fetch(`/api/posts/${encodeURIComponent(post.id)}/reactions`);
    const data = await res.json();
    if (!res.ok) {
      reactionsEl.innerHTML = `<h3>リアクション</h3><p class="post-reactions-error">取得に失敗しました: ${data.detail}</p>`;
      return;
    }

    if (data.length === 0) {
      reactionsEl.innerHTML = `<h3>リアクション</h3><p class="post-reactions-empty">リアクションはありません</p>`;
      return;
    }

    const list = data
      .map((r) => `<li><span class="reaction-emoji">:${r.emoji_name}:</span><span class="reaction-username">${r.username}</span></li>`)
      .join("");
    reactionsEl.innerHTML = `<h3>リアクション</h3><ul class="reaction-list">${list}</ul>`;
  } catch (err) {
    reactionsEl.innerHTML = `<h3>リアクション</h3><p class="post-reactions-error">ネットワークエラー: ${err.message}</p>`;
  }
}

// ============================================================
// リマインド文章の作成
// ============================================================

reminderBtn.addEventListener("click", async () => {
  hideMessage(reminderMessage);

  if (!selectedPostMessage) {
    showMessage(reminderMessage, "投稿を選択してください", "error");
    return;
  }

  reminderBtn.disabled = true;
  reminderBtn.textContent = "作成中...";

  try {
    const res = await fetch("/api/reminder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source: "mattermost",
        post_id: selectedPostId,
        message: selectedPostMessage,
        author_username: selectedPostUsername,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      showMessage(reminderMessage, `エラー: ${data.detail}`, "error");
      return;
    }
    dmInput.value = data.reminder;
    showMessage(reminderMessage, "リマインド文章をDM入力欄に反映しました。", "success");
  } catch (err) {
    showMessage(reminderMessage, `ネットワークエラー: ${err.message}`, "error");
  } finally {
    reminderBtn.disabled = false;
    reminderBtn.textContent = "リマインドを作成";
  }
});

// ============================================================
// GROUPSESSION: 新着記事の取得
// ============================================================

function resetGroupsessionDetail() {
  gsSelectedPostMessage = null;
  gsSelectedPostUsername = null;
  gsSelectedPostUrl = null;
  gsReminderBtn.disabled = true;
  hideMessage(gsReminderMessage);
  gsPostDetail.innerHTML = `<p class="post-detail-placeholder">左の一覧から記事を選択してください</p>`;
}

function selectGroupsessionPost(post, itemEl) {
  gsSelectedPostMessage = post.message;
  gsSelectedPostUsername = post.username;
  gsSelectedPostUrl = post.url;
  gsReminderBtn.disabled = false;
  hideMessage(gsReminderMessage);

  gsPostList.querySelectorAll(".post-list-item").forEach((el) => el.classList.remove("selected"));
  itemEl.classList.add("selected");

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

  gsPostDetail.innerHTML = `
    <div class="post-detail-header">
      <span class="post-username">${post.username}</span>
      <span class="post-time">${formatTimestamp(post.create_at)}</span>
    </div>
    <div class="post-detail-body post-detail-body-html">${post.detail_html || ""}</div>
    ${attachmentsHtml}
  `;
}

async function fetchAndRenderGroupsessionPosts() {
  hideMessage(gsMessage);
  gsPostList.innerHTML = "";
  resetGroupsessionDetail();

  const start = gsStartDateInput.value;
  const end = gsEndDateInput.value;
  if (!start || !end) {
    showMessage(gsMessage, "取得開始日・取得終了日を選択してください", "error");
    return;
  }

  gsFetchBtn.disabled = true;
  gsFetchBtn.textContent = "取得中...";

  try {
    const res = await fetch(
      `/api/webpage/announcements?start=${start}&end=${end}`
    );
    const data = await res.json();
    if (!res.ok) {
      showMessage(gsMessage, `エラー: ${data.detail}`, "error");
      return;
    }

    if (data.length === 0) {
      gsPostList.innerHTML = `<p class="post-list-placeholder">対象期間内にリマインド対象の記事はありませんでした</p>`;
      return;
    }

    data.forEach((post) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "post-list-item";
      item.innerHTML = `
        <div class="post-list-item-header">
          <span class="post-username">${post.username}</span>
          <span class="post-time">${formatTimestamp(post.create_at)}</span>
        </div>
        <div class="post-list-item-body"></div>
      `;
      item.querySelector(".post-list-item-body").textContent = truncateForPreview(post.message);
      item.addEventListener("click", () => selectGroupsessionPost(post, item));
      gsPostList.appendChild(item);
    });
  } catch (err) {
    showMessage(gsMessage, `ネットワークエラー: ${err.message}`, "error");
  } finally {
    gsFetchBtn.disabled = false;
    gsFetchBtn.textContent = "新着記事を取得";
  }
}

gsFetchBtn.addEventListener("click", fetchAndRenderGroupsessionPosts);

// ============================================================
// GROUPSESSION: リマインド文章の作成
// ============================================================

gsReminderBtn.addEventListener("click", async () => {
  hideMessage(gsReminderMessage);

  if (!gsSelectedPostMessage) {
    showMessage(gsReminderMessage, "記事を選択してください", "error");
    return;
  }

  gsReminderBtn.disabled = true;
  gsReminderBtn.textContent = "作成中...";

  try {
    const res = await fetch("/api/reminder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source: "web",
        message: gsSelectedPostMessage,
        author_username: gsSelectedPostUsername,
        source_url: gsSelectedPostUrl,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      showMessage(gsReminderMessage, `エラー: ${data.detail}`, "error");
      return;
    }
    dmInput.value = data.reminder;
    showMessage(gsReminderMessage, "リマインド文章をDM入力欄に反映しました。", "success");
  } catch (err) {
    showMessage(gsReminderMessage, `ネットワークエラー: ${err.message}`, "error");
  } finally {
    gsReminderBtn.disabled = false;
    gsReminderBtn.textContent = "リマインドを作成";
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

function selectAgendaPost(post, itemEl) {
  agendaCreateBtn.disabled = false;
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
  agendaPostList.innerHTML = "";

  if (agendaFetchedPosts.length === 0) {
    agendaPostList.innerHTML = `<p class="post-list-placeholder">指定期間内の投稿・記事はありませんでした</p>`;
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
    item
      .querySelector(".post-list-item-main")
      .addEventListener("click", () => selectAgendaPost(post, item));
    agendaPostList.appendChild(item);
  });
}

async function fetchAndRenderAgendaPosts() {
  hideMessage(agendaMessage);
  resetAgendaDetail();

  const channelId = channelSelect.value;
  const start = agendaStartDateInput.value;
  const end = agendaEndDateInput.value;
  if (!channelId) {
    showMessage(agendaMessage, "Mattermostのチャンネルが選択されていません(Mattermostタブを確認してください)", "error");
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
    const [mattermostRes, groupsessionRes] = await Promise.all([
      fetch(`/api/channels/${encodeURIComponent(channelId)}/posts?start=${start}&end=${end}`),
      fetch(`/api/webpage/announcements?start=${start}&end=${end}`),
    ]);
    const mattermostData = await mattermostRes.json();
    const groupsessionData = await groupsessionRes.json();

    if (!mattermostRes.ok) {
      showMessage(agendaMessage, `Mattermostの取得エラー: ${mattermostData.detail}`, "error");
      return;
    }
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

  try {
    const res = await fetch("/api/agenda/publish", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agenda, year, month }),
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
// DM投稿
// ============================================================

dmSubmitBtn.addEventListener("click", async () => {
  hideMessage(dmMessage);
  const message = dmInput.value.trim();
  if (!message) {
    showMessage(dmMessage, "メッセージを入力してください", "error");
    return;
  }

  dmSubmitBtn.disabled = true;
  dmSubmitBtn.textContent = "送信中...";

  try {
    const res = await fetch("/api/dm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    const data = await res.json();
    if (!res.ok) {
      showMessage(dmMessage, `エラー: ${data.detail}`, "error");
      return;
    }
    showMessage(dmMessage, "投稿しました。", "success");
    dmInput.value = "";
  } catch (err) {
    showMessage(dmMessage, `ネットワークエラー: ${err.message}`, "error");
  } finally {
    dmSubmitBtn.disabled = false;
    dmSubmitBtn.textContent = "投稿";
  }
});

// ============================================================
// 初期化
// ============================================================

async function loadTargetUsername() {
  try {
    const res = await fetch("/api/target-username");
    const data = await res.json();
    dmTargetUsername.textContent = data.username;
  } catch (err) {
    dmTargetUsername.textContent = "(取得失敗)";
  }
}

/** "YYYY-MM-DD" 形式の文字列を返す */
function toDateInputValue(date) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** settings.ini の設定(対象チャンネル・取得期間)を画面に反映する(履歴取得は自動実行しない) */
async function applySettings() {
  try {
    const res = await fetch("/api/settings");
    const settings = await res.json();
    if (!settings.channel) return;

    const matched = Array.from(channelSelect.options).find(
      (opt) => opt.value && opt.textContent.trim() === settings.channel.trim()
    );
    if (!matched) {
      showMessage(postsMessage, `settings.iniのチャンネル「${settings.channel}」が見つかりませんでした`, "error");
      return;
    }
    channelSelect.value = matched.value;
    fetchPostsBtn.disabled = false;

    const readDate = settings.read_date || 30;
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - (readDate - 1));
    startDateInput.value = toDateInputValue(start);
    endDateInput.value = toDateInputValue(end);
  } catch (err) {
    showMessage(postsMessage, `settings.iniの読み込みに失敗しました: ${err.message}`, "error");
  }
}

/** settings.ini の設定(GROUPSESSIONの取得期間)を画面に反映する */
async function applyGroupsessionSettings() {
  try {
    const res = await fetch("/api/settings");
    const settings = await res.json();

    const readDate = settings.groupsession_read_date || 30;
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - (readDate - 1));
    gsStartDateInput.value = toDateInputValue(start);
    gsEndDateInput.value = toDateInputValue(end);
  } catch (err) {
    showMessage(gsMessage, `settings.iniの読み込みに失敗しました: ${err.message}`, "error");
  }
}

/** settings.ini の設定(Mattermost・GROUPSESSIONそれぞれの取得期間のうち長い方)をアジェンダタブの期間初期値に反映する */
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
  } catch (err) {
    showMessage(agendaMessage, `settings.iniの読み込みに失敗しました: ${err.message}`, "error");
  }
}

async function init() {
  dmSlotMattermost.appendChild(dmSection);

  await loadChannels();
  loadTargetUsername();
  await applySettings();
  await applyGroupsessionSettings();
  await applyAgendaSettings();
}

init();
