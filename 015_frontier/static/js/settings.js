// 設定タブ: 実行時に取得するデータの設定(取得開始日 / GitHub / GROWI / チャンネル / ボード)。

import { $, $$, api, esc } from "./core.js";

// 親項目(チーム / ワークスペース)ごとにグループ化。1 行 3 列のグリッドで表示する。
function _groupBy(list, keyFn, labelFn) {
  const m = new Map();
  (list || []).forEach((x) => {
    const k = keyFn(x) || "(その他)";
    if (!m.has(k)) m.set(k, []);
    m.get(k).push({ id: x.id, label: labelFn(x) });
  });
  return [...m.entries()]
    .sort((a, b) => a[0].localeCompare(b[0], "ja"))
    .map(([title, items]) => ({ title, items: items.sort((a, b) => a.label.localeCompare(b.label, "ja")) }));
}
function renderGroupedCheckList(sel, error, groups, checkedIds, grp) {
  const el = $(sel);
  if (error) { el.innerHTML = `<span class="muted">${esc(error)}</span>`; return; }
  const total = groups.reduce((n, g) => n + g.items.length, 0);
  if (!total) { el.innerHTML = '<span class="muted">選択できる項目がありません。</span>'; return; }
  const set = new Set(checkedIds || []);
  el.innerHTML = groups.map((g) => `
    <div class="check-group">
      <div class="grp-title">${esc(g.title)}(${g.items.length})</div>
      <div class="check-grid">
        ${g.items.map((it) => `<label><input type="checkbox" data-grp="${grp}" value="${esc(it.id)}" ${set.has(it.id) ? "checked" : ""} /><span title="${esc(it.label)}">${esc(it.label)}</span></label>`).join("")}
      </div>
    </div>`).join("");
}
export async function loadSettings() {
  const d = await api("/api/settings");
  const c = d.config;
  $("#setSinceDate").value = c.since_date || "";
  $("#setGithubRepo").value = c.github_repo || "";
  $("#setGithubDesignPath").value = c.github_design_path || "";
  $("#setGrowiPath").value = c.growi_page_path || "";
  $("#githubRepoError").textContent = "";
  $("#githubDesignPathError").textContent = "";
  $("#growiPathError").textContent = "";
  renderGroupedCheckList(
    "#mmChannels", d.options.mattermost.error,
    _groupBy(d.options.mattermost.channels, (ch) => ch.team, (ch) => ch.name),
    c.mattermost_channel_ids, "mm",
  );
  renderGroupedCheckList(
    "#trelloBoards", d.options.trello.error,
    _groupBy(d.options.trello.boards, (b) => b.workspace, (b) => b.name),
    c.trello_board_ids, "tr",
  );
  $("#saveSettingsStatus").textContent = "";
}
export async function saveSettings() {
  const body = {
    since_date: $("#setSinceDate").value || null,
    mattermost_channel_ids: $$('input[data-grp="mm"]:checked').map((x) => x.value),
    trello_board_ids: $$('input[data-grp="tr"]:checked').map((x) => x.value),
    github_repo: $("#setGithubRepo").value.trim(),
    github_design_path: $("#setGithubDesignPath").value.trim(),
    growi_page_path: $("#setGrowiPath").value.trim(),
  };
  // 前回のフィールドエラー表示をクリア
  $("#githubRepoError").textContent = "";
  $("#githubDesignPathError").textContent = "";
  $("#growiPathError").textContent = "";
  $("#saveSettingsStatus").textContent = "保存中...(GitHub / GROWI へのアクセスを確認しています)";
  let r, j;
  try {
    r = await fetch("/api/settings", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    j = await r.json().catch(() => ({}));
  } catch (e) {
    $("#saveSettingsStatus").textContent = "エラー: " + e.message;
    return;
  }
  if (r.ok) {
    // 解決後の値(owner/repo 等)を反映
    if (j.config) {
      $("#setGithubRepo").value = j.config.github_repo || "";
      $("#setGithubDesignPath").value = j.config.github_design_path || "";
      $("#setGrowiPath").value = j.config.growi_page_path || "";
    }
    $("#saveSettingsStatus").textContent = "保存しました";
    return;
  }
  // 422: アクセス確認エラー。項目ごとにエラーを表示し、保存はされていない
  const detail = j.detail;
  const fieldErrors = (detail && typeof detail === "object" && detail.errors) || {};
  if (fieldErrors.github_repo) $("#githubRepoError").textContent = fieldErrors.github_repo;
  if (fieldErrors.github_design_path) $("#githubDesignPathError").textContent = fieldErrors.github_design_path;
  if (fieldErrors.growi_page_path) $("#growiPathError").textContent = fieldErrors.growi_page_path;
  const msg = (detail && typeof detail === "object" && detail.message) || (typeof detail === "string" ? detail : "保存できませんでした");
  $("#saveSettingsStatus").textContent = "保存されていません: " + msg;
}
