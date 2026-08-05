// ============================================================
// DOM参照
// ============================================================

const chatLog = document.getElementById("chat-log");
const chatInput = document.getElementById("chat-input");
const sendButton = document.getElementById("send-button");
const resetButton = document.getElementById("reset-btn");
const pptxUploadBtn = document.getElementById("pptx-upload-btn");
const pptxUploadInput = document.getElementById("pptx-upload-input");

const slideCardsEl = document.getElementById("slide-cards");
const reviseBtn = document.getElementById("revise-btn");
const downloadBtn = document.getElementById("download-btn");
const slidesMessageEl = document.getElementById("slides-message");

const imageLightboxModal = document.getElementById("image-lightbox-modal");
const imageLightboxImg = document.getElementById("image-lightbox-img");
const imageLightboxClose = document.getElementById("image-lightbox-close");

// ============================================================
// 状態
// ============================================================

// 会話履歴（role: "user" | "assistant"）。assistantはmessageの本文テキストのみを保持する
const history = [];

// ユーザが選択した資料スタイルの元画像（スライド画像生成時のベースとして使用）
let selectedStyleImageB64 = null;

// slide_number -> { slideNumber, title, imageB64, img, spinner, textarea, card }
const slidesState = new Map();

// チャット欄の初期表示メッセージ（履歴初期化時にも表示する。会話履歴には含めない）
const INITIAL_MESSAGE = "どのような資料を作成したいか教えてください。";
const SLIDES_READY_MESSAGE =
    "資料イメージを作成しましたので、確認をお願いします。変更したい箇所がある場合は、各カードの入力欄に記入して「修正依頼」を押してください。";
const SLIDES_REVISED_MESSAGE = "資料イメージを修正しましたので、確認をお願いします。変更したい箇所がある場合は教えてください。";

// ============================================================
// Markdown・数式レンダリング
// ============================================================

function escapeHtml(text) {
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}

/** インライン記法（コード・太字・斜体）をHTMLに変換する */
function renderInlineMarkdown(text) {
    return escapeHtml(text)
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
        .replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, "<em>$1</em>");
}

/** \[ ... \] や $$ ... $$ の数式ブロックが複数行にまたがっていても崩れないよう、内部の改行を1行に畳み込む */
function normalizeMathBlocks(text) {
    const collapseInner = (_match, inner) => inner.replace(/\s*\n\s*/g, " ").trim();
    return text
        .replace(/\\\[([\s\S]*?)\\\]/g, (m, inner) => `\\[${collapseInner(m, inner)}\\]`)
        .replace(/\$\$([\s\S]*?)\$\$/g, (m, inner) => `$$${collapseInner(m, inner)}$$`);
}

/** AIの返答に含まれる簡易Markdown（見出し・箇条書き・太字/斜体/コード）をHTMLに変換する */
function renderMarkdown(text) {
    const lines = normalizeMathBlocks(text).split("\n");
    const htmlParts = [];
    let listBuffer = [];

    const flushList = () => {
        if (listBuffer.length === 0) return;
        htmlParts.push(`<ul>${listBuffer.join("")}</ul>`);
        listBuffer = [];
    };

    for (const rawLine of lines) {
        const line = rawLine.trim();
        const listMatch = line.match(/^[-*]\s+(.*)$/);
        const headingMatch = line.match(/^(#{1,6})\s+(.*)$/);

        if (listMatch) {
            listBuffer.push(`<li>${renderInlineMarkdown(listMatch[1])}</li>`);
            continue;
        }
        flushList();

        if (headingMatch) {
            const level = headingMatch[1].length;
            htmlParts.push(`<h${level}>${renderInlineMarkdown(headingMatch[2])}</h${level}>`);
        } else if (line === "") {
            htmlParts.push("");
        } else {
            htmlParts.push(`<p>${renderInlineMarkdown(line)}</p>`);
        }
    }
    flushList();

    return htmlParts.filter((part) => part !== "").join("");
}

/** KaTeXのauto-renderで、要素内の \(...\) \[...\] $...$ $$...$$ 記法を数式として描画する */
function renderMath(el) {
    if (typeof renderMathInElement !== "function") return;
    try {
        renderMathInElement(el, {
            delimiters: [
                { left: "$$", right: "$$", display: true },
                { left: "\\[", right: "\\]", display: true },
                { left: "\\(", right: "\\)", display: false },
                { left: "$", right: "$", display: false },
            ],
            throwOnError: false,
        });
    } catch (err) {
        // 数式の描画に失敗しても、Markdownの表示自体は継続する
        console.error("数式の描画に失敗しました:", err);
    }
}

// ============================================================
// チャット表示
// ============================================================

function appendMessage(role, content) {
    const row = document.createElement("div");
    row.className = `chat-message-row ${role}`;

    // AI側の吹き出しの左に、話者を判別する丸アイコンを表示する
    if (role === "assistant") {
        const avatar = document.createElement("img");
        avatar.className = "avatar";
        avatar.src = "/images/kanata_icon.png";
        avatar.alt = "AI";
        row.appendChild(avatar);
    }

    const bubble = document.createElement("div");
    bubble.className = "message";
    // AIの返答はMarkdown記法を解釈して表示し、ユーザー入力はそのままテキスト表示する
    if (role === "assistant") {
        bubble.innerHTML = renderMarkdown(content);
        renderMath(bubble);
    } else {
        bubble.textContent = content;
    }
    row.appendChild(bubble);

    chatLog.appendChild(row);
    chatLog.scrollTop = chatLog.scrollHeight;
    return { row, bubble };
}

/** AIが提示した選択肢（テキストのみ、またはスタイル画像付き）をチャット欄にボタンとして表示する */
function renderOptions(options) {
    const wrap = document.createElement("div");
    wrap.className = "chat-options";

    options.forEach((opt) => {
        const isImageOption = typeof opt === "object" && opt !== null;
        const label = isImageOption ? opt.label : opt;

        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "chat-option-btn";

        if (isImageOption && opt.image_b64) {
            const img = document.createElement("img");
            img.className = "chat-option-thumb";
            img.src = `data:image/png;base64,${opt.image_b64}`;
            img.alt = label;
            btn.appendChild(img);
        }

        const span = document.createElement("span");
        span.textContent = label;
        btn.appendChild(span);

        btn.addEventListener("click", () => {
            // 選択後は同じ選択肢群を再度クリックできないようにする
            wrap.querySelectorAll(".chat-option-btn").forEach((b) => (b.disabled = true));
            if (isImageOption && opt.image_b64) {
                selectedStyleImageB64 = opt.image_b64;
            }
            sendMessage(label);
        });

        wrap.appendChild(btn);
    });

    chatLog.appendChild(wrap);
    chatLog.scrollTop = chatLog.scrollHeight;
}

/**
 * スタイル案（label/image_promptのみ、画像未生成）をチャット欄にプレースホルダーとして表示し、
 * 画像が生成できたものから順にサムネイルを差し替える
 */
function renderStyleOptions(proposals) {
    const wrap = document.createElement("div");
    wrap.className = "chat-options";

    const entries = proposals.map((proposal) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "chat-option-btn";
        btn.disabled = true; // 画像が届くまでは選択不可にする

        const thumbWrap = document.createElement("div");
        thumbWrap.className = "chat-option-thumb-wrap";

        const img = document.createElement("img");
        img.className = "chat-option-thumb hidden";
        img.alt = proposal.label;
        thumbWrap.appendChild(img);

        const spinner = document.createElement("div");
        spinner.className = "chat-option-spinner";
        spinner.innerHTML = '<span class="loading"></span>';
        thumbWrap.appendChild(spinner);

        btn.appendChild(thumbWrap);

        const span = document.createElement("span");
        span.textContent = proposal.label;
        btn.appendChild(span);

        let imageB64 = null;
        btn.addEventListener("click", () => {
            if (!imageB64) return;
            wrap.querySelectorAll(".chat-option-btn").forEach((b) => (b.disabled = true));
            selectedStyleImageB64 = imageB64;
            sendMessage(proposal.label);
        });

        wrap.appendChild(btn);

        return {
            setImage(b64) {
                imageB64 = b64;
                img.src = `data:image/png;base64,${b64}`;
                img.classList.remove("hidden");
                spinner.classList.add("hidden");
                btn.disabled = false;
            },
            setError(detail) {
                spinner.classList.add("hidden");
                thumbWrap.classList.add("chat-option-thumb-error");
                thumbWrap.title = detail;
                span.textContent = `${proposal.label}（生成失敗）`;
            },
        };
    });

    chatLog.appendChild(wrap);
    chatLog.scrollTop = chatLog.scrollHeight;
    return entries;
}

/** スタイル案の画像生成をSSEで購読し、完成したものから順にプレースホルダーへ反映する */
async function generateStyleImages(proposals) {
    const entries = renderStyleOptions(proposals);

    try {
        const res = await fetch("/api/chat/style-images", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ style_proposals: proposals }),
        });

        if (!res.ok) {
            const errorBody = await res.json().catch(() => ({}));
            throw new Error(errorBody.detail || "スタイル案の画像生成に失敗しました。");
        }

        await readSSEStream(res, (payload) => {
            const entry = entries[payload.index];
            if (!entry) return;
            if (payload.type === "style_image_done") {
                entry.setImage(payload.image_b64);
            } else if (payload.type === "style_image_error") {
                entry.setError(payload.detail);
            }
        });
    } catch (err) {
        appendMessage("assistant", `エラー: ${err.message}`);
    }
}

async function sendMessage(presetText) {
    const fromInput = presetText === undefined;
    const text = (fromInput ? chatInput.value : presetText).trim();
    if (!text) return;

    // ユーザーメッセージを表示・履歴に追加
    appendMessage("user", text);
    history.push({ role: "user", content: text });
    if (fromInput) {
        chatInput.value = "";
        chatInput.style.height = "auto";
    }

    await fetchAssistantReply();
}

/** 直近の履歴をもとにAIの返答を取得し、チャット欄・選択肢・スタイル案/スライド生成に反映する */
async function fetchAssistantReply() {
    // 送信中はボタンと入力欄を無効化
    sendButton.disabled = true;
    chatInput.disabled = true;
    const pending = appendMessage("assistant", "回答を生成中...");
    pending.bubble.classList.add("pending");

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ history }),
        });

        if (!response.ok) {
            const errorBody = await response.json().catch(() => ({}));
            throw new Error(errorBody.detail || "AIとの通信に失敗しました。");
        }

        const data = await response.json();
        pending.row.remove();
        appendMessage("assistant", data.message || "");
        history.push({ role: "assistant", content: data.message || "" });

        if (data.options && data.options.length > 0) {
            renderOptions(data.options);
        }

        if (data.style_proposals && data.style_proposals.length > 0) {
            generateStyleImages(data.style_proposals);
        }

        if (data.ready_to_generate && data.slide_plan && data.slide_plan.length > 0) {
            generateSlides(data.slide_plan);
        }
    } catch (err) {
        pending.row.remove();
        appendMessage("assistant", `エラー: ${err.message}`);
    } finally {
        sendButton.disabled = false;
        chatInput.disabled = false;
        chatInput.focus();
    }
}

/** アップロードされたpptxを解析してスタイル説明を取得し、参考資料としてチャット履歴に追加する */
async function uploadPptxStyle(file) {
    pptxUploadBtn.disabled = true;
    const pending = appendMessage("assistant", "アップロードされた資料のスタイルを解析中...");
    pending.bubble.classList.add("pending");

    try {
        const formData = new FormData();
        formData.append("file", file);
        const res = await fetch("/api/style/analyze-pptx", {
            method: "POST",
            body: formData,
        });

        if (!res.ok) {
            const errorBody = await res.json().catch(() => ({}));
            throw new Error(errorBody.detail || "資料のスタイル解析に失敗しました。");
        }

        const data = await res.json();
        pending.row.remove();

        const shortText = `参考資料「${file.name}」をアップロードしました。このスタイルを踏襲してください。`;
        const styleText = `[スタイル分析結果]\n${data.style_description}`;

        // 表示上はユーザー発言・AI発言の2つの吹き出しに分けるが、
        // AIに送る履歴としては1つのユーザー発言にまとめて渡す
        appendMessage("user", shortText);
        appendMessage("assistant", styleText);
        history.push({ role: "user", content: `${shortText}\n\n${styleText}` });

        await fetchAssistantReply();
    } catch (err) {
        pending.row.remove();
        appendMessage("assistant", `エラー: ${err.message}`);
    } finally {
        pptxUploadBtn.disabled = false;
        pptxUploadInput.value = "";
    }
}

function showSlideCardsPlaceholder() {
    slideCardsEl.innerHTML =
        '<p id="slide-cards-placeholder" class="panel-right-placeholder">チャットで資料の方向性が固まると、ここに資料イメージが表示されます</p>';
}

function resetChat() {
    history.length = 0;
    chatLog.innerHTML = "";
    selectedStyleImageB64 = null;
    slidesState.clear();
    showSlideCardsPlaceholder();
    reviseBtn.disabled = true;
    downloadBtn.disabled = true;
    hideSlidesMessage();
    appendMessage("assistant", INITIAL_MESSAGE);
}

sendButton.addEventListener("click", () => sendMessage());
resetButton.addEventListener("click", resetChat);

pptxUploadBtn.addEventListener("click", () => pptxUploadInput.click());
pptxUploadInput.addEventListener("change", () => {
    const file = pptxUploadInput.files && pptxUploadInput.files[0];
    if (file) {
        uploadPptxStyle(file);
    }
});

chatInput.addEventListener("keydown", (event) => {
    // Ctrl+Enter（Macの場合はCmd+Enter）で送信、Enter単独では改行する
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        sendMessage();
    }
});

chatInput.addEventListener("input", () => {
    chatInput.style.height = "auto";
    chatInput.style.height = `${chatInput.scrollHeight}px`;
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
// 右エリア: 資料イメージカード
// ============================================================

function showSlidesMessage(text, type) {
    slidesMessageEl.textContent = text;
    slidesMessageEl.className = `notice ${type}`;
}

function hideSlidesMessage() {
    slidesMessageEl.className = "notice hidden";
}

function createSlideCard(slideNumber, title) {
    const card = document.createElement("div");
    card.className = "slide-card";

    const titleEl = document.createElement("div");
    titleEl.className = "slide-card-title";
    titleEl.textContent = `スライド ${slideNumber}: ${title}`;
    card.appendChild(titleEl);

    const imageWrap = document.createElement("div");
    imageWrap.className = "slide-card-image-wrap";

    const img = document.createElement("img");
    img.className = "hidden";
    img.alt = `スライド ${slideNumber}`;
    img.addEventListener("click", () => {
        if (!img.getAttribute("src") || img.classList.contains("hidden")) return;
        openImageLightbox(img.src, img.alt);
    });
    imageWrap.appendChild(img);

    const spinner = document.createElement("div");
    spinner.className = "image-spinner";
    spinner.innerHTML = '<span class="loading"></span><span>生成中...</span>';
    imageWrap.appendChild(spinner);

    card.appendChild(imageWrap);

    const body = document.createElement("div");
    body.className = "slide-card-body";
    const textarea = document.createElement("textarea");
    textarea.placeholder = "このスライドへの修正指示があれば入力してください";
    body.appendChild(textarea);
    card.appendChild(body);

    slideCardsEl.appendChild(card);

    return { slideNumber, title, imageB64: null, img, spinner, textarea, card };
}

function updateSlideCardImage(slideNumber, imageB64) {
    const state = slidesState.get(slideNumber);
    if (!state) return;
    state.imageB64 = imageB64;
    state.img.src = `data:image/png;base64,${imageB64}`;
    state.img.classList.remove("hidden");
    state.spinner.classList.add("hidden");

    const errorEl = state.card.querySelector(".slide-card-error");
    if (errorEl) errorEl.remove();
}

function showSlideCardError(slideNumber, detail) {
    const state = slidesState.get(slideNumber);
    if (!state) return;
    state.spinner.classList.add("hidden");

    let errorEl = state.card.querySelector(".slide-card-error");
    if (!errorEl) {
        errorEl = document.createElement("div");
        errorEl.className = "slide-card-error";
        state.card.querySelector(".slide-card-image-wrap").appendChild(errorEl);
    }
    errorEl.textContent = `生成に失敗しました: ${detail}`;
}

async function generateSlides(slidePlan) {
    if (!selectedStyleImageB64) {
        showSlidesMessage("スタイルが選択されていないため、資料イメージを作成できませんでした。", "error");
        return;
    }

    slideCardsEl.innerHTML = "";
    slidesState.clear();
    slidePlan.forEach((slide) => {
        slidesState.set(slide.slide_number, createSlideCard(slide.slide_number, slide.title));
    });

    reviseBtn.disabled = true;
    downloadBtn.disabled = true;
    hideSlidesMessage();

    try {
        const res = await fetch("/api/slides/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ slide_plan: slidePlan, style_image_b64: selectedStyleImageB64 }),
        });

        if (!res.ok) {
            const errorBody = await res.json().catch(() => ({}));
            throw new Error(errorBody.detail || "資料イメージの生成に失敗しました。");
        }

        await readSSEStream(res, (payload) => {
            if (payload.type === "slide_done") {
                updateSlideCardImage(payload.slide_number, payload.image_b64);
            } else if (payload.type === "slide_error") {
                showSlideCardError(payload.slide_number, payload.detail);
            }
        });

        const hasAnyImage = Array.from(slidesState.values()).some((s) => s.imageB64);
        reviseBtn.disabled = !hasAnyImage;
        downloadBtn.disabled = !hasAnyImage;

        appendMessage("assistant", SLIDES_READY_MESSAGE);
        history.push({ role: "assistant", content: SLIDES_READY_MESSAGE });
    } catch (err) {
        showSlidesMessage(`ネットワークエラー: ${err.message}`, "error");
    }
}

reviseBtn.addEventListener("click", async () => {
    // 入力欄に修正指示があり、かつ画像が生成済みのカードのみを修正対象にする
    const targets = Array.from(slidesState.values()).filter((s) => s.textarea.value.trim() && s.imageB64);
    if (targets.length === 0) {
        showSlidesMessage("修正指示が入力されているカードがありません。", "error");
        return;
    }

    hideSlidesMessage();
    reviseBtn.disabled = true;
    downloadBtn.disabled = true;

    const payloadSlides = Array.from(slidesState.values())
        .filter((s) => s.imageB64)
        .map((s) => ({
            slide_number: s.slideNumber,
            image_b64: s.imageB64,
            instruction: s.textarea.value.trim(),
        }));

    targets.forEach((s) => {
        s.spinner.classList.remove("hidden");
        s.img.classList.add("hidden");
    });

    try {
        const res = await fetch("/api/slides/revise", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ slides: payloadSlides }),
        });

        if (!res.ok) {
            const errorBody = await res.json().catch(() => ({}));
            throw new Error(errorBody.detail || "資料イメージの修正に失敗しました。");
        }

        await readSSEStream(res, (payload) => {
            if (payload.type === "slide_done" || payload.type === "slide_skipped") {
                updateSlideCardImage(payload.slide_number, payload.image_b64);
            } else if (payload.type === "slide_error") {
                showSlideCardError(payload.slide_number, payload.detail);
            }
        });

        // 反映済みの修正指示はクリアする
        targets.forEach((s) => {
            s.textarea.value = "";
        });

        appendMessage("assistant", SLIDES_REVISED_MESSAGE);
        history.push({ role: "assistant", content: SLIDES_REVISED_MESSAGE });
    } catch (err) {
        showSlidesMessage(`ネットワークエラー: ${err.message}`, "error");
    } finally {
        reviseBtn.disabled = false;
        downloadBtn.disabled = !Array.from(slidesState.values()).some((s) => s.imageB64);
    }
});

downloadBtn.addEventListener("click", async () => {
    const slides = Array.from(slidesState.values())
        .filter((s) => s.imageB64)
        .sort((a, b) => a.slideNumber - b.slideNumber)
        .map((s) => ({ slide_number: s.slideNumber, image_b64: s.imageB64 }));

    if (slides.length === 0) return;

    hideSlidesMessage();
    downloadBtn.disabled = true;
    const originalLabel = downloadBtn.textContent;
    downloadBtn.textContent = "PDFを作成中...";

    try {
        const res = await fetch("/api/slides/export-pdf", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ slides }),
        });

        if (!res.ok) {
            const errorBody = await res.json().catch(() => ({}));
            throw new Error(errorBody.detail || "資料のダウンロードに失敗しました。");
        }

        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "slides.pdf";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    } catch (err) {
        showSlidesMessage(`ネットワークエラー: ${err.message}`, "error");
    } finally {
        downloadBtn.disabled = false;
        downloadBtn.textContent = originalLabel;
    }
});

// ============================================================
// スライド画像拡大表示（ライトボックス）
// ============================================================

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

imageLightboxModal.addEventListener("click", closeImageLightbox);
imageLightboxClose.addEventListener("click", closeImageLightbox);

document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !imageLightboxModal.classList.contains("hidden")) {
        closeImageLightbox();
    }
});

// 初期表示メッセージ
appendMessage("assistant", INITIAL_MESSAGE);
