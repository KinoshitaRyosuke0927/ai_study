// ヘッダの稼働状態バッジ(実行モード / AI 接続)。

import { $, api } from "./core.js";

export async function loadHealth() {
  try {
    const h = await api("/api/health");
    $("#modeBadge").textContent = "mode: " + h.run_mode + (h.status === "ok" ? "" : " (DB NG)");
    $("#aiBadge").textContent = "AI: " + (h.ai_enabled ? "接続" : "フォールバック");
  } catch (e) { $("#modeBadge").textContent = "health error"; }
}
