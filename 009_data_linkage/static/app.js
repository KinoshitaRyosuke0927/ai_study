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

/** 日付文字列 "YYYY-MM-DD" を "M月D日" 形式に変換する */
function formatDateJp(dateStr) {
  if (!dateStr) return "";
  const [, m, d] = dateStr.split("-");
  return `${parseInt(m, 10)}月${parseInt(d, 10)}日`;
}

// ============================================================
// DOM 参照
// ============================================================

const viewDateInput     = document.getElementById("view-date");
const viewDatePreview   = document.getElementById("view-date-preview");
const viewSearchMessage = document.getElementById("view-search-message");

const cardDetailBody        = document.getElementById("card-detail-body");
const cardDetailPlaceholder = document.querySelector(".card-detail-placeholder");
const detailName            = document.getElementById("detail-name");
const detailDesc            = document.getElementById("detail-desc");
const detailUrl             = document.getElementById("detail-url");

const commentInput     = document.getElementById("comment-input");
const commentSubmitBtn = document.getElementById("comment-submit-btn");
const commentMessage   = document.getElementById("comment-message");

const createDescInput = document.getElementById("create-desc");
const createSubmitBtn = document.getElementById("create-submit-btn");
const createMessage   = document.getElementById("create-message");

// ============================================================
// 状態管理
// ============================================================

// settings.ini から起動時に確定するリスト ID・名前
let viewListId    = "";
let createListId   = "";
let createListName = "";

// リスト選択時に取得・キャッシュするカード一覧
let viewCards = [];

// 日付検索でヒットしたカードの ID
let selectedCardId = null;

// ============================================================
// カード情報の表示・非表示
// ============================================================

function showCardDetail(card) {
  selectedCardId = card.id;
  detailName.textContent = card.name;
  detailDesc.textContent = card.desc || "（説明なし）";
  detailUrl.href         = card.url;
  detailUrl.textContent  = card.url;
  cardDetailPlaceholder.classList.add("hidden");
  cardDetailBody.classList.remove("hidden");

  commentInput.disabled = false;
  commentInput.placeholder = "コメントを入力してください";
  commentSubmitBtn.disabled = false;
}

function resetCardDetail() {
  selectedCardId = null;
  cardDetailPlaceholder.classList.remove("hidden");
  cardDetailBody.classList.add("hidden");
  detailName.textContent = "";
  detailDesc.textContent = "";
  detailUrl.href         = "#";
  detailUrl.textContent  = "";
  commentInput.disabled = true;
  commentInput.placeholder = "カードが見つかるとコメントを入力できます";
  commentSubmitBtn.disabled = true;
}

// ============================================================
// 日付変更 → カード検索
// ============================================================

viewDateInput.addEventListener("change", () => {
  const title = formatDateJp(viewDateInput.value);
  viewDatePreview.textContent = title ? `検索: ${title}` : "";
  hideMessage(viewSearchMessage);
  hideMessage(commentMessage);
  resetCardDetail();

  if (!title) return;

  const matched = viewCards.find((c) => c.name.trim() === title);
  if (!matched) {
    showMessage(viewSearchMessage, `「${title}」というカードが見つかりませんでした`, "error");
    return;
  }
  showCardDetail(matched);
});

// ============================================================
// コメントを投稿
// ============================================================

commentSubmitBtn.addEventListener("click", async () => {
  hideMessage(commentMessage);
  const text = commentInput.value.trim();
  if (!text) {
    showMessage(commentMessage, "コメント本文は必須です", "error");
    return;
  }
  if (!selectedCardId) {
    showMessage(commentMessage, "カードが選択されていません", "error");
    return;
  }

  commentSubmitBtn.disabled = true;
  commentSubmitBtn.textContent = "送信中...";

  try {
    const res = await fetch(`/api/cards/${encodeURIComponent(selectedCardId)}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const data = await res.json();
    if (!res.ok) {
      showMessage(commentMessage, `エラー: ${data.error}`, "error");
      return;
    }
    showMessage(commentMessage, `カード「${detailName.textContent}」にフィードバックを投稿しました。`, "success");
    commentInput.value = "";
  } catch (err) {
    showMessage(commentMessage, `ネットワークエラー: ${err.message}`, "error");
  } finally {
    commentSubmitBtn.disabled = !selectedCardId;
    commentSubmitBtn.textContent = "コメントを投稿";
  }
});

// ============================================================
// カードを新規追加
// ============================================================

createSubmitBtn.addEventListener("click", async () => {
  hideMessage(createMessage);

  const title       = formatDateJp(viewDateInput.value);
  const description = createDescInput.value.trim();

  if (!createListId) {
    showMessage(createMessage, "追加先リストを取得できていません。ページを再読み込みしてください", "error");
    return;
  }
  if (!title) {
    showMessage(createMessage, "日付を選択してください", "error");
    return;
  }

  createSubmitBtn.disabled = true;
  createSubmitBtn.textContent = "送信中...";

  try {
    const res = await fetch("/api/cards", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ list_id: createListId, title, description }),
    });
    const data = await res.json();
    if (!res.ok) {
      showMessage(createMessage, `エラー: ${data.error}`, "error");
      return;
    }
    showMessage(createMessage, `リスト「${createListName}」にフィードバックカードを追加しました。`, "success");
    createDescInput.value = "";

    // 追加後、同じ日付でカード一覧を再取得して表示を更新する
    await refreshViewCards();
  } catch (err) {
    showMessage(createMessage, `ネットワークエラー: ${err.message}`, "error");
  } finally {
    createSubmitBtn.disabled = false;
    createSubmitBtn.textContent = "カードを追加";
  }
});

// ============================================================
// カード一覧の取得・更新
// ============================================================

/** viewListId のカード一覧を取得してキャッシュを更新する */
async function refreshViewCards() {
  if (!viewListId) return;

  try {
    const res = await fetch(`/api/cards?list_id=${encodeURIComponent(viewListId)}`);
    const data = await res.json();
    if (!res.ok) {
      showMessage(viewSearchMessage, `カード取得エラー: ${data.error}`, "error");
      return;
    }
    viewCards = data;

    // 日付が選択済みなら再検索して表示を更新
    if (viewDateInput.value) {
      const title   = formatDateJp(viewDateInput.value);
      const matched = viewCards.find((c) => c.name.trim() === title);
      if (matched) showCardDetail(matched);
    }
  } catch (err) {
    showMessage(viewSearchMessage, `ネットワークエラー: ${err.message}`, "error");
  }
}

// ============================================================
// ページ読み込み時: settings.ini の値で自動初期化
// ============================================================

async function initFromSettings() {
  const errors = [];

  // 左（カード参照）用: ボード → リスト → カード一覧をキャッシュ
  if (SETTINGS.view_board_url && SETTINGS.view_default_list) {
    try {
      const res  = await fetch(`/api/lists?board_url=${encodeURIComponent(SETTINGS.view_board_url)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);

      const matched = data.find(
        (l) => l.name.trim().toLowerCase() === SETTINGS.view_default_list.trim().toLowerCase()
      );
      if (!matched) throw new Error(`リスト「${SETTINGS.view_default_list}」が見つかりません`);

      viewListId = matched.id;
      await refreshViewCards();
      viewDateInput.disabled = false;
    } catch (err) {
      errors.push(`カード参照: ${err.message}`);
    }
  }

  // 右（カード追加）用: ボード → リスト ID を確定
  if (SETTINGS.create_board_url && SETTINGS.create_default_list) {
    try {
      const res  = await fetch(`/api/lists?board_url=${encodeURIComponent(SETTINGS.create_board_url)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);

      const matched = data.find(
        (l) => l.name.trim().toLowerCase() === SETTINGS.create_default_list.trim().toLowerCase()
      );
      if (!matched) throw new Error(`リスト「${SETTINGS.create_default_list}」が見つかりません`);

      createListId   = matched.id;
      createListName = matched.name;
    } catch (err) {
      errors.push(`カード追加: ${err.message}`);
    }
  }

  if (errors.length > 0) {
    showMessage(viewSearchMessage, `初期化エラー: ${errors.join(" / ")}`, "error");
  }
}

initFromSettings();
