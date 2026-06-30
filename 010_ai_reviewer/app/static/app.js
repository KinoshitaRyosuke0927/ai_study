// ============================================================
// ユーティリティ
// ============================================================

function showMessage(el, text, type) {
  el.textContent = text;
  el.className = `message ${type}`;
}

function hideMessage(el) {
  el.className = "message hidden";
}

function escHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

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
// 右パネル
const rightContent       = document.getElementById("right-content");
const tabBtns            = document.querySelectorAll(".tab-btn");
const tabInputEl         = document.getElementById("tab-input");
const tabSummaryEl       = document.getElementById("tab-summary");
const summaryPlaceholder = document.getElementById("summary-placeholder");
const summaryContent     = document.getElementById("summary-content");
const summaryBody        = document.getElementById("summary-body");

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
let reviewData        = null;      // APIから返ってきたレビュー結果
let activeTab         = "input";   // "input" | "review" | "summary"

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
      showMessage(uploadMessage, `エラー: ${data.detail}`, "error");
      return;
    }

    thumbnails    = data.thumbnails || [];
    slidePngs     = data.slide_pngs || [];
    thumbnailMime = data.thumbnail_mime || "image/png";
    renderMethod  = data.render_method || "none";
    slideCount    = data.slide_count || 0;
    reviewData    = null;
    selectedSlide = null;
    perSlideMessages = {};

    // 左パネルの各セクションを表示
    overallSection.classList.remove("hidden");
    slideListSection.classList.remove("hidden");
    reviewAction.classList.remove("hidden");
    if (summaryPlaceholder) summaryPlaceholder.classList.remove("hidden");
    if (summaryContent) summaryContent.classList.add("hidden");

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

    item.addEventListener("click", () => selectSlide(i));
    slideList.appendChild(item);
  }
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
    refreshRightPanel();
  });
});

// ============================================================
// 右パネルの内容更新
// ============================================================

function refreshRightPanel() {
  if (activeTab === "input") {
    if (selectedSlide) renderInputTab(selectedSlide);
  }
  // summary タブはレビュー実行時に描画済みのため再描画不要
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
// レビュー結果HTML生成
// ============================================================

let _accordionCounter = 0;

function buildSlideReviewHtml(slide) {
  const perspectives = slide.perspectives || [];
  if (perspectives.length === 0) return "<p class='placeholder-text'>レビュー結果がありません</p>";

  return perspectives.map((p) => {
    const label   = escHtml(p.label || p.type || "");
    const summary = escHtml(p.summary || "");
    const bodyId  = `accordion-body-${++_accordionCounter}`;
    return `
      <div class="accordion open">
        <button class="accordion-btn" data-target="${bodyId}" onclick="toggleAccordion(this)">
          <span>${label}</span>
          <span class="accordion-icon">▼</span>
        </button>
        <div class="accordion-body open" id="${bodyId}">
          <p class="perspective-summary">${summary}</p>
        </div>
      </div>
    `;
  }).join("");
}

function toggleAccordion(btn) {
  const bodyId = btn.dataset.target;
  const body = document.getElementById(bodyId);
  const isOpen = body.classList.toggle("open");
  btn.closest(".accordion").classList.toggle("open", isOpen);
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
      showMessage(reviewMessage, `エラー: ${data.detail}`, "error");
      return;
    }

    reviewData = data;

    showMessage(reviewMessage, "レビューが完了しました", "success");

    // 総評タブに切り替えて全体サマリーを表示
    activeTab = "summary";
    tabBtns.forEach((b) => b.classList.toggle("active", b.dataset.tab === "summary"));
    tabInputEl.classList.add("hidden");
    tabSummaryEl.classList.remove("hidden");

    renderOverallSummary(data.presentation_summary);

    selectSlide(1);
  } catch (err) {
    showMessage(reviewMessage, `ネットワークエラー: ${err.message}`, "error");
  } finally {
    reviewBtn.disabled = false;
    reviewBtn.textContent = "AIでレビューする";
  }
});

// ============================================================
// 全体サマリー（総評タブ）
// ============================================================

function renderOverallSummary(summary) {
  if (!summary) return;
  const perspectives = summary.perspectives || [];
  summaryBody.innerHTML = perspectives.length > 0
    ? buildSlideReviewHtml({ perspectives })
    : "<p class='placeholder-text'>レビュー結果がありません</p>";
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

