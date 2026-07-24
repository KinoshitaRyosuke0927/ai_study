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

const dmTargetUsername = document.getElementById("dm-target-username");
const dmInput           = document.getElementById("dm-input");
const dmSubmitBtn       = document.getElementById("dm-submit-btn");
const dmMessage         = document.getElementById("dm-message");

// ============================================================
// 状態管理
// ============================================================

let fetchedPosts = [];
let selectedPostId = null;
let selectedPostMessage = null;
let selectedPostUsername = null;

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
      body: JSON.stringify({ message: selectedPostMessage, author_username: selectedPostUsername }),
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

/** settings.ini の設定(対象チャンネル・取得期間)を画面に反映し、履歴取得を自動実行する */
async function applySettingsAndFetch() {
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

    await fetchAndRenderPosts();
  } catch (err) {
    showMessage(postsMessage, `settings.iniの読み込みに失敗しました: ${err.message}`, "error");
  }
}

async function init() {
  await loadChannels();
  loadTargetUsername();
  await applySettingsAndFetch();
}

init();
