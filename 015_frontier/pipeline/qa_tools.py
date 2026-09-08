"""Q&A エージェントが呼び出せる検索ツール群。

- ステップ1: 「分析結果検索」(このプロジェクトで DB に蓄積されている設計書/コード分析、
  実装差分、KPT、暗黙知、アクティビティ分析)。キーワードによる単純な部分一致検索。
- ステップ2: 「元データ検索」(search_raw_data)。分析結果だけでは不十分な場合に、
  Mattermost投稿・Trelloカード・コード変更履歴・GitHub活動の生データを、embeddings
  テーブル(意味検索用ベクトル)に対するコサイン類似度検索で直接調べる。
- ステップ3: 「ファイル直接参照」(read_repo_file)。search_design_code が返す
  file_path/start_line/end_line を使って、設計書・コードの実ファイルを直接読む。

分析結果系の各ツールは「最新の分析結果を取得 → キーワードで単純に絞り込み →
上限件数に切り詰め」という共通の形を取る(専用の検索SQLは書かず、既存の
*_store.get_latest_* を再利用する)。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

MAX_RESULTS_DEFAULT = 8
# ツール結果として AI に返すテキストの上限(プロンプト肥大化の防止)
MAX_TEXT_CHARS = 800
# 意味検索(embeddings)で類似度計算の対象にする最大行数(MySQL に pgvector 相当が無く
# アプリ側でブルートフォース計算するため、データ増加時の防波堤として上限を設ける)
MAX_EMBEDDINGS_SCAN = 5000
# read_repo_file で 1 回に返すファイル内容の上限(行数 / 文字数)
MAX_FILE_LINES = 400
MAX_FILE_CHARS = 8000


def _norm(s: str) -> str:
    return (s or "").lower()


def _matches(query: str, *texts: str) -> bool:
    """query の語(空白区切り)のいずれか 1 つでも、text に部分一致で含まれていれば一致とみなす。

    AND条件(全語一致)にすると、AIが自然文の長いクエリ("画像からCSVへの変換機能 実装の意図
    設計判断" 等)を渡した際にほぼヒットしなくなるため、OR条件(いずれか一致)にして
    再現率を優先する(精度はAI側が結果を見て取捨選択する前提)。
    """
    terms = [t for t in _norm(query).split() if t]
    if not terms:
        return True
    haystack = " ".join(_norm(t) for t in texts)
    return any(term in haystack for term in terms)


def _trim(s: str | None, size: int = MAX_TEXT_CHARS) -> str:
    s = (s or "").strip()
    return s if len(s) <= size else s[:size] + "…(省略)"


def _resolve_repo() -> str:
    """設定画面で選択中の GitHub リポジトリ(owner/repo)を解決する。"""
    from config.runtime import load_runtime_config
    from config.settings import get_settings
    from viewers import github as github_view

    settings = get_settings()
    rc = load_runtime_config()
    return github_view._resolve_repo(settings, (rc.github_repo or "").strip())


# ----------------------------------------------------------------------
# 個別ツール
# ----------------------------------------------------------------------
def search_design_code(query: str, kind: str = "both", limit: int = MAX_RESULTS_DEFAULT) -> dict[str, Any]:
    """設計書 / コード分析の機能(analysis_features)をキーワードで検索する。"""
    from pipeline import analysis_store

    repo = _resolve_repo()
    kinds = ["design", "code"] if kind not in ("design", "code") else [kind]
    matched: list[dict[str, Any]] = []
    for k in kinds:
        run = analysis_store.get_latest_run(k, repo)
        if not run:
            continue
        for feat in run.get("features", []):
            sec_text = " ".join(s.get("body", "") for s in feat.get("sections") or [])
            if not _matches(query, feat.get("name", ""), feat.get("overview", ""), sec_text):
                continue
            matched.append({
                "kind": k,
                "name": feat.get("name"),
                "overview": _trim(feat.get("overview")),
                "sections": [
                    {"heading": s.get("heading"), "body": _trim(s.get("body"), 400)}
                    for s in (feat.get("sections") or [])[:4]
                ],
                "refs": [
                    {
                        "ref_kind": r.get("ref_kind"), "file_path": r.get("file_path"),
                        "symbol_name": r.get("symbol_name"),
                        "start_line": r.get("start_line"), "end_line": r.get("end_line"),
                    }
                    for r in (feat.get("refs") or [])[:6]
                ],
            })
    matched = matched[:limit]
    return {"count": len(matched), "items": matched}


def search_spec_diff(query: str, severity: str | None = None, limit: int = MAX_RESULTS_DEFAULT) -> dict[str, Any]:
    """設計書とコードの相違点(実装差分解析)をキーワードで検索する。"""
    from pipeline import analysis_store

    repo = _resolve_repo()
    diff = analysis_store.get_latest_diff(repo)
    matched: list[dict[str, Any]] = []
    for it in (diff or {}).get("items", []):
        if severity and it.get("severity") != severity:
            continue
        if not _matches(query, it.get("feature_name", ""), it.get("summary", ""),
                         it.get("design_state", ""), it.get("code_state", "")):
            continue
        matched.append({
            "feature_name": it.get("feature_name"),
            "verdict": it.get("verdict"),
            "severity": it.get("severity"),
            "summary": it.get("summary"),
            "design_state": _trim(it.get("design_state"), 400),
            "code_state": _trim(it.get("code_state"), 400),
        })
    matched = matched[:limit]
    return {"count": len(matched), "items": matched}


def search_kpt(query: str, kind: str | None = None, limit: int = MAX_RESULTS_DEFAULT) -> dict[str, Any]:
    """KPT分析(Keep/Problem/Try)をキーワードで検索する。重要度(★)が高い順に返す。"""
    from pipeline import kpt_store

    latest = kpt_store.get_latest_analysis()
    matched: list[dict[str, Any]] = []
    for k in ("keep", "problem", "try"):
        if kind and kind != k:
            continue
        for it in (latest or {}).get(k, []):
            if not _matches(query, it.get("title", ""), it.get("detail", "")):
                continue
            matched.append({
                "kind": k,
                "title": it.get("title"),
                "detail": _trim(it.get("detail")),
                "importance": it.get("importance", 0),
                "sources": it.get("sources", []),
            })
    matched.sort(key=lambda x: x["importance"], reverse=True)
    matched = matched[:limit]
    return {"count": len(matched), "items": matched}


def search_tacit_knowledge(
    query: str, source: str | None = None, min_rating: int | None = None, limit: int = MAX_RESULTS_DEFAULT
) -> dict[str, Any]:
    """暗黙知(Mattermost/Trello/GitHubから抽出したプロジェクト固有の知見)をキーワードで検索する。

    評価値(★)が高いものほど信頼できる知見として優先的に返す。
    """
    from pipeline import tacit_store

    items = tacit_store.list_items(rating=None, limit=1000)
    matched: list[dict[str, Any]] = []
    for it in items:
        if source and it.get("source") != source:
            continue
        rating = it.get("rating")
        if min_rating is not None and (rating is None or rating < min_rating):
            continue
        if not _matches(query, it.get("title", ""), it.get("content", "")):
            continue
        matched.append({
            "source": it.get("source"),
            "title": it.get("title"),
            "content": _trim(it.get("content")),
            "rating": rating,
            "source_detail": it.get("source_detail"),
        })
    matched.sort(key=lambda x: (x["rating"] if x["rating"] is not None else -1), reverse=True)
    matched = matched[:limit]
    return {"count": len(matched), "items": matched}


def search_user_activity(query: str, limit: int = MAX_RESULTS_DEFAULT) -> dict[str, Any]:
    """メンバーのアクティビティ分析(役割・担当範囲・働き方)をキーワードで検索する。

    メンバーの日本語表示名と、各ツール(Mattermost/Trello/GitHub等)でのアカウント名の
    対応も一緒に返す(有識者探しなど、メンバーの特定に使える)。
    """
    from pipeline import user_activity_store

    latest = user_activity_store.get_latest_analysis()
    matched: list[dict[str, Any]] = []
    for it in (latest or {}).get("items", []):
        sec_text = " ".join(s.get("body", "") for s in it.get("sections") or [])
        if not _matches(query, it.get("display_name", ""), it.get("personal", ""), it.get("overview", ""), sec_text):
            continue
        matched.append({
            "display_name": it.get("display_name"),
            "is_member": it.get("is_member"),
            "accounts": it.get("accounts"),
            "personal": _trim(it.get("personal"), 300),
            "overview": _trim(it.get("overview")),
            "sections": [
                {"heading": s.get("heading"), "body": _trim(s.get("body"), 400)}
                for s in (it.get("sections") or [])[:4]
            ],
        })
    matched = matched[:limit]
    return {"count": len(matched), "items": matched}


def find_experts(query: str, limit: int = 5) -> dict[str, Any]:
    """特定の話題・機能について詳しそうな人(有識者)を探す。

    Mattermost/Trello/GitHubコミットの各アカウント別分析(overview/sections)と、暗黙知の
    出典(誰の発言・コメット・コミットか)から query に関連する記述があるアカウントを集計し、
    アクティビティ分析のアカウント対応表(settings.ini の [USER_ID])を使って
    ユーザー名/ログイン名を日本語の表示名に解決して返す。一致件数が多い人ほど、
    その話題に関与している可能性が高いと考えられる。
    """
    from pipeline import changelog_store, mm_store, tacit_store, trello_store, user_activity_store

    # ユーザー名/ログイン名 -> {display_name, accounts} の対応表(ツールごと)
    name_by_account: dict[str, dict[str, str]] = {"mattermost": {}, "trello": {}, "github": {}}
    accounts_by_name: dict[str, dict[str, str]] = {}
    ua = user_activity_store.get_latest_analysis()
    for it in (ua or {}).get("items", []):
        dn = it.get("display_name")
        if not dn:
            continue
        acc = it.get("accounts") or {}
        accounts_by_name[dn] = acc
        for tool, uname in acc.items():
            if tool in name_by_account and uname:
                name_by_account[tool][uname] = dn

    def resolve(tool: str, username: str) -> str:
        return name_by_account.get(tool, {}).get(username) or username

    tally: dict[str, dict[str, Any]] = {}

    def add_evidence(tool: str, username: str, snippet: str) -> None:
        if not username:
            return
        name = resolve(tool, username)
        entry = tally.setdefault(name, {"display_name": name, "accounts": accounts_by_name.get(name), "matches": []})
        entry["matches"].append({"tool": tool, "account": username, "snippet": _trim(snippet, 300)})

    # 1. 各ツールのアカウント別分析(overview / sections)から、話題に触れているアカウントを探す
    for tool, analysis in (
        ("mattermost", mm_store.get_latest_account_analysis()),
        ("trello", trello_store.get_latest_account_analysis()),
        ("github", changelog_store.get_latest_author_analysis()),
    ):
        for acc in (analysis or {}).get("accounts", []):
            sec_text = " ".join(s.get("body", "") for s in acc.get("sections") or [])
            if _matches(query, acc.get("overview", ""), sec_text):
                add_evidence(tool, acc.get("username", ""), acc.get("overview") or sec_text)

    # 2. 暗黙知の出典(誰の発言・コメント・コミットか)からも探す
    for it in tacit_store.list_items(rating=None, limit=1000):
        if not _matches(query, it.get("title", ""), it.get("content", "")):
            continue
        src = it.get("source")
        if src not in ("mattermost", "trello", "github"):
            continue
        detail = it.get("source_detail") or {}
        username = detail.get("username") or detail.get("actor") or ""
        add_evidence(src, username, it.get("content", ""))

    ranked = sorted(tally.values(), key=lambda x: len(x["matches"]), reverse=True)
    for entry in ranked:
        entry["match_count"] = len(entry["matches"])
        entry["matches"] = entry["matches"][:5]  # 根拠は上限5件に切り詰め
    ranked = ranked[:limit]
    return {"count": len(ranked), "items": ranked}


_SOURCE_LABEL = {
    "mattermost": "Mattermost投稿",
    "trello": "Trelloカード/コメント",
    "github_change": "コード変更履歴(コミット)",
    "github_activity": "GitHub活動(PR/ブランチ)",
}


def search_raw_data(query: str, source: str | None = None, limit: int = 6) -> dict[str, Any]:
    """分析結果だけでは不十分な場合に、元データ(Mattermost投稿・Trelloカード・コード変更
    履歴・GitHub活動)を意味検索(embeddings のコサイン類似度)で直接調べる。

    分析結果検索(search_kpt 等)や暗黙知検索は既に要約・抽出された情報を返すのに対し、
    このツールは会話や変更内容そのものの断片を返す。より具体的な一次情報が必要な場合、
    または分析結果に該当が無かった場合に使う。
    """
    from common.vectors import cosine, from_blob
    from config.settings import get_settings
    from infra.db import get_session_factory
    from pipeline.ai import AiAnalyzer
    from sqlalchemy import text

    settings = get_settings()
    analyzer = AiAnalyzer(settings)
    vectors, embedding_model = analyzer.embed_texts([query])
    if not vectors:
        return {"count": 0, "items": [], "note": "検索クエリの埋め込みに失敗しました"}
    qvec = vectors[0]

    session = get_session_factory(settings)()
    try:
        where = "WHERE source = :src" if source else ""
        params: dict[str, Any] = {"src": source} if source else {}
        rows = session.execute(
            text(
                f"SELECT chunk_id, week, source, ref, text, vec FROM embeddings {where} "
                "ORDER BY created_at DESC LIMIT :cap"
            ),
            {**params, "cap": MAX_EMBEDDINGS_SCAN},
        ).all()
    finally:
        session.close()

    scored = [(cosine(qvec, from_blob(r.vec)), r) for r in rows]
    scored.sort(key=lambda x: x[0], reverse=True)

    items = [
        {
            "source": r.source,
            "source_label": _SOURCE_LABEL.get(r.source, r.source),
            "ref": r.ref,
            "week": r.week,
            "similarity": round(score, 3),
            "text": _trim(r.text, 900),
        }
        for score, r in scored[:limit]
        if score > 0
    ]
    note = None if items else "類似する元データが見つかりませんでした"
    return {"count": len(items), "items": items, "embedding_model": embedding_model, **({"note": note} if note else {})}


def read_repo_file(file_path: str, start_line: int | None = None, end_line: int | None = None) -> dict[str, Any]:
    """設計書・コードの実ファイルを、対象リポジトリ(設定画面のGitHubリポジトリ)から直接読む。

    search_design_code が返す refs の file_path / start_line / end_line をそのまま渡せる。
    行範囲を指定しない場合はファイル先頭から MAX_FILE_LINES 行まで返す。
    """
    import base64
    import binascii
    from urllib.parse import quote

    from collectors.base import HttpClient
    from config.settings import get_settings

    settings = get_settings()
    repo = _resolve_repo()
    if not repo:
        return {"error": "GitHub リポジトリが設定画面で設定されていません"}
    if not settings.github_token or settings.github_token == "changeme":
        return {"error": "GitHub トークンが未設定です(.env の GITHUB_TOKEN)"}

    path = (file_path or "").strip().lstrip("/")
    if not path:
        return {"error": "file_path が空です"}

    http = HttpClient({
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        data = http.get_json(f"https://api.github.com/repos/{repo}/contents/{quote(path, safe='/')}")
    except Exception as exc:
        return {"error": f"ファイルを取得できませんでした(パス/権限を確認してください): {exc}"}

    if isinstance(data, list):
        return {"error": f"'{path}' はファイルではなくディレクトリです"}

    try:
        raw = base64.b64decode(data.get("content", "") or "")
    except (binascii.Error, ValueError):
        return {"error": "ファイル内容をデコードできませんでした"}
    if b"\x00" in raw:
        return {"error": "バイナリファイルのため表示できません"}
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        return {"error": "テキストとして読み取れませんでした(文字コード不明)"}

    lines = content.splitlines()
    if start_line or end_line:
        s = max((start_line or 1) - 1, 0)
        e = end_line if end_line else len(lines)
        lines = lines[s:e]

    truncated = False
    if len(lines) > MAX_FILE_LINES:
        lines = lines[:MAX_FILE_LINES]
        truncated = True
    snippet = "\n".join(lines)
    if len(snippet) > MAX_FILE_CHARS:
        snippet = snippet[:MAX_FILE_CHARS]
        truncated = True

    return {
        "repo": repo,
        "file_path": path,
        "start_line": start_line,
        "end_line": end_line,
        "truncated": truncated,
        "content": snippet,
    }


# ドキュメントらしいファイルの拡張子・除外したいディレクトリ(依存関係の同梱物などノイズ)
_DOC_EXTENSIONS = (".md", ".mdx", ".rst", ".txt")
_DOC_EXCLUDE_SEGMENTS = ("node_modules", "vendor", ".venv", "venv", "site-packages", "__pycache__")


def list_repo_docs() -> dict[str, Any]:
    """README・環境構築手順・CONTRIBUTING等、特定の機能に紐づかないドキュメントの
    ファイル一覧をリポジトリ全体から取得する。

    search_design_code は「機能単位」の分析結果しか対象にしないため、READMEのような
    プロジェクト全体に関わる説明・セットアップ手順はそちらでは見つからない。
    このツールで該当しそうなファイルを見つけたら、read_repo_file で中身を読むこと。
    """
    from urllib.parse import quote

    from collectors.base import HttpClient
    from config.settings import get_settings

    settings = get_settings()
    repo = _resolve_repo()
    if not repo:
        return {"error": "GitHub リポジトリが設定画面で設定されていません"}
    if not settings.github_token or settings.github_token == "changeme":
        return {"error": "GitHub トークンが未設定です(.env の GITHUB_TOKEN)"}

    http = HttpClient({
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        repo_info = http.get_json(f"https://api.github.com/repos/{repo}")
        branch = repo_info.get("default_branch") or "main"
        tree = http.get_json(
            f"https://api.github.com/repos/{repo}/git/trees/{quote(branch, safe='')}",
            params={"recursive": "1"},
        )
    except Exception as exc:
        return {"error": f"リポジトリのファイル一覧を取得できませんでした: {exc}"}

    files: list[str] = []
    for entry in tree.get("tree", []):
        if entry.get("type") != "blob":
            continue
        path = entry.get("path", "")
        low = path.lower()
        if not low.endswith(_DOC_EXTENSIONS):
            continue
        if any(seg in low for seg in _DOC_EXCLUDE_SEGMENTS):
            continue
        files.append(path)

    truncated = len(files) > 100
    return {"repo": repo, "count": len(files), "files": files[:100], "truncated": truncated}


def assess_impact(query: str, limit: int = MAX_RESULTS_DEFAULT) -> dict[str, Any]:
    """機能の追加・変更が既存アプリ全体に与える影響範囲を調べる(影響度調査)。

    1. query に関連する設計書/コード機能(search_design_code 相当)を特定し、その機能が
       参照しているコードファイルを「直接の影響範囲」の起点にする。
    2. 各ファイルの変更実績(gh_files: 変更頻度・変更者・最終更新日)を付与する
       (変更頻度が高いファイルは触り慣れている一方、低いファイルは想定外の影響が出やすい)。
    3. それらのファイルと過去に同じコミットで一緒に変更されたことがあるファイル(co-change)を
       gh_commit_files から集計し、「一緒に変更されがち=影響が波及しやすい」候補として返す。
    """
    import json

    from sqlalchemy import bindparam, text

    from config.settings import get_settings
    from infra.db import get_session_factory
    from pipeline import analysis_store

    repo = _resolve_repo()

    # 1. 関連する設計書/コード機能と、それが参照する実装ファイルを集める
    related_features: list[dict[str, Any]] = []
    seed_files: set[str] = set()
    for k in ("design", "code"):
        run = analysis_store.get_latest_run(k, repo)
        if not run:
            continue
        for feat in run.get("features", []):
            sec_text = " ".join(s.get("body", "") for s in feat.get("sections") or [])
            if not _matches(query, feat.get("name", ""), feat.get("overview", ""), sec_text):
                continue
            file_paths = sorted({r.get("file_path") for r in (feat.get("refs") or []) if r.get("file_path")})
            related_features.append({
                "kind": k, "name": feat.get("name"),
                "overview": _trim(feat.get("overview"), 300),
                "files": file_paths,
            })
            seed_files.update(file_paths)

    if not seed_files:
        return {
            "related_features": [],
            "impacted_files_direct": [],
            "impacted_files_co_change": [],
            "note": "関連する機能・ファイルが見つかりませんでした。まず search_design_code で機能名を確認してから、その名称で再度試してください。",
        }

    session = get_session_factory(get_settings())()
    try:
        # 2. 起点ファイルの変更実績(gh_files)
        rows = session.execute(
            text(
                "SELECT path, change_count, additions, deletions, author_logins, last_change_at "
                "FROM gh_files WHERE repo = :repo AND path IN :paths"
            ).bindparams(bindparam("paths", expanding=True)),
            {"repo": repo, "paths": list(seed_files)},
        ).all()
        stats_by_path = {}
        for r in rows:
            authors = r.author_logins
            if isinstance(authors, (str, bytes)):
                authors = json.loads(authors)
            stats_by_path[r.path] = {
                "change_count": r.change_count,
                "additions": r.additions,
                "deletions": r.deletions,
                "authors": authors or [],
                "last_change_at": r.last_change_at.isoformat() if r.last_change_at else None,
            }

        # 3. 起点ファイルと同じコミットで一緒に変更された他ファイル(co-change)を集計
        co_rows = session.execute(
            text(
                """
                SELECT cf2.path AS path, COUNT(DISTINCT cf1.sha) AS n
                FROM gh_commit_files cf1
                JOIN gh_commit_files cf2 ON cf1.sha = cf2.sha AND cf2.path <> cf1.path
                WHERE cf1.path IN :paths
                GROUP BY cf2.path
                ORDER BY n DESC
                LIMIT 100
                """
            ).bindparams(bindparam("paths", expanding=True)),
            {"paths": list(seed_files)},
        ).all()
    finally:
        session.close()

    impacted_files_direct = [
        {"file_path": p, **(stats_by_path.get(p) or {"change_count": 0, "authors": []})}
        for p in sorted(seed_files)
    ]
    impacted_files_co_change = [
        {"file_path": r.path, "co_change_count": r.n}
        for r in co_rows
        if r.path not in seed_files
    ][:limit]

    return {
        "related_features": related_features,
        "impacted_files_direct": impacted_files_direct,
        "impacted_files_co_change": impacted_files_co_change,
    }


IMAGE_MODEL = "gpt-image-2"
DEFAULT_IMAGE_SIZE = "1024x1024"


def generate_image(prompt: str, size: str = DEFAULT_IMAGE_SIZE) -> dict[str, Any]:
    """説明用の画像を生成する(text-to-image、gpt-image-2。013_pp_angel と同じ呼び出し方)。

    構造図・フローチャート・シーケンス図など正確さが重要な図は、回答本文に Mermaid 記法の
    コードブロック(```mermaid)で書く方が確実なので、まずそちらを優先すること。
    実写・イラスト風の説明画像など、Mermaidで表現しにくいものにこのツールを使う。
    """
    from openai import OpenAI

    from config.settings import get_settings

    settings = get_settings()
    if not settings.ai_enabled:
        return {"error": "Azure OpenAI が未設定です(.env の AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY を確認してください)"}

    client = OpenAI(base_url=settings.azure_openai_endpoint, api_key=settings.azure_openai_api_key)
    try:
        result = client.images.generate(model=IMAGE_MODEL, prompt=prompt, size=size, n=1)
    except Exception as exc:
        logger.exception("Q&A 画像生成に失敗")
        return {"error": f"画像生成に失敗しました: {exc}"}

    return {"prompt": prompt, "image_base64": result.data[0].b64_json, "mime": "image/png"}


# ----------------------------------------------------------------------
# OpenAI Tool Calling 定義 + ディスパッチ
# ----------------------------------------------------------------------
TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_design_code",
            "description": "設計書・コード分析の機能単位の情報(概要・詳細セクション・関連ファイル/シンボル)をキーワードで検索する。仕様に関する質問の第一手段。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "検索キーワード(機能名や関連語。空白区切りでAND検索)"},
                    "kind": {"type": "string", "enum": ["design", "code", "both"], "description": "検索対象。既定は both"},
                    "limit": {"type": "integer", "description": "最大件数(既定8)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_spec_diff",
            "description": "設計書とコードの相違点(実装差分解析)をキーワードで検索する。仕様と実装が食い違っていないか調べたい場合に使う。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "検索キーワード"},
                    "severity": {"type": "string", "enum": ["high", "mid", "low"], "description": "重大度で絞り込む(任意)"},
                    "limit": {"type": "integer", "description": "最大件数(既定8)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_kpt",
            "description": "KPT分析(Keep/Problem/Try)をキーワードで検索する。プロジェクトの進め方・課題・今後の改善に関する質問に使う。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "検索キーワード"},
                    "kind": {"type": "string", "enum": ["keep", "problem", "try"], "description": "種別で絞り込む(任意)"},
                    "limit": {"type": "integer", "description": "最大件数(既定8)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_tacit_knowledge",
            "description": "暗黙知(Mattermost/Trello/GitHubから抽出したドキュメント化されていないプロジェクト固有の知見)をキーワードで検索する。評価値(★)が高いものほど信頼できる。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "検索キーワード"},
                    "source": {"type": "string", "enum": ["mattermost", "trello", "github"], "description": "出典ソースで絞り込む(任意)"},
                    "min_rating": {"type": "integer", "description": "この評価値以上のものだけに絞る(任意、0〜5)"},
                    "limit": {"type": "integer", "description": "最大件数(既定8)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_user_activity",
            "description": "メンバーごとの役割・担当範囲・働き方の分析結果をキーワードで検索する。誰が何を担当しているか(有識者探し)の手がかりに使う。日本語の表示名と各ツールでのアカウント名の対応も返す。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "検索キーワード(担当領域・技術名・メンバー名など)"},
                    "limit": {"type": "integer", "description": "最大件数(既定8)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_raw_data",
            "description": (
                "分析結果(search_kpt 等)や暗黙知検索だけでは情報が不十分だった場合に、"
                "Mattermost投稿・Trelloカード/コメント・コード変更履歴・GitHub活動(PR/ブランチ)の"
                "元データを意味検索で直接調べる。会話や変更内容そのものの断片が返る。"
                "分析結果に該当が無かった、またはより具体的な一次情報が必要な場合に使う。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "検索したい内容を自然文で(単語の羅列より文章の方が精度が良い)"},
                    "source": {
                        "type": "string",
                        "enum": ["mattermost", "trello", "github_change", "github_activity"],
                        "description": "検索対象ソースで絞り込む(任意。省略時は全ソース横断)",
                    },
                    "limit": {"type": "integer", "description": "最大件数(既定6)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_repo_docs",
            "description": (
                "README・環境構築手順・CONTRIBUTING等、特定の機能に紐づかないドキュメントの"
                "ファイル一覧をリポジトリ全体から取得する(引数なし)。search_design_code は"
                "機能単位の分析結果しか対象にしないため、プロジェクト概要・セットアップ手順・"
                "使い方など機能に紐づかない資料を探す場合はこちらを使う。見つけたファイルの"
                "中身は read_repo_file で読むこと。"
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_repo_file",
            "description": (
                "設計書・コードの実ファイルをリポジトリから直接読む。search_design_code の "
                "refs に含まれる file_path、または list_repo_docs が返すファイルパスを"
                "そのまま渡せる。分析結果の概要だけでは不十分で、原文そのものを確認したい場合に使う。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "リポジトリ内のファイルパス(search_design_code の refs.file_path)"},
                    "start_line": {"type": "integer", "description": "抜粋開始行(1始まり。省略時は先頭から)"},
                    "end_line": {"type": "integer", "description": "抜粋終了行(省略時は上限行数まで)"},
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_experts",
            "description": (
                "特定の話題・機能に詳しそうな人(有識者)を探す。Mattermost/Trello/GitHubコミットの"
                "各アカウント別分析と暗黙知の出典を横断集計し、一致件数が多い人を日本語の表示名で返す。"
                "「誰が担当したか」「詳しい人は誰か」といった質問に使う。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "調べたい話題・機能・技術要素など"},
                    "limit": {"type": "integer", "description": "最大人数(既定5)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "assess_impact",
            "description": (
                "機能の追加・変更が既存アプリ全体に与える影響範囲を調べる。関連する設計書/コード"
                "機能から実装ファイルを特定し(直接の影響範囲)、それらの変更実績(頻度・変更者)と、"
                "過去に一緒に変更される傾向があった関連ファイル(co-change、影響が波及しやすい候補)を"
                "返す。「影響度」「どこに影響するか」「他に直す必要がある箇所」を調べる質問に使う。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "追加・変更したい機能や対象領域(search_design_codeで確認した機能名が望ましい)"},
                    "limit": {"type": "integer", "description": "co-changeファイルの最大件数(既定8)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": (
                "説明用の画像を生成する(text-to-image、gpt-image-2)。構造図・フローチャート・"
                "シーケンス図など正確さが重要な図は、回答本文に Mermaid 記法のコードブロック"
                "(```mermaid)で書く方が確実なので、まずそちらを優先すること。実写・イラスト風の"
                "説明画像など、Mermaidで表現しにくいものにこのツールを使う。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "生成したい画像の内容を具体的に(日本語可)"},
                    "size": {
                        "type": "string",
                        "enum": ["1024x1024", "1536x1024", "1024x1536"],
                        "description": "画像サイズ(既定: 1024x1024)",
                    },
                },
                "required": ["prompt"],
            },
        },
    },
]

_DISPATCH = {
    "search_design_code": search_design_code,
    "search_spec_diff": search_spec_diff,
    "search_kpt": search_kpt,
    "search_tacit_knowledge": search_tacit_knowledge,
    "search_user_activity": search_user_activity,
    "search_raw_data": search_raw_data,
    "list_repo_docs": list_repo_docs,
    "read_repo_file": read_repo_file,
    "find_experts": find_experts,
    "assess_impact": assess_impact,
    "generate_image": generate_image,
}


def execute_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """ツール名 + 引数から対応する検索関数を実行する。未知のツール名や例外は結果に含める。"""
    fn = _DISPATCH.get(name)
    if fn is None:
        return {"error": f"未知のツールです: {name}"}
    try:
        return fn(**args)
    except Exception as exc:  # ツール呼び出し 1 件の失敗でエージェント全体は止めない
        logger.exception("Q&A ツール実行に失敗 name=%s args=%s", name, args)
        return {"error": f"ツール実行に失敗しました: {exc}"}
