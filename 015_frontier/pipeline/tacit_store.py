"""「暗黙知抽出」の DB 入出力。

- fetch_candidates(): Mattermost投稿 / Trelloカード内容・コメント / GitHub PRコメント・
  レビューのうち、まだ抽出処理をしていない(または内容が変わった)ものを候補として集める。
- save_extraction(): AI 抽出結果を暗黙知アイテムとして保存し、走査した候補を処理済みとして記録する。
- list_items() / update_rating() : 「暗黙知共有」画面向けの一覧取得・評価値の更新。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from config.settings import get_settings
from infra.db import get_session_factory

# 1 回の抽出実行・1 ソースあたりの候補数上限(AI 呼び出しコストの抑制)
MAX_CANDIDATES_PER_SOURCE = 300
# これより短いテキストは相槌等とみなし、最初から対象外にする
MIN_TEXT_CHARS = 6


def _new_session() -> Session:
    return get_session_factory(get_settings())()


def _json_col(value: Any) -> Any:
    if value is None:
        return None
    return value if not isinstance(value, (str, bytes)) else json.loads(value)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _text_hash(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------
# 候補収集(3 ソースの生データ → 未処理分だけに絞り込む)
# ----------------------------------------------------------------------
def _processed_hashes(session: Session, source: str, refs: list[str]) -> dict[str, str]:
    """source_ref -> 処理済みハッシュ のマップ(未処理の ref は含まれない)。"""
    if not refs:
        return {}
    rows = session.execute(
        text(
            "SELECT source_ref, content_hash FROM tacit_processed_refs "
            "WHERE source = :s AND source_ref IN :refs"
        ).bindparams(bindparam("refs", expanding=True)),
        {"s": source, "refs": refs},
    ).all()
    return {r.source_ref: r.content_hash for r in rows}


def _select_new(
    session: Session, source: str, items: list[dict[str, Any]], force: bool
) -> list[dict[str, Any]]:
    """items のうち、未処理 or 内容変更分だけを返す(force なら全件)。"""
    items = [it for it in items if len((it.get("text") or "").strip()) >= MIN_TEXT_CHARS]
    if force:
        return items[:MAX_CANDIDATES_PER_SOURCE]
    processed = _processed_hashes(session, source, [it["source_ref"] for it in items])
    fresh = [it for it in items if processed.get(it["source_ref"]) != _text_hash(it["text"])]
    return fresh[:MAX_CANDIDATES_PER_SOURCE]


def _fetch_mattermost(session: Session) -> list[dict[str, Any]]:
    """mm_posts(投稿本文)を候補化する。"""
    rows = session.execute(
        text(
            """
            SELECT p.post_id, p.channel_id, c.display_name AS channel_name,
                   p.user_id, u.username, p.created_at, p.message
            FROM mm_posts p
            LEFT JOIN mm_channels c ON c.channel_id = p.channel_id
            LEFT JOIN mm_users u ON u.user_id = p.user_id
            WHERE CHAR_LENGTH(TRIM(p.message)) > 0
            ORDER BY p.created_at DESC
            LIMIT 2000
            """
        )
    ).all()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append({
            "source_ref": r.post_id,
            "text": r.message,
            "context": f'[Mattermost投稿] #{r.channel_name or r.channel_id} {r.username or r.user_id}',
            "detail": {
                "channel_id": r.channel_id,
                "channel_name": r.channel_name,
                "user_id": r.user_id,
                "username": r.username,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            },
        })
    return out


def _fetch_trello(session: Session) -> list[dict[str, Any]]:
    """tr_cards(カード説明)+ tr_activity(コメント)を候補化する。"""
    out: list[dict[str, Any]] = []
    cards = session.execute(
        text(
            """
            SELECT card_id, board_id, list_name, name, description, url
            FROM tr_cards
            WHERE CHAR_LENGTH(TRIM(description)) > 0
            ORDER BY snapshot_at DESC
            LIMIT 1000
            """
        )
    ).all()
    for c in cards:
        out.append({
            "source_ref": f"card:{c.card_id}",
            "text": c.description,
            "context": f'[Trelloカード説明] 「{c.list_name}」{c.name}',
            "detail": {
                "board_id": c.board_id, "card_id": c.card_id,
                "card_name": c.name, "list_name": c.list_name, "url": c.url,
            },
        })

    acts = session.execute(
        text(
            """
            SELECT a.activity_id, a.card_id, a.board_id, a.username, a.text, a.created_at,
                   c.name AS card_name, c.list_name, c.url
            FROM tr_activity a
            LEFT JOIN tr_cards c ON c.card_id = a.card_id
            WHERE a.kind = 'comment' AND CHAR_LENGTH(TRIM(a.text)) > 0
            ORDER BY a.created_at DESC
            LIMIT 2000
            """
        )
    ).all()
    for a in acts:
        out.append({
            "source_ref": f"comment:{a.activity_id}",
            "text": a.text,
            "context": f'[Trelloコメント] 「{a.list_name}」{a.card_name} / {a.username}',
            "detail": {
                "board_id": a.board_id, "card_id": a.card_id, "card_name": a.card_name,
                "list_name": a.list_name, "url": a.url, "username": a.username,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            },
        })
    return out


def _fetch_github(session: Session, repo: str) -> list[dict[str, Any]]:
    """gh_activity(PRコメント / レビュー)を候補化する。"""
    if not repo:
        return []
    rows = session.execute(
        text(
            """
            SELECT event_id, actor, occurred_at, pr_number, title, body, url
            FROM gh_activity
            WHERE repo = :repo AND kind IN ('pr_comment', 'pr_review')
              AND CHAR_LENGTH(TRIM(body)) > 0
            ORDER BY occurred_at DESC
            LIMIT 2000
            """
        ),
        {"repo": repo},
    ).all()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append({
            "source_ref": r.event_id,
            "text": r.body,
            "context": f'[GitHub PR #{r.pr_number}] {r.title} / {r.actor}',
            "detail": {
                "repo": repo, "pr_number": r.pr_number, "title": r.title,
                "actor": r.actor, "url": r.url,
                "created_at": r.occurred_at.isoformat() if r.occurred_at else None,
            },
        })
    return out


def fetch_candidates(repo: str, force: bool = False) -> dict[str, list[dict[str, Any]]]:
    """3 ソースの抽出対象候補を集める。

    Returns:
        {"mattermost": [...], "trello": [...], "github": [...]}
        各要素は {"source_ref", "text", "context", "detail"}。
    """
    session = _new_session()
    try:
        return {
            "mattermost": _select_new(session, "mattermost", _fetch_mattermost(session), force),
            "trello": _select_new(session, "trello", _fetch_trello(session), force),
            "github": _select_new(session, "github", _fetch_github(session, repo), force),
        }
    finally:
        session.close()


# ----------------------------------------------------------------------
# 抽出結果の保存
# ----------------------------------------------------------------------
def save_extraction(
    *,
    model: str,
    candidates: dict[str, list[dict[str, Any]]],
    extracted: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """AI 抽出結果を保存し、走査した候補をすべて処理済みとして記録する。

    Args
    -----------------
    - candidates: fetch_candidates() の戻り(ソースごとの候補リスト)。
    - extracted: {source: [{"candidate_index", "title", "content"}, ...]}
      candidate_index は candidates[source] の何番目の候補から抽出したかを示す。

    Returns
    -----------------
    - {"run_id", "stats", "inserted_count"}
    """
    session = _new_session()
    try:
        now = _now()
        stats = {
            "scanned": {s: len(v) for s, v in candidates.items()},
            "extracted": {s: len(extracted.get(s, [])) for s in candidates},
        }
        res = session.execute(
            text("INSERT INTO tacit_extract_runs (model, stats, status) VALUES (:m, :s, 'success')"),
            {"m": model, "s": json.dumps(stats, ensure_ascii=False)},
        )
        run_id = int(res.lastrowid)

        inserted = 0
        for source, cands in candidates.items():
            for it in extracted.get(source, []):
                idx = it.get("candidate_index")
                if not isinstance(idx, int) or not (0 <= idx < len(cands)):
                    continue
                cand = cands[idx]
                content = (it.get("content") or "").strip()
                if not content:
                    continue
                chash = _text_hash(f'{source}\x00{cand["source_ref"]}\x00{content}')
                res_i = session.execute(
                    text(
                        """
                        INSERT IGNORE INTO tacit_knowledge_items
                          (run_id, source, source_ref, source_detail, title, content, content_hash)
                        VALUES (:run, :src, :ref, :det, :title, :content, :hash)
                        """
                    ),
                    {
                        "run": run_id, "src": source, "ref": cand["source_ref"],
                        "det": json.dumps(cand.get("detail") or {}, ensure_ascii=False),
                        "title": (it.get("title") or content[:60])[:255],
                        "content": content, "hash": chash,
                    },
                )
                inserted += res_i.rowcount or 0

            # 走査した候補はすべて処理済みとして記録する(知見が無かった投稿も次回スキップする)
            for cand in cands:
                session.execute(
                    text(
                        """
                        INSERT INTO tacit_processed_refs (source, source_ref, content_hash, processed_at)
                        VALUES (:src, :ref, :hash, :t)
                        ON DUPLICATE KEY UPDATE
                          content_hash = VALUES(content_hash), processed_at = VALUES(processed_at)
                        """
                    ),
                    {"src": source, "ref": cand["source_ref"], "hash": _text_hash(cand["text"]), "t": now},
                )
        session.commit()
        return {"run_id": run_id, "stats": stats, "inserted_count": inserted}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def save_run_empty(model: str) -> dict[str, Any]:
    """抽出対象が 0 件だった場合の run 記録。"""
    session = _new_session()
    try:
        stats = {"scanned": {}, "extracted": {}}
        session.execute(
            text("INSERT INTO tacit_extract_runs (model, stats, status) VALUES (:m, :s, 'success')"),
            {"m": model, "s": json.dumps(stats, ensure_ascii=False)},
        )
        session.commit()
        return {"run_id": None, "stats": stats, "inserted_count": 0}
    finally:
        session.close()


# ----------------------------------------------------------------------
# 画面向け: 一覧取得・評価
# ----------------------------------------------------------------------
def _item_row(r: Any) -> dict[str, Any]:
    return {
        "id": r.id,
        "source": r.source,
        "source_ref": r.source_ref,
        "source_detail": _json_col(r.source_detail) or {},
        "title": r.title,
        "content": r.content,
        "rating": r.rating,
        "predicted_rating": r.predicted_rating,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


_ITEM_COLUMNS = (
    "id, source, source_ref, source_detail, title, content, rating, predicted_rating, created_at"
)


def list_items(rating: str | None = None, limit: int = 1000) -> list[dict[str, Any]]:
    """暗黙知アイテムの一覧を新しい順で返す。rating で絞り込みできる("unrated" / "0"〜"5")。"""
    session = _new_session()
    try:
        where = ""
        params: dict[str, Any] = {"lim": limit}
        if rating == "unrated":
            where = "WHERE rating IS NULL"
        elif rating not in (None, ""):
            where = "WHERE rating = :r"
            params["r"] = int(rating)
        rows = session.execute(
            text(f"SELECT {_ITEM_COLUMNS} FROM tacit_knowledge_items {where} ORDER BY id DESC LIMIT :lim"),
            params,
        ).all()
        return [_item_row(r) for r in rows]
    finally:
        session.close()


def update_rating(item_id: int, rating: int | None) -> dict[str, Any] | None:
    """画面での★評価を保存する(rating=None で未評価に戻す)。"""
    session = _new_session()
    try:
        exists = session.execute(
            text("SELECT id FROM tacit_knowledge_items WHERE id = :id"), {"id": item_id}
        ).first()
        if not exists:
            return None
        session.execute(
            text("UPDATE tacit_knowledge_items SET rating = :r, rated_at = :t WHERE id = :id"),
            {"r": rating, "t": _now() if rating is not None else None, "id": item_id},
        )
        session.commit()
        row = session.execute(
            text(f"SELECT {_ITEM_COLUMNS} FROM tacit_knowledge_items WHERE id = :id"),
            {"id": item_id},
        ).first()
        return _item_row(row)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ----------------------------------------------------------------------
# 評価値学習: 教師データ収集・予測結果の反映
# ----------------------------------------------------------------------
def fetch_rated_items() -> list[dict[str, Any]]:
    """★評価済み(rating が設定済み)のアイテムを教師データとして返す。"""
    session = _new_session()
    try:
        rows = session.execute(
            text("SELECT id, content, rating FROM tacit_knowledge_items WHERE rating IS NOT NULL")
        ).all()
        return [{"id": r.id, "content": r.content, "rating": r.rating} for r in rows]
    finally:
        session.close()


def fetch_unrated_unscored_items(limit: int = 2000) -> list[dict[str, Any]]:
    """未評価かつ、まだ AI 予測も付いていないアイテム(抽出直後のスコアリング対象)。"""
    session = _new_session()
    try:
        rows = session.execute(
            text(
                """
                SELECT id, content FROM tacit_knowledge_items
                WHERE rating IS NULL AND predicted_rating IS NULL
                ORDER BY id LIMIT :lim
                """
            ),
            {"lim": limit},
        ).all()
        return [{"id": r.id, "content": r.content} for r in rows]
    finally:
        session.close()


def fetch_all_unrated_items(limit: int = 5000) -> list[dict[str, Any]]:
    """未評価の全アイテム(学習し直した後、最新モデルで一括再スコアリングする対象)。"""
    session = _new_session()
    try:
        rows = session.execute(
            text("SELECT id, content FROM tacit_knowledge_items WHERE rating IS NULL ORDER BY id LIMIT :lim"),
            {"lim": limit},
        ).all()
        return [{"id": r.id, "content": r.content} for r in rows]
    finally:
        session.close()


def bulk_update_predicted_rating(pairs: list[tuple[int, float]]) -> int:
    """[(item_id, predicted_rating), ...] をまとめて反映する。"""
    if not pairs:
        return 0
    session = _new_session()
    try:
        for item_id, pred in pairs:
            session.execute(
                text("UPDATE tacit_knowledge_items SET predicted_rating = :p WHERE id = :id"),
                {"p": pred, "id": item_id},
            )
        session.commit()
        return len(pairs)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ----------------------------------------------------------------------
# 評価値学習: 実行管理(バックグラウンドタスクの進捗をポーリングで確認する)
# ----------------------------------------------------------------------
def running_training_run_id() -> int | None:
    """実行中の学習 run があればその id。"""
    session = _new_session()
    try:
        row = session.execute(
            text("SELECT id FROM tacit_training_runs WHERE status = 'running' ORDER BY id DESC LIMIT 1")
        ).first()
        return int(row.id) if row else None
    finally:
        session.close()


def create_training_run() -> int:
    session = _new_session()
    try:
        res = session.execute(text("INSERT INTO tacit_training_runs (status) VALUES ('running')"))
        session.commit()
        return int(res.lastrowid)
    finally:
        session.close()


def finish_training_run(
    run_id: int,
    *,
    status: str,
    algorithm: str = "",
    training_item_count: int = 0,
    feature_dim: int = 0,
    model_path: str | None = None,
    metrics: dict[str, Any] | None = None,
    detail: str | None = None,
    ratings_hash: str | None = None,
) -> None:
    """学習 run を終了状態にする(成功 / 失敗)。"""
    session = _new_session()
    try:
        session.execute(
            text(
                """
                UPDATE tacit_training_runs
                SET status = :st, algorithm = :algo, training_item_count = :tic,
                    feature_dim = :fd, model_path = :mp, metrics = :m, detail = :d,
                    ratings_hash = :rh, finished_at = :t
                WHERE id = :id
                """
            ),
            {
                "st": status, "algo": algorithm, "tic": training_item_count, "fd": feature_dim,
                "mp": model_path, "m": json.dumps(metrics or {}, ensure_ascii=False),
                "d": (detail or None) and detail[:60000], "rh": ratings_hash, "t": _now(), "id": run_id,
            },
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def hash_rated_pairs(items: list[dict[str, Any]]) -> str:
    """評価済みアイテムの (id, rating) 集合から、学習要否判定用のハッシュを作る(純粋関数)。

    学習に使った内容(items: [{"id","rating",...}])から直接計算するため、
    実際に学習した内容とハッシュが必ず一致する。
    """
    h = hashlib.sha256()
    for it in sorted(items, key=lambda x: x["id"]):
        h.update(f'{it["id"]}:{it["rating"]}\n'.encode("utf-8"))
    return h.hexdigest()


def get_latest_successful_ratings_hash() -> str | None:
    """直近で学習に成功した際の評価内容ハッシュ(無ければ None)。"""
    session = _new_session()
    try:
        row = session.execute(
            text(
                """
                SELECT ratings_hash FROM tacit_training_runs
                WHERE status = 'success' AND ratings_hash IS NOT NULL
                ORDER BY id DESC LIMIT 1
                """
            )
        ).first()
        return row.ratings_hash if row else None
    finally:
        session.close()


def _training_run_row(r: Any) -> dict[str, Any]:
    return {
        "id": r.id,
        "status": r.status,
        "algorithm": r.algorithm,
        "training_item_count": r.training_item_count,
        "feature_dim": r.feature_dim,
        "metrics": _json_col(r.metrics) or {},
        "model_path": r.model_path,
        "detail": r.detail,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
    }


_TRAINING_RUN_COLUMNS = (
    "id, status, algorithm, training_item_count, feature_dim, metrics, model_path, detail, "
    "started_at, finished_at"
)


def get_training_run(run_id: int) -> dict[str, Any] | None:
    session = _new_session()
    try:
        row = session.execute(
            text(f"SELECT {_TRAINING_RUN_COLUMNS} FROM tacit_training_runs WHERE id = :id"),
            {"id": run_id},
        ).first()
        return _training_run_row(row) if row else None
    finally:
        session.close()


def get_latest_training_run() -> dict[str, Any] | None:
    session = _new_session()
    try:
        row = session.execute(
            text(f"SELECT {_TRAINING_RUN_COLUMNS} FROM tacit_training_runs ORDER BY id DESC LIMIT 1")
        ).first()
        return _training_run_row(row) if row else None
    finally:
        session.close()


def list_training_runs(limit: int = 30) -> list[dict[str, Any]]:
    session = _new_session()
    try:
        rows = session.execute(
            text(f"SELECT {_TRAINING_RUN_COLUMNS} FROM tacit_training_runs ORDER BY id DESC LIMIT :lim"),
            {"lim": limit},
        ).all()
        return [_training_run_row(r) for r in rows]
    finally:
        session.close()


def get_latest_successful_model_path() -> str | None:
    """直近で学習に成功したモデルのファイルパス(無ければ None)。"""
    session = _new_session()
    try:
        row = session.execute(
            text(
                """
                SELECT model_path FROM tacit_training_runs
                WHERE status = 'success' AND model_path IS NOT NULL
                ORDER BY id DESC LIMIT 1
                """
            )
        ).first()
        return row.model_path if row else None
    finally:
        session.close()


def list_runs(limit: int = 30) -> list[dict[str, Any]]:
    session = _new_session()
    try:
        rows = session.execute(
            text(
                """
                SELECT id, model, stats, status, created_at
                FROM tacit_extract_runs ORDER BY id DESC LIMIT :lim
                """
            ),
            {"lim": limit},
        ).all()
        return [
            {
                "id": r.id, "model": r.model, "stats": _json_col(r.stats) or {},
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    finally:
        session.close()
