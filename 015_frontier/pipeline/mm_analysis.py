"""「Mattermost 情報解析」の AI 処理(2 段)。

1. list_team_topics(): アカウント一覧と発言サンプルを渡し、チーム内で扱われている
   話題の語彙を洗い出す(1 コール、任意)。2 段目に共通コンテキストとして渡すと、
   アカウント間でトピック表記が揃う。
2. analyze_account(): 1 アカウントについて、チャンネル横断の発言と統計を渡し、
   発言の傾向・話題・役割・他者との関わり などを分析する(アカウントごとに並列)。

AI クライアントは design_features / code_features と同じ OpenAI 互換エンドポイント。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI

from config.settings import Settings

logger = logging.getLogger(__name__)

MODEL_NAME = "gpt-5.4-mini"

TOPICS_SYSTEM_PROMPT = """\
チームの Mattermost 発言サンプル(アカウント別)が与えられます。このチームで実際に
話題になっている事柄を、日本語の短い名詞句で 30 個以内に洗い出してください。

- サンプルに現れる具体的な話題(プロジェクト名・機能名・作業・障害・イベントなど)を挙げる。
- 一般語(「会議」「連絡」など)だけの項目は避け、できるだけ具体的にする。
- 前置きや説明は付けず、次の形式の JSON オブジェクトのみを出力してください:
  {"topics": ["...", "..."]}
"""

ACCOUNT_SYSTEM_PROMPT = """\
1 人のアカウントについて、複数チャンネルにまたがる Mattermost 発言(時系列)と活動統計が
与えられます。このアカウントがチームでどのような発言・活動をしているかを、
与えられた内容だけを根拠に日本語で分析してください。

観点(該当するもののみ):
- 発言の傾向・トーン(質問が多い/回答役/報告中心/雑談 など)
- 主に扱う話題(与えられたトピック語彙を参考にしてよい)
- よく参加するチャンネルと、そこでの役割
- 他メンバーとのやり取り(誰と多くやり取りしているか、依頼/相談/レビュー など)
- 目立った貢献・意思決定・アナウンス
- 気になる点(偏り、負荷、コミュニケーション上のリスク など)

ルール:
- 与えられた発言・統計に無いことを推測で補わないでください。
- sections は見出し(heading)と本文(body)の配列です。body は箇条書きを含む
  プレーンテキストで記述してください(Markdown 記法は使わない)。
- 前置きや説明は付けず、次の形式の JSON オブジェクトのみを出力してください:
  {"overview": "1〜2文の要約", "sections": [{"heading": "...", "body": "..."}]}
"""


class MmAnalysisError(Exception):
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
        logger.error("Mattermost 分析の AI 呼び出しに失敗 [%s]: %s", label or "-", exc)
        raise MmAnalysisError(f"AI 呼び出しに失敗しました: {exc}") from exc

    usage = getattr(response, "usage", None)
    if usage is not None:
        logger.info(
            "Mattermost 分析 AI トークン [%s] prompt=%s completion=%s total=%s",
            label or "-",
            getattr(usage, "prompt_tokens", "?"),
            getattr(usage, "completion_tokens", "?"),
            getattr(usage, "total_tokens", "?"),
        )

    raw = _strip_code_fence(response.choices[0].message.content or "")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Mattermost 分析 応答の JSON 解析に失敗 [%s]: %s / raw=%s", label or "-", exc, raw[:500])
        raise MmAnalysisError("AI 応答を解析できませんでした") from exc


# ----------------------------------------------------------------------
# 1 段目: チーム内トピックの洗い出し(任意)
# ----------------------------------------------------------------------
def list_team_topics(
    settings: Settings, contexts: list[dict[str, Any]], max_accounts: int = 40
) -> list[str]:
    """アカウント一覧と発言サンプルからチーム内トピックを洗い出す。失敗時は []。"""
    if not settings.ai_enabled or not contexts:
        return []
    brief = [
        {
            "username": c["username"],
            "stats": {k: c["stats"][k] for k in ("post_count", "channel_count", "active_days")},
            "sample": c["context"][:1500],
        }
        for c in contexts[:max_accounts]
    ]
    try:
        parsed = _call_chat(
            settings,
            TOPICS_SYSTEM_PROMPT,
            json.dumps({"accounts": brief}, ensure_ascii=False),
            label="1段目:トピック",
        )
    except MmAnalysisError:
        return []
    raw = parsed.get("topics", []) if isinstance(parsed, dict) else []
    return [str(x).strip() for x in raw if str(x).strip()][:30]


# ----------------------------------------------------------------------
# 2 段目: アカウント単位の分析
# ----------------------------------------------------------------------
def analyze_account(
    settings: Settings, account: dict[str, Any], topics: list[str]
) -> dict[str, Any]:
    """1 アカウントについて、チャンネル横断の発言から傾向・話題・役割を分析する。

    Args
    -----------------
    - settings: Settings,   アプリ設定(Azure OpenAI の接続情報を含む)
    - account: dict,        build_account_contexts() の 1 要素
                            (username / stats / context を使用)
    - topics: list[str],    1 段目で洗い出したチーム内トピック(空でも可)

    Returns
    -----------------
    - {"overview": str, "sections": [{"heading", "body"}]}

    Raises
    -----------------
    - MmAnalysisError: Azure OpenAI 未設定、AI 呼び出し失敗、応答解析失敗
    """
    if not settings.ai_enabled:
        raise MmAnalysisError(
            "Azure OpenAI が未設定です(.env の AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY を確認してください)"
        )

    user_prompt = (
        f"アカウント: {account.get('username', '')}\n"
        f"活動統計: {json.dumps(account.get('stats', {}), ensure_ascii=False)}\n"
        + (f"チーム内の主な話題(参考): {', '.join(topics)}\n" if topics else "")
        + "\n=== このアカウントの発言(チャンネル横断・時系列)===\n"
        + (account.get("context") or "(発言なし)")
    )
    parsed = _call_chat(
        settings, ACCOUNT_SYSTEM_PROMPT, user_prompt, label=f"2段目:{account.get('username', '?')}"
    )
    if not isinstance(parsed, dict):
        raise MmAnalysisError("AI 応答の形式が想定と異なります")

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
