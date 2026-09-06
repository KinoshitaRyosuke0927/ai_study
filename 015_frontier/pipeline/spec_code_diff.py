"""実装差分解析: 設計書分析の結果とコード分析の結果を機能ごとに突き合わせ、
相違点を抽出する。

手順:
1. _pair_features(): 設計書側の機能とコード側の機能を、名前・概要をもとに AI で対応付ける。
   対応が付かないものは design_only(設計書にあるが実装が見当たらない)/
   code_only(実装はあるが設計書に見当たらない)とする。
2. _diff_pair(): 対応が付いた各ペアについて、設計書から読み取った仕様とコードから
   読み取った仕様を AI で比較し、相違点だけを列挙する(機能ごとに並列実行する)。

AI クライアントは design_features / code_features と同じ OpenAI 互換エンドポイント。
結果は analysis_store.save_diff() で DB へ保存する。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI

from config.settings import Settings

logger = logging.getLogger(__name__)

MODEL_NAME = "gpt-5.4-mini"

# 1 ペアの比較で AI へ渡す、片側の詳細セクション本文の合計上限
MAX_SIDE_CHARS = 8000

PAIRING_SYSTEM_PROMPT = """\
設計書から抽出した機能の一覧と、ソースコードから抽出した機能の一覧が与えられます。
同じ機能を指すものどうしを対応付けてください。

ルール:
- 名前の表記が違っても、概要から見て同じ機能なら対応付けてください。
- 対応は 1 対 1 です(1 つの設計機能に複数のコード機能をまとめない)。
- どちらにも対応が見つからないものは design_only / code_only に入れてください。
- 名前は与えられた一覧の値をそのまま使ってください(創作しない)。
- 前置きや説明は付けず、次の形式の JSON オブジェクトのみを出力してください:
  {"pairs": [{"design": "<設計側の機能名>", "code": "<コード側の機能名>"}],
   "design_only": ["<設計側の機能名>"], "code_only": ["<コード側の機能名>"]}
"""

DIFF_SYSTEM_PROMPT = """\
1 つの機能について、設計書から読み取った仕様(design)と、ソースコードから読み取った
仕様(code)が与えられます。両者の「相違点」だけを日本語で列挙してください。

ルール:
- 一致している点は挙げないでください。相違が無ければ differences は空配列にします。
- 相違とは、片方にあって片方に無い仕様、値・条件・処理内容の食い違い、などです。
- 各相違について次を記載してください:
  - severity: high / mid / low(利用者影響やデータ不整合の大きさ)
  - summary: 相違点を 1 文で
  - design_state: 設計書ではどうなっているか(記載が無ければ「設計書に記載なし」)
  - code_state: コードではどうなっているか(該当が無ければ「コードに実装なし」)
- 与えられた内容だけを根拠にし、推測で相違を作らないでください。
- 前置きや説明は付けず、次の形式の JSON オブジェクトのみを出力してください:
  {"differences": [{"severity": "...", "summary": "...",
                    "design_state": "...", "code_state": "..."}]}
"""


class SpecCodeDiffError(Exception):
    """Azure OpenAI 未設定、または AI 応答を解析できなかった場合。"""


# ----------------------------------------------------------------------
# AI 呼び出し
# ----------------------------------------------------------------------
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
        logger.error("実装差分解析の AI 呼び出しに失敗 [%s]: %s", label or "-", exc)
        raise SpecCodeDiffError(f"AI 呼び出しに失敗しました: {exc}") from exc

    usage = getattr(response, "usage", None)
    if usage is not None:
        logger.info(
            "実装差分解析 AI トークン [%s] prompt=%s completion=%s total=%s",
            label or "-",
            getattr(usage, "prompt_tokens", "?"),
            getattr(usage, "completion_tokens", "?"),
            getattr(usage, "total_tokens", "?"),
        )

    raw = _strip_code_fence(response.choices[0].message.content or "")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("実装差分解析 応答の JSON 解析に失敗 [%s]: %s / raw=%s", label or "-", exc, raw[:500])
        raise SpecCodeDiffError("AI 応答を解析できませんでした") from exc


# ----------------------------------------------------------------------
# 機能テキストの整形
# ----------------------------------------------------------------------
def _feature_brief(feat: dict[str, Any]) -> dict[str, str]:
    """対応付け用の軽量表現(名前 + 概要)。"""
    return {
        "name": str(feat.get("name", "")).strip(),
        "overview": str(feat.get("overview", "")).strip(),
    }


def _feature_spec_text(feat: dict[str, Any]) -> str:
    """比較用に、機能の概要 + 詳細セクションをテキスト化する(上限で打ち切り)。"""
    parts: list[str] = []
    ov = str(feat.get("overview", "")).strip()
    if ov:
        parts.append("概要: " + ov)
    total = 0
    for sec in feat.get("sections") or []:
        heading = str(sec.get("heading", "")).strip()
        body = str(sec.get("body", "")).strip()
        block = f"【{heading}】\n{body}"
        if parts and total + len(block) > MAX_SIDE_CHARS:
            parts.append("...(以降は文字数上限のため省略)...")
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts) if parts else "(記載なし)"


# ----------------------------------------------------------------------
# 1. 機能の対応付け
# ----------------------------------------------------------------------
def _pair_features(
    settings: Settings,
    design_features: list[dict[str, Any]],
    code_features: list[dict[str, Any]],
) -> dict[str, Any]:
    """設計側 / コード側の機能を対応付ける。

    Returns
    -----------------
    - {"pairs": [(design_feat, code_feat)], "design_only": [design_feat], "code_only": [code_feat]}
    """
    d_by_name = {f["name"].strip(): f for f in design_features if f.get("name")}
    c_by_name = {f["name"].strip(): f for f in code_features if f.get("name")}

    payload = {
        "design_features": [_feature_brief(f) for f in design_features],
        "code_features": [_feature_brief(f) for f in code_features],
    }
    parsed = _call_chat(
        settings,
        PAIRING_SYSTEM_PROMPT,
        json.dumps(payload, ensure_ascii=False),
        label="対応付け",
    )

    used_d: set[str] = set()
    used_c: set[str] = set()
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for p in (parsed.get("pairs") or []) if isinstance(parsed, dict) else []:
        if not isinstance(p, dict):
            continue
        dn = str(p.get("design", "")).strip()
        cn = str(p.get("code", "")).strip()
        d = d_by_name.get(dn)
        c = c_by_name.get(cn)
        if d and c and dn not in used_d and cn not in used_c:
            pairs.append((d, c))
            used_d.add(dn)
            used_c.add(cn)

    # AI の design_only/code_only は参考程度に扱い、最終的には「ペアに含まれなかったもの」で確定する
    design_only = [f for n, f in d_by_name.items() if n not in used_d]
    code_only = [f for n, f in c_by_name.items() if n not in used_c]
    return {"pairs": pairs, "design_only": design_only, "code_only": code_only}


# ----------------------------------------------------------------------
# 2. ペアごとの相違点抽出
# ----------------------------------------------------------------------
def _evidence(design_feat: dict[str, Any] | None, code_feat: dict[str, Any] | None) -> dict[str, Any]:
    """相違点に添えるトレーサビリティ(設計書セクション / コードシンボル)。"""
    return {
        "design": (design_feat or {}).get("refs", []) or [],
        "code": (code_feat or {}).get("refs", []) or [],
    }


def diff_pair(
    settings: Settings, design_feat: dict[str, Any], code_feat: dict[str, Any]
) -> list[dict[str, Any]]:
    """対応が付いた 1 ペアを比較し、相違点(0 件以上)を返す。"""
    if not settings.ai_enabled:
        raise SpecCodeDiffError(
            "Azure OpenAI が未設定です(.env の AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY を確認してください)"
        )

    name = str(design_feat.get("name", "")).strip() or str(code_feat.get("name", "")).strip()
    user_prompt = (
        f"機能名: {name}\n\n"
        "=== design(設計書から読み取った仕様)===\n"
        + _feature_spec_text(design_feat)
        + "\n\n=== code(コードから読み取った仕様)===\n"
        + _feature_spec_text(code_feat)
    )
    parsed = _call_chat(settings, DIFF_SYSTEM_PROMPT, user_prompt, label=f"比較:{name or '?'}")

    items: list[dict[str, Any]] = []
    raw = parsed.get("differences", []) if isinstance(parsed, dict) else []
    for d in raw or []:
        if not isinstance(d, dict):
            continue
        summary = str(d.get("summary", "")).strip()
        if not summary:
            continue
        sev = str(d.get("severity", "")).strip().lower()
        if sev not in ("high", "mid", "low"):
            sev = "mid"
        items.append({
            "feature_name": name,
            "verdict": "conflict",
            "severity": sev,
            "summary": summary,
            "design_state": str(d.get("design_state", "")).strip() or None,
            "code_state": str(d.get("code_state", "")).strip() or None,
            "design_feature_id": design_feat.get("id"),
            "code_feature_id": code_feat.get("id"),
            "evidence": _evidence(design_feat, code_feat),
        })
    return items


def unmatched_item(feat: dict[str, Any], verdict: str) -> dict[str, Any]:
    """design_only / code_only の 1 件を、相違点アイテムへ変換する。"""
    name = str(feat.get("name", "")).strip()
    overview = str(feat.get("overview", "")).strip()
    if verdict == "design_only":
        summary = f"設計書に定義があるが、対応する実装が見当たらない: {name}"
        design_state = overview or "(概要なし)"
        code_state = "コードに実装なし"
        design_feature_id, code_feature_id = feat.get("id"), None
        evidence = _evidence(feat, None)
    else:  # code_only
        summary = f"実装は存在するが、設計書に対応する記載が見当たらない: {name}"
        design_state = "設計書に記載なし"
        code_state = overview or "(概要なし)"
        design_feature_id, code_feature_id = None, feat.get("id")
        evidence = _evidence(None, feat)
    return {
        "feature_name": name,
        "verdict": verdict,
        "severity": "mid",
        "summary": summary,
        "design_state": design_state,
        "code_state": code_state,
        "design_feature_id": design_feature_id,
        "code_feature_id": code_feature_id,
        "evidence": evidence,
    }


def prepare_pairs(
    settings: Settings, design_run: dict[str, Any], code_run: dict[str, Any]
) -> dict[str, Any]:
    """対応付けまで行い、比較対象のペアと未対応機能を返す(2 段目の並列呼び出しは呼び出し側)。"""
    if not settings.ai_enabled:
        raise SpecCodeDiffError(
            "Azure OpenAI が未設定です(.env の AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY を確認してください)"
        )
    design_features = design_run.get("features") or []
    code_features = code_run.get("features") or []
    return _pair_features(settings, design_features, code_features)
