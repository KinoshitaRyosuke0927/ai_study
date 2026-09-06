// ダッシュボードタブ: 最新の実装差分(機能別テーブル)と KPT分析の状況カード。

import { $, api, esc } from "./core.js";
import { selectTab } from "./nav.js";
import { openSpecDiffFeature } from "./specdiff.js";
import { KPT_SOURCE_LABEL } from "./kpt.js";

// ダッシュボード: 保存済みの最新の差分を「機能別 × 重大度別」に集計した強化テーブル
export async function loadDiffCard() {
  const cont = $("#diffCards");
  try {
    const sd = await api("/api/spec-diff/latest");
    if (!sd.diff_id) {
      cont.innerHTML = '<span class="muted">実装差分解析はまだ実行されていません。「実装差分解析」タブから実行してください。</span>';
      return;
    }
    const at = (sd.created_at || "").replace("T", " ").slice(0, 16);
    // 機能ごとに High / Mid / Low の件数を数える
    const byFeat = new Map();
    (sd.items || []).forEach((it) => {
      const k = it.feature_name || "(機能名なし)";
      if (!byFeat.has(k)) byFeat.set(k, { high: 0, mid: 0, low: 0 });
      const b = byFeat.get(k);
      if (b[it.severity] != null) b[it.severity]++;
    });
    const rows = [...byFeat.entries()]
      .map(([name, b]) => ({ name, ...b, total: b.high + b.mid + b.low }))
      .sort((a, b) => (b.high - a.high) || (b.mid - a.mid) || (b.low - a.low) || (b.total - a.total));
    const tot = rows.reduce((a, r) => ({
      high: a.high + r.high, mid: a.mid + r.mid, low: a.low + r.low, total: a.total + r.total,
    }), { high: 0, mid: 0, low: 0, total: 0 });

    // 非ゼロは重大度色、0 はグレー
    const num = (n, cls) => n ? `<span class="${cls}">${n}</span>` : '<span class="sd-z">0</span>';
    // High/Mid/Low を比率で塗り分けた積み上げバー
    const bar = (r) => {
      const seg = (n, cls) => n ? `<span class="${cls}" style="flex:${n} 0 0"></span>` : "";
      return `<div class="sd-bar" title="High ${r.high} / Mid ${r.mid} / Low ${r.low}">`
        + seg(r.high, "sd-seg-h") + seg(r.mid, "sd-seg-m") + seg(r.low, "sd-seg-l") + `</div>`;
    };

    cont.innerHTML = `
      <div class="panel sd-panel" style="flex:1 1 100%;margin-top:0" title="実装差分解析へ">
        <h2 style="margin-bottom:6px">実装差分(機能別 / 最新 ${esc(at)})</h2>
        <p class="sd-sum">全体
          <b class="sd-h">High ${tot.high}</b> ・
          <b class="sd-m">Mid ${tot.mid}</b> ・
          <b class="sd-l">Low ${tot.low}</b> ／ 計 <b>${tot.total}</b>(差分あり ${rows.length} 機能)</p>
        <table class="sd-table">
          <thead><tr>
            <th>機能</th>
            <th class="bar">分布</th>
            <th class="num sd-h">High</th><th class="num sd-m">Mid</th><th class="num sd-l">Low</th>
            <th class="num">計</th>
          </tr></thead>
          <tbody>
            ${rows.map((r) => `<tr>
              <td><span class="sd-feat" data-feature="${esc(r.name)}">${esc(r.name)}</span></td>
              <td class="bar">${bar(r)}</td>
              <td class="num">${num(r.high, "sd-h")}</td>
              <td class="num">${num(r.mid, "sd-m")}</td>
              <td class="num">${num(r.low, "sd-l")}</td>
              <td class="num"><b>${r.total}</b></td>
            </tr>`).join("")}
          </tbody>
          <tfoot><tr>
            <th>合計</th><th class="bar"></th>
            <th class="num">${tot.high}</th><th class="num">${tot.mid}</th><th class="num">${tot.low}</th>
            <th class="num">${tot.total}</th>
          </tr></tfoot>
        </table>
      </div>`;
    // 機能名クリック: その機能のアコーディオンを開いた状態で差分画面へ
    cont.querySelectorAll(".sd-feat").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        openSpecDiffFeature(el.dataset.feature);
      });
    });
    // それ以外(バー・数値・見出し)をクリックしたら差分画面へ
    cont.querySelector(".panel").addEventListener("click", () => selectTab("specdiff"));
  } catch (e) { cont.innerHTML = '<span class="muted">差分件数を取得できませんでした。</span>'; }
}

// ダッシュボード: 保存済みの最新 KPT分析の状況(件数 + 重要度の高い項目)
export async function loadKptCard() {
  const cont = $("#kptCards");
  try {
    const r = await api("/api/kpt/latest");
    if (!r.analysis_id) {
      cont.innerHTML = '<span class="muted">KPT分析はまだ実行されていません。「定期実行設定」から実行してください。</span>';
      return;
    }
    const at = (r.saved_at || "").replace("T", " ").slice(0, 16);
    const cols = [["keep", "Keep"], ["problem", "Problem"], ["try", "Try"]];
    const counts = {};
    let total = 0;
    cols.forEach(([k]) => { counts[k] = (r[k] || []).length; total += counts[k]; });

    // 重要度(★1以上)がついた項目を集めて降順に
    const rated = [];
    cols.forEach(([k, label]) => (r[k] || []).forEach((it) => {
      if ((it.importance || 0) > 0) rated.push({ kind: k, label, imp: it.importance, title: it.title });
    }));
    rated.sort((a, b) => b.imp - a.imp);
    const top = rated.slice(0, 6);
    const topHtml = top.length
      ? `<div style="margin-top:8px"><div class="muted" style="font-size:12px">重要度の高い項目</div>
         <ul class="kpt-dash-list">${top.map((t) =>
           `<li><span class="kpt-dash-tag ${t.kind}">${t.label}</span>`
           + `<span class="kpt-dash-star">${"★".repeat(t.imp)}</span>${esc(t.title)}</li>`).join("")}</ul></div>`
      : '<div class="muted" style="font-size:12px;margin-top:8px">重要度が設定された項目はありません(「KPT分析」タブで★を設定できます)。</div>';

    const src = ((r.stats && r.stats.available_sources) || [])
      .map((s) => KPT_SOURCE_LABEL[s] || s).join("、 ");
    cont.innerHTML = `
      <div class="panel sd-panel" style="flex:1 1 100%;margin-top:0" title="KPT分析へ">
        <h2 style="margin-bottom:6px">KPT分析(最新 ${esc(at)})</h2>
        <p class="sd-sum">
          <b style="color:var(--keep)">Keep ${counts.keep}</b> ・
          <b style="color:var(--problem)">Problem ${counts.problem}</b> ・
          <b style="color:var(--try)">Try ${counts.try}</b> ／ 計 <b>${total}</b>${src ? ` / 対象ソース: ${esc(src)}` : ""}</p>
        ${topHtml}
      </div>`;
    cont.querySelector(".panel").addEventListener("click", () => selectTab("kpt"));
  } catch (e) { cont.innerHTML = '<span class="muted">KPTの状況を取得できませんでした。</span>'; }
}
