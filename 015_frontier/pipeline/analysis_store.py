"""設計書分析 / コード分析の結果を DB へ保存・取得するモジュール(方式D)。

- analysis_runs        : 分析 1 回ぶんのメタ(入力フィンガープリント含む)
- analysis_features    : 機能単位の本体(概要 + 詳細セクション)
- analysis_feature_refs: 機能が参照する設計書セクション / コードシンボル(トレーサビリティ)

同一入力(content_hash)の成功済み結果があれば再利用でき、AI 呼び出しを省ける。
将来の「設計書とコードの差分抽出」や RAG が、この 3 テーブルを参照する。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from config.settings import get_settings
from infra.db import get_session_factory


# ----------------------------------------------------------------------
# ヘルパ
# ----------------------------------------------------------------------
def _new_session() -> Session:
    """新しい SQLAlchemy セッションを返す。"""
    return get_session_factory(get_settings())()


def _json_col(value: Any) -> Any:
    """JSON カラム値(dict または str)を Python オブジェクトへ。"""
    if value is None:
        return None
    return value if not isinstance(value, (str, bytes)) else json.loads(value)


def compute_content_hash(files: list[dict[str, Any]]) -> str:
    """分析対象ファイル群(name + content)から決定的なハッシュを作る。

    ファイルの並び順に依存しないよう name でソートしてから連結する。
    """
    h = hashlib.sha256()
    for f in sorted(files, key=lambda x: x.get("name", "")):
        h.update((f.get("name", "") or "").encode("utf-8"))
        h.update(b"\x00")
        h.update((f.get("content", "") or "").encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


# ----------------------------------------------------------------------
# 取得
# ----------------------------------------------------------------------
def _get_run(session: Session, run_id: int) -> dict[str, Any] | None:
    """run 1 件を、機能・参照込みで組み立てて返す(セッション指定版)。"""
    r = session.execute(
        text(
            """
            SELECT id, kind, repo, branch, tree_sha, content_hash, model,
                   params, stats, status, detail, created_at
            FROM analysis_runs WHERE id = :id
            """
        ),
        {"id": run_id},
    ).first()
    if not r:
        return None

    frows = session.execute(
        text(
            """
            SELECT id, ordinal, name, overview, context_mode, meta, sections
            FROM analysis_features WHERE run_id = :r ORDER BY ordinal
            """
        ),
        {"r": run_id},
    ).all()
    refrows = session.execute(
        text(
            """
            SELECT feature_id, ref_kind, file_path, locator, heading,
                   symbol_name, start_line, end_line, extra
            FROM analysis_feature_refs WHERE run_id = :r ORDER BY id
            """
        ),
        {"r": run_id},
    ).all()

    refs_by_feature: dict[int, list[dict[str, Any]]] = {}
    for rr in refrows:
        entry: dict[str, Any] = {
            "ref_kind": rr.ref_kind,
            "file_path": rr.file_path,
            "locator": rr.locator,
            "heading": rr.heading,
            "symbol_name": rr.symbol_name,
            "start_line": rr.start_line,
            "end_line": rr.end_line,
        }
        if rr.extra is not None:
            entry["extra"] = _json_col(rr.extra)
        refs_by_feature.setdefault(rr.feature_id, []).append(entry)

    features: list[dict[str, Any]] = []
    for fr in frows:
        meta = _json_col(fr.meta) or {}
        features.append({
            "id": fr.id,
            "name": fr.name,
            "overview": fr.overview,
            "context_mode": fr.context_mode,
            "sections": _json_col(fr.sections) or [],
            "refs": refs_by_feature.get(fr.id, []),
            **meta,  # context_char_len / selected_* / error など画面表示用メタ
        })

    return {
        "id": r.id,
        "kind": r.kind,
        "repo": r.repo,
        "branch": r.branch,
        "tree_sha": r.tree_sha,
        "content_hash": r.content_hash,
        "model": r.model,
        "params": _json_col(r.params),
        "stats": _json_col(r.stats),
        "status": r.status,
        "detail": r.detail,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "features": features,
    }


def get_run(run_id: int) -> dict[str, Any] | None:
    """run 1 件を機能・参照込みで返す。存在しなければ None。"""
    session = _new_session()
    try:
        return _get_run(session, run_id)
    finally:
        session.close()


def find_cached_run(kind: str, content_hash: str) -> dict[str, Any] | None:
    """同一入力(content_hash)で成功済みの最新 run を返す(キャッシュ再利用用)。"""
    session = _new_session()
    try:
        row = session.execute(
            text(
                """
                SELECT id FROM analysis_runs
                WHERE kind = :kind AND content_hash = :h AND status = 'success'
                ORDER BY id DESC LIMIT 1
                """
            ),
            {"kind": kind, "h": content_hash},
        ).first()
        return _get_run(session, row.id) if row else None
    finally:
        session.close()


def get_latest_run(kind: str, repo: str | None = None) -> dict[str, Any] | None:
    """指定 kind(repo を渡せば絞り込み)の成功済み最新 run を返す。"""
    session = _new_session()
    try:
        where = "WHERE kind = :kind AND status = 'success'"
        params: dict[str, Any] = {"kind": kind}
        if repo:
            where += " AND repo = :repo"
            params["repo"] = repo
        row = session.execute(
            text(f"SELECT id FROM analysis_runs {where} ORDER BY id DESC LIMIT 1"),
            params,
        ).first()
        return _get_run(session, row.id) if row else None
    finally:
        session.close()


def list_runs(
    kind: str | None = None, repo: str | None = None, limit: int = 30
) -> list[dict[str, Any]]:
    """run の一覧(新しい順)。機能本体は含めず、件数だけ付ける。"""
    clauses: list[str] = []
    params: dict[str, Any] = {"lim": limit}
    if kind:
        clauses.append("kind = :kind")
        params["kind"] = kind
    if repo:
        clauses.append("repo = :repo")
        params["repo"] = repo
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    session = _new_session()
    try:
        rows = session.execute(
            text(
                f"""
                SELECT id, kind, repo, branch, tree_sha, content_hash, model,
                       stats, status, created_at
                FROM analysis_runs {where} ORDER BY id DESC LIMIT :lim
                """
            ),
            params,
        ).all()
        counts = dict(
            session.execute(
                text(
                    """
                    SELECT run_id, COUNT(*) FROM analysis_features
                    GROUP BY run_id
                    """
                )
            ).all()
        )
        return [
            {
                "id": r.id,
                "kind": r.kind,
                "repo": r.repo,
                "branch": r.branch,
                "tree_sha": r.tree_sha,
                "content_hash": r.content_hash,
                "model": r.model,
                "stats": _json_col(r.stats),
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "feature_count": int(counts.get(r.id, 0)),
            }
            for r in rows
        ]
    finally:
        session.close()


def find_feature_refs(
    file_path: str | None = None, ref_kind: str | None = None, limit: int = 200
) -> list[dict[str, Any]]:
    """参照先(ファイル / 種別)から、それを参照している機能を逆引きする(RAG 用)。"""
    clauses: list[str] = []
    params: dict[str, Any] = {"lim": limit}
    if file_path:
        clauses.append("r.file_path = :fp")
        params["fp"] = file_path
    if ref_kind:
        clauses.append("r.ref_kind = :rk")
        params["rk"] = ref_kind
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    session = _new_session()
    try:
        rows = session.execute(
            text(
                f"""
                SELECT r.run_id, r.feature_id, r.ref_kind, r.file_path, r.locator,
                       r.heading, r.symbol_name, r.start_line, r.end_line,
                       f.name AS feature_name, run.kind AS run_kind
                FROM analysis_feature_refs r
                JOIN analysis_features f ON f.id = r.feature_id
                JOIN analysis_runs run ON run.id = r.run_id
                {where}
                ORDER BY r.id DESC LIMIT :lim
                """
            ),
            params,
        ).all()
        return [dict(row._mapping) for row in rows]
    finally:
        session.close()


# ----------------------------------------------------------------------
# 保存
# ----------------------------------------------------------------------
def save_analysis(
    *,
    kind: str,
    repo: str,
    branch: str,
    tree_sha: str | None,
    content_hash: str,
    model: str,
    params: dict[str, Any],
    stats: dict[str, Any],
    features: list[dict[str, Any]],
) -> dict[str, Any]:
    """分析結果 1 回ぶんを保存し、保存後の run(get_run 相当)を返す。

    Args
    -----------------
    - kind: str,              "design" / "code"
    - repo / branch / tree_sha / content_hash,  入力フィンガープリント
    - model: str,             使用したモデル名
    - params: dict,           再現用パラメータ
    - stats: dict,            ファイル数・セクション数など(画面表示にも使う)
    - features: list[dict],   API が組み立てた機能一覧
                              (name / overview / sections / context_mode /
                               context_char_len / selected_* / error / refs)

    Returns
    -----------------
    - run: dict,  保存後の run(_get_run と同形)
    """
    session = _new_session()
    try:
        res = session.execute(
            text(
                """
                INSERT INTO analysis_runs
                  (kind, repo, branch, tree_sha, content_hash, model, params, stats, status)
                VALUES
                  (:kind, :repo, :branch, :tree_sha, :h, :model, :params, :stats, 'success')
                """
            ),
            {
                "kind": kind,
                "repo": repo,
                "branch": branch,
                "tree_sha": tree_sha,
                "h": content_hash,
                "model": model,
                "params": json.dumps(params, ensure_ascii=False),
                "stats": json.dumps(stats, ensure_ascii=False),
            },
        )
        run_id = int(res.lastrowid)

        for i, feat in enumerate(features):
            # 画面表示用メタ(selected_* は kind により入るキーが異なる)
            meta: dict[str, Any] = {"context_char_len": feat.get("context_char_len")}
            for key in ("selected_section_ids", "selected_symbols", "selected_paths", "error"):
                if feat.get(key) is not None:
                    meta[key] = feat[key]

            fres = session.execute(
                text(
                    """
                    INSERT INTO analysis_features
                      (run_id, ordinal, name, overview, context_mode, meta, sections)
                    VALUES
                      (:run_id, :ordinal, :name, :overview, :cm, :meta, :sections)
                    """
                ),
                {
                    "run_id": run_id,
                    "ordinal": i,
                    "name": (feat.get("name") or "")[:512],
                    "overview": feat.get("overview") or "",
                    "cm": feat.get("context_mode") or "",
                    "meta": json.dumps(meta, ensure_ascii=False),
                    "sections": json.dumps(feat.get("sections") or [], ensure_ascii=False),
                },
            )
            feature_id = int(fres.lastrowid)

            for ref in feat.get("refs") or []:
                session.execute(
                    text(
                        """
                        INSERT INTO analysis_feature_refs
                          (run_id, feature_id, ref_kind, file_path, locator,
                           heading, symbol_name, start_line, end_line, extra)
                        VALUES
                          (:run_id, :fid, :rk, :fp, :loc, :hd, :sn, :sl, :el, :ex)
                        """
                    ),
                    {
                        "run_id": run_id,
                        "fid": feature_id,
                        "rk": ref.get("ref_kind") or "",
                        "fp": (ref.get("file_path") or "")[:512],
                        "loc": (ref.get("locator") or "")[:512],
                        "hd": ref.get("heading"),
                        "sn": ref.get("symbol_name"),
                        "sl": ref.get("start_line"),
                        "el": ref.get("end_line"),
                        "ex": (
                            json.dumps(ref["extra"], ensure_ascii=False)
                            if ref.get("extra") is not None
                            else None
                        ),
                    },
                )

        session.commit()
        return _get_run(session, run_id)  # type: ignore[return-value]
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ----------------------------------------------------------------------
# 実装差分解析(spec_code_diffs / spec_code_diff_items)
# ----------------------------------------------------------------------
def _get_diff(session: Session, diff_id: int) -> dict[str, Any] | None:
    """差分解析 1 件を、相違点込みで組み立てて返す(セッション指定版)。"""
    d = session.execute(
        text(
            """
            SELECT id, repo, design_run_id, code_run_id, model, stats,
                   diff_count, status, detail, created_at
            FROM spec_code_diffs WHERE id = :id
            """
        ),
        {"id": diff_id},
    ).first()
    if not d:
        return None

    rows = session.execute(
        text(
            """
            SELECT id, ordinal, feature_name, design_feature_id, code_feature_id,
                   verdict, severity, summary, design_state, code_state, evidence
            FROM spec_code_diff_items WHERE diff_id = :d ORDER BY ordinal
            """
        ),
        {"d": diff_id},
    ).all()
    items = [
        {
            "id": r.id,
            "feature_name": r.feature_name,
            "design_feature_id": r.design_feature_id,
            "code_feature_id": r.code_feature_id,
            "verdict": r.verdict,
            "severity": r.severity,
            "summary": r.summary,
            "design_state": r.design_state,
            "code_state": r.code_state,
            "evidence": _json_col(r.evidence) or {},
        }
        for r in rows
    ]
    return {
        "id": d.id,
        "repo": d.repo,
        "design_run_id": d.design_run_id,
        "code_run_id": d.code_run_id,
        "model": d.model,
        "stats": _json_col(d.stats),
        "diff_count": d.diff_count,
        "status": d.status,
        "detail": d.detail,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "items": items,
    }


def get_diff(diff_id: int) -> dict[str, Any] | None:
    """差分解析 1 件(相違点込み)を返す。"""
    session = _new_session()
    try:
        return _get_diff(session, diff_id)
    finally:
        session.close()


def get_latest_diff(repo: str | None = None) -> dict[str, Any] | None:
    """成功済みの最新の差分解析を返す(画面初期表示 / ダッシュボード用)。"""
    session = _new_session()
    try:
        where = "WHERE status = 'success'"
        params: dict[str, Any] = {}
        if repo:
            where += " AND repo = :repo"
            params["repo"] = repo
        row = session.execute(
            text(f"SELECT id FROM spec_code_diffs {where} ORDER BY id DESC LIMIT 1"),
            params,
        ).first()
        return _get_diff(session, row.id) if row else None
    finally:
        session.close()


def list_diffs(repo: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
    """差分解析の一覧(新しい順、相違点本体は含めない)。"""
    session = _new_session()
    try:
        where = ""
        params: dict[str, Any] = {"lim": limit}
        if repo:
            where = "WHERE repo = :repo"
            params["repo"] = repo
        rows = session.execute(
            text(
                f"""
                SELECT id, repo, design_run_id, code_run_id, model, stats,
                       diff_count, status, created_at
                FROM spec_code_diffs {where} ORDER BY id DESC LIMIT :lim
                """
            ),
            params,
        ).all()
        return [
            {
                "id": r.id,
                "repo": r.repo,
                "design_run_id": r.design_run_id,
                "code_run_id": r.code_run_id,
                "model": r.model,
                "stats": _json_col(r.stats),
                "diff_count": r.diff_count,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    finally:
        session.close()


def save_diff(
    *,
    repo: str,
    design_run_id: int,
    code_run_id: int,
    model: str,
    stats: dict[str, Any],
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    """差分解析の結果を保存し、保存後の差分(_get_diff 相当)を返す。"""
    session = _new_session()
    try:
        res = session.execute(
            text(
                """
                INSERT INTO spec_code_diffs
                  (repo, design_run_id, code_run_id, model, stats, diff_count, status)
                VALUES
                  (:repo, :drid, :crid, :model, :stats, :cnt, 'success')
                """
            ),
            {
                "repo": repo,
                "drid": design_run_id,
                "crid": code_run_id,
                "model": model,
                "stats": json.dumps(stats, ensure_ascii=False),
                "cnt": len(items),
            },
        )
        diff_id = int(res.lastrowid)

        for i, it in enumerate(items):
            session.execute(
                text(
                    """
                    INSERT INTO spec_code_diff_items
                      (diff_id, ordinal, feature_name, design_feature_id, code_feature_id,
                       verdict, severity, summary, design_state, code_state, evidence)
                    VALUES
                      (:diff_id, :ordinal, :fn, :dfid, :cfid, :verdict, :severity,
                       :summary, :ds, :cs, :ev)
                    """
                ),
                {
                    "diff_id": diff_id,
                    "ordinal": i,
                    "fn": (it.get("feature_name") or "")[:512],
                    "dfid": it.get("design_feature_id"),
                    "cfid": it.get("code_feature_id"),
                    "verdict": it.get("verdict") or "conflict",
                    "severity": it.get("severity") or "mid",
                    "summary": (it.get("summary") or "")[:1024],
                    "ds": it.get("design_state"),
                    "cs": it.get("code_state"),
                    "ev": json.dumps(it.get("evidence") or {}, ensure_ascii=False),
                },
            )
        session.commit()
        return _get_diff(session, diff_id)  # type: ignore[return-value]
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
