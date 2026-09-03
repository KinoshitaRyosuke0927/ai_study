"""埋め込み生成と自然文検索(RAG)。

- 各イベントのテキストを ~800 文字のチャンクへ分割して embeddings に蓄積する
  (週ごとに一度だけ生成し、既存チャンクは再利用してトークンを節約)。
- 検索はクエリを埋め込み、Python 側でコサイン類似度 top-k を抽出してから
  チャットモデルに渡して回答を生成する。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ai import AiAnalyzer
from vectors import cosine, from_blob, to_blob

logger = logging.getLogger(__name__)

CHUNK_SIZE = 800


def _event_text(etype: str, payload: dict[str, Any]) -> str:
    """イベント種別に応じて埋め込み対象テキストを組み立てる。"""
    if etype == "post":
        return payload.get("text", "")
    if etype == "commit":
        return payload.get("message", "")
    if etype.startswith("page_"):
        return f"{payload.get('title', '')} {payload.get('path', '')}".strip()
    # card_* / pr_* / issue_*
    return payload.get("title", "")


def _chunks(s: str, size: int = CHUNK_SIZE) -> list[str]:
    """文字列を size 文字ごとに分割する。"""
    s = s.strip()
    if not s:
        return []
    return [s[i : i + size] for i in range(0, len(s), size)]


def build_and_store_embeddings(
    session: Session, analyzer: AiAnalyzer, week: str
) -> int:
    """指定週のイベントテキストを埋め込み、embeddings へ保存する。

    Returns:
        新規に保存したチャンク数。
    """
    # 既に生成済みのチャンク ID を取得(再生成を避ける)
    existing = set(
        session.execute(
            text("SELECT chunk_id FROM embeddings WHERE week = :w"), {"w": week}
        ).scalars()
    )
    rows = session.execute(
        text(
            """
            SELECT source, ref, type, payload
            FROM events
            WHERE week = :w
            ORDER BY ts ASC, id ASC
            """
        ),
        {"w": week},
    ).all()

    pending: list[tuple[str, str, str, str]] = []  # (chunk_id, source, ref, text)
    for source, ref, etype, payload_raw in rows:
        payload = payload_raw if isinstance(payload_raw, dict) else json.loads(payload_raw or "{}")
        body = _event_text(etype, payload)
        for idx, chunk in enumerate(_chunks(body)):
            chunk_id = f"{source}:{ref}:{idx}"
            if chunk_id in existing:
                continue
            pending.append((chunk_id, source, ref, chunk))

    if not pending:
        logger.info("embeddings: 新規チャンクなし (week=%s)", week)
        return 0

    vectors, model = analyzer.embed_texts([p[3] for p in pending])
    stmt = text(
        """
        INSERT INTO embeddings (chunk_id, week, source, ref, text, vec, model)
        VALUES (:chunk_id, :week, :source, :ref, :text, :vec, :model)
        ON DUPLICATE KEY UPDATE text = VALUES(text), vec = VALUES(vec), model = VALUES(model)
        """
    )
    for (chunk_id, source, ref, chunk), vec in zip(pending, vectors):
        session.execute(
            stmt,
            {
                "chunk_id": chunk_id,
                "week": week,
                "source": source,
                "ref": ref,
                "text": chunk,
                "vec": to_blob(vec),
                "model": model,
            },
        )
    logger.info("embeddings 保存: %d チャンク (week=%s, model=%s)", len(pending), week, model)
    return len(pending)


def search(
    session: Session, analyzer: AiAnalyzer, query: str, k: int = 6
) -> dict[str, Any]:
    """自然文クエリに対する RAG 検索を行い、回答と出典を返す。"""
    query = (query or "").strip()
    if not query:
        return {"answer": "クエリが空です。", "sources": []}

    qvec, _model = analyzer.embed_query(query)
    rows = session.execute(
        text("SELECT chunk_id, week, source, ref, text, vec FROM embeddings")
    ).all()
    if not rows:
        return {"answer": "まだ埋め込みが生成されていません。パイプラインを実行してください。", "sources": []}

    # Python 側でコサイン類似度 top-k を抽出する
    scored: list[tuple[float, dict[str, Any]]] = []
    for chunk_id, week, source, ref, chunk_text, vec_blob in rows:
        score = cosine(qvec, from_blob(vec_blob))
        scored.append(
            (
                score,
                {
                    "chunk_id": chunk_id,
                    "week": week,
                    "source": source,
                    "ref": ref,
                    "text": chunk_text,
                    "score": round(score, 4),
                },
            )
        )
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [item for _score, item in scored[:k]]

    answer = analyzer.answer_with_context(query, top)
    return {"answer": answer, "sources": top}
