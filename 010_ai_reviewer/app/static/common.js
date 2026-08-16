// ============================================================
// index.html（メイン画面）と share.html（共有閲覧画面）の両方で使う共通ユーティリティ
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
// Markdownダウンロード用ユーティリティ
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
