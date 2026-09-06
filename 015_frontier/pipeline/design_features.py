"""「設計書情報取得」画面の「機能分析」用モジュール。

AI とのやり取りを 2 段階に分けて行う。

1. plan_analysis() / list_features():
   設計書フォルダ配下のデータをすべて AI に渡し、アプリケーション全体にどのような
   機能があるかを洗い出す(1 回のやり取り)。あわせて、各機能の仕様が書かれている
   設計書の「セクション」(Markdown 見出し単位で分割したもの)を AI に特定させる。
2. analyze_feature_detail():
   機能ごとに、1 で特定したセクション + 常時添付する共通ドキュメントだけを AI に渡し、
   その機能の詳細な仕様を読み取って画面表示用の情報を組み立てる。
   絞り込んだ抜粋が薄すぎる機能は、安全側に倒して設計書全文へフォールバックする。
   機能ごとの呼び出しは呼び出し側(app.py)で並列に実行する。

AI クライアントは 010_ai_reviewer / 011_chat_linkage と同じく、OpenAI 互換
エンドポイント(``.../openai/v1``)へ ``OpenAI`` クライアントで接続する。
画面表示用であり、結果は DB へは保存しない。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import OpenAI

from config.settings import Settings

logger = logging.getLogger(__name__)

# デプロイしたモデルの名称(010_ai_reviewer / 011_chat_linkage と合わせる)
MODEL_NAME = "gpt-5.4-mini"

# 1 回目のやり取りで、1 ファイルあたり AI へ渡す本文の最大文字数
MAX_CHARS_PER_FILE = 6000
# 2 回目のやり取りで組み立てる抜粋コンテキストの最大文字数
MAX_CONTEXT_CHARS = 12000
# このファイル名パターン、またはこの文字数以下のファイルは「共通ドキュメント」とみなし、
# すべての機能の 2 回目リクエストに常に添付する
COMMON_FILE_MAX_CHARS = 1500
COMMON_FILE_NAME_RE = re.compile(
    r"(readme|overview|index|glossary|term|用語|共通|概要|全体|前提|非機能|architecture|アーキ)",
    re.IGNORECASE,
)
# 機能に紐づく抜粋の合計がこの文字数未満なら、絞り込みをやめて設計書全文で解析する
FALLBACK_MIN_CHARS = 800

# Markdown 見出し行(# 〜 ######)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")

# --- 1 回目: 機能の洗い出し + 該当セクション特定用システムプロンプト ---
LIST_FEATURES_SYSTEM_PROMPT = """\
あなたはソフトウェアの設計書を読み解き、そのアプリケーションが持つ機能の全体像を
洗い出すアシスタントです。与えられた設計書ファイル群(全文)の内容だけを根拠に、この
アプリケーションにどのような機能があるかを日本語で列挙してください。あわせて、各機能の
仕様が記載されている箇所を、後述のセクションアウトラインの「セクションID」で指し示して
ください。

出力ルール:
- 設計書に書かれていない機能を推測で追加したり、内容を創作したりしないでください。
- 利用者から見て意味のある単位(画面・バッチ処理・API・外部連携など)でまとめてください。
- 同じ機能が複数のファイルに跨って書かれている場合は 1 つにまとめてください。
- この段階では詳細仕様は不要です。機能の名称と、一言の概要だけを記載してください。
- section_ids には、その機能に関係する記述があるセクションのIDだけを、アウトラインから
  選んで列挙してください。関係の薄いIDは含めないでください。共通仕様・用語集などに
  跨る場合は、そのセクションIDも含めてください。
- IDはアウトラインに実在するものだけを使い、創作しないでください。
- 前置き・説明・コードブロックは付けず、次の形式の JSON オブジェクトのみを出力してください:
  {"features": [{"name": "...", "summary": "...", "section_ids": ["a.md::1", "b.md::3"]}]}
"""

# --- 2 回目: 機能ごとの詳細仕様の書き起こし用システムプロンプト ---
FEATURE_DETAIL_SYSTEM_PROMPT = """\
あなたはソフトウェアの設計書を読み解き、指定された 1 つの機能について詳細仕様を
書き起こすアシスタントです。与えられた設計書の抜粋の内容だけを根拠に、対象機能の
仕様を日本語で整理してください。

出力ルール:
- 抜粋に書かれていない内容を推測で補ったり、創作したりしないでください。
  抜粋から読み取れない観点は省略して構いません。
- 対象機能に関係する記述を抜粋から拾い、次のような観点でまとめてください:
  画面・入力項目、処理内容・ロジック、入出力データ、他機能や外部システムとの連携、
  制約・バリデーション、例外・エラー時の挙動。該当する観点のみで構いません。
- sections は見出し(heading)と本文(body)の配列です。body は箇条書きを含む
  プレーンテキストで記述してください(Markdown 記法は使わない)。
- 前置き・説明・コードブロックは付けず、次の形式の JSON オブジェクトのみを出力してください:
  {"name": "...", "overview": "...", "sections": [{"heading": "...", "body": "..."}]}
"""


class DesignFeatureAnalysisError(Exception):
    """Azure OpenAI が未設定、または AI 応答を解析できなかった場合。"""


# ----------------------------------------------------------------------
# AI 呼び出し
# ----------------------------------------------------------------------
def _build_client(settings: Settings) -> OpenAI:
    """OpenAI 互換エンドポイント向けのクライアントを生成する。"""
    return OpenAI(
        base_url=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
    )


def _strip_code_fence(text: str) -> str:
    """```json ... ``` のようなコードフェンスが付いていれば取り除く。"""
    t = text.strip()
    if t.startswith("```"):
        # 先頭行(``` または ```json)と末尾の ``` を除去する
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def _call_chat(
    settings: Settings, system_prompt: str, user_prompt: str, label: str = ""
) -> Any:
    """system / user プロンプトを Azure OpenAI に送信し、JSON を解析して返す。

    Args
    -----------------
    - settings: Settings,     アプリ設定(Azure OpenAI の接続情報を含む)
    - system_prompt: str,     システムプロンプト
    - user_prompt: str,       ユーザープロンプト
    - label: str,             ログ出力用のラベル(どのやり取りかを識別)

    Returns
    -----------------
    - parsed: Any,            AI 応答を JSON として解析した結果

    Raises
    -----------------
    - DesignFeatureAnalysisError: AI 呼び出し失敗、または JSON 解析に失敗した場合
    """
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
    except Exception as exc:  # AI 呼び出しの失敗は画面へエラーとして返す
        logger.error("設計書分析の AI 呼び出しに失敗 [%s]: %s", label or "-", exc)
        raise DesignFeatureAnalysisError(f"AI 呼び出しに失敗しました: {exc}") from exc

    # トークン使用量を記録する(2 回目の情報量削減効果を測るため)
    usage = getattr(response, "usage", None)
    if usage is not None:
        logger.info(
            "設計書分析 AI トークン [%s] prompt=%s completion=%s total=%s",
            label or "-",
            getattr(usage, "prompt_tokens", "?"),
            getattr(usage, "completion_tokens", "?"),
            getattr(usage, "total_tokens", "?"),
        )

    raw = _strip_code_fence(response.choices[0].message.content or "")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error(
            "設計書分析 応答の JSON 解析に失敗 [%s]: %s / raw=%s",
            label or "-", exc, raw[:500],
        )
        raise DesignFeatureAnalysisError("AI 応答を解析できませんでした") from exc


# ----------------------------------------------------------------------
# 設計書のセクション分割 / 共通ドキュメント判定
# ----------------------------------------------------------------------
def _is_common_file(name: str, content: str) -> bool:
    """常時添付する「共通ドキュメント」かどうかを判定する。"""
    if COMMON_FILE_NAME_RE.search(name or ""):
        return True
    return len((content or "").strip()) <= COMMON_FILE_MAX_CHARS


def split_sections(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """設計書ファイル群を Markdown 見出し単位のセクションへ分割する。

    Args
    -----------------
    - files: list[dict],  設計書ファイル一覧(各要素は "name", "content" を持つ)

    Returns
    -----------------
    - sections: list[dict],  セクション一覧。各要素は
      "id"(= "<ファイル名>::<連番>")、"file"、"level"(見出しレベル。先頭部は 0)、
      "heading"、"heading_path"(親見出しを " > " で連結)、"body"、
      "char_len"、"is_common" を持つ。ファイル出現順・ファイル内出現順で並ぶ。
    """
    sections: list[dict[str, Any]] = []
    for f in files:
        name = f.get("name", "")
        content = f.get("content") or ""
        is_common = _is_common_file(name, content)
        lines = content.splitlines()

        # 見出し行の位置・レベル・タイトルを収集する
        heads: list[tuple[int, int, str]] = []
        for i, ln in enumerate(lines):
            m = HEADING_RE.match(ln)
            if m:
                heads.append((i, len(m.group(1)), m.group(2).strip()))

        # (開始行, 終了行, レベル, タイトル)のスパンを組み立てる
        spans: list[tuple[int, int, int, str]] = []
        if not heads or heads[0][0] > 0:
            # 最初の見出しより前の「先頭部」
            end = heads[0][0] if heads else len(lines)
            spans.append((0, end, 0, "(先頭)"))
        for idx, (li, lvl, title) in enumerate(heads):
            end = heads[idx + 1][0] if idx + 1 < len(heads) else len(lines)
            spans.append((li, end, lvl, title))

        # 親見出しスタックを使って heading_path を組み立てる
        stack: list[tuple[int, str]] = []
        for si, (s, e, lvl, title) in enumerate(spans):
            if lvl == 0:
                heading_path = name
            else:
                while stack and stack[-1][0] >= lvl:
                    stack.pop()
                stack.append((lvl, title))
                heading_path = " > ".join(t for _, t in stack)
            body = "\n".join(lines[s:e]).strip()
            sections.append({
                "id": f"{name}::{si}",
                "file": name,
                "level": lvl,
                "heading": title,
                "heading_path": heading_path,
                "body": body,
                "char_len": len(body),
                "is_common": is_common,
            })
    return sections


def _document_outline(sections: list[dict[str, Any]]) -> str:
    """1 回目のやり取りで AI に渡すセクションアウトライン(テキスト)を作る。"""
    by_file: dict[str, list[dict[str, Any]]] = {}
    for s in sections:
        by_file.setdefault(s["file"], []).append(s)

    lines: list[str] = []
    for fname, secs in by_file.items():
        tag = " [共通ドキュメント]" if secs and secs[0]["is_common"] else ""
        lines.append(f"- {fname}{tag}")
        for s in secs:
            lines.append(f"    - {s['id']} | {s['heading_path']} ({s['char_len']}字)")
    return "\n".join(lines)


def _build_files_payload(files: list[dict[str, Any]]) -> str:
    """設計書ファイル群を AI へ渡す JSON 文字列に整形する(本文は上限で打ち切る)。"""
    payload_files = [
        {
            "name": f.get("name", ""),
            "content": (f.get("content") or "")[:MAX_CHARS_PER_FILE],
        }
        for f in files
    ]
    return json.dumps({"files": payload_files}, ensure_ascii=False)


# ----------------------------------------------------------------------
# 1 回目: 機能の洗い出し + 該当セクション特定
# ----------------------------------------------------------------------
def list_features(
    settings: Settings,
    files: list[dict[str, Any]],
    sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """1 回目のやり取り: 機能を洗い出し、機能ごとに該当セクションIDを特定する。

    Args
    -----------------
    - settings: Settings,     アプリ設定(Azure OpenAI の接続情報を含む)
    - files: list[dict],      設計書ファイル一覧(全文。"name", "content")
    - sections: list[dict],   split_sections() の結果

    Returns
    -----------------
    - features: list[dict],   機能一覧。各要素は "name"、"summary"、
                              "section_ids"(実在IDのみに検証済み)を持つ

    Raises
    -----------------
    - DesignFeatureAnalysisError: Azure OpenAI 未設定、AI 呼び出し失敗、
                                  または応答の解析に失敗した場合
    """
    # --- AI の接続情報が揃っているか確認する ---
    if not settings.ai_enabled:
        raise DesignFeatureAnalysisError(
            "Azure OpenAI が未設定です(.env の AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY を確認してください)"
        )

    # --- 設計書の全文とセクションアウトラインを渡して機能を列挙させる ---
    user_prompt = (
        "設計書ファイル(全文):\n"
        + _build_files_payload(files)
        + "\n\nセクションアウトライン(section_id | 見出し | 文字数):\n"
        + _document_outline(sections)
    )
    parsed = _call_chat(
        settings, LIST_FEATURES_SYSTEM_PROMPT, user_prompt, label="1回目:機能洗い出し"
    )

    raw_features = parsed.get("features", []) if isinstance(parsed, dict) else parsed
    known_ids = {s["id"] for s in sections}

    features: list[dict[str, Any]] = []
    for item in raw_features or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        summary = str(item.get("summary", "")).strip()
        if not name and not summary:
            continue
        # AI が返した section_ids のうち、アウトラインに実在するものだけ採用する
        raw_ids = item.get("section_ids") or []
        section_ids = [str(x) for x in raw_ids if str(x) in known_ids]
        features.append({
            "name": name or "(名称なし)",
            "summary": summary,
            "section_ids": section_ids,
        })
    return features


# ----------------------------------------------------------------------
# 2 回目のコンテキスト組み立て
# ----------------------------------------------------------------------
def _with_ancestors(
    by_id: dict[str, dict[str, Any]], sec: dict[str, Any]
) -> list[dict[str, Any]]:
    """あるセクションと、同一ファイル内のその親見出しセクション群を返す。"""
    result = [sec]
    parts = sec["heading_path"].split(" > ")
    if len(parts) > 1:
        prefixes = {" > ".join(parts[:k]) for k in range(1, len(parts))}
        for s in by_id.values():
            if s["file"] == sec["file"] and s["heading_path"] in prefixes:
                result.append(s)
    return result


def _render_sections(ordered: list[dict[str, Any]]) -> tuple[str, list[str]]:
    """セクション群を抜粋テキストに整形する(合計文字数の上限で打ち切る)。"""
    parts: list[str] = []
    used: list[str] = []
    total = 0
    for s in ordered:
        block = f"### {s['file']} — {s['heading_path']}\n{s['body']}\n"
        if parts and total + len(block) > MAX_CONTEXT_CHARS:
            parts.append("... (以降は文字数上限のため省略) ...")
            break
        parts.append(block)
        total += len(block)
        used.append(s["id"])
    return "\n".join(parts), used


def _assemble_context(
    sections: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    common_ids: list[str],
    requested_ids: list[str],
) -> tuple[str, str, list[str]]:
    """機能に紐づく 2 回目用の抜粋コンテキストを組み立てる。

    Returns
    -----------------
    - (context_text, mode, used_ids)
      mode: "narrowed"(絞り込み)/ "full"(全文フォールバック)
    """
    # 指定IDを実在セクション(+親見出し)へ解決する
    chosen: dict[str, dict[str, Any]] = {}
    for rid in requested_ids:
        s = by_id.get(rid)
        if not s:
            continue
        for a in _with_ancestors(by_id, s):
            chosen[a["id"]] = a

    selected_len = sum(s["char_len"] for s in chosen.values())

    # 抜粋が薄すぎる場合は安全側に倒して設計書全文で解析する
    if selected_len < FALLBACK_MIN_CHARS:
        mode = "full"
        chosen = dict(by_id)
    else:
        mode = "narrowed"

    # 共通ドキュメントのセクションは常に添付する
    for cid in common_ids:
        if cid in by_id:
            chosen.setdefault(cid, by_id[cid])

    # 元のセクション順に並べてテキスト化する
    ordered = [s for s in sections if s["id"] in chosen]
    text, used = _render_sections(ordered)
    return text, mode, used


def plan_analysis(
    settings: Settings, files: list[dict[str, Any]]
) -> dict[str, Any]:
    """1 回目のやり取りを行い、機能ごとの 2 回目用コンテキストまで組み立てる。

    Args
    -----------------
    - settings: Settings,   アプリ設定(Azure OpenAI の接続情報を含む)
    - files: list[dict],    分析対象の設計書ファイル一覧("name", "content")

    Returns
    -----------------
    - plan: dict,  次のキーを持つ:
      "sections_total": セクション総数
      "common_section_ids": 共通ドキュメントのセクションID一覧
      "features": 機能ごとの解析計画一覧。各要素は
        "name"、"summary"、"context"(2 回目に渡す抜粋)、
        "context_mode"("narrowed" / "full")、"context_char_len"、
        "selected_section_ids"、"refs"(トレーサビリティ用の参照先セクション)を持つ

    Raises
    -----------------
    - DesignFeatureAnalysisError: 1 回目のやり取りに失敗した場合
    """
    # 設計書をセクションへ分割し、共通ドキュメントを特定する
    sections = split_sections(files)
    by_id = {s["id"]: s for s in sections}
    common_ids = [s["id"] for s in sections if s["is_common"]]

    # 1 回目: 機能の洗い出し + 該当セクション特定
    features = list_features(settings, files, sections)

    # 機能ごとに 2 回目用の抜粋コンテキストを組み立てる
    planned: list[dict[str, Any]] = []
    for f in features:
        context, mode, used_ids = _assemble_context(
            sections, by_id, common_ids, f.get("section_ids") or []
        )
        # トレーサビリティ: 1 回目で「この機能に関係する」と特定されたセクション
        refs = []
        for sid in f.get("section_ids") or []:
            s = by_id.get(sid)
            if s:
                refs.append({
                    "ref_kind": "design_section",
                    "file_path": s["file"],
                    "locator": s["id"],
                    "heading": s["heading_path"],
                })
        planned.append({
            "name": f["name"],
            "summary": f["summary"],
            "context": context,
            "context_mode": mode,
            "context_char_len": len(context),
            "selected_section_ids": used_ids,
            "refs": refs,
        })

    return {
        "sections_total": len(sections),
        "common_section_ids": common_ids,
        "features": planned,
    }


# ----------------------------------------------------------------------
# 2 回目: 機能ごとの詳細仕様の書き起こし
# ----------------------------------------------------------------------
def analyze_feature_detail(
    settings: Settings, feature: dict[str, Any]
) -> dict[str, Any]:
    """2 回目のやり取り: 1 つの機能について抜粋から詳細仕様を書き起こす。

    機能ごとに独立して呼び出せるため、呼び出し側で並列実行する。

    Args
    -----------------
    - settings: Settings,   アプリ設定(Azure OpenAI の接続情報を含む)
    - feature: dict,        plan_analysis() が返す機能の計画
                            (``name`` / ``summary`` / ``context`` を使用)

    Returns
    -----------------
    - detail: dict,   画面表示用の詳細仕様。
                      "name"(機能の名称)、"overview"(概要)、
                      "sections"(``heading`` / ``body`` の配列)を持つ

    Raises
    -----------------
    - DesignFeatureAnalysisError: Azure OpenAI 未設定、AI 呼び出し失敗、
                                  または応答の解析に失敗した場合
    """
    # --- AI の接続情報が揃っているか確認する ---
    if not settings.ai_enabled:
        raise DesignFeatureAnalysisError(
            "Azure OpenAI が未設定です(.env の AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY を確認してください)"
        )

    name = str(feature.get("name", "")).strip()
    summary = str(feature.get("summary", "")).strip()
    context = feature.get("context", "") or ""

    # --- 対象機能を指定しつつ、絞り込んだ抜粋を渡して詳細仕様を書き起こさせる ---
    user_prompt = (
        "対象機能:\n"
        f"- 名称: {name or '(名称なし)'}\n"
        f"- 概要: {summary or '(概要なし)'}\n\n"
        "設計書の抜粋:\n" + context
    )
    parsed = _call_chat(
        settings, FEATURE_DETAIL_SYSTEM_PROMPT, user_prompt, label=f"2回目:{name or '?'}"
    )
    if not isinstance(parsed, dict):
        raise DesignFeatureAnalysisError("AI 応答の形式が想定と異なります")

    # --- sections を画面表示用に整形する ---
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
        "name": str(parsed.get("name", "")).strip() or name or "(名称なし)",
        "overview": str(parsed.get("overview", "")).strip() or summary,
        "sections": sections,
    }
