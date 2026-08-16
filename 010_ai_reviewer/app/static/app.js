// ============================================================
// DOM 参照
// ============================================================

// 左パネル
const fileInput          = document.getElementById("file-input");
const fileNameHint       = document.getElementById("file-name");
const fileDrop           = document.getElementById("file-drop");
const uploadBtn          = document.getElementById("upload-btn");
const uploadMessage      = document.getElementById("upload-message");
const overallSection     = document.getElementById("overall-section");
const intendedMessage    = document.getElementById("intended-message");
const slideListSection   = document.getElementById("slide-list-section");
const slideList          = document.getElementById("slide-list");
const reviewAction       = document.getElementById("review-action");
const reviewBtn          = document.getElementById("review-btn");
const reviewMessage      = document.getElementById("review-message");
const suggestBtn         = document.getElementById("suggest-btn");
const suggestMessage     = document.getElementById("suggest-message");
const qaBtn              = document.getElementById("qa-btn");
const qaMessage          = document.getElementById("qa-message");
const downloadCsvBtn     = document.getElementById("download-csv-btn");
const downloadSuggestionBtn = document.getElementById("download-suggestion-btn");
const downloadQaBtn      = document.getElementById("download-qa-btn");
// レビュー観点設定モーダル
const reviewPointSettingsBtn = document.getElementById("review-point-settings-btn");
const reviewPointModal       = document.getElementById("review-point-modal");
const reviewPointColumns     = document.getElementById("review-point-columns");
const reviewPointListLeft    = document.getElementById("review-point-list-left");
const reviewPointListRight   = document.getElementById("review-point-list-right");
const reviewPointLoading     = document.getElementById("review-point-loading");
const reviewPointCancelBtn   = document.getElementById("review-point-cancel-btn");
const reviewPointSaveBtn     = document.getElementById("review-point-save-btn");
const reviewPointMessage     = document.getElementById("review-point-message");
// 修正対象指摘事項選択モーダル
const suggestSelectionModal      = document.getElementById("suggest-selection-modal");
const suggestSelectionEmpty      = document.getElementById("suggest-selection-empty");
const suggestSelectionList       = document.getElementById("suggest-selection-list");
const suggestSelectionCancelBtn  = document.getElementById("suggest-selection-cancel-btn");
const suggestSelectionRunBtn     = document.getElementById("suggest-selection-run-btn");
const suggestSelectionMessage    = document.getElementById("suggest-selection-message");
// 共有リンク発行モーダル
const shareBtn                = document.getElementById("share-btn");
const shareModal              = document.getElementById("share-modal");
const shareUrlInput           = document.getElementById("share-url-input");
const shareMessage            = document.getElementById("share-message");
const shareCloseBtn           = document.getElementById("share-close-btn");
const shareCopyBtn            = document.getElementById("share-copy-btn");
// 右パネル
const rightContent       = document.getElementById("right-content");
const tabBtns               = document.querySelectorAll(".tab-btn");
const tabInputEl            = document.getElementById("tab-input");
const tabSummaryEl          = document.getElementById("tab-summary");
const tabSuggestionEl       = document.getElementById("tab-suggestion");
const tabQaEl               = document.getElementById("tab-qa");
const summaryPlaceholder    = document.getElementById("summary-placeholder");
const summaryContent        = document.getElementById("summary-content");
const summarySlideLabel     = document.getElementById("summary-slide-label");
const summarySlideImg       = document.getElementById("summary-slide-img");
const perspectiveSelectorEl = document.getElementById("perspective-selector");
const summaryPerspectiveBody = document.getElementById("summary-perspective-body");
const suggestionPlaceholder = document.getElementById("suggestion-placeholder");
const suggestionContent     = document.getElementById("suggestion-content");
const suggestionSlideLabel  = document.getElementById("suggestion-slide-label");
const suggestionBeforeImg   = document.getElementById("suggestion-before-img");
const suggestionAfterImg    = document.getElementById("suggestion-after-img");
const suggestionAfterSpinner = document.getElementById("suggestion-after-spinner");
const suggestionBody        = document.getElementById("suggestion-body");
const qaPlaceholder         = document.getElementById("qa-placeholder");
const qaContent             = document.getElementById("qa-content");
const qaList                = document.getElementById("qa-list");

// 伝えたいことタブ
const inputSlideLabel    = document.getElementById("input-slide-label");
const slidePreviewImg    = document.getElementById("slide-preview-img");
const slideMessageInput  = document.getElementById("slide-message-input");

// ============================================================
// 状態
// ============================================================

let currentFile       = null;
let thumbnails        = [];        // 一覧用 Base64 画像（JPEG or PNG）
let slidePngs         = [];        // プレビュー用 Base64 PNG (LibreOffice 高品質)
let thumbnailMime     = "image/png";  // thumbnails の MIME タイプ
let renderMethod      = "none";    // "libre_office" | "pillow" | "none"
let slideCount        = 0;
let selectedSlide     = null;      // 現在選択中のスライド番号（1始まり）
let perSlideMessages  = {};        // slideNum -> string
let reviewData              = null;  // APIから返ってきたレビュー結果
let suggestionBySlide       = {};    // slide_number -> 修正方針テキスト（またはエラー情報）
let qaData                  = null;  // APIから返ってきた想定質問一覧
let activeTab               = "input"; // "input" | "summary" | "suggestion" | "qa"
let activePerspectiveIndex  = 0;
let suggestInProgress       = false; // 修正方針提案のストリーミング処理中かどうか

// ============================================================
// ファイル選択
// ============================================================

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  if (file) setFile(file);
});

fileDrop.addEventListener("dragover", (e) => {
  e.preventDefault();
  fileDrop.style.borderColor = "#0052cc";
  fileDrop.style.backgroundColor = "#f0f4ff";
});

fileDrop.addEventListener("dragleave", () => {
  fileDrop.style.borderColor = "";
  fileDrop.style.backgroundColor = "";
});

fileDrop.addEventListener("drop", (e) => {
  e.preventDefault();
  fileDrop.style.borderColor = "";
  fileDrop.style.backgroundColor = "";
  const file = e.dataTransfer.files[0];
  if (!file || !file.name.toLowerCase().endsWith(".pptx")) {
    showMessage(uploadMessage, ".pptx ファイルをドロップしてください", "error");
    return;
  }
  setFile(file);
});

function setFile(file) {
  currentFile = file;
  fileNameHint.textContent = file.name;
  fileNameHint.classList.add("selected");
  uploadBtn.disabled = false;
  hideMessage(uploadMessage);
}

// ============================================================
// アップロード → スライド一覧を左パネルに表示
// ============================================================

uploadBtn.addEventListener("click", async () => {
  if (!currentFile) return;

  hideMessage(uploadMessage);
  uploadBtn.disabled = true;
  uploadBtn.innerHTML = '<span class="loading"></span>読み込み中...';

  try {
    const form = new FormData();
    form.append("file", currentFile);

    const res  = await fetch("/api/upload", { method: "POST", body: form });
    const data = await res.json();

    if (!res.ok) {
      showMessage(uploadMessage, `エラー: ${formatErrorDetail(data.detail)}`, "error");
      return;
    }

    thumbnails    = data.thumbnails || [];
    slidePngs     = data.slide_pngs || [];
    thumbnailMime = data.thumbnail_mime || "image/png";
    renderMethod  = data.render_method || "none";
    slideCount    = data.slide_count || 0;
    reviewData    = null;
    suggestionBySlide = {};
    qaData        = null;
    selectedSlide = null;
    perSlideMessages = {};
    downloadCsvBtn.disabled = true;
    suggestBtn.disabled = true;
    qaBtn.disabled = false;
    downloadSuggestionBtn.disabled = true;
    downloadQaBtn.disabled = true;
    shareBtn.disabled = true;

    // 左パネルの各セクションを表示
    overallSection.classList.remove("hidden");
    slideListSection.classList.remove("hidden");
    reviewAction.classList.remove("hidden");
    if (summaryPlaceholder) summaryPlaceholder.classList.remove("hidden");
    if (summaryContent) summaryContent.classList.add("hidden");
    if (suggestionPlaceholder) suggestionPlaceholder.classList.remove("hidden");
    if (suggestionContent) suggestionContent.classList.add("hidden");
    if (qaPlaceholder) qaPlaceholder.classList.remove("hidden");
    if (qaContent) qaContent.classList.add("hidden");

    // スライド一覧を構築
    buildSlideList(thumbnails, slideCount);

    // 右パネルをリセット
    rightContent.classList.add("hidden");

    // 最初のスライドを自動選択
    if (slideCount > 0) selectSlide(1);

    showMessage(uploadMessage, `${slideCount} 枚のスライドを読み込みました`, "success");
  } catch (err) {
    showMessage(uploadMessage, `ネットワークエラー: ${err.message}`, "error");
  } finally {
    uploadBtn.disabled = false;
    uploadBtn.textContent = "スライドを表示";
  }
});

// ============================================================
// スライド一覧の構築（左パネル）
// ============================================================

function buildSlideList(thumbs, count) {
  slideList.innerHTML = "";
  for (let i = 1; i <= count; i++) {
    const item = document.createElement("div");
    item.className = "slide-list-item";
    item.dataset.slide = i;

    if (thumbs && thumbs[i - 1]) {
      const img = document.createElement("img");
      img.src   = `data:${thumbnailMime};base64,${thumbs[i - 1]}`;
      img.alt   = `スライド ${i}`;
      img.className = "slide-list-thumb";
      item.appendChild(img);
    }

    const label = document.createElement("span");
    label.className = "slide-list-label";
    label.textContent = `スライド ${i}`;
    item.appendChild(label);

    const status = document.createElement("span");
    status.className = "slide-list-status hidden";
    item.appendChild(status);

    item.addEventListener("click", () => selectSlide(i));
    slideList.appendChild(item);
  }
}

// ============================================================
// スライド一覧の進捗ステータス表示（修正方針の提案処理用）
// ============================================================

// 提案処理の開始前に、スライド一覧の各アイテムからステータス表示をリセットする
function resetSlideListSuggestStatus() {
  document.querySelectorAll(".slide-list-item .slide-list-status").forEach((el) => {
    el.className = "slide-list-status hidden";
    el.textContent = "";
    el.title = "";
  });
}

// 指定したスライド番号の一覧アイテムに、処理状況（pending/done/skipped/error）を反映する
function setSlideListSuggestStatus(num, status) {
  const item = slideList.querySelector(`.slide-list-item[data-slide="${num}"]`);
  const statusEl = item && item.querySelector(".slide-list-status");
  if (!statusEl) return;

  const statusConfig = {
    pending: { text: "", title: "修正方針を検討中です" },
    done:    { text: "✓", title: "修正方針の提案が完了しました" },
    skipped: { text: "―", title: "修正不要と判断されました" },
    error:   { text: "!", title: "修正方針の生成に失敗しました" },
  };
  const config = statusConfig[status];
  if (!config) return;

  statusEl.className = `slide-list-status slide-list-status-${status}`;
  statusEl.textContent = config.text;
  statusEl.title = config.title;
}

// ============================================================
// スライド選択
// ============================================================

function selectSlide(num) {
  // 現在の入力タブのテキストエリアを保存してから切り替える
  if (selectedSlide && activeTab === "input") {
    perSlideMessages[selectedSlide] = slideMessageInput.value;
  }

  selectedSlide = num;

  // リストのアクティブ状態を更新
  document.querySelectorAll(".slide-list-item").forEach((el) => {
    el.classList.toggle("active", parseInt(el.dataset.slide, 10) === num);
  });

  // 右パネルを表示して内容を更新
  rightContent.classList.remove("hidden");

  refreshRightPanel();
}

// ============================================================
// タブ切り替え（右パネル）
// ============================================================

tabBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    // 入力タブを離れる前にテキストエリアの値を保存
    if (activeTab === "input" && selectedSlide) {
      perSlideMessages[selectedSlide] = slideMessageInput.value;
    }
    activeTab = btn.dataset.tab;
    tabBtns.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    tabInputEl.classList.toggle("hidden", activeTab !== "input");
    tabSummaryEl.classList.toggle("hidden", activeTab !== "summary");
    tabSuggestionEl.classList.toggle("hidden", activeTab !== "suggestion");
    tabQaEl.classList.toggle("hidden", activeTab !== "qa");
    refreshRightPanel();
  });
});

// ============================================================
// 右パネルの内容更新
// ============================================================

function refreshRightPanel() {
  if (activeTab === "input") {
    if (selectedSlide) renderInputTab(selectedSlide);
  } else if (activeTab === "summary") {
    if (selectedSlide) renderSummaryTab(selectedSlide);
  } else if (activeTab === "suggestion") {
    if (selectedSlide) renderSuggestionTab(selectedSlide);
  } else if (activeTab === "qa") {
    renderQaTab();
  }
}

function renderInputTab(num) {
  const badge = renderMethod === "libre_office"
    ? ' <span class="render-badge">LibreOffice</span>'
    : (renderMethod === "pillow" ? ' <span class="render-badge render-badge-pillow">簡易表示</span>' : "");
  inputSlideLabel.innerHTML = `スライド ${num}${badge}`;

  // プレビューは高品質 PNG を優先、なければ一覧用サムネイルを使用
  const src  = slidePngs[num - 1] || thumbnails[num - 1];
  const mime = slidePngs[num - 1] ? "image/png" : thumbnailMime;
  slidePreviewImg.src = src ? `data:${mime};base64,${src}` : "";
  slidePreviewImg.alt = `スライド ${num}`;

  // 保存済みのメッセージを復元
  slideMessageInput.value = perSlideMessages[num] || "";
}

// ============================================================
// 総評タブ — スライド画像・観点セレクタ
// ============================================================

function renderSummaryTab(num) {
  const src  = slidePngs[num - 1] || thumbnails[num - 1];
  const mime = slidePngs[num - 1] ? "image/png" : thumbnailMime;
  summarySlideLabel.textContent = `スライド ${num}`;
  summarySlideImg.src = src ? `data:${mime};base64,${src}` : "";
  summarySlideImg.alt = `スライド ${num}`;
}

function selectPerspective(index) {
  activePerspectiveIndex = index;
  perspectiveSelectorEl.querySelectorAll(".tab-btn").forEach((btn, i) => {
    btn.classList.toggle("active", i === index);
  });
  const perspectives = reviewData?.presentation_summary?.perspectives || [];
  showPerspective(perspectives, index);
}

function renderSuggestionTab(num) {
  const beforeSrc = slidePngs[num - 1] || thumbnails[num - 1];
  const beforeMime = slidePngs[num - 1] ? "image/png" : thumbnailMime;
  suggestionSlideLabel.textContent = `スライド ${num}`;
  suggestionBeforeImg.src = beforeSrc ? `data:${beforeMime};base64,${beforeSrc}` : "";
  suggestionBeforeImg.alt = `スライド ${num} 修正前`;

  const data = suggestionBySlide[num];
  if (!data) {
    suggestionAfterImg.src = "";
    suggestionAfterImg.classList.toggle("hidden", suggestInProgress);
    suggestionAfterSpinner.classList.toggle("hidden", !suggestInProgress);
    suggestionBody.innerHTML = suggestInProgress
      ? "<p class='placeholder-text'>このスライドの修正方針を検討中です...</p>"
      : "<p class='placeholder-text'>このスライドの修正方針はありません</p>";
    return;
  }

  suggestionAfterSpinner.classList.add("hidden");
  suggestionAfterImg.classList.remove("hidden");

  if (data.error) {
    suggestionAfterImg.src = "";
    suggestionBody.innerHTML = `<p class="placeholder-text">このスライドの修正方針の生成に失敗しました: ${escHtml(data.error)}</p>`;
    return;
  }

  if (data.skipped) {
    suggestionAfterImg.src = data.image_png_b64 ? `data:image/png;base64,${data.image_png_b64}` : beforeSrc ? `data:${beforeMime};base64,${beforeSrc}` : "";
    suggestionAfterImg.alt = `スライド ${num} 修正後（修正なし）`;
    suggestionBody.innerHTML = "<p class='placeholder-text'>このスライドに該当する指摘事項はありませんでした（修正不要と判断されました）。</p>";
    return;
  }

  suggestionAfterImg.src = data.edited_image_b64 ? `data:image/png;base64,${data.edited_image_b64}` : "";
  suggestionAfterImg.alt = `スライド ${num} 修正後`;

  suggestionBody.innerHTML = `
    <div class="review-section-block">
      <div class="review-section-label">実際に施した修正内容</div>
      <div class="review-item markdown-body">${renderMarkdown(data.description || "")}</div>
    </div>
  `;
}

// ============================================================
// 想定質問タブ
// ============================================================

function renderQaTab() {
  if (!qaData || qaData.length === 0) {
    qaPlaceholder.classList.remove("hidden");
    qaContent.classList.add("hidden");
    return;
  }

  qaPlaceholder.classList.add("hidden");
  qaContent.classList.remove("hidden");

  qaList.innerHTML = qaData.map((q, i) => `
    <div class="qa-item">
      <div class="qa-question">Q${i + 1}. ${escHtml(q.question || "")}</div>
      ${q.hint ? `<div class="qa-hint markdown-body">${renderMarkdown(q.hint)}</div>` : ""}
    </div>
  `).join("");
}

function showPerspective(perspectives, index) {
  const p = perspectives[index];
  if (!p) {
    summaryPerspectiveBody.innerHTML = "<p class='placeholder-text'>レビュー結果がありません</p>";
    return;
  }
  summaryPerspectiveBody.innerHTML = `<div class="perspective-summary markdown-body">${renderMarkdown(p.summary || "")}</div>`;
}

// ============================================================
// AIレビュー実行
// ============================================================

// 入力タブを離れる前に現在のテキストエリアを保存するヘルパー
function saveCurrentInput() {
  if (selectedSlide && activeTab === "input") {
    perSlideMessages[selectedSlide] = slideMessageInput.value;
  }
}

reviewBtn.addEventListener("click", async () => {
  if (!currentFile) return;

  saveCurrentInput();
  hideMessage(reviewMessage);
  reviewBtn.disabled = true;
  reviewBtn.innerHTML = '<span class="loading"></span>AIがレビュー中...';

  try {
    const overallMsg = intendedMessage.value.trim();
    const slides = thumbnails.map((thumb, i) => ({
      slide_number: i + 1,
      image_jpeg_b64: thumb,
      intended_message: (perSlideMessages[i + 1] || "").trim() || overallMsg,
    }));

    const res  = await fetch("/api/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ overall_intended_message: overallMsg, slides }),
    });
    const data = await res.json();

    if (!res.ok) {
      showMessage(reviewMessage, `エラー: ${formatErrorDetail(data.detail)}`, "error");
      return;
    }

    reviewData = data;
    suggestionBySlide = {};
    downloadCsvBtn.disabled = false;
    suggestBtn.disabled = false;
    shareBtn.disabled = false;
    downloadSuggestionBtn.disabled = true;
    if (suggestionPlaceholder) suggestionPlaceholder.classList.remove("hidden");
    if (suggestionContent) suggestionContent.classList.add("hidden");

    showMessage(reviewMessage, "レビューが完了しました", "success");

    // 総評タブに切り替えて全体サマリーを表示
    activeTab = "summary";
    tabBtns.forEach((b) => b.classList.toggle("active", b.dataset.tab === "summary"));
    tabInputEl.classList.add("hidden");
    tabSummaryEl.classList.remove("hidden");
    tabSuggestionEl.classList.add("hidden");

    renderOverallSummary(data.presentation_summary);

    selectSlide(1);
  } catch (err) {
    showMessage(reviewMessage, `ネットワークエラー: ${err.message}`, "error");
  } finally {
    reviewBtn.disabled = false;
    reviewBtn.textContent = "レビューする";
  }
});

// ============================================================
// 想定質問の生成
// ============================================================

qaBtn.addEventListener("click", async () => {
  if (!currentFile) return;

  saveCurrentInput();
  hideMessage(qaMessage);
  qaBtn.disabled = true;
  qaBtn.innerHTML = '<span class="loading"></span>AIが想定質問を検討中...';

  try {
    const overallMsg = intendedMessage.value.trim();
    const slides = thumbnails.map((thumb, i) => ({
      slide_number: i + 1,
      image_jpeg_b64: thumb,
      intended_message: (perSlideMessages[i + 1] || "").trim() || overallMsg,
    }));

    const res  = await fetch("/api/anticipated-questions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ overall_intended_message: overallMsg, slides }),
    });
    const data = await res.json();

    if (!res.ok) {
      showMessage(qaMessage, `エラー: ${formatErrorDetail(data.detail)}`, "error");
      return;
    }

    qaData = data.questions || [];
    downloadQaBtn.disabled = qaData.length === 0;
    showMessage(qaMessage, "想定質問の提案が完了しました", "success");

    // 想定質問タブに切り替えて結果を表示
    activeTab = "qa";
    tabBtns.forEach((b) => b.classList.toggle("active", b.dataset.tab === "qa"));
    tabInputEl.classList.add("hidden");
    tabSummaryEl.classList.add("hidden");
    tabSuggestionEl.classList.add("hidden");
    tabQaEl.classList.remove("hidden");

    renderQaTab();
  } catch (err) {
    showMessage(qaMessage, `ネットワークエラー: ${err.message}`, "error");
  } finally {
    qaBtn.disabled = false;
    qaBtn.textContent = "想定質問を提案する";
  }
});

// ============================================================
// SSEストリームの読み取り
// ============================================================

// fetch のレスポンスボディを "data: {json}\n\n" 形式のSSEイベントとして逐次読み取り、
// イベントが届くたびに onEvent(payload) を呼び出す
async function readSSEStream(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sepIndex;
    while ((sepIndex = buffer.indexOf("\n\n")) >= 0) {
      const rawEvent = buffer.slice(0, sepIndex);
      buffer = buffer.slice(sepIndex + 2);
      const dataLine = rawEvent.split("\n").find((line) => line.startsWith("data:"));
      if (!dataLine) continue;
      try {
        onEvent(JSON.parse(dataLine.slice(5).trim()));
      } catch (err) {
        console.error("SSEイベントの解析に失敗しました", err);
      }
    }
  }
}

// ============================================================
// 修正方針の提案
// ============================================================

suggestBtn.addEventListener("click", () => {
  const perspectives = reviewData?.presentation_summary?.perspectives || [];
  if (!currentFile || perspectives.length === 0) return;
  openSuggestSelectionModal(perspectives);
});

async function runSuggestionProcess(perspectives) {
  hideMessage(suggestMessage);
  suggestBtn.disabled = true;
  suggestInProgress = true;

  const slides = slidePngs.map((png, i) => ({
    slide_number: i + 1,
    image_png_b64: png,
  }));
  const total = slides.length;
  let completed = 0;
  let hasError = false;

  suggestionBySlide = {};
  downloadSuggestionBtn.disabled = true;

  // 左パネルのスライド一覧に進捗ステータスを表示し、どのスライドが処理待ちかを示す
  resetSlideListSuggestStatus();
  slides.forEach((s) => setSlideListSuggestStatus(s.slide_number, "pending"));

  // 修正方針タブに切り替え、結果が届くたびに反映されるようにする
  activeTab = "suggestion";
  tabBtns.forEach((b) => b.classList.toggle("active", b.dataset.tab === "suggestion"));
  tabInputEl.classList.add("hidden");
  tabSummaryEl.classList.add("hidden");
  tabSuggestionEl.classList.remove("hidden");
  suggestionPlaceholder.classList.add("hidden");
  suggestionContent.classList.remove("hidden");
  if (selectedSlide) renderSuggestionTab(selectedSlide);

  const updateProgressLabel = () => {
    suggestBtn.innerHTML = `<span class="loading"></span>AIが修正方針を検討中... (${completed}/${total})`;
  };
  updateProgressLabel();

  try {
    const res = await fetch("/api/suggest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slides,
        perspectives: perspectives.map((p) => ({
          type: p.type || "",
          label: p.label || "",
          summary: p.summary || "",
        })),
      }),
    });

    if (!res.ok) {
      const data = await res.json();
      showMessage(suggestMessage, `エラー: ${formatErrorDetail(data.detail)}`, "error");
      return;
    }

    await readSSEStream(res, (payload) => {
      if (payload.type === "slide_done") {
        suggestionBySlide[payload.slide_number] = payload;
        completed += 1;
        updateProgressLabel();
        setSlideListSuggestStatus(payload.slide_number, "done");
        if (selectedSlide === payload.slide_number && activeTab === "suggestion") {
          renderSuggestionTab(selectedSlide);
        }
      } else if (payload.type === "slide_error") {
        hasError = true;
        suggestionBySlide[payload.slide_number] = { slide_number: payload.slide_number, error: payload.detail };
        completed += 1;
        updateProgressLabel();
        setSlideListSuggestStatus(payload.slide_number, "error");
        if (selectedSlide === payload.slide_number && activeTab === "suggestion") {
          renderSuggestionTab(selectedSlide);
        }
      } else if (payload.type === "slide_skipped") {
        suggestionBySlide[payload.slide_number] = {
          slide_number: payload.slide_number,
          skipped: true,
          image_png_b64: payload.image_png_b64,
        };
        completed += 1;
        updateProgressLabel();
        setSlideListSuggestStatus(payload.slide_number, "skipped");
        if (selectedSlide === payload.slide_number && activeTab === "suggestion") {
          renderSuggestionTab(selectedSlide);
        }
      }
    });

    const hasAnySuccess = Object.values(suggestionBySlide).some((s) => s.edited_image_b64);
    downloadSuggestionBtn.disabled = !hasAnySuccess;

    if (hasError) {
      showMessage(suggestMessage, "一部のスライドで修正方針の生成に失敗しました", "error");
    } else {
      showMessage(suggestMessage, "修正方針の検討が完了しました", "success");
    }
  } catch (err) {
    showMessage(suggestMessage, `ネットワークエラー: ${err.message}`, "error");
  } finally {
    suggestInProgress = false;
    suggestBtn.disabled = false;
    suggestBtn.textContent = "修正方針を提示する";
    if (selectedSlide && activeTab === "suggestion") renderSuggestionTab(selectedSlide);
  }
}

// ============================================================
// 修正対象指摘事項選択モーダル
// ============================================================

let suggestFindingItems = []; // { id, perspective_type, perspective_label, text, checked }

// レビュー結果の各観点summary（Markdown箇条書き）を、指摘事項単位のリストに分解する
function buildSuggestFindingItems(perspectives) {
  const items = [];
  let id = 0;
  perspectives.forEach((p) => {
    const label = p.label || p.type || "";
    const summary = (p.summary || "").trim();
    // 指摘事項が存在しない観点は選択対象に含めない
    if (!summary || summary === "特に指摘事項はありません") return;
    extractMarkdownItems(summary).forEach((text) => {
      items.push({
        id: id++,
        perspective_type: p.type || label,
        perspective_label: label,
        text,
        checked: true,
      });
    });
  });
  return items;
}

function renderSuggestSelectionList() {
  const groups = groupReviewPointItems(suggestFindingItems);

  suggestSelectionList.innerHTML = groups.map((group) => {
    const rows = group.items.map((item) => {
      const checkboxId = `suggest-finding-${item.id}`;
      return `
        <div class="review-point-row">
          <input type="checkbox" id="${checkboxId}" data-id="${item.id}" ${item.checked ? "checked" : ""}>
          <label for="${checkboxId}">${escHtml(item.text)}</label>
        </div>
      `;
    }).join("");
    return `
      <div class="review-point-group">
        <div class="review-point-group-title">
          <input type="checkbox" class="review-point-group-toggle">
          <span>${escHtml(group.label)}</span>
        </div>
        ${rows}
      </div>
    `;
  }).join("");

  wireCheckboxGroupToggles(suggestSelectionList, (checkbox) => {
    const id = Number(checkbox.dataset.id);
    const item = suggestFindingItems.find((i) => i.id === id);
    if (item) item.checked = checkbox.checked;
  });
}

// チェックが入っている指摘事項のみを観点単位に再構成し、/api/suggest に渡すperspectives配列を作る
function buildFilteredPerspectivesFromSelection() {
  const order = [];
  const grouped = {};
  suggestFindingItems.forEach((item) => {
    if (!item.checked) return;
    if (!grouped[item.perspective_type]) {
      grouped[item.perspective_type] = { type: item.perspective_type, label: item.perspective_label, lines: [] };
      order.push(item.perspective_type);
    }
    grouped[item.perspective_type].lines.push(item.text);
  });
  return order.map((type) => ({
    type: grouped[type].type,
    label: grouped[type].label,
    summary: grouped[type].lines.map((line) => `- ${line}`).join("\n"),
  }));
}

function openSuggestSelectionModal(perspectives) {
  hideMessage(suggestSelectionMessage);
  suggestFindingItems = buildSuggestFindingItems(perspectives);
  suggestSelectionModal.classList.remove("hidden");

  if (suggestFindingItems.length === 0) {
    suggestSelectionList.classList.add("hidden");
    suggestSelectionEmpty.classList.remove("hidden");
  } else {
    suggestSelectionEmpty.classList.add("hidden");
    suggestSelectionList.classList.remove("hidden");
    renderSuggestSelectionList();
  }
}

function closeSuggestSelectionModal() {
  suggestSelectionModal.classList.add("hidden");
}

suggestSelectionCancelBtn.addEventListener("click", closeSuggestSelectionModal);

suggestSelectionModal.addEventListener("click", (e) => {
  if (e.target === suggestSelectionModal) closeSuggestSelectionModal();
});

suggestSelectionRunBtn.addEventListener("click", () => {
  const filteredPerspectives = buildFilteredPerspectivesFromSelection();
  if (filteredPerspectives.length === 0) {
    showMessage(suggestSelectionMessage, "少なくとも1つの指摘事項を選択してください", "error");
    return;
  }
  closeSuggestSelectionModal();
  runSuggestionProcess(filteredPerspectives);
});

// ============================================================
// 全体サマリー（総評タブ）
// ============================================================

function renderOverallSummary(summary) {
  if (!summary) return;
  const perspectives = summary.perspectives || [];

  perspectiveSelectorEl.className = "tab-bar";
  perspectiveSelectorEl.innerHTML = perspectives.map((p, i) =>
    `<button class="tab-btn${i === 0 ? " active" : ""}" onclick="selectPerspective(${i})">${escHtml(p.label || p.type || "")}</button>`
  ).join("");

  activePerspectiveIndex = 0;
  showPerspective(perspectives, 0);

  summaryPlaceholder.classList.add("hidden");
  summaryContent.classList.remove("hidden");
}

// ============================================================
// スライドメッセージの自動保存
// ============================================================

slideMessageInput.addEventListener("input", () => {
  if (selectedSlide) {
    perSlideMessages[selectedSlide] = slideMessageInput.value;
  }
});

// ============================================================
// レビュー結果のMarkdownダウンロード
// ============================================================

downloadCsvBtn.addEventListener("click", () => {
  const perspectives = reviewData?.presentation_summary?.perspectives || [];
  if (perspectives.length === 0) return;

  const lines = ["| No | 観点 | 指摘事項 |", "| --- | --- | --- |"];
  let no = 1;
  perspectives.forEach((p) => {
    const label = p.label || p.type || "";
    extractMarkdownItems(p.summary || "").forEach((item) => {
      lines.push(`| ${no} | ${markdownTableEscape(label)} | ${markdownTableEscape(item)} |`);
      no += 1;
    });
  });

  const markdownContent = lines.join("\n") + "\n";
  const blob = new Blob([markdownContent], { type: "text/markdown;charset=utf-8;" });
  const url = URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = url;
  a.download = "review_result.md";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
});

// ============================================================
// 想定質問のMarkdownダウンロード
// ============================================================

downloadQaBtn.addEventListener("click", () => {
  if (!qaData || qaData.length === 0) return;

  const lines = ["| No | 想定質問 | 準備のヒント |", "| --- | --- | --- |"];
  qaData.forEach((q, i) => {
    lines.push(`| ${i + 1} | ${markdownTableEscape(q.question || "")} | ${markdownTableEscape(q.hint || "")} |`);
  });

  const markdownContent = lines.join("\n") + "\n";
  const blob = new Blob([markdownContent], { type: "text/markdown;charset=utf-8;" });
  const url = URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = url;
  a.download = "anticipated_questions.md";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
});

// ============================================================
// レビュー結果の共有リンク発行
// ============================================================

shareBtn.addEventListener("click", async () => {
  if (!reviewData) return;

  hideMessage(shareMessage);
  shareBtn.disabled = true;
  shareBtn.innerHTML = '<span class="loading"></span>共有リンクを作成中...';

  try {
    const slides = slidePngs.map((png, i) => ({
      slide_number: i + 1,
      image_png_b64: png,
      intended_message: perSlideMessages[i + 1] || "",
    }));

    const payload = {
      file_name: currentFile ? currentFile.name : "",
      overall_intended_message: intendedMessage.value.trim(),
      slides,
      review: reviewData,
      suggestions: suggestionBySlide,
      qa: qaData,
    };

    const res = await fetch("/api/share", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok) {
      showMessage(shareMessage, `エラー: ${formatErrorDetail(data.detail)}`, "error");
      shareModal.classList.remove("hidden");
      return;
    }

    shareUrlInput.value = `${location.origin}${data.url}`;
    shareModal.classList.remove("hidden");
  } catch (err) {
    showMessage(shareMessage, `ネットワークエラー: ${err.message}`, "error");
    shareModal.classList.remove("hidden");
  } finally {
    shareBtn.disabled = false;
    shareBtn.textContent = "共有する";
  }
});

shareCloseBtn.addEventListener("click", () => {
  shareModal.classList.add("hidden");
});

shareModal.addEventListener("click", (e) => {
  if (e.target === shareModal) shareModal.classList.add("hidden");
});

shareCopyBtn.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(shareUrlInput.value);
    showMessage(shareMessage, "URLをコピーしました", "success");
  } catch (err) {
    shareUrlInput.select();
    showMessage(shareMessage, "自動コピーに失敗しました。選択されたURLを手動でコピーしてください", "error");
  }
});

// ============================================================
// 修正後スライドのPDFダウンロード
// ============================================================

downloadSuggestionBtn.addEventListener("click", async () => {
  const slides = Object.keys(suggestionBySlide)
    .map(Number)
    .sort((a, b) => a - b)
    .filter((num) => suggestionBySlide[num]?.edited_image_b64)
    .map((num) => ({
      slide_number: num,
      edited_image_b64: suggestionBySlide[num].edited_image_b64,
    }));
  if (slides.length === 0) return;

  hideMessage(suggestMessage);
  const originalLabel = downloadSuggestionBtn.textContent;
  downloadSuggestionBtn.disabled = true;
  downloadSuggestionBtn.innerHTML = '<span class="loading"></span>PDFを作成中...';

  try {
    const res = await fetch("/api/suggest/export-pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slides }),
    });

    if (!res.ok) {
      const data = await res.json();
      showMessage(suggestMessage, `エラー: ${formatErrorDetail(data.detail)}`, "error");
      return;
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "revision_suggestion.pdf";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (err) {
    showMessage(suggestMessage, `ネットワークエラー: ${err.message}`, "error");
  } finally {
    downloadSuggestionBtn.disabled = false;
    downloadSuggestionBtn.textContent = originalLabel;
  }
});

// ============================================================
// レビュー観点設定モーダル
// ============================================================

let reviewPointItems = []; // サーバから取得した観点設定一覧（_original に読み込み時点のapply_flagを保持）

function groupReviewPointItems(items) {
  const groups = [];
  const indexByType = {};
  items.forEach((item) => {
    const key = item.perspective_type;
    if (!(key in indexByType)) {
      indexByType[key] = groups.length;
      groups.push({ type: key, label: item.perspective_label || key, items: [] });
    }
    groups[indexByType[key]].items.push(item);
  });
  return groups;
}

// グループ見出しの一括ON/OFFチェックボックスと、個別チェックボックスの状態を同期させる
// （観点設定モーダル・指摘事項選択モーダルの両方で使う共通処理）
function wireCheckboxGroupToggles(containerEl, onItemToggle) {
  containerEl.querySelectorAll(".review-point-group").forEach((groupEl) => {
    const groupToggle = groupEl.querySelector(".review-point-group-toggle");
    const getItemCheckboxes = () => groupEl.querySelectorAll('.review-point-row input[type="checkbox"]');

    const syncGroupToggle = () => {
      const boxes = Array.from(getItemCheckboxes());
      const checkedCount = boxes.filter((b) => b.checked).length;
      groupToggle.checked = boxes.length > 0 && checkedCount === boxes.length;
      groupToggle.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
    };

    getItemCheckboxes().forEach((checkbox) => {
      checkbox.addEventListener("change", () => {
        onItemToggle(checkbox);
        syncGroupToggle();
      });
    });

    groupToggle.addEventListener("change", () => {
      const checked = groupToggle.checked;
      groupToggle.indeterminate = false;
      getItemCheckboxes().forEach((checkbox) => {
        checkbox.checked = checked;
        onItemToggle(checkbox);
      });
    });

    syncGroupToggle();
  });
}

function renderReviewPointColumn(containerEl, items) {
  const groups = groupReviewPointItems(items);

  containerEl.innerHTML = groups.map((group) => {
    const rows = group.items.map((item) => {
      const checkboxId = `review-point-${item.source}-${item.row_index}`;
      return `
        <div class="review-point-row">
          <input type="checkbox" id="${checkboxId}" data-source="${escHtml(item.source)}" data-row-index="${item.row_index}" ${item.apply_flag ? "checked" : ""}>
          <label for="${checkboxId}">${escHtml(item.detail)}</label>
        </div>
      `;
    }).join("");
    return `
      <div class="review-point-group">
        <div class="review-point-group-title">
          <input type="checkbox" class="review-point-group-toggle">
          <span>${escHtml(group.label)}</span>
        </div>
        ${rows}
      </div>
    `;
  }).join("");

  wireCheckboxGroupToggles(containerEl, (checkbox) => {
    const source = checkbox.dataset.source;
    const rowIndex = Number(checkbox.dataset.rowIndex);
    const item = reviewPointItems.find((i) => i.source === source && i.row_index === rowIndex);
    if (item) item.apply_flag = checkbox.checked;
  });
}

function renderReviewPointList() {
  renderReviewPointColumn(reviewPointListLeft, reviewPointItems.filter((i) => i.source === "review_point"));
  renderReviewPointColumn(reviewPointListRight, reviewPointItems.filter((i) => i.source === "pp_check_points"));
}

async function openReviewPointModal() {
  hideMessage(reviewPointMessage);
  reviewPointModal.classList.remove("hidden");
  reviewPointColumns.classList.add("hidden");
  reviewPointLoading.classList.remove("hidden");
  reviewPointLoading.textContent = "読み込み中...";

  try {
    const res = await fetch("/api/review-points");
    const data = await res.json();

    if (!res.ok) {
      reviewPointLoading.textContent = `エラー: ${formatErrorDetail(data.detail)}`;
      return;
    }

    reviewPointItems = (data.items || []).map((item) => ({ ...item, _original: item.apply_flag }));
    renderReviewPointList();
    reviewPointLoading.classList.add("hidden");
    reviewPointColumns.classList.remove("hidden");
  } catch (err) {
    reviewPointLoading.textContent = `ネットワークエラー: ${err.message}`;
  }
}

function closeReviewPointModal() {
  reviewPointModal.classList.add("hidden");
}

reviewPointSettingsBtn.addEventListener("click", openReviewPointModal);
reviewPointCancelBtn.addEventListener("click", closeReviewPointModal);

reviewPointModal.addEventListener("click", (e) => {
  if (e.target === reviewPointModal) closeReviewPointModal();
});

reviewPointSaveBtn.addEventListener("click", async () => {
  const updates = reviewPointItems
    .filter((item) => item.apply_flag !== item._original)
    .map((item) => ({ source: item.source, row_index: item.row_index, apply_flag: item.apply_flag }));

  if (updates.length === 0) {
    closeReviewPointModal();
    return;
  }

  hideMessage(reviewPointMessage);
  reviewPointSaveBtn.disabled = true;
  reviewPointSaveBtn.innerHTML = '<span class="loading"></span>保存中...';

  try {
    const res = await fetch("/api/review-points", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ updates }),
    });
    const data = await res.json();

    if (!res.ok) {
      showMessage(reviewPointMessage, `エラー: ${formatErrorDetail(data.detail)}`, "error");
      return;
    }

    reviewPointItems = (data.items || []).map((item) => ({ ...item, _original: item.apply_flag }));
    closeReviewPointModal();
  } catch (err) {
    showMessage(reviewPointMessage, `ネットワークエラー: ${err.message}`, "error");
  } finally {
    reviewPointSaveBtn.disabled = false;
    reviewPointSaveBtn.textContent = "保存する";
  }
});

// ============================================================
// スライド画像拡大表示（ライトボックス）
// ============================================================

const imageLightboxModal = document.getElementById("image-lightbox-modal");
const imageLightboxImg   = document.getElementById("image-lightbox-img");
const imageLightboxClose = document.getElementById("image-lightbox-close");
const imageLightboxPrev  = document.getElementById("image-lightbox-prev");
const imageLightboxNext  = document.getElementById("image-lightbox-next");

let lightboxSequence = [];  // { slideNum, variant, src, alt } の配列（開いた時点のタブに応じて構築）
let lightboxIndex    = -1;

// kind: "slide"（伝えたいこと・指摘事項タブ用、スライド1枚のみ） / "suggestion"（修正方針タブ用、修正前後を含む）
function buildLightboxSequence(kind) {
  const seq = [];
  if (kind === "slide") {
    for (let i = 1; i <= slideCount; i++) {
      const src  = slidePngs[i - 1] || thumbnails[i - 1];
      const mime = slidePngs[i - 1] ? "image/png" : thumbnailMime;
      if (!src) continue;
      seq.push({ slideNum: i, variant: "single", src: `data:${mime};base64,${src}`, alt: `スライド ${i}` });
    }
  } else if (kind === "suggestion") {
    for (let i = 1; i <= slideCount; i++) {
      const beforeSrc  = slidePngs[i - 1] || thumbnails[i - 1];
      const beforeMime = slidePngs[i - 1] ? "image/png" : thumbnailMime;
      if (beforeSrc) {
        seq.push({ slideNum: i, variant: "before", src: `data:${beforeMime};base64,${beforeSrc}`, alt: `スライド ${i} 修正前` });
      }
      const data = suggestionBySlide[i];
      if (data && data.edited_image_b64) {
        seq.push({ slideNum: i, variant: "after", src: `data:image/png;base64,${data.edited_image_b64}`, alt: `スライド ${i} 修正後` });
      }
    }
  }
  return seq;
}

function showLightboxFrame() {
  const item = lightboxSequence[lightboxIndex];
  if (!item) return;
  imageLightboxImg.src = item.src;
  imageLightboxImg.alt = item.alt;
  imageLightboxPrev.classList.toggle("hidden", lightboxIndex <= 0);
  imageLightboxNext.classList.toggle("hidden", lightboxIndex >= lightboxSequence.length - 1);
  // 背後の画面も、拡大表示で移動した先のスライドに連動させる
  if (item.slideNum !== selectedSlide) selectSlide(item.slideNum);
}

function lightboxPrev() {
  if (lightboxIndex > 0) {
    lightboxIndex -= 1;
    showLightboxFrame();
  }
}

function lightboxNext() {
  if (lightboxIndex < lightboxSequence.length - 1) {
    lightboxIndex += 1;
    showLightboxFrame();
  }
}

// kind/slideNum/variant から該当する画像を探して拡大表示する
function openImageLightbox(kind, slideNum, variant) {
  const seq = buildLightboxSequence(kind);
  const idx = seq.findIndex((item) => item.slideNum === slideNum && item.variant === variant);
  if (idx === -1) return;
  lightboxSequence = seq;
  lightboxIndex = idx;
  showLightboxFrame();
  imageLightboxModal.classList.remove("hidden");
}

function closeImageLightbox() {
  imageLightboxModal.classList.add("hidden");
  imageLightboxImg.src = "";
  lightboxSequence = [];
  lightboxIndex = -1;
}

// スライド画像エリア（伝えたいこと / 指摘事項 / 修正方針の各タブ）のクリックで拡大表示
slidePreviewImg.addEventListener("click", () => {
  if (!slidePreviewImg.getAttribute("src")) return;
  openImageLightbox("slide", selectedSlide, "single");
});
summarySlideImg.addEventListener("click", () => {
  if (!summarySlideImg.getAttribute("src")) return;
  openImageLightbox("slide", selectedSlide, "single");
});
suggestionBeforeImg.addEventListener("click", () => {
  if (!suggestionBeforeImg.getAttribute("src")) return;
  openImageLightbox("suggestion", selectedSlide, "before");
});
suggestionAfterImg.addEventListener("click", () => {
  if (!suggestionAfterImg.getAttribute("src") || suggestionAfterImg.classList.contains("hidden")) return;
  openImageLightbox("suggestion", selectedSlide, "after");
});

imageLightboxModal.addEventListener("click", (e) => {
  if (e.target === imageLightboxModal) closeImageLightbox();
});
imageLightboxClose.addEventListener("click", closeImageLightbox);
imageLightboxPrev.addEventListener("click", lightboxPrev);
imageLightboxNext.addEventListener("click", lightboxNext);

document.addEventListener("keydown", (e) => {
  if (imageLightboxModal.classList.contains("hidden")) return;
  if (e.key === "Escape") closeImageLightbox();
  else if (e.key === "ArrowLeft") lightboxPrev();
  else if (e.key === "ArrowRight") lightboxNext();
});

