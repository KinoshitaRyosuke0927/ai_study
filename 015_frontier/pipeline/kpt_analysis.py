"""「KPT分析」の AI 処理。

Mattermost / Trello / 変更履歴 / GitHub / 実装差分 / アクティビティ分析 の各分析結果を
プロジェクト全体で 1 つに束ね、ふりかえりフレームワーク KPT(Keep / Problem / Try)に
沿って、このプロジェクトの K・P・T を 1 回の AI 呼び出しで導出する。

技術・実装面に偏らないよう、各アカウント別分析のセクション本文(稼働状況・担当範囲・
タスクの進め方・コミュニケーションの傾向)まで材料に含め、業務・プロセス面の観点も
拾えるようにしている。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI

from config.settings import Settings

logger = logging.getLogger(__name__)

MODEL_NAME = "gpt-5.4-mini"

# --- 材料テキストの上限(プロンプト肥大化の防止)---
MAX_TOPICS = 12
MAX_ACCOUNTS = 12
MAX_OVERVIEW_CHARS = 500
MAX_ACCOUNT_SECTIONS = 4
MAX_SECTION_BODY_CHARS = 600
MAX_SPEC_DIFF_ITEMS = 8
MAX_GH_ACTORS = 15

# 各 KPT 項目が根拠にできるソースキー
SOURCE_KEYS = ("mattermost", "trello", "github", "changelog", "spec_diff", "user_activity")
_SOURCE_LABEL = {
    "mattermost": "Mattermost情報分析",
    "trello": "Trello情報分析",
    "github": "GitHub情報取得",
    "changelog": "変更履歴分析",
    "spec_diff": "実装差分解析",
    "user_activity": "アクティビティ分析",
}

SYSTEM_PROMPT = """\
あなたは開発プロジェクトのふりかえりを支援するアナリストです。ふりかえりフレームワーク
KPT(Keep / Problem / Try)に沿って、このプロジェクト全体の K・P・T を導出してください。

- Keep : うまくいっていて続けるべきこと
- Problem : うまくいっていない・障害になっていること
- Try : Problem を改善する、または Keep を伸ばすために次に試すこと

与えられる材料(プロジェクト全体で集約済み):
- アクティビティ分析 … メンバーごとの役割・働き方・チーム内での関わり方・気になる点
- Mattermost情報分析 … コミュニケーションの話題、各メンバーの発言傾向・トーン・チャンネルでの役割
- Trello情報分析 … タスク管理・進行、各メンバーの担当案件・関わるボード/リスト(todo〜doneの流れ)
- 変更履歴分析 … コード変更の傾向、各メンバーの担当領域・変更の粒度/頻度
- GitHub情報取得 … コミット / PR / レビューなどの操作実績(アカウント別集計)
- 実装差分解析 … 設計書と実装の相違点(重大度つき。技術面の参考情報)

重要な観点(技術面と業務面の両方を必ず検討し、どちらかに偏らないこと。特に業務・プロセス面を軽視しない):
- 技術・実装面 : 設計書と実装の乖離、変更の傾向、基盤整備・リファクタの進み方、品質(テスト・不具合)
- 業務・プロセス面 :
  - メンバーの稼働バランス・負荷の偏り(特定の人に集中していないか、関与の薄い人はいないか)
  - タスクの進め方(粒度、滞留、リードタイム、レビュー待ちの溜まり方、着手前の方針確認の有無)
  - レビューの回り方(誰がレビューしているか、指摘の質、承認までの流れ)
  - 情報共有・意思決定の仕方(どのチャンネル/ボードで何が決まっているか、認識合わせのコスト)
  - ふりかえり(週報 / KPT ボード)の運用そのもの、ミーティングの持ち方

ルール:
- 材料に無いことを推測で補わないでください。根拠の弱い項目は挙げないこと。
- 各項目は具体的に。「コミュニケーション」ではなく「どのチャンネルで誰が何をしているか」まで書く。
- Try は Keep / Problem と結びつけ、実行可能な行動として書く。
- evidence には、その項目の根拠にした具体的な観察(どのツール/誰について何が見られたか)を書く。
- sources には、その項目が根拠にしたソースを配列で挙げる。
  使えるソースキー: "user_activity", "mattermost", "trello", "changelog", "github", "spec_diff"
- 各観点はおおむね 3〜7 項目。うち少なくとも半分は業務・プロセス面の項目にすること。
- 該当が無い観点は空配列にする。
- 前置きや説明は付けず、次の形式の JSON オブジェクトのみを出力してください:
  {"keep": [{"title": "...", "detail": "...", "evidence": "...", "sources": ["..."]}],
   "problem": [...], "try": [...]}
"""


class KptAnalysisError(Exception):
    """Azure OpenAI 未設定、または AI 応答を解析できなかった場合。"""


def _build_client(settings: Settings) -> OpenAI:
    return OpenAI(
        base_url=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
    )


def _strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def _call_chat(settings: Settings, system_prompt: str, user_prompt: str, label: str = "") -> Any:
    client = _build_client(settings)
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        logger.error("KPT分析の AI 呼び出しに失敗 [%s]: %s", label or "-", exc)
        raise KptAnalysisError(f"AI 呼び出しに失敗しました: {exc}") from exc

    usage = getattr(response, "usage", None)
    if usage is not None:
        logger.info(
            "KPT分析 AI トークン [%s] prompt=%s completion=%s total=%s",
            label or "-",
            getattr(usage, "prompt_tokens", "?"),
            getattr(usage, "completion_tokens", "?"),
            getattr(usage, "total_tokens", "?"),
        )

    raw = _strip_code_fence(response.choices[0].message.content or "")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("KPT分析 応答の JSON 解析に失敗 [%s]: %s / raw=%s", label or "-", exc, raw[:500])
        raise KptAnalysisError("AI 応答を解析できませんでした") from exc


# ----------------------------------------------------------------------
# 材料の集約(純粋関数・テスト対象)
# ----------------------------------------------------------------------
def _clean_stats(stats: dict[str, Any] | None) -> dict[str, Any]:
    """プロンプトに載せる統計値だけを抜き出す(配列・ネストは落とす)。"""
    out: dict[str, Any] = {}
    for k, v in (stats or {}).items():
        if k in ("error", "top_files", "channels", "boards"):
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
    return out


def _sections_digest(sections: Any) -> list[dict[str, str]]:
    """分析セクションを {heading, body(要約切り詰め)} の配列へ圧縮する。

    見出しだけでは業務面(発言傾向・担当範囲・ボードでの動き方など)が
    読み取れないため、本文も一定長まで残す。
    """
    out: list[dict[str, str]] = []
    for s in (sections or [])[:MAX_ACCOUNT_SECTIONS]:
        heading = str(s.get("heading", "")).strip()
        body = str(s.get("body", "")).strip()[:MAX_SECTION_BODY_CHARS]
        if not heading and not body:
            continue
        out.append({"heading": heading or "(見出しなし)", "body": body})
    return out


def _account_digest(src: dict[str, Any] | None) -> list[dict[str, Any]]:
    """アカウント別分析を {username, overview, sections:[{heading, body}]} の配列へ圧縮する。"""
    digest: list[dict[str, Any]] = []
    for acc in (src or {}).get("accounts", [])[:MAX_ACCOUNTS]:
        digest.append({
            "username": acc.get("username") or acc.get("user_id") or "?",
            "overview": (acc.get("overview") or "").strip()[:MAX_OVERVIEW_CHARS],
            "sections": _sections_digest(acc.get("sections")),
        })
    return digest


def _analysis_digest(src: dict[str, Any] | None, topic_key: str) -> dict[str, Any] | None:
    """mm / trello / changelog の run-level 分析を 1 ソースぶんの digest に。"""
    if not src:
        return None
    return {
        "topics": (src.get(topic_key) or [])[:MAX_TOPICS],
        "stats": _clean_stats(src.get("stats")),
        "accounts": _account_digest(src),
    }


def _github_digest(gh: dict[str, Any] | None) -> dict[str, Any] | None:
    if not gh or not gh.get("activity_total"):
        return None
    tally = []
    for a in (gh.get("by_actor") or [])[:MAX_GH_ACTORS]:
        tally.append({
            "actor": a.get("actor"),
            "total": a.get("total", 0),
            "commit": a.get("commit", 0),
            "pr_opened": a.get("pr_opened", 0),
            "pr_merged": a.get("pr_merged", 0),
            "pr_comment": a.get("pr_comment", 0),
            "pr_review": a.get("pr_review", 0),
        })
    return {
        "repo": gh.get("repo"),
        "activity_total": gh.get("activity_total"),
        "branch_count": gh.get("branch_count"),
        "pr_count": gh.get("pr_count"),
        "by_actor": tally,
    }


def _spec_diff_digest(sd: dict[str, Any] | None) -> dict[str, Any] | None:
    if not sd or not sd.get("items"):
        return None
    sev_order = {"high": 0, "mid": 1, "low": 2}
    items = sorted(
        sd.get("items") or [],
        key=lambda it: sev_order.get(it.get("severity"), 3),
    )
    counts = {"high": 0, "mid": 0, "low": 0}
    for it in sd.get("items") or []:
        if it.get("severity") in counts:
            counts[it["severity"]] += 1
    return {
        "diff_count": sd.get("diff_count"),
        "severity_counts": counts,
        "stats": _clean_stats(sd.get("stats")),
        "note": "技術面の参考。件数と重大度の高い相違点のみ抜粋",
        "items": [
            {
                "feature": it.get("feature_name"),
                "verdict": it.get("verdict"),
                "severity": it.get("severity"),
                "summary": (it.get("summary") or "").strip()[:MAX_OVERVIEW_CHARS],
            }
            for it in items[:MAX_SPEC_DIFF_ITEMS]
        ],
    }


def _user_activity_digest(ua: dict[str, Any] | None) -> dict[str, Any] | None:
    """アクティビティ分析(メンバー別)を {people:[{name, role, overview, sections}]} へ圧縮する。"""
    if not ua or not ua.get("items"):
        return None
    people: list[dict[str, Any]] = []
    for it in (ua.get("items") or [])[:MAX_ACCOUNTS]:
        overview = (it.get("overview") or "").strip()
        sections = _sections_digest(it.get("sections"))
        if not overview and not sections:
            continue
        people.append({
            "name": it.get("display_name") or "?",
            "is_member": bool(it.get("is_member")),
            "role": (it.get("personal") or "").strip()[:200],
            "overview": overview[:MAX_OVERVIEW_CHARS],
            "sections": sections,
        })
    if not people:
        return None
    stats = ua.get("stats") or {}
    return {
        "member_count": stats.get("member_count"),
        "other_count": stats.get("other_count"),
        "people": people,
    }


def build_bundle(
    mm: dict[str, Any] | None,
    tr: dict[str, Any] | None,
    cl: dict[str, Any] | None,
    gh: dict[str, Any] | None,
    sd: dict[str, Any] | None,
    ua: dict[str, Any] | None,
    tool_context: dict[str, str] | None,
) -> dict[str, Any]:
    """6 ソースをプロジェクト全体の 1 つの材料 dict に束ねる(純粋関数)。"""
    sources = {
        "user_activity": _user_activity_digest(ua),
        "mattermost": _analysis_digest(mm, "topics"),
        "trello": _analysis_digest(tr, "themes"),
        "changelog": _analysis_digest(cl, "themes"),
        "github": _github_digest(gh),
        "spec_diff": _spec_diff_digest(sd),
    }
    return {
        "sources": sources,
        "available": [k for k, v in sources.items() if v],
        "tool_context": {
            k: (tool_context or {}).get(k)
            for k in ("mattermost", "trello", "github")
            if (tool_context or {}).get(k)
        },
    }


# ----------------------------------------------------------------------
# ユーザープロンプト組み立て
# ----------------------------------------------------------------------
def _source_block(label: str, digest: dict[str, Any] | None) -> str:
    if not digest:
        return f"--- {label} ---\n(この材料はありません)"
    return f"--- {label} ---\n" + json.dumps(digest, ensure_ascii=False, indent=1)


def build_user_prompt(bundle: dict[str, Any]) -> str:
    src = bundle.get("sources", {})
    parts: list[str] = ["=== プロジェクトでのツール運用方法 ==="]
    tc = bundle.get("tool_context", {})
    for key, label in (("mattermost", "[Mattermost]"), ("trello", "[Trello]"), ("github", "[GitHub]")):
        if tc.get(key):
            parts.append(f"{label}\n{tc[key]}")
    if len(parts) == 1:
        parts.append("(記載なし)")

    parts.append("")
    parts.append("=== 集約済みの材料(プロジェクト全体)===")
    parts.append(_source_block("アクティビティ分析(メンバー別)", src.get("user_activity")))
    parts.append(_source_block("Mattermost情報分析", src.get("mattermost")))
    parts.append(_source_block("Trello情報分析", src.get("trello")))
    parts.append(_source_block("変更履歴分析", src.get("changelog")))
    parts.append(_source_block("GitHub情報取得", src.get("github")))
    parts.append(_source_block("実装差分解析(技術面の参考)", src.get("spec_diff")))
    parts.append("")
    parts.append(
        "上記の材料から、このプロジェクトの Keep / Problem / Try を導出してください。"
        "技術・実装面と業務・プロセス面(メンバーの稼働状況、タスクの進め方、レビューや"
        "情報共有の回り方、ふりかえり運用 など)の両方をバランス良く含めること。"
    )
    return "\n".join(parts)


# ----------------------------------------------------------------------
# 応答の正規化
# ----------------------------------------------------------------------
def _norm_items(raw: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for it in raw or []:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title", "")).strip()
        detail = str(it.get("detail", "")).strip()
        if not title and not detail:
            continue
        srcs = [s for s in (it.get("sources") or []) if s in SOURCE_KEYS]
        items.append({
            "title": (title or "(タイトルなし)")[:500],
            "detail": detail,
            "evidence": str(it.get("evidence", "")).strip(),
            "sources": srcs,
        })
    return items


def analyze_kpt(settings: Settings, bundle: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """プロジェクト全体の KPT を 1 回の AI 呼び出しで導出する。

    Returns
    -----------------
    - {"keep": [item...], "problem": [item...], "try": [item...]}
      item = {"title", "detail", "evidence", "sources": [ソースキー...]}
    """
    if not settings.ai_enabled:
        raise KptAnalysisError(
            "Azure OpenAI が未設定です(.env の AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY を確認してください)"
        )
    if not bundle.get("available"):
        raise KptAnalysisError("KPT分析の材料がありません")

    parsed = _call_chat(settings, SYSTEM_PROMPT, build_user_prompt(bundle), label="KPT")
    if not isinstance(parsed, dict):
        raise KptAnalysisError("AI 応答の形式が想定と異なります")

    return {
        "keep": _norm_items(parsed.get("keep")),
        "problem": _norm_items(parsed.get("problem")),
        "try": _norm_items(parsed.get("try")),
    }
