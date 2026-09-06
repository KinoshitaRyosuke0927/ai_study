"""「アクティビティ分析」の AI 処理。

Mattermost / Trello / コード変更履歴 の各アカウント別分析結果と、GitHub 情報(操作ログ)から
1 人ぶんの材料を束ね、プロジェクトでのツール運用方法を踏まえて、そのメンバーの
プロジェクトにおけるアクティビティをまとめる。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI

from config.settings import Settings

logger = logging.getLogger(__name__)

MODEL_NAME = "gpt-5.4-mini"
MAX_SECTION_BODY_CHARS = 2000
MAX_GITHUB_RECENT = 15

SYSTEM_PROMPT = """\
あなたは開発プロジェクトのふりかえりを支援するアナリストです。1 人のメンバーについて、
複数ツール(Mattermost / Trello / GitHub / コード変更履歴)から抽出済みのアクティビティ分析と、
このプロジェクトでの各ツールの運用方法、そのメンバーの役割説明が与えられます。
これらを突き合わせ、このプロジェクトにおけるそのメンバーのアクティビティを日本語でまとめてください。

観点(該当するもののみ):
- プロジェクトでの役割・担当している工程や領域
- 各ツールでの動き方(何を発信し、何をレビューし、何を実装/管理しているか)
- チーム内での関わり方(誰と、どのように連携しているか)
- 特徴・強み
- 気になる点(偏り、停滞、コミュニケーション上の懸念 など)

ルール:
- 与えられた材料に無いことを推測で補わないでください。材料が少ない観点は省略します。
- 各ツールの運用方法(チャンネルやボードの役割)を踏まえて解釈してください。
- sections は見出し(heading)と本文(body)の配列です。body は箇条書きを含む
  プレーンテキストで記述してください(Markdown 記法は使わない)。
- 前置きや説明は付けず、次の形式の JSON オブジェクトのみを出力してください:
  {"overview": "2〜3文の要約", "sections": [{"heading": "...", "body": "..."}]}
"""


class UserActivityAnalysisError(Exception):
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
        logger.error("アクティビティ分析の AI 呼び出しに失敗 [%s]: %s", label or "-", exc)
        raise UserActivityAnalysisError(f"AI 呼び出しに失敗しました: {exc}") from exc

    usage = getattr(response, "usage", None)
    if usage is not None:
        logger.info(
            "アクティビティ分析 AI トークン [%s] prompt=%s completion=%s total=%s",
            label or "-",
            getattr(usage, "prompt_tokens", "?"),
            getattr(usage, "completion_tokens", "?"),
            getattr(usage, "total_tokens", "?"),
        )

    raw = _strip_code_fence(response.choices[0].message.content or "")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("アクティビティ分析 応答の JSON 解析に失敗 [%s]: %s / raw=%s", label or "-", exc, raw[:500])
        raise UserActivityAnalysisError("AI 応答を解析できませんでした") from exc


# ----------------------------------------------------------------------
# 材料テキストの整形
# ----------------------------------------------------------------------
def _analysis_block(label: str, src: dict[str, Any] | None) -> str:
    if not src:
        return f"--- {label} ---\n(この期間のこのメンバーの分析結果はありません)"
    lines = [f"--- {label} ---"]
    if src.get("overview"):
        lines.append(f"概要: {src['overview']}")
    for sec in src.get("sections") or []:
        body = str(sec.get("body", "")).strip()[:MAX_SECTION_BODY_CHARS]
        lines.append(f"【{sec.get('heading', '')}】\n{body}")
    stats = {k: v for k, v in (src.get("stats") or {}).items()
             if k not in ("error", "top_files", "channels", "boards")}
    if stats:
        lines.append("統計: " + json.dumps(stats, ensure_ascii=False))
    return "\n".join(lines)


def _github_block(gh: dict[str, Any] | None) -> str:
    if not gh:
        return "--- GitHub 情報(操作・コメント)---\n(このメンバーの GitHub 操作記録はありません)"
    t = gh.get("tally", {})
    lines = [
        "--- GitHub 情報(操作・コメント)---",
        f"アカウント: {gh.get('actor', '')}",
        (
            f"集計: コミット {t.get('commit', 0)} / PR作成 {t.get('pr_opened', 0)} / "
            f"マージ {t.get('pr_merged', 0)} / PRクローズ {t.get('pr_closed', 0)} / "
            f"コメント {t.get('pr_comment', 0)} / レビュー {t.get('pr_review', 0)}"
        ),
    ]
    recent = gh.get("recent") or []
    if recent:
        lines.append("主な操作(新しい順):")
        for a in recent[:MAX_GITHUB_RECENT]:
            tgt = f" PR#{a['pr_number']}" if a.get("pr_number") is not None else (f" {a['branch']}" if a.get("branch") else "")
            body = f" — {a['body_excerpt']}" if a.get("body_excerpt") else ""
            lines.append(f"  [{(a.get('occurred_at') or '')[:16]}] {a.get('kind_label')}{tgt}: {a.get('summary')}{body}")
    return "\n".join(lines)


def build_user_prompt(bundle: dict[str, Any], tool_context: dict[str, str]) -> str:
    """1 メンバーぶんの材料からユーザープロンプトを組み立てる。"""
    acc = bundle.get("accounts", {})
    parts = [
        f"対象メンバー: {bundle.get('name', '')}"
        + ("(USER_ID に未登録のアカウント)" if not bundle.get("is_member") else ""),
        f"役割: {bundle.get('personal') or '(記載なし)'}",
        "ひもづくアカウント: "
        + f"Mattermost={acc.get('mattermost') or '-'}, Trello={acc.get('trello') or '-'}, GitHub={acc.get('github') or '-'}",
        "",
        "=== プロジェクトでのツール運用方法 ===",
    ]
    for key, label in (("mattermost", "[Mattermost]"), ("trello", "[Trello]"), ("github", "[GitHub]")):
        ctx = (tool_context or {}).get(key)
        if ctx:
            parts.append(f"{label}\n{ctx}")
    parts.append("")
    parts.append("=== このメンバーのアクティビティ(ツール別・抽出済み)===")
    src = bundle.get("sources", {})
    parts.append(_analysis_block("Mattermost 情報分析", src.get("mattermost")))
    parts.append(_analysis_block("Trello 情報分析", src.get("trello")))
    parts.append(_analysis_block("コード変更履歴 分析", src.get("changelog")))
    parts.append(_github_block(src.get("github")))
    return "\n".join(parts)


def analyze_user(
    settings: Settings, bundle: dict[str, Any], tool_context: dict[str, str]
) -> dict[str, Any]:
    """1 メンバーのプロジェクトにおけるアクティビティを分析する。

    Returns
    -----------------
    - {"overview": str, "sections": [{"heading", "body"}]}
    """
    if not settings.ai_enabled:
        raise UserActivityAnalysisError(
            "Azure OpenAI が未設定です(.env の AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY を確認してください)"
        )

    parsed = _call_chat(
        settings, SYSTEM_PROMPT, build_user_prompt(bundle, tool_context),
        label=f"分析:{bundle.get('name', '?')}",
    )
    if not isinstance(parsed, dict):
        raise UserActivityAnalysisError("AI 応答の形式が想定と異なります")

    sections: list[dict[str, str]] = []
    for sec in parsed.get("sections", []) or []:
        if not isinstance(sec, dict):
            continue
        heading = str(sec.get("heading", "")).strip()
        body = str(sec.get("body", "")).strip()
        if not heading and not body:
            continue
        sections.append({"heading": heading or "(見出しなし)", "body": body})

    return {
        "overview": str(parsed.get("overview", "")).strip(),
        "sections": sections,
    }
