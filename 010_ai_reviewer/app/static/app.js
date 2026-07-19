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

function formatErrorDetail(detail) {
  if (Array.isArray(detail)) {
    // FastAPI の 422 バリデーションエラー（{loc, msg, type} の配列）を整形
    return detail
      .map((d) => (d && typeof d === "object" ? `${(d.loc || []).join(".")}: ${d.msg || JSON.stringify(d)}` : String(d)))
      .join(" / ");
  }
  if (detail && typeof detail === "object") {
    return JSON.stringify(detail);
  }
  return String(detail);
}

function escHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ============================================================
// 簡易Markdownレンダリング（箇条書き・太字・インラインコード対応）
// ============================================================

function inlineMarkdown(text) {
  return escHtml(text)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`(.+?)`/g, "<code>$1</code>");
}

function renderMarkdown(text) {
  const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
  const htmlParts = [];
  let currentListTag = null;
  let paragraphLines = [];

  const flushParagraph = () => {
    if (paragraphLines.length) {
      htmlParts.push(`<p>${paragraphLines.map(inlineMarkdown).join("<br>")}</p>`);
      paragraphLines = [];
    }
  };
  const closeList = () => {
    if (currentListTag) {
      htmlParts.push(`</${currentListTag}>`);
      currentListTag = null;
    }
  };

  lines.forEach((rawLine) => {
    const bulletMatch = rawLine.match(/^\s*[-*+]\s+(.*)$/);
    const orderedMatch = rawLine.match(/^\s*\d+[.)]\s+(.*)$/);
    const match = bulletMatch || orderedMatch;

    if (match) {
      flushParagraph();
      const tag = bulletMatch ? "ul" : "ol";
      if (currentListTag !== tag) {
        closeList();
        htmlParts.push(`<${tag}>`);
        currentListTag = tag;
      }
      htmlParts.push(`<li>${inlineMarkdown(match[1])}</li>`);
    } else if (rawLine.trim() === "") {
      closeList();
      flushParagraph();
    } else {
      closeList();
      paragraphLines.push(rawLine.trim());
    }
  });
  closeList();
  flushParagraph();

  return htmlParts.join("");
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
const suggestBtn         = document.getElementById("suggest-btn");
const suggestMessage     = document.getElementById("suggest-message");
const downloadCsvBtn     = document.getElementById("download-csv-btn");
const downloadSuggestionBtn = document.getElementById("download-suggestion-btn");
// 右パネル
const rightContent       = document.getElementById("right-content");
const tabBtns               = document.querySelectorAll(".tab-btn");
const tabInputEl            = document.getElementById("tab-input");
const tabSummaryEl          = document.getElementById("tab-summary");
const tabSuggestionEl       = document.getElementById("tab-suggestion");
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
const suggestionBody        = document.getElementById("suggestion-body");

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
let suggestionBySlide       = {};    // slide_number -> 修正方針テキスト
let activeTab               = "input"; // "input" | "summary" | "suggestion"
let activePerspectiveIndex  = 0;

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
    selectedSlide = null;
    perSlideMessages = {};
    downloadCsvBtn.disabled = true;
    suggestBtn.disabled = true;
    downloadSuggestionBtn.disabled = true;

    // 左パネルの各セクションを表示
    overallSection.classList.remove("hidden");
    slideListSection.classList.remove("hidden");
    reviewAction.classList.remove("hidden");
    if (summaryPlaceholder) summaryPlaceholder.classList.remove("hidden");
    if (summaryContent) summaryContent.classList.add("hidden");
    if (suggestionPlaceholder) suggestionPlaceholder.classList.remove("hidden");
    if (suggestionContent) suggestionContent.classList.add("hidden");

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
    tabSuggestionEl.classList.toggle("hidden", activeTab !== "suggestion");
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
    suggestionBody.innerHTML = "<p class='placeholder-text'>このスライドの修正方針はありません</p>";
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
    reviewBtn.textContent = "AIでレビューする";
  }
});

// ============================================================
// 修正方針の提案
// ============================================================

suggestBtn.addEventListener("click", async () => {
  const perspectives = reviewData?.presentation_summary?.perspectives || [];
  if (!currentFile || perspectives.length === 0) return;

  hideMessage(suggestMessage);
  suggestBtn.disabled = true;
  suggestBtn.innerHTML = '<span class="loading"></span>AIが修正方針を検討中...';

  try {
    const slides = slidePngs.map((png, i) => ({
      slide_number: i + 1,
      image_png_b64: png,
    }));

    const res  = await fetch("/api/suggest", {
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
    const data = await res.json();

    if (!res.ok) {
      showMessage(suggestMessage, `エラー: ${formatErrorDetail(data.detail)}`, "error");
      return;
    }

    suggestionBySlide = {};
    (data.slide_suggestions || []).forEach((s) => {
      suggestionBySlide[s.slide_number] = s;
    });
    downloadSuggestionBtn.disabled = false;

    showMessage(suggestMessage, "修正方針の提案が完了しました", "success");

    // 修正方針タブに切り替えて結果を表示
    activeTab = "suggestion";
    tabBtns.forEach((b) => b.classList.toggle("active", b.dataset.tab === "suggestion"));
    tabInputEl.classList.add("hidden");
    tabSummaryEl.classList.add("hidden");
    tabSuggestionEl.classList.remove("hidden");

    suggestionPlaceholder.classList.add("hidden");
    suggestionContent.classList.remove("hidden");

    if (selectedSlide) renderSuggestionTab(selectedSlide);
  } catch (err) {
    showMessage(suggestMessage, `ネットワークエラー: ${err.message}`, "error");
  } finally {
    suggestBtn.disabled = false;
    suggestBtn.textContent = "修正方針を提示する";
  }
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

function markdownTableEscape(value) {
  const str = String(value ?? "");
  return str.replace(/\|/g, "\\|").replace(/\r?\n/g, "<br>");
}

// Markdownの箇条書き（- / * / + / 1. など）を1項目ずつのテキスト配列に分解する
// 箇条書きが見つからない場合は、テキスト全体を1項目として扱う
function extractMarkdownItems(text) {
  const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
  const items = [];

  lines.forEach((rawLine) => {
    const bulletMatch = rawLine.match(/^\s*[-*+]\s+(.*)$/);
    const orderedMatch = rawLine.match(/^\s*\d+[.)]\s+(.*)$/);
    const match = bulletMatch || orderedMatch;
    const content = match ? match[1].trim() : rawLine.trim();
    if (content) items.push(content);
  });

  if (items.length === 0) {
    const whole = String(text || "").trim();
    if (whole) items.push(whole);
  }

  return items;
}

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

