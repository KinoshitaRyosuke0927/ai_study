// エントリポイント: 各タブのボタンにハンドラを配線し、初期表示を整える。
// (index.html は <script type="module" src="/static/js/main.js"> でこれだけ読み込む)

import { $ } from "./core.js";
import "./nav.js";  // サイドメニュー / ブランドのクリック配線(副作用 import)
import { loadHealth } from "./health.js";
import { saveSettings } from "./settings.js";
import { fetchMattermost, analyzeMattermost } from "./mattermost.js";
import { fetchTrello, analyzeTrello } from "./trello.js";
import { loadGrowiPages, fetchGrowi } from "./growi.js";
import { fetchGithub, ingestGithub } from "./github.js";
import { fetchDesign, analyzeDesign } from "./design.js";
import { fetchCode, analyzeCode } from "./code.js";
import { fetchChangelog, analyzeChangelog } from "./changelog.js";
import { runPipeline } from "./pipeline.js";
import { saveKpt } from "./kpt.js";
import { loadDiffCard, loadKptCard } from "./dashboard.js";

// ダッシュボードのカード類 + ヘルスバッジを最新化する
async function refreshAll() {
  await Promise.all([
    loadHealth(),
    loadDiffCard().catch(() => {}),
    loadKptCard().catch(() => {}),
  ]);
}

// --- 各タブのアクションボタンを配線 ---
$("#saveSettingsBtn").addEventListener("click", saveSettings);
$("#mmCurrentBtn").addEventListener("click", () => fetchMattermost("current"));
$("#mmAnalyzeBtn").addEventListener("click", analyzeMattermost);
$("#mmRangeBtn").addEventListener("click", () => fetchMattermost("range"));
$("#trelloFetchBtn").addEventListener("click", fetchTrello);
$("#trelloAnalyzeBtn").addEventListener("click", analyzeTrello);
$("#growiListBtn").addEventListener("click", loadGrowiPages);
$("#growiFetchBtn").addEventListener("click", fetchGrowi);
$("#ghFetchBtn").addEventListener("click", fetchGithub);
$("#ghIngestBtn").addEventListener("click", ingestGithub);
$("#dsgFetchBtn").addEventListener("click", fetchDesign);
$("#dsgAnalyzeBtn").addEventListener("click", analyzeDesign);
$("#codeFetchBtn").addEventListener("click", fetchCode);
$("#codeAnalyzeBtn").addEventListener("click", analyzeCode);
$("#plRunBtn").addEventListener("click", runPipeline);
$("#clFetchBtn").addEventListener("click", fetchChangelog);
$("#clAnalyzeBtn").addEventListener("click", analyzeChangelog);
$("#kptSaveBtn").addEventListener("click", saveKpt);

refreshAll();
