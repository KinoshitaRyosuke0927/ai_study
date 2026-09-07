// Q&Aタブ: AIとのチャット(ステートレス。会話履歴はこのモジュールの変数に保持し、
// 毎回のリクエストで全履歴をサーバーへ送る。013_pp_angel の app.js の送信フローを踏襲)。

import { $, esc } from "./core.js";

let qaHistory = [];   // [{role: "user"|"assistant", content: string}]
let qaSending = false;

// --- 簡易 Markdown レンダラ(AIの返答のみに適用。ユーザー発言は常にプレーンテキスト) ---
// ライブラリは使わず、見出し・箇条書き・強調・インラインコード・コードブロックのみ対応する
// (013_pp_angel の自前パーサーと同じ方針)。HTML特殊文字は必ず esc() を通してから組み立てる。
function qaInlineMd(s) {
  let t = esc(s);
  t = t.replace(/`([^`]+)`/g, "<code>$1</code>");
  t = t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  t = t.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, "<em>$1</em>");
  t = t.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  return t;
}

// AIの返答テキストから ```mermaid ブロックと ```suggestions ブロックを抜き出す。
// qaHistory に保存する元のテキストは書き換えず、表示直前にこの関数を通す。
function qaExtractBlocks(content) {
  const diagrams = [];
  const suggestions = [];
  let text = (content || "").replace(/```mermaid\n?([\s\S]*?)```/g, (_, code) => {
    diagrams.push(code.trim());
    return "\n\n(図を右のエリアに表示しました)\n\n";
  });
  text = text.replace(/```suggestions\n?([\s\S]*?)```/g, (_, block) => {
    block.split("\n").map((l) => l.trim().replace(/^[-*]\s*/, "")).filter(Boolean).forEach((l) => suggestions.push(l));
    return "";
  });
  return { text: text.trim(), diagrams, suggestions };
}

function qaRenderMarkdown(src) {
  // 1. コードブロック(```)を先に抜き出し、プレースホルダに置き換える(中を Markdown 変換しない)。
  //    mermaid / suggestions は qaExtractBlocks で既に取り除かれている前提。
  const codeBlocks = [];
  const withPlaceholders = (src || "").replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const idx = codeBlocks.length;
    codeBlocks.push(`<pre class="qa-code"><code>${esc(code.replace(/\n$/, ""))}</code></pre>`);
    return ` CODEBLOCK${idx} `;
  });

  const lines = withPlaceholders.split("\n");
  const out = [];
  let inUl = false;
  let inOl = false;
  const closeLists = () => {
    if (inUl) { out.push("</ul>"); inUl = false; }
    if (inOl) { out.push("</ol>"); inOl = false; }
  };

  // GFM形式のテーブル判定: "| a | b |" のような行と、区切り行("|---|---|")
  const splitRow = (line) => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
  const isTableRow = (line) => line.includes("|") && line.trim() !== "" && !line.match(/^ CODEBLOCK\d+ $/);
  const isTableSep = (line) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(line);

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];

    const cb = line.match(/^ CODEBLOCK(\d+) $/);
    if (cb) { closeLists(); out.push(codeBlocks[Number(cb[1])]); i++; continue; }

    if (isTableRow(line) && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      closeLists();
      const headers = splitRow(line);
      const bodyRows = [];
      let j = i + 2;
      while (j < lines.length && isTableRow(lines[j])) {
        bodyRows.push(splitRow(lines[j]));
        j++;
      }
      const thead = `<tr>${headers.map((h) => `<th>${qaInlineMd(h)}</th>`).join("")}</tr>`;
      const tbody = bodyRows.map((r) =>
        `<tr>${headers.map((_, ci) => `<td>${qaInlineMd(r[ci] ?? "")}</td>`).join("")}</tr>`
      ).join("");
      out.push(`<div class="qa-table-wrap"><table class="qa-table"><thead>${thead}</thead><tbody>${tbody}</tbody></table></div>`);
      i = j;
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      closeLists();
      const level = heading[1].length;
      out.push(`<h${level} class="qa-md-h">${qaInlineMd(heading[2])}</h${level}>`);
      i++; continue;
    }
    const ol = line.match(/^\d+\.\s+(.*)$/);
    if (ol) {
      if (!inUl && !inOl) out.push("<ol>");
      else if (inUl) { closeLists(); out.push("<ol>"); }
      inOl = true;
      out.push(`<li>${qaInlineMd(ol[1])}</li>`);
      i++; continue;
    }
    const ul = line.match(/^[-*]\s+(.*)$/);
    if (ul) {
      if (!inUl && !inOl) out.push("<ul>");
      else if (inOl) { closeLists(); out.push("<ul>"); }
      inUl = true;
      out.push(`<li>${qaInlineMd(ul[1])}</li>`);
      i++; continue;
    }
    closeLists();
    if (line.trim() === "") out.push("");
    else out.push(`<p>${qaInlineMd(line)}</p>`);
    i++;
  }
  closeLists();
  return out.join("\n");
}

// --- 拡大表示(ライトボックス) ---
function qaOpenLightbox(html) {
  $("#qaLightboxInner").innerHTML = html;
  $("#qaLightbox").hidden = false;
}
function qaCloseLightbox() {
  $("#qaLightbox").hidden = true;
  $("#qaLightboxInner").innerHTML = "";
}

// --- 右エリア: 図(Mermaid)・生成画像(gpt-image-2)の表示。根拠(citations)は表示しない
//     (ユーザーが求めない限り不要なため。回答文中では触れず、必要なら口頭で聞く運用)。
let qaMermaidInited = false;
function qaMermaidAvailable() {
  return typeof window !== "undefined" && !!window.mermaid;
}
function qaInitMermaid() {
  if (qaMermaidInited || !qaMermaidAvailable()) return;
  window.mermaid.initialize({ startOnLoad: false, securityLevel: "strict" });
  qaMermaidInited = true;
}

async function qaRenderSidePanel(diagrams, citations) {
  const panel = $("#qaSidePanel");
  const images = (citations || []).filter((c) => c.type === "image" && c.image_base64);
  const hasDiagrams = diagrams && diagrams.length > 0;
  const hasImages = images.length > 0;
  if (!hasDiagrams && !hasImages) {
    panel.innerHTML = '<div class="qa-placeholder">図や生成画像がある場合はここに表示されます</div>';
    return;
  }

  const parts = [];
  if (hasDiagrams) {
    diagrams.forEach((_, i) => {
      parts.push(`<div class="qa-cite qa-cite-diagram">`
        + `<div class="qa-cite-badge">図</div>`
        + `<div class="qa-diagram-render" id="qa-diagram-slot-${i}">描画中...</div></div>`);
    });
  }
  images.forEach((c, i) => {
    parts.push(`<div class="qa-cite qa-cite-image-wrap">`
      + `<div class="qa-cite-badge">生成画像</div>`
      + `<img class="qa-cite-image qa-zoomable" id="qa-image-slot-${i}" src="data:${c.mime || "image/png"};base64,${c.image_base64}" alt="${esc(c.label || "生成画像")}"></div>`);
  });
  panel.innerHTML = parts.join("");

  // 生成画像: クリックで拡大表示
  images.forEach((c, i) => {
    const el = document.getElementById(`qa-image-slot-${i}`);
    if (el) el.addEventListener("click", () => qaOpenLightbox(`<img src="${el.src}" alt="">`));
  });

  if (!hasDiagrams) return;
  qaInitMermaid();
  for (let i = 0; i < diagrams.length; i++) {
    const el = document.getElementById(`qa-diagram-slot-${i}`);
    if (!el) continue;
    if (!qaMermaidAvailable()) {
      el.innerHTML = `<pre class="qa-code"><code>${esc(diagrams[i])}</code></pre>`;
      continue;
    }
    try {
      const { svg } = await window.mermaid.render(`qa-mmd-${Date.now()}-${i}`, diagrams[i]);
      el.innerHTML = svg;
      el.classList.add("qa-zoomable");
      // 図をクリックすると拡大表示する
      el.addEventListener("click", () => qaOpenLightbox(el.innerHTML));
    } catch (e) {
      el.innerHTML = '<span class="muted">図の描画に失敗しました(Mermaid構文エラーの可能性があります)</span>';
    }
  }
}

// --- フォローアップ提案ボタン ---
function qaSuggestionsHtml(suggestions) {
  if (!suggestions || !suggestions.length) return "";
  const btns = suggestions.map((s) => `<button type="button" class="qa-suggest-btn" data-q="${esc(s)}">${esc(s)}</button>`).join("");
  return `<div class="qa-suggestions">${btns}</div>`;
}

function qaBubbleHtml(role, content, pending) {
  const renderMd = role === "assistant" && !pending;
  let bodyHtml;
  let suggestions = [];
  if (renderMd) {
    const extracted = qaExtractBlocks(content);
    bodyHtml = qaRenderMarkdown(extracted.text);
    suggestions = extracted.suggestions;
  } else {
    bodyHtml = esc(content);
  }
  return `<div class="qa-row ${role}">
    <div class="qa-bubble${pending ? " pending" : ""}${renderMd ? " md" : ""}">${bodyHtml}${qaSuggestionsHtml(suggestions)}</div>
  </div>`;
}

function qaRenderLog() {
  const log = $("#qaLog");
  log.innerHTML = qaHistory.map((m) => qaBubbleHtml(m.role, m.content)).join("");
  log.scrollTop = log.scrollHeight;
}

function qaAppendPending() {
  const log = $("#qaLog");
  log.insertAdjacentHTML("beforeend", qaBubbleHtml("assistant", "回答を生成中...", true));
  log.scrollTop = log.scrollHeight;
}

function qaSetSending(sending) {
  qaSending = sending;
  $("#qaSendBtn").disabled = sending;
  $("#qaInput").disabled = sending;
}

async function qaSendText(text) {
  if (!text || qaSending) return;

  qaHistory.push({ role: "user", content: text });
  qaRenderLog();
  qaSetSending(true);
  qaAppendPending();

  try {
    const res = await fetch("/api/qa/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ history: qaHistory }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || res.statusText);
    }
    const data = await res.json();
    qaHistory.push({ role: "assistant", content: data.message || "" });
    qaRenderLog();
    const { diagrams } = qaExtractBlocks(data.message || "");
    qaRenderSidePanel(diagrams, data.citations || []);
  } catch (e) {
    qaHistory.push({ role: "assistant", content: `エラー: ${e.message}` });
    qaRenderLog();
  } finally {
    qaSetSending(false);
    $("#qaInput").focus();
  }
}

function qaSend() {
  const input = $("#qaInput");
  const text = input.value.trim();
  if (!text || qaSending) return;
  input.value = "";
  qaAutoGrow(input);
  qaSendText(text);
}

function qaReset() {
  if (qaSending) return;
  qaHistory = [];
  qaRenderLog();
  qaRenderSidePanel([], []);
}

// textarea の高さを内容に合わせて自動調整する(120px を上限)
function qaAutoGrow(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 120) + "px";
}

const qaInput = $("#qaInput");
qaInput.addEventListener("input", () => qaAutoGrow(qaInput));
// Enter で送信、Shift+Enter で改行。
qaInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    qaSend();
  }
});
$("#qaSendBtn").addEventListener("click", qaSend);
$("#qaResetBtn").addEventListener("click", qaReset);
$("#qaLightbox").addEventListener("click", qaCloseLightbox);

// 提案ボタンのクリック(動的に挿入される要素なのでイベント委譲で拾う)
$("#qaLog").addEventListener("click", (e) => {
  const btn = e.target.closest(".qa-suggest-btn");
  if (!btn) return;
  qaSendText(btn.dataset.q);
});
