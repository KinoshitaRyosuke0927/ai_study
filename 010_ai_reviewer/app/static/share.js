// ============================================================
// DOM 参照
// ============================================================

const shareLoading   = document.getElementById("share-loading");
const shareError     = document.getElementById("share-error");
const sharePanels    = document.getElementById("share-panels");
const shareBanner    = document.getElementById("share-banner");
const shareFileName  = document.getElementById("share-file-name");
const shareCreatedAt = document.getElementById("share-created-at");
const shareExpiresAt = document.getElementById("share-expires-at");

const slideList = document.getElementById("slide-list");

const tabBtns         = document.querySelectorAll(".tab-btn");
const tabInputEl       = document.getElementById("tab-input");
const tabSummaryEl     = document.getElementById("tab-summary");
const tabSuggestionEl  = document.getElementById("tab-suggestion");
const tabQaEl          = document.getElementById("tab-qa");

const inputSlideLabel   = document.getElementById("input-slide-label");
const slidePreviewImg   = document.getElementById("slide-preview-img");
const slideMessageText  = document.getElementById("slide-message-text");

const summaryPlaceholder     = document.getElementById("summary-placeholder");
const summaryContent         = document.getElementById("summary-content");
const summarySlideLabel      = document.getElementById("summary-slide-label");
const summarySlideImg        = document.getElementById("summary-slide-img");
const perspectiveSelectorEl  = document.getElementById("perspective-selector");
const summaryPerspectiveBody = document.getElementById("summary-perspective-body");

const suggestionPlaceholder = document.getElementById("suggestion-placeholder");
const suggestionContent     = document.getElementById("suggestion-content");
const suggestionSlideLabel  = document.getElementById("suggestion-slide-label");
const suggestionBeforeImg   = document.getElementById("suggestion-before-img");
const suggestionAfterImg    = document.getElementById("suggestion-after-img");
const suggestionBody        = document.getElementById("suggestion-body");

const qaPlaceholder = document.getElementById("qa-placeholder");
const qaContent     = document.getElementById("qa-content");
const qaList        = document.getElementById("qa-list");

// ============================================================
// 状態
// ============================================================

let shareData     = null;  // GET /api/share/{id} の結果
let selectedSlide = null;
let activeTab     = "input";
let activePerspectiveIndex = 0;

// ============================================================
// データ取得
// ============================================================

async function loadShare() {
  // "/share/{share_id}" からIDを取り出す
  const match = location.pathname.match(/\/share\/([^/]+)/);
  const shareId = match ? match[1] : "";

  try {
    const res = await fetch(`/api/share/${shareId}`);
    if (!res.ok) {
      shareLoading.classList.add("hidden");
      shareError.classList.remove("hidden");
      return;
    }
    shareData = await res.json();
  } catch (err) {
    shareLoading.classList.add("hidden");
    shareError.classList.remove("hidden");
    return;
  }

  shareLoading.classList.add("hidden");
  renderBanner(shareData);
  buildSlideList(shareData.slides || []);
  sharePanels.classList.remove("hidden");

  if ((shareData.slides || []).length > 0) selectSlide(1);
  renderSummaryTab();
  renderQaTab();
}

function renderBanner(data) {
  shareFileName.textContent = data.file_name || "（ファイル名なし）";
  const createdAt = data.created_at ? new Date(data.created_at) : null;
  const expiresAt = data.expires_at ? new Date(data.expires_at) : null;
  shareCreatedAt.textContent = createdAt ? `共有日: ${createdAt.toLocaleDateString("ja-JP")}` : "";
  shareExpiresAt.textContent = expiresAt ? `　有効期限: ${expiresAt.toLocaleDateString("ja-JP")}まで` : "";
  shareBanner.classList.remove("hidden");
}

// ============================================================
// スライド一覧
// ============================================================

function buildSlideList(slides) {
  slideList.innerHTML = "";
  slides.forEach((slide) => {
    const num = slide.slide_number;
    const item = document.createElement("div");
    item.className = "slide-list-item";
    item.dataset.slide = num;

    if (slide.image_png_b64) {
      const img = document.createElement("img");
      img.src = `data:image/png;base64,${slide.image_png_b64}`;
      img.alt = `スライド ${num}`;
      img.className = "slide-list-thumb";
      item.appendChild(img);
    }

    const label = document.createElement("span");
    label.className = "slide-list-label";
    label.textContent = `スライド ${num}`;
    item.appendChild(label);

    item.addEventListener("click", () => selectSlide(num));
    slideList.appendChild(item);
  });
}

function findSlide(num) {
  return (shareData.slides || []).find((s) => s.slide_number === num);
}

function selectSlide(num) {
  selectedSlide = num;
  document.querySelectorAll(".slide-list-item").forEach((el) => {
    el.classList.toggle("active", parseInt(el.dataset.slide, 10) === num);
  });
  refreshRightPanel();
}

// ============================================================
// タブ切り替え
// ============================================================

tabBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
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

function refreshRightPanel() {
  if (activeTab === "input") {
    if (selectedSlide) renderInputTab(selectedSlide);
  } else if (activeTab === "summary") {
    if (selectedSlide) renderSummarySlideImage(selectedSlide);
  } else if (activeTab === "suggestion") {
    if (selectedSlide) renderSuggestionTab(selectedSlide);
  }
}

function renderInputTab(num) {
  const slide = findSlide(num);
  inputSlideLabel.textContent = `スライド ${num}`;
  slidePreviewImg.src = slide && slide.image_png_b64 ? `data:image/png;base64,${slide.image_png_b64}` : "";
  slidePreviewImg.alt = `スライド ${num}`;
  const message = (slide && slide.intended_message) || shareData.overall_intended_message || "";
  slideMessageText.textContent = message || "（入力なし）";
}

// ============================================================
// 指摘事項タブ
// ============================================================

function renderSummarySlideImage(num) {
  const slide = findSlide(num);
  summarySlideLabel.textContent = `スライド ${num}`;
  summarySlideImg.src = slide && slide.image_png_b64 ? `data:image/png;base64,${slide.image_png_b64}` : "";
  summarySlideImg.alt = `スライド ${num}`;
}

function renderSummaryTab() {
  const perspectives = shareData.review?.presentation_summary?.perspectives || [];
  if (perspectives.length === 0) {
    summaryPlaceholder.classList.remove("hidden");
    summaryContent.classList.add("hidden");
    return;
  }

  perspectiveSelectorEl.className = "tab-bar";
  perspectiveSelectorEl.innerHTML = perspectives.map((p, i) =>
    `<button class="tab-btn${i === 0 ? " active" : ""}" data-index="${i}">${escHtml(p.label || p.type || "")}</button>`
  ).join("");
  perspectiveSelectorEl.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => selectPerspective(perspectives, Number(btn.dataset.index)));
  });

  activePerspectiveIndex = 0;
  showPerspective(perspectives, 0);

  summaryPlaceholder.classList.add("hidden");
  summaryContent.classList.remove("hidden");
}

function selectPerspective(perspectives, index) {
  activePerspectiveIndex = index;
  perspectiveSelectorEl.querySelectorAll(".tab-btn").forEach((btn, i) => {
    btn.classList.toggle("active", i === index);
  });
  showPerspective(perspectives, index);
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
// 修正方針タブ
// ============================================================

function renderSuggestionTab(num) {
  const slide = findSlide(num);
  const beforeSrc = slide && slide.image_png_b64 ? `data:image/png;base64,${slide.image_png_b64}` : "";

  const suggestions = shareData.suggestions || {};
  const data = suggestions[num];

  if (!data) {
    suggestionPlaceholder.classList.remove("hidden");
    suggestionContent.classList.add("hidden");
    return;
  }

  suggestionPlaceholder.classList.add("hidden");
  suggestionContent.classList.remove("hidden");

  suggestionSlideLabel.textContent = `スライド ${num}`;
  suggestionBeforeImg.src = beforeSrc;
  suggestionBeforeImg.alt = `スライド ${num} 修正前`;

  if (data.error) {
    suggestionAfterImg.src = "";
    suggestionBody.innerHTML = `<p class="placeholder-text">このスライドの修正方針の生成に失敗しました: ${escHtml(data.error)}</p>`;
    return;
  }

  if (data.skipped) {
    suggestionAfterImg.src = data.image_png_b64 ? `data:image/png;base64,${data.image_png_b64}` : beforeSrc;
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
  const qa = shareData.qa || [];
  if (qa.length === 0) {
    qaPlaceholder.classList.remove("hidden");
    qaContent.classList.add("hidden");
    return;
  }

  qaPlaceholder.classList.add("hidden");
  qaContent.classList.remove("hidden");

  qaList.innerHTML = qa.map((q, i) => `
    <div class="qa-item">
      <div class="qa-question">Q${i + 1}. ${escHtml(q.question || "")}</div>
      ${q.hint ? `<div class="qa-hint markdown-body">${renderMarkdown(q.hint)}</div>` : ""}
    </div>
  `).join("");
}

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

// kind: "slide"（スライド・指摘事項タブ用、スライド1枚のみ） / "suggestion"（修正方針タブ用、修正前後を含む）
function buildLightboxSequence(kind) {
  const seq = [];
  const slides = shareData.slides || [];
  if (kind === "slide") {
    slides.forEach((slide) => {
      if (!slide.image_png_b64) return;
      seq.push({
        slideNum: slide.slide_number,
        variant: "single",
        src: `data:image/png;base64,${slide.image_png_b64}`,
        alt: `スライド ${slide.slide_number}`,
      });
    });
  } else if (kind === "suggestion") {
    const suggestions = shareData.suggestions || {};
    slides.forEach((slide) => {
      const num = slide.slide_number;
      if (slide.image_png_b64) {
        seq.push({ slideNum: num, variant: "before", src: `data:image/png;base64,${slide.image_png_b64}`, alt: `スライド ${num} 修正前` });
      }
      const data = suggestions[num];
      if (data && data.edited_image_b64) {
        seq.push({ slideNum: num, variant: "after", src: `data:image/png;base64,${data.edited_image_b64}`, alt: `スライド ${num} 修正後` });
      }
    });
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
  if (!suggestionAfterImg.getAttribute("src")) return;
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

// ============================================================
// 初期化
// ============================================================

loadShare();
