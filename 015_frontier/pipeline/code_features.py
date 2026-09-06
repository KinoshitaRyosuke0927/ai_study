"""「コード情報取得」画面の「機能分析」用モジュール。

設計書版(pipeline/design_features.py)と同じく AI とのやり取りを 2 段階に分ける。

1. plan_analysis() / list_features():
   リポジトリ全体から作った「コードアウトライン」(ファイルパス + 関数/クラス/
   ルートなどのシンボル一覧)を AI に渡し、アプリの機能を洗い出す。あわせて、各機能の
   実装が含まれるファイルパスを AI に特定させる。
2. analyze_feature_detail():
   機能ごとに、特定されたファイル + コアファイル(entrypoint / models / config)の
   本文だけを AI に渡し、詳細な分析結果を組み立てる。抜粋が薄すぎる機能は、
   コアセット(entrypoint 群)へフォールバックする。
   機能ごとの呼び出しは呼び出し側(app.py)で並列に実行する。

AI クライアントは 010_ai_reviewer / 011_chat_linkage と同じく、OpenAI 互換
エンドポイント(``.../openai/v1``)へ ``OpenAI`` クライアントで接続する。
画面表示用であり、結果は DB へは保存しない。
"""

from __future__ import annotations

import ast
import json
import logging
import re
from typing import Any

from openai import OpenAI

from config.settings import Settings

logger = logging.getLogger(__name__)

# デプロイしたモデルの名称(010_ai_reviewer / 011_chat_linkage と合わせる)
MODEL_NAME = "gpt-5.4-mini"

# 1 回目のアウトライン: 1 ファイルあたりのシンボル数の上限 / アウトライン全体の文字数上限
MAX_SYMBOLS_PER_FILE = 40
MAX_OUTLINE_CHARS = 20000
# 2 回目: 抜粋コンテキスト全体の文字数上限
MAX_CONTEXT_CHARS = 28000
# 2 回目: 関数/クラス 1 定義あたりのソースの上限(巨大な定義の保険)
MAX_SYMBOL_SOURCE_CHARS = 8000
# 2 回目: シンボルを特定できなかったファイルの先頭抜粋の上限
MAX_FILE_HEAD_CHARS = 4000
# 2 回目: コアファイル / フォールバック時に 1 ファイル丸ごと渡すときの上限
MAX_FILE_CONTENT_CHARS = 8000
# 機能に紐づく抜粋の合計がこの文字数未満なら、コアセットへフォールバックする
FALLBACK_MIN_CHARS = 2000

# コアファイル(全機能の 2 回目リクエストに常に添付)の判定
CORE_FILE_RE = re.compile(
    r"(^|/)(main|app|asgi|wsgi|settings|config|conf|models?|schema|database|db|urls|routes?|deps|dependencies)\.[A-Za-z0-9]+$",
    re.IGNORECASE,
)
# entrypoint らしさ(HTTP ルート定義・__main__・ルータ生成など)の判定
ENTRYPOINT_RE = re.compile(
    r"@\w+\.(get|post|put|delete|patch|route|websocket)\(|"
    r"if\s+__name__\s*==\s*['\"]__main__['\"]|"
    r"add_url_rule|APIRouter\(|FastAPI\(|Flask\(|createRouter\(|express\(\)",
    re.IGNORECASE,
)

# 非 Python ファイル用の簡易シンボル抽出パターン
_JS_FUNC_RE = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([A-Za-z0-9_$]+)", re.MULTILINE)
_JS_CLASS_RE = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?class\s+([A-Za-z0-9_$]+)", re.MULTILINE)
_JS_CONST_FN_RE = re.compile(r"^\s*(?:export\s+)?const\s+([A-Za-z0-9_$]+)\s*=\s*(?:async\s*)?\(", re.MULTILINE)
_GENERIC_DEF_RE = re.compile(r"^\s*(?:public|private|protected|static|\s)*(?:func|fun|def|sub)\s+([A-Za-z0-9_]+)", re.MULTILINE)
_ROUTE_STR_RE = re.compile(r"\.(get|post|put|delete|patch|route|use)\(\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)

# --- 1 回目: 機能の洗い出し + 該当ファイル/定義特定用システムプロンプト ---
LIST_FEATURES_SYSTEM_PROMPT = """\
あなたはアプリケーションのソースコードを読み、利用者・運用者から見た「機能」を
洗い出すアシスタントです。与えられたコードアウトライン(ファイル一覧と、その中の
関数・クラス・HTTP ルートなどのシンボル)だけを根拠に、このアプリケーションに
どのような機能があるかを日本語で列挙し、各機能の実装が含まれるファイルと、
その中の関数・クラス(シンボル)を指し示してください。

出力ルール:
- HTTP エンドポイント、画面、CLI コマンド、定期実行ジョブ、外部システム連携など、
  利用者・運用者から見て意味のある単位でまとめてください。
- ロギングや設定読み込みのような共通基盤そのものは機能として挙げないでください
  (ある機能の実装として共通基盤の関数を挙げるのは構いません)。
- file_paths には、その機能に関係するファイルのパスを列挙してください。
- symbols には、その機能の中心的な実装である関数・クラスを "<パス>::<名前>" の形式で
  列挙してください(例: "app/main.py::create_user")。アウトラインに載っている名前だけを
  使い、創作しないでください。分かる範囲で構いませんが、できるだけ具体的に挙げてください。
- パス・名前はアウトラインに実在するものだけを使ってください。
- 前置き・説明・コードブロックは付けず、次の形式の JSON オブジェクトのみを出力してください:
  {"features": [{"name": "...", "summary": "...",
                 "file_paths": ["app/main.py"],
                 "symbols": ["app/main.py::create_user", "app/schemas.py::UserIn"]}]}
"""

# --- 2 回目: 機能ごとの詳細分析用システムプロンプト ---
FEATURE_DETAIL_SYSTEM_PROMPT = """\
あなたはソースコードを読み、指定された 1 つの機能の詳細仕様を書き起こすアシスタントです。
与えられたコード抜粋の内容だけを根拠に、日本語で整理してください。

抜粋は、対象機能に関係する関数・クラスの全文と、それらが属するファイルの
「定義一覧」(名前と行範囲のみ)で構成されます。定義一覧にあってソースが無いものは
本分析の対象外というだけで、実装が存在しないわけではありません。

出力ルール:
- 抜粋に書かれていない内容を推測で補ったり、創作したりしないでください。
  抜粋から読み取れない観点は省略して構いません。
- 対象機能に関係する実装を抜粋から読み取り、次のような観点でまとめてください:
  目的・概要、起動方法/トリガー(HTTP メソッドとパス、画面、スケジュール、CLI など)、
  入力(リクエスト/パラメータ/フォーム)と出力(レスポンス/画面/生成物)、
  主な処理フロー(手順)、依存(参照する DB テーブル、呼び出す外部 API、利用する他モジュール)、
  バリデーション・制約・エラー時の挙動。該当する観点のみで構いません。
- sections は見出し(heading)と本文(body)の配列です。body は箇条書きを含む
  プレーンテキストで記述してください(Markdown 記法は使わない)。
- 前置き・説明・コードブロックは付けず、次の形式の JSON オブジェクトのみを出力してください:
  {"name": "...", "overview": "...", "sections": [{"heading": "...", "body": "..."}]}
"""


class CodeAnalysisError(Exception):
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
    - settings: Settings,   アプリ設定(Azure OpenAI の接続情報を含む)
    - system_prompt: str,   システムプロンプト
    - user_prompt: str,     ユーザープロンプト
    - label: str,           ログ出力用のラベル(どのやり取りかを識別)

    Returns
    -----------------
    - parsed: Any,          AI 応答を JSON として解析した結果

    Raises
    -----------------
    - CodeAnalysisError: AI 呼び出し失敗、または JSON 解析に失敗した場合
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
        logger.error("コード分析の AI 呼び出しに失敗 [%s]: %s", label or "-", exc)
        raise CodeAnalysisError(f"AI 呼び出しに失敗しました: {exc}") from exc

    # トークン使用量を記録する(2 回目の情報量削減効果を測るため)
    usage = getattr(response, "usage", None)
    if usage is not None:
        logger.info(
            "コード分析 AI トークン [%s] prompt=%s completion=%s total=%s",
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
            "コード分析 応答の JSON 解析に失敗 [%s]: %s / raw=%s", label or "-", exc, raw[:500]
        )
        raise CodeAnalysisError("AI 応答を解析できませんでした") from exc


# ----------------------------------------------------------------------
# コードアウトラインの作成
# ----------------------------------------------------------------------
def _py_decorator_label(dec: ast.expr) -> str:
    """Python のデコレータ AST を "@..." のラベル文字列にする。"""
    try:
        return "@" + ast.unparse(dec)
    except Exception:  # ast.unparse 非対応など
        if isinstance(dec, ast.Call):
            dec = dec.func
        if isinstance(dec, ast.Attribute):
            return "@" + dec.attr
        if isinstance(dec, ast.Name):
            return "@" + dec.id
        return "@decorator"


def _python_source_symbols(content: str, lines: list[str]) -> list[dict[str, Any]]:
    """Python ソースからトップレベルの関数・クラスを、行範囲・全文つきで抽出する。"""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return _generic_source_symbols(content, lines)

    out: list[dict[str, Any]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            deco_lines = [getattr(d, "lineno", node.lineno) for d in node.decorator_list]
            start = min([node.lineno] + deco_lines)
            end = getattr(node, "end_lineno", None) or node.lineno
            if isinstance(node, ast.ClassDef):
                label = f"class {node.name}"
                kind = "class"
            else:
                decos = " ".join(_py_decorator_label(d) for d in node.decorator_list)
                label = f"{decos} def {node.name}".strip()
                kind = "func"
            out.append({
                "name": node.name,
                "kind": kind,
                "label": label,
                "start": start,
                "end": end,
                "source": "\n".join(lines[start - 1:end]),
            })
    return out


def _generic_source_symbols(content: str, lines: list[str]) -> list[dict[str, Any]]:
    """非 Python ソースから、正規表現で関数・クラスを抽出する(行範囲は近似)。"""
    marks: list[tuple[int, str, str]] = []
    for m in _JS_CLASS_RE.finditer(content):
        marks.append((content[:m.start()].count("\n"), m.group(1), f"class {m.group(1)}"))
    for rx in (_JS_FUNC_RE, _JS_CONST_FN_RE, _GENERIC_DEF_RE):
        for m in rx.finditer(content):
            marks.append((content[:m.start()].count("\n"), m.group(1), f"def {m.group(1)}"))
    marks.sort()

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, (ln, name, label) in enumerate(marks):
        if name in seen:
            continue
        seen.add(name)
        # 次の定義の開始 / +150 行 / ファイル末尾 のうち最小を終端とみなす
        nxt = marks[i + 1][0] if i + 1 < len(marks) else len(lines)
        end = min(nxt, ln + 150, len(lines))
        out.append({
            "name": name,
            "kind": "def",
            "label": label,
            "start": ln + 1,
            "end": end,
            "source": "\n".join(lines[ln:end]),
        })
    return out


def _extract_source_symbols(path: str, content: str, lines: list[str]) -> list[dict[str, Any]]:
    """ファイルの拡張子に応じて、行範囲・全文つきのシンボル一覧を抽出する。"""
    if path.endswith(".py"):
        return _python_source_symbols(content, lines)
    return _generic_source_symbols(content, lines)


def _scan_code(
    files: list[dict[str, Any]]
) -> tuple[str, dict[str, dict[str, Any]]]:
    """コードアウトライン(テキスト)と、シンボル索引を作る。

    Returns
    -----------------
    - outline: str,  "- <path> (<行数>行): sym1, sym2, ..." を並べたテキスト
    - index: dict,   "<path>::<名前>" -> {"file","name","kind","label","start","end","source"}
    """
    outline_lines: list[str] = []
    index: dict[str, dict[str, Any]] = {}
    total = 0
    for f in files:
        path = f.get("name", "")
        content = f.get("content") or ""
        lines = content.splitlines()
        loc = len(lines)

        labels: list[str] = []
        # Python はモジュール docstring 冒頭行もアウトラインに出す(索引には入れない)
        if path.endswith(".py"):
            try:
                doc = ast.get_docstring(ast.parse(content))
            except SyntaxError:
                doc = None
            if doc:
                labels.append("# " + doc.splitlines()[0].strip())

        for s in _extract_source_symbols(path, content, lines)[:MAX_SYMBOLS_PER_FILE]:
            key = f"{path}::{s['name']}"
            index.setdefault(key, {**s, "file": path})
            labels.append(s["label"])

        entry = f"- {path} ({loc}行)"
        if labels:
            entry += ": " + ", ".join(labels)
        if outline_lines and total + len(entry) > MAX_OUTLINE_CHARS:
            outline_lines.append("... (以降は文字数上限のため省略) ...")
            break
        outline_lines.append(entry)
        total += len(entry)
    return "\n".join(outline_lines), index


def build_code_outline(files: list[dict[str, Any]]) -> str:
    """1 回目のやり取りで AI に渡すコードアウトライン(テキスト)を作る。"""
    return _scan_code(files)[0]


# ----------------------------------------------------------------------
# 1 回目: 機能の洗い出し + 該当ファイル特定
# ----------------------------------------------------------------------
def _normalize_path(p: str) -> str:
    """AI が返したパスの表記ゆれ(先頭 ./ や /)をならす。"""
    return str(p).strip().lstrip("./").lstrip("/")


def _resolve_path(raw: str, known_paths: set[str]) -> str | None:
    """AI が返したパスを、実在するファイルパスへ解決する(末尾一致まで許容)。"""
    p = _normalize_path(raw)
    if p in known_paths:
        return p
    # 末尾一致(例: "main.py" -> "app/main.py")。曖昧な場合は採用しない
    cands = [k for k in known_paths if k == p or k.endswith("/" + p)]
    return cands[0] if len(cands) == 1 else None


def _resolve_symbol(raw: str, index_keys: set[str]) -> str | None:
    """AI が返した "<パス>::<名前>" を、実在するシンボル索引キーへ解決する。"""
    r = str(raw).strip()
    if "::" not in r:
        return None
    path_part, _, name = r.partition("::")
    key = f"{_normalize_path(path_part)}::{name}"
    if key in index_keys:
        return key
    # パス表記がずれている場合、名前の末尾一致が一意ならそれを採用する
    cands = [k for k in index_keys if k.rsplit("::", 1)[-1] == name]
    return cands[0] if len(cands) == 1 else None


def list_features(
    settings: Settings,
    files: list[dict[str, Any]],
    outline: str,
    symbol_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """1 回目のやり取り: 機能を洗い出し、機能ごとに該当ファイル・シンボルを特定する。

    Args
    -----------------
    - settings: Settings,        アプリ設定(Azure OpenAI の接続情報を含む)
    - files: list[dict],         ソースファイル一覧("name", "content")
    - outline: str,              _scan_code() のアウトライン
    - symbol_index: dict,        _scan_code() のシンボル索引(キーの検証に使う)

    Returns
    -----------------
    - features: list[dict],  各要素は "name"、"summary"、
                             "file_paths"(実在パスのみ)、
                             "symbols"(実在する索引キーのみ)を持つ

    Raises
    -----------------
    - CodeAnalysisError: Azure OpenAI 未設定、AI 呼び出し失敗、応答解析失敗
    """
    if not settings.ai_enabled:
        raise CodeAnalysisError(
            "Azure OpenAI が未設定です(.env の AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY を確認してください)"
        )

    user_prompt = "コードアウトライン(パス | 行数 | シンボル):\n" + outline
    parsed = _call_chat(
        settings, LIST_FEATURES_SYSTEM_PROMPT, user_prompt, label="1回目:機能洗い出し"
    )

    raw_features = parsed.get("features", []) if isinstance(parsed, dict) else parsed
    known_paths = {f.get("name", "") for f in files}
    index_keys = set(symbol_index)

    features: list[dict[str, Any]] = []
    for item in raw_features or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        summary = str(item.get("summary", "")).strip()
        if not name and not summary:
            continue

        file_paths: list[str] = []
        for raw in item.get("file_paths") or []:
            hit = _resolve_path(raw, known_paths)
            if hit and hit not in file_paths:
                file_paths.append(hit)

        symbols: list[str] = []
        for raw in item.get("symbols") or []:
            hit = _resolve_symbol(raw, index_keys)
            if hit and hit not in symbols:
                symbols.append(hit)
        # シンボルの属するファイルは file_paths にも含めておく
        for key in symbols:
            fp = symbol_index[key]["file"]
            if fp not in file_paths:
                file_paths.append(fp)

        features.append({
            "name": name or "(名称なし)",
            "summary": summary,
            "file_paths": file_paths,
            "symbols": symbols,
        })
    return features


# ----------------------------------------------------------------------
# 2 回目のコンテキスト組み立て
# ----------------------------------------------------------------------
def _is_core_file(path: str) -> bool:
    """全機能に常に添付する「コアファイル」かどうか。"""
    return bool(CORE_FILE_RE.search(path)) or path.lower().endswith("schema.sql")


def _looks_entrypoint(content: str) -> bool:
    """HTTP ルート定義や __main__ を含む entrypoint らしいファイルか。"""
    return bool(ENTRYPOINT_RE.search(content or ""))


def _render_files(
    ordered: list[str], by_path: dict[str, str]
) -> tuple[str, list[str]]:
    """ファイル群を丸ごと抜粋テキストに整形する(合計文字数の上限で打ち切る)。"""
    parts: list[str] = []
    used: list[str] = []
    total = 0
    for p in ordered:
        body = (by_path.get(p) or "")[:MAX_FILE_CONTENT_CHARS]
        block = f"### {p}\n```\n{body}\n```\n"
        if parts and total + len(block) > MAX_CONTEXT_CHARS:
            parts.append("... (以降は文字数上限のため省略) ...")
            break
        parts.append(block)
        total += len(block)
        used.append(p)
    return "\n".join(parts), used


def _file_skeleton(path: str, symbol_index: dict[str, dict[str, Any]]) -> str:
    """ファイル内の全定義の一覧(ラベルと行範囲)を返す。"""
    rows = [
        f"  - {v['label']} (L{v['start']}-{v['end']})"
        for v in symbol_index.values()
        if v["file"] == path
    ]
    return "\n".join(rows)


def _assemble_context(
    by_path: dict[str, str],
    symbol_index: dict[str, dict[str, Any]],
    selected_paths: list[str],
    selected_symbols: list[str],
    core_paths: list[str],
    entrypoint_paths: list[str],
) -> tuple[str, str, list[str], list[str]]:
    """機能に紐づく 2 回目用の抜粋コンテキストを組み立てる(関数/クラス単位で抜粋)。

    Returns
    -----------------
    - (context_text, mode, used_paths, used_symbols)
      mode: "narrowed"(定義単位で絞り込み)/ "fallback"(entrypoint 群へフォールバック)
    """
    # 指定シンボルを索引から解決し、ファイルごとにまとめる
    resolved = [symbol_index[k] for k in selected_symbols if k in symbol_index]
    syms_by_file: dict[str, list[dict[str, Any]]] = {}
    for s in resolved:
        syms_by_file.setdefault(s["file"], []).append(s)

    sym_chars = sum(min(len(s["source"]), MAX_SYMBOL_SOURCE_CHARS) for s in resolved)
    # シンボルを特定できなかった選択ファイルは「先頭抜粋」で補う
    head_files = [
        p for p in selected_paths if p in by_path and p not in syms_by_file
    ]
    head_chars = sum(min(len(by_path[p]), MAX_FILE_HEAD_CHARS) for p in head_files)

    # 抜粋が薄すぎる場合は entrypoint 群 + コアへフォールバック(全リポジトリは送らない)
    if sym_chars + head_chars < FALLBACK_MIN_CHARS:
        ordered = list(dict.fromkeys(entrypoint_paths + core_paths))
        text, used = _render_files(ordered, by_path)
        return text, "fallback", used, []

    # (path, symbol_keys, block_text) を組み立てる
    entries: list[tuple[str, list[str], str]] = []

    # 1) 選択された関数/クラスを、ファイル内の定義一覧(スケルトン)付きで全文
    for path, syms in syms_by_file.items():
        parts = [f"### {path}(関連する定義)"]
        skel = _file_skeleton(path, symbol_index)
        if skel:
            parts.append("ファイル内の定義一覧:\n" + skel)
        keys: list[str] = []
        for s in syms:
            src = s["source"]
            if len(src) > MAX_SYMBOL_SOURCE_CHARS:
                src = src[:MAX_SYMBOL_SOURCE_CHARS] + "\n# ... (この定義は長いため以降省略) ..."
            parts.append(f"# L{s['start']}-{s['end']}  {s['label']}\n```\n{src}\n```")
            keys.append(f"{path}::{s['name']}")
        entries.append((path, keys, "\n\n".join(parts)))

    # 2) シンボル未特定の選択ファイルは先頭抜粋
    for p in head_files:
        body = by_path[p][:MAX_FILE_HEAD_CHARS]
        entries.append((p, [], f"### {p}(先頭抜粋)\n```\n{body}\n```"))

    # 3) コアファイルを丸ごと(まだ入っていないもの)
    for p in core_paths:
        if p in syms_by_file or p in head_files or p not in by_path:
            continue
        body = by_path[p][:MAX_FILE_CONTENT_CHARS]
        entries.append((p, [], f"### {p}(コアファイル)\n```\n{body}\n```"))

    # 合計文字数の上限で打ち切りつつ結合する
    out: list[str] = []
    used_paths: list[str] = []
    used_syms: list[str] = []
    total = 0
    for path, keys, block in entries:
        if out and total + len(block) > MAX_CONTEXT_CHARS:
            out.append("... (以降は文字数上限のため省略) ...")
            break
        out.append(block)
        total += len(block)
        used_paths.append(path)
        used_syms.extend(keys)
    return "\n\n".join(out), "narrowed", used_paths, used_syms


def plan_analysis(settings: Settings, files: list[dict[str, Any]]) -> dict[str, Any]:
    """1 回目のやり取りを行い、機能ごとの 2 回目用コンテキストまで組み立てる。

    Args
    -----------------
    - settings: Settings,  アプリ設定(Azure OpenAI の接続情報を含む)
    - files: list[dict],   分析対象のソースファイル一覧("name", "content")

    Returns
    -----------------
    - plan: dict,  次のキーを持つ:
      "file_count": 対象ファイル数
      "symbol_count": シンボル索引の件数
      "core_paths": コアファイルのパス一覧
      "features": 機能ごとの解析計画一覧。各要素は
        "name"、"summary"、"context"、"context_mode"("narrowed" / "fallback")、
        "context_char_len"、"selected_paths"、"selected_symbols" を持つ

    Raises
    -----------------
    - CodeAnalysisError: 1 回目のやり取りに失敗した場合
    """
    by_path = {f.get("name", ""): (f.get("content") or "") for f in files}
    core_paths = [p for p in by_path if _is_core_file(p)]
    entrypoint_paths = [p for p, c in by_path.items() if _looks_entrypoint(c)]

    outline, symbol_index = _scan_code(files)
    features = list_features(settings, files, outline, symbol_index)

    planned: list[dict[str, Any]] = []
    for f in features:
        context, mode, used_paths, used_syms = _assemble_context(
            by_path,
            symbol_index,
            f.get("file_paths") or [],
            f.get("symbols") or [],
            core_paths,
            entrypoint_paths,
        )
        # トレーサビリティ: 1 回目で特定された関数/クラス(と、シンボル無しの参照ファイル)
        refs: list[dict[str, Any]] = []
        ref_files: set[str] = set()
        for key in f.get("symbols") or []:
            si = symbol_index.get(key)
            if not si:
                continue
            refs.append({
                "ref_kind": "code_symbol",
                "file_path": si["file"],
                "locator": key,
                "symbol_name": si["name"],
                "start_line": si["start"],
                "end_line": si["end"],
                "heading": si["label"],
            })
            ref_files.add(si["file"])
        for p in f.get("file_paths") or []:
            if p not in ref_files:
                refs.append({"ref_kind": "code_file", "file_path": p, "locator": p})
        planned.append({
            "name": f["name"],
            "summary": f["summary"],
            "context": context,
            "context_mode": mode,
            "context_char_len": len(context),
            "selected_paths": used_paths,
            "selected_symbols": used_syms,
            "refs": refs,
        })

    return {
        "file_count": len(files),
        "symbol_count": len(symbol_index),
        "core_paths": core_paths,
        "features": planned,
    }


# ----------------------------------------------------------------------
# 2 回目: 機能ごとの詳細分析
# ----------------------------------------------------------------------
def analyze_feature_detail(
    settings: Settings, feature: dict[str, Any]
) -> dict[str, Any]:
    """2 回目のやり取り: 1 つの機能についてコード抜粋から詳細仕様を書き起こす。

    機能ごとに独立して呼び出せるため、呼び出し側で並列実行する。

    Args
    -----------------
    - settings: Settings,  アプリ設定(Azure OpenAI の接続情報を含む)
    - feature: dict,       plan_analysis() が返す機能の計画
                           (``name`` / ``summary`` / ``context`` を使用)

    Returns
    -----------------
    - detail: dict,  画面表示用。"name"、"overview"、
                     "sections"(``heading`` / ``body`` の配列)を持つ

    Raises
    -----------------
    - CodeAnalysisError: Azure OpenAI 未設定、AI 呼び出し失敗、応答解析失敗
    """
    if not settings.ai_enabled:
        raise CodeAnalysisError(
            "Azure OpenAI が未設定です(.env の AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY を確認してください)"
        )

    name = str(feature.get("name", "")).strip()
    summary = str(feature.get("summary", "")).strip()
    context = feature.get("context", "") or ""

    user_prompt = (
        "対象機能:\n"
        f"- 名称: {name or '(名称なし)'}\n"
        f"- 概要: {summary or '(概要なし)'}\n\n"
        "コード抜粋:\n" + context
    )
    parsed = _call_chat(
        settings, FEATURE_DETAIL_SYSTEM_PROMPT, user_prompt, label=f"2回目:{name or '?'}"
    )
    if not isinstance(parsed, dict):
        raise CodeAnalysisError("AI 応答の形式が想定と異なります")

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
