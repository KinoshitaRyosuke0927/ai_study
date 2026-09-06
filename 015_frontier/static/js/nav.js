// サイドメニュー / ヘッダのタブ切り替え。
// タブ表示のたびに、そのタブの「表示用ヒント更新」「保存済み結果の復元」を呼ぶ。

import { $, $$ } from "./core.js";
import { loadSettings } from "./settings.js";
import { loadMattermostMeta, loadLatestMattermostAnalysis } from "./mattermost.js";
import { loadTrelloBoards, loadLatestTrelloAnalysis } from "./trello.js";
import { loadGrowiMeta } from "./growi.js";
import { loadGithubMeta, loadGithubActivity } from "./github.js";
import { loadDesignMeta, loadLatestDesignAnalysis } from "./design.js";
import { loadCodeMeta, loadLatestCodeAnalysis } from "./code.js";
import { loadLatestSpecDiff } from "./specdiff.js";
import { loadLatestUserActivity } from "./useractivity.js";
import { loadLatestKpt } from "./kpt.js";
import { loadDiffCard, loadKptCard } from "./dashboard.js";
import { pollPipeline } from "./pipeline.js";
import {
  loadChangelogMeta,
  loadChangelogSummary,
  loadLatestChangelogAnalysis,
} from "./changelog.js";

// --- タブ切り替え(サイドメニュー / ヘッダのブランド共通) ---
export function selectTab(name) {
  $$("#side .side-item").forEach((x) => x.classList.toggle("active", x.dataset.tab === name));
  $$(".tab").forEach((x) => x.classList.toggle("active", x.id === "tab-" + name));
  // 設定画面は表示のたびに最新の選択肢(チャンネル/ボード)を取得する
  if (name === "settings") loadSettings().catch(() => {});
  // Mattermost 情報取得は条件欄のヒントだけ更新(取得結果はそのまま残す)
  if (name === "mattermost") { loadMattermostMeta().catch(() => {}); loadLatestMattermostAnalysis().catch(() => {}); }
  // Trello 情報取得はボード選択肢だけ更新(取得結果はそのまま残す)
  if (name === "trello") { loadTrelloBoards().catch(() => {}); loadLatestTrelloAnalysis().catch(() => {}); }
  // wiki 情報取得は設定パスのヒントだけ更新(一覧・取得結果はそのまま残す)
  if (name === "growi") loadGrowiMeta().catch(() => {});
  // GitHub 情報取得は対象リポジトリのヒントだけ更新(取得結果はそのまま残す)
  if (name === "github") { loadGithubMeta().catch(() => {}); loadGithubActivity().catch(() => {}); }
  // 設計書情報取得: 対象フォルダのヒント更新 + 未表示なら保存済み分析結果を復元
  if (name === "design") { loadDesignMeta().catch(() => {}); loadLatestDesignAnalysis().catch(() => {}); }
  // コード情報取得: 対象リポジトリのヒント更新 + 未表示なら保存済み分析結果を復元
  if (name === "code") { loadCodeMeta().catch(() => {}); loadLatestCodeAnalysis().catch(() => {}); }
  // 実装差分解析: 未表示なら保存済みの差分解析結果を復元
  if (name === "specdiff") loadLatestSpecDiff().catch(() => {});
  // アクティビティ分析: 未表示なら保存済みの結果を復元
  if (name === "useractivity") loadLatestUserActivity().catch(() => {});
  // KPT分析: 未表示なら保存済みの結果を復元
  if (name === "kpt") loadLatestKpt().catch(() => {});
  // ダッシュボード: カード類を最新化
  if (name === "dashboard") { loadDiffCard().catch(() => {}); loadKptCard().catch(() => {}); }
  // 定期実行設定: 最新のパイプライン進捗を取得(実行中なら自動でポーリング継続)
  if (name === "pipeline") pollPipeline().catch(() => {});
  // 変更履歴取得: 対象ヒント更新 + 保存済みサマリ・分析を復元
  if (name === "changelog") {
    loadChangelogMeta().catch(() => {});
    loadChangelogSummary().catch(() => {});
    loadLatestChangelogAnalysis().catch(() => {});
  }
}

// サイドメニューのクリック / ヘッダの「Frontier」クリックでタブを切り替える
$$("#side .side-item").forEach((b) => b.addEventListener("click", () => selectTab(b.dataset.tab)));
$("#brand").addEventListener("click", () => selectTab("dashboard"));
