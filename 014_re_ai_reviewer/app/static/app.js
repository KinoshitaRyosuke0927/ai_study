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
const downloadFindingsBtn   = document.getElementById("download-findings-btn");
const downloadSuggestionBtn = document.getElementById("download-suggestion-btn");
// 修正対象指摘事項選択モーダル
const suggestSelectionModal      = document.getElementById("suggest-selection-modal");
const suggestSelectionEmpty      = document.getElementById("suggest-selection-empty");
const suggestSelectionList       = document.getElementById("suggest-selection-list");
const suggestSelectionCancelBtn  = document.getElementById("suggest-selection-cancel-btn");
const suggestSelectionRunBtn     = document.getElementById("suggest-selection-run-btn");
const suggestSelectionMessage    = document.getElementById("suggest-selection-message");
// 右パネル
const rightContent       = document.getElementById("right-content");
const tabBtns               = document.querySelectorAll(".tab-btn");
const tabInputEl            = document.getElementById("tab-input");
const tabFindingsEl         = document.getElementById("tab-findings");
const tabSuggestionEl       = document.getElementById("tab-suggestion");
const findingsPlaceholder   = document.getElementById("findings-placeholder");
const findingsContent       = document.getElementById("findings-content");
const findingsOverallSummaryEl = document.getElementById("findings-overall-summary");
const findingsSlideLabel    = document.getElementById("findings-slide-label");
const findingsSlideImg      = document.getElementById("findings-slide-img");
const findingsSlideBody     = document.getElementById("findings-slide-body");
const suggestionPlaceholder = document.getElementById("suggestion-placeholder");
const suggestionContent     = document.getElementById("suggestion-content");
const suggestionSlideLabel  = document.getElementById("suggestion-slide-label");
const suggestionBeforeImg   = document.getElementById("suggestion-before-img");
const suggestionAfterImg    = document.getElementById("suggestion-after-img");
const suggestionAfterSpinner = document.getElementById("suggestion-after-spinner");
const suggestionBody        = document.getElementById("suggestion-body");

// 伝えたいことタブ
const inputSlideLabel    = document.getElementById("input-slide-label");
const slidePreviewImg    = document.getElementById("slide-preview-img");
const slideMessageInput  = document.getElementById("slide-message-input");

// ============================================================
// 状態
// ============================================================

let currentFile       = null;
let thumbnails        = [];        // 一覧用 Base64 画像（JPEG）
let slidePngs         = [];        // プレビュー・AI入力用 Base64 PNG（LibreOffice高品質）
let thumbnailMime     = "image/png";  // thumbnails の MIME タイプ
let renderMethod      = "none";    // "libre_office" | "none"
let slideCount        = 0;
let selectedSlide     = null;      // 現在選択中のスライド番号（1始まり）
let perSlideMessages  = {};        // slideNum -> string
let findingsData             = null; // APIから返ってきた指摘事項（Finding[]）
let suggestionBySlide        = {};   // slide_number -> 修正方針テキスト（またはエラー情報）
let activeTab                = "input"; // "input" | "findings" | "suggestion"
let suggestInProgress        = false; // 修正方針提案のストリーミング処理中かどうか

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
    findingsData      = null;
    suggestionBySlide  = {};
    selectedSlide      = null;
    perSlideMessages   = {};
    downloadFindingsBtn.disabled = true;
    suggestBtn.disabled = true;
    downloadSuggestionBtn.disabled = true;

    // 左パネルの各セクションを表示
    overallSection.classList.remove("hidden");
    slideListSection.classList.remove("hidden");
    reviewAction.classList.remove("hidden");
    if (findingsPlaceholder) findingsPlaceholder.classList.remove("hidden");
    if (findingsContent) findingsContent.classList.add("hidden");
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

function resetSlideListSuggestStatus() {
  document.querySelectorAll(".slide-list-item .slide-list-status").forEach((el) => {
    el.className = "slide-list-status hidden";
    el.textContent = "";
    el.title = "";
  });
}

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
  if (selectedSlide && activeTab === "input") {
    perSlideMessages[selectedSlide] = slideMessageInput.value;
  }

  selectedSlide = num;

  document.querySelectorAll(".slide-list-item").forEach((el) => {
    el.classList.toggle("active", parseInt(el.dataset.slide, 10) === num);
  });

  rightContent.classList.remove("hidden");

  refreshRightPanel();
}

// ============================================================
// タブ切り替え（右パネル）
// ============================================================

tabBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    if (activeTab === "input" && selectedSlide) {
      perSlideMessages[selectedSlide] = slideMessageInput.value;
    }
    activeTab = btn.dataset.tab;
    tabBtns.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    tabInputEl.classList.toggle("hidden", activeTab !== "input");
    tabFindingsEl.classList.toggle("hidden", activeTab !== "findings");
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
  } else if (activeTab === "findings") {
    if (selectedSlide) renderFindingsTab(selectedSlide);
  } else if (activeTab === "suggestion") {
    if (selectedSlide) renderSuggestionTab(selectedSlide);
  }
}

function renderInputTab(num) {
  const badge = renderMethod === "libre_office"
    ? ' <span class="render-badge">LibreOffice</span>'
    : "";
  inputSlideLabel.innerHTML = `スライド ${num}${badge}`;

  const src  = slidePngs[num - 1] || thumbnails[num - 1];
  const mime = slidePngs[num - 1] ? "image/png" : thumbnailMime;
  slidePreviewImg.src = src ? `data:${mime};base64,${src}` : "";
  slidePreviewImg.alt = `スライド ${num}`;

  slideMessageInput.value = perSlideMessages[num] || "";
}

// ============================================================
// 指摘事項タブ — スライドごとの指摘カード
// ============================================================

const SEVERITY_LABELS = { blocker: "blocker", high: "high", medium: "medium", low: "low" };

function renderFindingsTab(num) {
  const src  = slidePngs[num - 1] || thumbnails[num - 1];
  const mime = slidePngs[num - 1] ? "image/png" : thumbnailMime;
  findingsSlideLabel.textContent = `スライド ${num}`;
  findingsSlideImg.src = src ? `data:${mime};base64,${src}` : "";
  findingsSlideImg.alt = `スライド ${num}`;

  const slideFindings = (findingsData || []).filter((f) => f.slide_number === num);

  if (slideFindings.length === 0) {
    findingsSlideBody.innerHTML = `<div class="good-point">このスライドに指摘事項はありませんでした。</div>`;
    return;
  }

  findingsSlideBody.innerHTML = `
    <div class="review-section-block">
      <div class="review-section-label">指摘事項（${slideFindings.length}件）</div>
      ${slideFindings.map(renderFindingCard).join("")}
    </div>
  `;
}

function renderFindingCard(f) {
  const likeness = Math.round((f.manager_likeness || 0) * 100);
  return `
    <div class="review-item severity-${f.severity}">
      <div class="review-item-title">
        <span class="tag severity-${f.severity}">${escHtml(SEVERITY_LABELS[f.severity] || f.severity)}</span>
        ${f.category ? `<span>${escHtml(f.category)}</span>` : ""}
        <span>上司らしさ ${likeness}%</span>
      </div>
      <p>${escHtml(f.issue)}</p>
      <ul>
        ${f.evidence ? `<li>根拠: ${escHtml(f.evidence)}</li>` : ""}
        ${f.critic_comment ? `<li>検証コメント: ${escHtml(f.critic_comment)}</li>` : ""}
        ${f.suggestion ? `<li class="suggestion">修正提案: ${escHtml(f.suggestion)}</li>` : ""}
      </ul>
    </div>
  `;
}

function renderOverallFindingsSummary(findings) {
  const counts = { blocker: 0, high: 0, medium: 0, low: 0 };
  findings.forEach((f) => {
    if (f.severity in counts) counts[f.severity] += 1;
  });

  findingsOverallSummaryEl.innerHTML = `
    <p>資料全体で ${findings.length} 件の指摘事項が見つかりました。</p>
    <div class="tag-list">
      <span class="tag severity-blocker">blocker ${counts.blocker}</span>
      <span class="tag severity-high">high ${counts.high}</span>
      <span class="tag severity-medium">medium ${counts.medium}</span>
      <span class="tag severity-low">low ${counts.low}</span>
    </div>
  `;

  findingsPlaceholder.classList.add("hidden");
  findingsContent.classList.remove("hidden");
}

// ============================================================
// 修正方針タブ — 修正前後の画像比較
// ============================================================

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
// AIレビュー実行
// ============================================================

function saveCurrentInput() {
  if (selectedSlide && activeTab === "input") {
    perSlideMessages[selectedSlide] = slideMessageInput.value;
  }
}

// overall_intended_message と、各スライドの個別メッセージ（あれば）をまとめて1つのテキストにする
// （現状のAIレビューパイプラインは資料全体の意図テキストを1本受け取る設計のため）
function buildCombinedIntendedMessage() {
  const overallMsg = intendedMessage.value.trim();
  const slideNotes = Object.entries(perSlideMessages)
    .filter(([, v]) => (v || "").trim())
    .map(([num, v]) => `スライド${num}: ${v.trim()}`);

  if (slideNotes.length === 0) return overallMsg;

  const notesBlock = "各スライドの補足:\n" + slideNotes.join("\n");
  return overallMsg ? `${overallMsg}\n\n${notesBlock}` : notesBlock;
}

reviewBtn.addEventListener("click", async () => {
  if (!currentFile) return;

  saveCurrentInput();
  hideMessage(reviewMessage);
  reviewBtn.disabled = true;
  reviewBtn.innerHTML = '<span class="loading"></span>AIがレビュー中...';

  try {
    const overallIntendedMessage = buildCombinedIntendedMessage();
    const slides = slidePngs.map((png, i) => ({
      slide_number: i + 1,
      image_png_b64: png,
    }));

    const res  = await fetch("/api/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ overall_intended_message: overallIntendedMessage, slides }),
    });
    const data = await res.json();

    if (!res.ok) {
      showMessage(reviewMessage, `エラー: ${formatErrorDetail(data.detail)}`, "error");
      return;
    }

    findingsData = data.findings || [];
    suggestionBySlide = {};
    downloadFindingsBtn.disabled = findingsData.length === 0;
    suggestBtn.disabled = false;
    downloadSuggestionBtn.disabled = true;
    if (suggestionPlaceholder) suggestionPlaceholder.classList.remove("hidden");
    if (suggestionContent) suggestionContent.classList.add("hidden");

    showMessage(reviewMessage, `レビューが完了しました（${findingsData.length}件の指摘）`, "success");

    // 指摘事項タブに切り替えて結果を表示
    activeTab = "findings";
    tabBtns.forEach((b) => b.classList.toggle("active", b.dataset.tab === "findings"));
    tabInputEl.classList.add("hidden");
    tabFindingsEl.classList.remove("hidden");
    tabSuggestionEl.classList.add("hidden");

    renderOverallFindingsSummary(findingsData);

    selectSlide(1);
  } catch (err) {
    showMessage(reviewMessage, `ネットワークエラー: ${err.message}`, "error");
  } finally {
    reviewBtn.disabled = false;
    reviewBtn.textContent = "AIレビューを実行";
  }
});

// ============================================================
// SSEストリームの読み取り
// ============================================================

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
// 修正方針の提案（010_ai_reviewerの画像編集提案機能を移植）
// ============================================================

suggestBtn.addEventListener("click", () => {
  if (!currentFile || !findingsData) return;
  openSuggestSelectionModal(findingsData);
});

async function runSuggestionProcess(findings) {
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

  resetSlideListSuggestStatus();
  slides.forEach((s) => setSlideListSuggestStatus(s.slide_number, "pending"));

  activeTab = "suggestion";
  tabBtns.forEach((b) => b.classList.toggle("active", b.dataset.tab === "suggestion"));
  tabInputEl.classList.add("hidden");
  tabFindingsEl.classList.add("hidden");
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
      body: JSON.stringify({ slides, findings }),
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

let suggestFindingItems = []; // { id, slide_number, text, checked, finding }

function groupFindingsBySlide(items) {
  const groups = [];
  const indexBySlide = {};
  items.forEach((item) => {
    const key = item.slide_number;
    if (!(key in indexBySlide)) {
      indexBySlide[key] = groups.length;
      groups.push({ slide_number: key, label: `スライド ${key}`, items: [] });
    }
    groups[indexBySlide[key]].items.push(item);
  });
  return groups;
}

// グループ見出しの一括ON/OFFチェックボックスと、個別チェックボックスの状態を同期させる
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

function renderSuggestSelectionList() {
  const groups = groupFindingsBySlide(suggestFindingItems);

  suggestSelectionList.innerHTML = groups.map((group) => {
    const rows = group.items.map((item) => {
      const checkboxId = `suggest-finding-${item.id}`;
      return `
        <div class="review-point-row">
          <input type="checkbox" id="${checkboxId}" data-id="${item.id}" ${item.checked ? "checked" : ""}>
          <label for="${checkboxId}">[${escHtml(item.finding.severity)}] ${escHtml(item.text)}</label>
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

function buildFilteredFindingsFromSelection() {
  return suggestFindingItems.filter((item) => item.checked).map((item) => item.finding);
}

function openSuggestSelectionModal(findings) {
  hideMessage(suggestSelectionMessage);
  suggestFindingItems = findings.map((f, i) => ({
    id: i,
    slide_number: f.slide_number,
    text: f.issue,
    checked: true,
    finding: f,
  }));
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
  const filteredFindings = buildFilteredFindingsFromSelection();
  if (filteredFindings.length === 0) {
    showMessage(suggestSelectionMessage, "少なくとも1つの指摘事項を選択してください", "error");
    return;
  }
  closeSuggestSelectionModal();
  runSuggestionProcess(filteredFindings);
});

// ============================================================
// スライドメッセージの自動保存
// ============================================================

slideMessageInput.addEventListener("input", () => {
  if (selectedSlide) {
    perSlideMessages[selectedSlide] = slideMessageInput.value;
  }
});

// ============================================================
// 指摘事項のMarkdownダウンロード
// ============================================================

function markdownTableEscape(value) {
  const str = String(value ?? "");
  return str.replace(/\|/g, "\\|").replace(/\r?\n/g, "<br>");
}

downloadFindingsBtn.addEventListener("click", () => {
  if (!findingsData || findingsData.length === 0) return;

  const lines = ["| No | スライド | カテゴリ | severity | 上司らしさ | 指摘事項 | 根拠 | 修正提案 |", "| --- | --- | --- | --- | --- | --- | --- | --- |"];
  findingsData.forEach((f, i) => {
    lines.push(
      `| ${i + 1} | ${f.slide_number} | ${markdownTableEscape(f.category)} | ${markdownTableEscape(f.severity)} | ` +
      `${Math.round((f.manager_likeness || 0) * 100)}% | ${markdownTableEscape(f.issue)} | ${markdownTableEscape(f.evidence)} | ${markdownTableEscape(f.suggestion)} |`
    );
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
// 修正後スライドのPDFダウンロード（010_ai_reviewerと同一）
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
// スライド画像拡大表示（ライトボックス）
// ============================================================

const imageLightboxModal = document.getElementById("image-lightbox-modal");
const imageLightboxImg   = document.getElementById("image-lightbox-img");
const imageLightboxClose = document.getElementById("image-lightbox-close");

function openImageLightbox(src, alt) {
  if (!src) return;
  imageLightboxImg.src = src;
  imageLightboxImg.alt = alt || "";
  imageLightboxModal.classList.remove("hidden");
}

function closeImageLightbox() {
  imageLightboxModal.classList.add("hidden");
  imageLightboxImg.src = "";
}

document.querySelectorAll(".slide-image-wrap img").forEach((img) => {
  img.addEventListener("click", () => {
    if (!img.getAttribute("src") || img.classList.contains("hidden")) return;
    openImageLightbox(img.src, img.alt);
  });
});

imageLightboxModal.addEventListener("click", closeImageLightbox);
imageLightboxClose.addEventListener("click", closeImageLightbox);

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !imageLightboxModal.classList.contains("hidden")) {
    closeImageLightbox();
  }
});
