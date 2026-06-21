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
const overallSumSection  = document.getElementById("overall-summary-section");
const overallSumBody     = document.getElementById("overall-summary-body");

// 右パネル
const rightContent       = document.getElementById("right-content");
const tabBtns            = document.querySelectorAll(".tab-btn");
const tabInputEl         = document.getElementById("tab-input");
const tabReviewEl        = document.getElementById("tab-review");

// 伝えたいことタブ
const inputSlideLabel    = document.getElementById("input-slide-label");
const slidePreviewImg    = document.getElementById("slide-preview-img");
const slideMessageInput  = document.getElementById("slide-message-input");

// レビュー結果タブ
const reviewSlideLabel   = document.getElementById("review-slide-label");
const reviewSlideImg     = document.getElementById("review-slide-img");
const reviewSlidePlaceholder = document.getElementById("review-slide-placeholder");
const reviewSlideContent = document.getElementById("review-slide-content");
const reviewSlideDetails = document.getElementById("review-slide-details");

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
let activeTab         = "input";   // "input" | "review"

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
    overallSumSection.classList.add("hidden");

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
    tabReviewEl.classList.toggle("hidden", activeTab !== "review");
    // 全体評価はレビュー結果タブ表示時のみ表示
    overallSumSection.classList.toggle("hidden", activeTab !== "review" || !reviewData);
    refreshRightPanel();
  });
});

// ============================================================
// 右パネルの内容更新
// ============================================================

function refreshRightPanel() {
  if (!selectedSlide) return;

  if (activeTab === "input") {
    renderInputTab(selectedSlide);
  } else {
    renderReviewTab(selectedSlide);
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

function renderReviewTab(num) {
  const label = `スライド ${num}`;
  reviewSlideLabel.textContent = label;

  const src  = slidePngs[num - 1] || thumbnails[num - 1];
  const mime = slidePngs[num - 1] ? "image/png" : thumbnailMime;
  reviewSlideImg.src = src ? `data:${mime};base64,${src}` : "";
  reviewSlideImg.alt = label;

  if (!reviewData) {
    reviewSlidePlaceholder.classList.remove("hidden");
    reviewSlideContent.classList.add("hidden");
    return;
  }

  const slideResult = (reviewData.slides || []).find((s) => s.slide_number === num);
  if (!slideResult) {
    reviewSlidePlaceholder.textContent = "このスライドのレビュー結果がありません";
    reviewSlidePlaceholder.classList.remove("hidden");
    reviewSlideContent.classList.add("hidden");
    return;
  }

  reviewSlideDetails.innerHTML = buildSlideReviewHtml(slideResult);
  reviewSlidePlaceholder.classList.add("hidden");
  reviewSlideContent.classList.remove("hidden");
}

// ============================================================
// レビュー結果の各スライドHTML生成
// ============================================================

function buildSlideReviewHtml(slide) {
  // 概要エリア（summary + good_point をまとめて表示）
  const summaryParts = [];
  if (slide.summary) {
    summaryParts.push(`<p class="review-summary-text">${escHtml(slide.summary)}</p>`);
  }
  if (slide.good_point) {
    summaryParts.push(`<div class="good-point">✓ ${escHtml(slide.good_point)}</div>`);
  }
  const summarySection = summaryParts.length > 0
    ? `<div class="review-section-block">
         <div class="review-section-label">概要</div>
         ${summaryParts.join("")}
       </div>`
    : "";

  // 観点別エリア（構造・ビジュアル・内容）
  const gridSection = `
    <div class="review-section-block">
      <div class="review-section-label">観点別</div>
      <div class="review-grid">
        ${buildReviewItem("構造", slide.structure_review)}
        ${buildReviewItem("ビジュアル", slide.visual_review)}
        ${buildReviewItem("内容", slide.content_review)}
      </div>
    </div>
  `;

  return summarySection + gridSection;
}

function buildReviewItem(label, review) {
  if (!review) return "";
  const findings    = (review.findings    || []).map((f) => `<li>${escHtml(f)}</li>`).join("");
  const suggestions = (review.suggestions || []).map((s) => `<li class="suggestion">${escHtml(s)}</li>`).join("");
  return `
    <div class="review-item">
      <div class="review-item-title">${label}</div>
      <ul>${findings}${suggestions}</ul>
    </div>
  `;
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

function buildPerSlideMessagesStr() {
  const lines = [];
  for (let i = 1; i <= slideCount; i++) {
    const msg = (perSlideMessages[i] || "").trim();
    if (msg) lines.push(`${i}: ${msg}`);
  }
  return lines.join("\n");
}

reviewBtn.addEventListener("click", async () => {
  if (!currentFile) return;

  saveCurrentInput();
  hideMessage(reviewMessage);
  reviewBtn.disabled = true;
  reviewBtn.innerHTML = '<span class="loading"></span>AIがレビュー中...';

  try {
    const form = new FormData();
    form.append("file", currentFile);
    form.append("overall_intended_message", intendedMessage.value.trim());
    form.append("per_slide_intended_messages", buildPerSlideMessagesStr());

    const res  = await fetch("/api/review", { method: "POST", body: form });
    const data = await res.json();

    if (!res.ok) {
      showMessage(reviewMessage, `エラー: ${data.detail}`, "error");
      return;
    }

    reviewData = data;

    showMessage(reviewMessage, "レビューが完了しました", "success");

    // レビュー結果タブに切り替えてスライド1を選択・表示
    activeTab = "review";
    tabBtns.forEach((b) => b.classList.toggle("active", b.dataset.tab === "review"));
    tabInputEl.classList.add("hidden");
    tabReviewEl.classList.remove("hidden");

    // 全体サマリーをタブ上部に表示（レビュー結果タブ時のみ）
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
// 全体サマリー（タブ上部）
// ============================================================

function renderOverallSummary(summary) {
  if (!summary) return;

  const alignment = summary.overall_alignment
    ? `<p>${escHtml(summary.overall_alignment)}</p>`
    : "";

  const risks = renderTagList(summary.overall_risks, "risk", "リスク");
  const actions = renderTagList(summary.priority_actions, "action", "優先アクション");

  overallSumBody.innerHTML = alignment + risks + actions;
  overallSumSection.classList.remove("hidden");
}

function renderTagList(items, tagClass, label) {
  if (!items || items.length === 0) return "";
  const tags = items.map((t) => `<span class="tag ${tagClass}">${escHtml(t)}</span>`).join("");
  return `<p style="font-size:0.75rem;color:#718096;margin:8px 0 4px;">${label}</p>
          <div class="tag-list">${tags}</div>`;
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
// 全体評価アコーディオン
// ============================================================

document.getElementById("overall-summary-toggle").addEventListener("click", () => {
  const body    = document.getElementById("overall-summary-body");
  const chevron = document.querySelector(".accordion-chevron");
  const closing = !body.classList.contains("closed");
  body.classList.toggle("closed", closing);
  chevron.classList.toggle("closed", closing);
});
