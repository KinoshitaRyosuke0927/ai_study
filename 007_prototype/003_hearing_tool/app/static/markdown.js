/* 簡単な Markdown の変換
 *
 * 画面で使う範囲の記法だけを扱う：見出し、段落、改行、太字、取り消し線、インラインコード、
 * リンク、箇条書き、番号付きの箇条書き、チェックボックス、引用、表、コードブロック、区切り線。
 * 入力はすべてエスケープしてから変換するので、HTML を書いてもそのまま文字として表示される。
 */

/**
 * HTML の特殊文字をエスケープする。
 * @param {string} text 文字列
 * @returns {string} エスケープした文字列
 */
function mdEscape(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

/**
 * 1行の中の記法（太字、コード、リンクなど）を変換する。
 * @param {string} text 1行の文字列（エスケープ前）
 * @returns {string} HTML
 */
function mdInline(text) {
  // インラインコードは中身を変換しないよう、先に取り出しておく
  const codes = [];
  let html = mdEscape(text).replace(/`([^`]+)`/g, (_, code) => {
    codes.push(`<code>${code}</code>`);
    return `\u0000${codes.length - 1}\u0000`;
  });

  // 太字と取り消し線
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/~~(.+?)~~/g, "<del>$1</del>");

  // リンク（http、https、相対パス、# だけを許可する）
  html = html.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (all, label, url) => (
    /^(https?:\/\/|\.{0,2}\/|#)/.test(url) ? `<a href="${url}" target="_blank" rel="noopener">${label}</a>` : all
  ));

  // 取り出しておいたコードを戻す
  return html.replace(/\u0000(\d+)\u0000/g, (_, i) => codes[Number(i)]);
}

/**
 * 表の1行をセルに分ける。
 * @param {string} line 表の行
 * @returns {string[]} セルの一覧
 */
function mdCells(line) {
  // 先頭と末尾の縦線を除き、エスケープされていない縦線で分ける
  const body = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return body.split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, "|"));
}

/**
 * Markdown を HTML に変換する。
 * @param {string} source Markdown の文字列
 * @returns {string} HTML
 */
function renderMarkdown(source) {
  const lines = String(source ?? "").replace(/\r\n/g, "\n").split("\n");
  const out = [];
  let paragraph = [];

  // たまった段落を出力する（段落の中の改行は <br> にする）
  const flush = () => {
    if (paragraph.length) out.push(`<p>${paragraph.map(mdInline).join("<br>")}</p>`);
    paragraph = [];
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // コードブロック
    if (/^\s*```/.test(line)) {
      flush();
      const code = [];
      i++;
      while (i < lines.length && !/^\s*```/.test(lines[i])) code.push(lines[i++]);
      out.push(`<pre><code>${mdEscape(code.join("\n"))}</code></pre>`);
      continue;
    }

    // 空行は段落の区切り
    if (!line.trim()) { flush(); continue; }

    // 見出し
    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      flush();
      const level = Math.min(heading[1].length + 2, 6);
      out.push(`<h${level}>${mdInline(heading[2])}</h${level}>`);
      continue;
    }

    // 表（次の行が |---| の区切りの行のとき）
    if (/^\s*\|/.test(line) && i + 1 < lines.length && /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/.test(lines[i + 1])) {
      flush();
      const header = mdCells(line);
      i += 2;
      const rows = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) rows.push(mdCells(lines[i++]));
      i--;
      out.push(`<table><thead><tr>${header.map((c) => `<th>${mdInline(c)}</th>`).join("")}</tr></thead><tbody>${
        rows.map((r) => `<tr>${header.map((_, k) => `<td>${mdInline(r[k] ?? "")}</td>`).join("")}</tr>`).join("")
      }</tbody></table>`);
      continue;
    }

    // 区切り線
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) { flush(); out.push("<hr>"); continue; }

    // 引用（続く > の行をまとめる）
    if (/^\s*>/.test(line)) {
      flush();
      const quote = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) quote.push(lines[i++].replace(/^\s*>\s?/, ""));
      i--;
      out.push(`<blockquote>${renderMarkdown(quote.join("\n"))}</blockquote>`);
      continue;
    }

    // 箇条書きと番号付きの箇条書き（続く同じ種類の行をまとめる）
    const bullet = /^\s*[-*+]\s+(.*)$/;
    const numbered = /^\s*\d+[.)]\s+(.*)$/;
    if (bullet.test(line) || numbered.test(line)) {
      flush();
      const pattern = bullet.test(line) ? bullet : numbered;
      const tag = pattern === bullet ? "ul" : "ol";
      const items = [];
      while (i < lines.length && pattern.test(lines[i])) {
        let text = lines[i++].match(pattern)[1];
        // チェックボックス
        text = text.replace(/^\[ \]\s*/, "☐ ").replace(/^\[[xX]\]\s*/, "☑ ");
        items.push(`<li>${mdInline(text)}</li>`);
      }
      i--;
      out.push(`<${tag}>${items.join("")}</${tag}>`);
      continue;
    }

    // それ以外は段落の行
    paragraph.push(line);
  }
  flush();
  return out.join("");
}
