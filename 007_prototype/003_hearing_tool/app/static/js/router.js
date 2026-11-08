/* ヒアリング管理ツールの画面：画面の切り替えと起動（最後に読み込む）
 *
 * 元は app.js の一部。ファイルをまたいで関数と定数を共有するため、index.html での読み込み順を変えないこと。
 */

// ------------------------------------------------------------------ 画面の切り替え

/**
 * URL の # 以降に応じて画面を表示する。
 * @returns {Promise<void>}
 */
async function route() {
  const main = document.getElementById("main");
  const [, page, id] = (location.hash || "#/").split("/");

  // 前の画面のタイマーを止める
  clearInterval(timers.live);
  timers.live = null;
  if (page !== "transcript") { clearInterval(timers.poll); timers.poll = null; }

  // 本人向けの表示では、メニューなどを隠す
  document.body.classList.toggle("screen-mode", page === "screen");

  // 左のメニューの選択を合わせる
  const navKey = { "": "home", person: "home", session: "home", live: "home", transcript: "home" }[page] ?? page;
  document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === navKey));

  try {
    switch (page) {
      case "person": renderPerson(main, id); break;
      case "session": await renderSession(main, id); break;
      case "live": renderLive(main, id); break;
      case "screen": renderScreen(main, id); break;
      case "transcript": await renderTranscript(main, id); break;
      case "issues": renderIssues(main); break;
      case "data": renderSources(main); break;
      case "common": renderCommon(main); break;
      case "terms": renderTerms(main); break;
      case "io": renderIo(main); break;
      case "overview": await renderOverview(main); break;
      case "evaluation": await renderEvaluation(main); break;
      default: await renderHome(main);
    }
  } catch (e) {
    main.innerHTML = `<div class="notice">${h(e.message)}</div>`;
  }
}

// Markdown の入力欄の「記述」「プレビュー」の切り替え
document.addEventListener("click", (event) => {
  const tab = event.target.closest("[data-md-tab]");
  if (!tab) return;
  const editor = tab.closest(".md-editor");
  const textarea = editor.querySelector("textarea");
  const preview = editor.querySelector(".md-preview");
  const showPreview = tab.dataset.mdTab === "preview";

  // プレビューに切り替えるときは、今の記述を変換して表示する
  if (showPreview) preview.innerHTML = renderMarkdown(textarea.value) || '<p class="muted">（未入力）</p>';
  textarea.hidden = showPreview;
  preview.hidden = !showPreview;
  editor.querySelectorAll("[data-md-tab]").forEach((b) => b.classList.toggle("active", b === tab));
});

// 起動時にデータを読み込み、画面を表示する
window.addEventListener("hashchange", route);
reload().then(route).catch((e) => toast(e.message, true));
