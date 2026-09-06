// アクティビティ分析タブ(表示のみ。分析の実行は「定期実行設定」)。

import { $, api, esc } from "./core.js";
import { accountAnalysisCard } from "./components.js";

let userActivity = null;
function renderUserActivityItem(it) {
  return accountAnalysisCard({
    title: it.display_name,
    chips: (it.sources || []),
    overview: it.overview,
    sections: it.sections,
    extraTop: it.personal
      ? `<div class="field-hint" style="margin:8px 12px">役割: ${esc(it.personal)}</div>` : "",
    emptyText: "対象データにアクティビティが見つかりませんでした。",
  });
}
function renderUserActivity(r) {
  $("#uaStatus").textContent = "";
  $("#uaSummary").textContent =
    `メンバー ${r.member_count ?? (r.members || []).length} 人 / その他 ${r.other_count ?? (r.others || []).length} 人`
    + ((r.available_sources || []).length ? ` / 対象ソース: ${(r.available_sources || []).join("、 ")}` : "");
  const members = (r.members || []).map(renderUserActivityItem).join("")
    || '<span class="muted">メンバーの分析結果がありません。</span>';
  const others = (r.others || []).length
    ? `<h3 style="margin-top:20px">その他のメンバー(settings.ini の [USER_ID] に未登録)</h3>` + r.others.map(renderUserActivityItem).join("")
    : "";
  $("#uaResults").innerHTML = `<h3>メンバー</h3>${members}${others}`;
}
export async function loadLatestUserActivity() {
  if (userActivity) return;
  try {
    const r = await api("/api/user-activity/latest");
    if (!r.analysis_id) {
      $("#uaStatus").innerHTML = '<span class="muted">まだ分析結果がありません。「定期実行設定」画面から実行してください。</span>';
      return;
    }
    userActivity = r;
    renderUserActivity(r);
    $("#uaStatus").innerHTML = `<span class="muted">保存済みの分析結果を表示しています(analysis #${r.analysis_id} / ${esc((r.saved_at || "").replace("T", " ").slice(0, 16))})。</span>`;
  } catch (e) { /* 無ければ何もしない */ }
}
