"""「暗黙知抽出」の AI 処理。

Mattermost の投稿本文 / Trello のカード説明・コメント / GitHub の PR コメント・レビュー
から、ドキュメント化されていないプロジェクト固有の知見(暗黙知)を抽出する。

この処理では知見の価値の大小を判断しない。重要度の判定は「暗黙知共有」画面での
ユーザー評価と、それを学習する仕組み(今後追加予定)に委ねるため、少しでも知見として
成立しそうな情報は取りこぼさず抽出するようプロンプトで指示している。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI

from config.settings import Settings

logger = logging.getLogger(__name__)

MODEL_NAME = "gpt-5.4-mini"

BATCH_SIZE = 15          # 1 回の AI 呼び出しに含める断片数
MAX_TEXT_CHARS = 1500     # 1 断片あたりの文字数上限(長文コメント対策)

SOURCE_LABEL = {
    "mattermost": "Mattermostの投稿",
    "trello": "Trelloのカード説明・コメント",
    "github": "GitHubのPRコメント・レビュー",
}

SYSTEM_PROMPT = """\
あなたはソフトウェア開発プロジェクトの暗黙知(ドキュメント化されていないプロジェクト固有の
知見)を発掘するアナリストです。Mattermost の投稿 / Trello のカード説明・コメント /
GitHub の PR コメント・レビュー から抜粋した断片が与えられます。

抽出対象(該当しそうならジャンルを問わず対象にすること):
- 環境構築・設定に関する具体的な手順・値・注意点
- 仕様や実装上の決定とその理由
- ハマりどころ・トラブルとその対処法(ワークアラウンド)
- チーム内の暗黙のルール・命名規則・運用ルール
- 外部サービス/APIの制約や癖、ライブラリのバージョン依存の問題
- その他、明文化されたドキュメントには載っていなさそうな、プロジェクト固有の知見

方針(重要):
- この時点では知見の重要度・価値の大小を判断しないでください。「重要かどうか」は、
  この後に人による評価と機械学習を組み合わせた別の仕組みで判定します。
- 少しでも上記に当てはまる可能性がある情報は、確信が持てなくても漏らさず抽出してください。
  取りこぼしよりも過剰抽出を優先すること。
- 挨拶・雑談・進捗報告のみ("done" "了解です" 等)で、上記のいずれにも当てはまらない
  ものだけを抽出対象から除外してください。
- 1 つの断片から複数の異なる知見が読み取れる場合は、それぞれ別項目として抽出してください。
- content には、後から単独で読んでも意味が分かるように、必要な文脈(何についての話か)を
  補って書いてください(原文の丸写しではなく要約でよい)。
- 与えられたテキストに書かれていない情報を推測で補わないでください。

出力形式: 前置きなしで次の JSON のみを出力してください。
{"items": [{"ref": <入力の[ref=N]の数値>, "title": "短い見出し", "content": "知見の内容"}]}
どの断片からも知見が見当たらない場合は {"items": []} としてください。
"""


class TacitAnalysisError(Exception):
    """Azure OpenAI 未設定、または AI 応答を解析できなかった場合。"""


def _build_client(settings: Settings) -> OpenAI:
    return OpenAI(base_url=settings.azure_openai_endpoint, api_key=settings.azure_openai_api_key)


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
        logger.error("暗黙知抽出の AI 呼び出しに失敗 [%s]: %s", label or "-", exc)
        raise TacitAnalysisError(f"AI 呼び出しに失敗しました: {exc}") from exc

    usage = getattr(response, "usage", None)
    if usage is not None:
        logger.info(
            "暗黙知抽出 AI トークン [%s] prompt=%s completion=%s total=%s",
            label or "-",
            getattr(usage, "prompt_tokens", "?"),
            getattr(usage, "completion_tokens", "?"),
            getattr(usage, "total_tokens", "?"),
        )

    raw = _strip_code_fence(response.choices[0].message.content or "")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("暗黙知抽出 応答の JSON 解析に失敗 [%s]: %s / raw=%s", label or "-", exc, raw[:500])
        raise TacitAnalysisError("AI 応答を解析できませんでした") from exc


def _build_user_prompt(source_label: str, batch: list[dict[str, Any]]) -> str:
    lines = [f"=== {source_label} の断片(以下から暗黙知を抽出してください) ==="]
    for i, c in enumerate(batch):
        ctx = (c.get("context") or "").strip()
        txt = (c.get("text") or "").strip()[:MAX_TEXT_CHARS]
        lines.append(f"[ref={i}] {ctx}\n{txt}")
    return "\n\n".join(lines)


def extract_batch(settings: Settings, source: str, batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """1 バッチぶんの候補から AI で暗黙知を抽出する。

    Returns:
        [{"ref_index": バッチ内インデックス, "title": ..., "content": ...}, ...]
    """
    label = SOURCE_LABEL.get(source, source)
    parsed = _call_chat(settings, SYSTEM_PROMPT, _build_user_prompt(label, batch), label=label)
    raw_items = parsed.get("items") if isinstance(parsed, dict) else None

    out: list[dict[str, Any]] = []
    for it in raw_items or []:
        if not isinstance(it, dict):
            continue
        ref = it.get("ref")
        content = str(it.get("content", "")).strip()
        title = str(it.get("title", "")).strip()
        if not isinstance(ref, int) or not (0 <= ref < len(batch)) or not content:
            continue
        out.append({"ref_index": ref, "title": (title or content[:60])[:255], "content": content})
    return out


def extract_all(
    settings: Settings, candidates_by_source: dict[str, list[dict[str, Any]]]
) -> dict[str, list[dict[str, Any]]]:
    """ソースごとの候補リスト(すでにフィルタ済み)をバッチ処理し、抽出結果を返す。

    Args
    -----------------
    - candidates_by_source: {"mattermost": [...], "trello": [...], "github": [...]}
      各要素は {"text", "context"} を持つ(pipeline.tacit_store.fetch_candidates の戻り)。

    Returns
    -----------------
    - {source: [{"candidate_index": candidates_by_source[source] 内のインデックス,
                 "title", "content"}, ...]}
    """
    if not settings.ai_enabled:
        raise TacitAnalysisError(
            "Azure OpenAI が未設定です(.env の AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY を確認してください)"
        )

    results: dict[str, list[dict[str, Any]]] = {}
    for source, candidates in candidates_by_source.items():
        out: list[dict[str, Any]] = []
        for start in range(0, len(candidates), BATCH_SIZE):
            batch = candidates[start : start + BATCH_SIZE]
            for it in extract_batch(settings, source, batch):
                out.append({
                    "candidate_index": start + it["ref_index"],
                    "title": it["title"],
                    "content": it["content"],
                })
        results[source] = out
    return results
