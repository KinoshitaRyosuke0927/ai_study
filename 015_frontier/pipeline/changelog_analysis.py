"""「変更履歴取得」の AI 処理(2 段)。

1. list_repo_themes(): コミットメッセージから、このリポジトリで進んでいる作業テーマを洗い出す。
2. analyze_author(): 1 アカウントについて、変更したファイル群・コミットの傾向・粒度・
   よく一緒に触るファイルなどを分析する(アカウントごとに並列)。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI

from config.settings import Settings

logger = logging.getLogger(__name__)

MODEL_NAME = "gpt-5.4-mini"

THEMES_SYSTEM_PROMPT = """\
リポジトリのコミットメッセージ(先頭行)の一覧が与えられます。このリポジトリで実際に
進んでいる作業テーマを、日本語の短い名詞句で 30 個以内に洗い出してください。

- メッセージに現れる具体的な機能・修正・リファクタ・基盤整備などを挙げる。
- 一般語(「修正」「更新」など)だけの項目は避け、できるだけ具体的にする。
- 前置きや説明は付けず、次の形式の JSON オブジェクトのみを出力してください:
  {"themes": ["...", "..."]}
"""

AUTHOR_SYSTEM_PROMPT = """\
1 人のアカウント(コミット作者)について、複数ファイルにまたがるコミット履歴(時系列。
各行にメッセージ先頭行・追加/削除行数・変更ファイル)と活動統計、よく触るファイルが
与えられます。このアカウントがこのリポジトリでどのような変更をしているかを、
与えられた内容だけを根拠に日本語で分析してください。

観点(該当するもののみ):
- どの領域・ファイル群を変更しているか(担当している範囲)
- 変更の傾向(機能追加・不具合修正・リファクタ・設定/基盤・テスト・ドキュメント など)
- 変更の粒度・頻度(小さくこまめか、大きくまとめてか)
- よく一緒に触るファイル(co-change)、関わっている工程
- 目立った変更・意思決定
- 気になる点(変更が集中しているファイル、巨大なコミット、偏り など)

ルール:
- 与えられた履歴・統計に無いことを推測で補わないでください。
- sections は見出し(heading)と本文(body)の配列です。body は箇条書きを含む
  プレーンテキストで記述してください(Markdown 記法は使わない)。
- 前置きや説明は付けず、次の形式の JSON オブジェクトのみを出力してください:
  {"overview": "1〜2文の要約", "sections": [{"heading": "...", "body": "..."}]}
"""


class ChangelogAnalysisError(Exception):
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
        logger.error("変更履歴分析の AI 呼び出しに失敗 [%s]: %s", label or "-", exc)
        raise ChangelogAnalysisError(f"AI 呼び出しに失敗しました: {exc}") from exc

    usage = getattr(response, "usage", None)
    if usage is not None:
        logger.info(
            "変更履歴分析 AI トークン [%s] prompt=%s completion=%s total=%s",
            label or "-",
            getattr(usage, "prompt_tokens", "?"),
            getattr(usage, "completion_tokens", "?"),
            getattr(usage, "total_tokens", "?"),
        )

    raw = _strip_code_fence(response.choices[0].message.content or "")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("変更履歴分析 応答の JSON 解析に失敗 [%s]: %s / raw=%s", label or "-", exc, raw[:500])
        raise ChangelogAnalysisError("AI 応答を解析できませんでした") from exc


def list_repo_themes(
    settings: Settings, commits: list[dict[str, Any]], max_messages: int = 250
) -> list[str]:
    """コミットメッセージ先頭行からリポジトリの作業テーマを洗い出す。失敗時は []。"""
    if not settings.ai_enabled or not commits:
        return []
    msgs = []
    for c in commits[:max_messages]:
        first = (c.get("message") or "").strip().splitlines()
        if first:
            msgs.append(first[0].strip())
    try:
        parsed = _call_chat(
            settings, THEMES_SYSTEM_PROMPT,
            json.dumps({"messages": msgs}, ensure_ascii=False), label="1段目:テーマ",
        )
    except ChangelogAnalysisError:
        return []
    raw = parsed.get("themes", []) if isinstance(parsed, dict) else []
    return [str(x).strip() for x in raw if str(x).strip()][:30]


def analyze_author(
    settings: Settings, author: dict[str, Any], themes: list[str]
) -> dict[str, Any]:
    """1 アカウントの変更履歴から、担当領域・傾向・粒度・co-change を分析する。

    Returns
    -----------------
    - {"overview": str, "sections": [{"heading", "body"}]}

    Raises
    -----------------
    - ChangelogAnalysisError: Azure OpenAI 未設定、AI 呼び出し失敗、応答解析失敗
    """
    if not settings.ai_enabled:
        raise ChangelogAnalysisError(
            "Azure OpenAI が未設定です(.env の AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY を確認してください)"
        )

    stats = account_stats_for_prompt(author)
    user_prompt = (
        f"アカウント: {author.get('author', '')}"
        + (f"({author.get('author_name')})" if author.get("author_name") else "")
        + "\n"
        f"活動統計: {json.dumps(stats, ensure_ascii=False)}\n"
        + (f"リポジトリの作業テーマ(参考): {', '.join(themes)}\n" if themes else "")
        + "\n" + (author.get("context") or "(コミットなし)")
    )
    parsed = _call_chat(
        settings, AUTHOR_SYSTEM_PROMPT, user_prompt, label=f"2段目:{author.get('author', '?')}"
    )
    if not isinstance(parsed, dict):
        raise ChangelogAnalysisError("AI 応答の形式が想定と異なります")

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


def account_stats_for_prompt(author: dict[str, Any]) -> dict[str, Any]:
    """プロンプトに載せる統計(冗長なキーを除いた要約)。"""
    s = author.get("stats", {}) or {}
    keys = ("commit_count", "additions", "deletions", "files_touched", "first_at", "last_at", "top_files")
    return {k: s[k] for k in keys if k in s}
