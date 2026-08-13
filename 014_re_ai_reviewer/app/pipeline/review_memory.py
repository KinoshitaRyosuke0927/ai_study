from __future__ import annotations

import json
import sys
from difflib import SequenceMatcher
from pathlib import Path

from app.schemas.models import ReviewMemoryEntry

if getattr(sys, "frozen", False):
    _APP_ROOT = Path(sys.executable).resolve().parent
else:
    _APP_ROOT = Path(__file__).resolve().parents[2]

_REVIEW_LOG_PATH = _APP_ROOT / "data" / "review_log.jsonl"

# 過去レビュー指摘ログの整備（スライド要約付きで指摘事項を再構造化する作業）が別途進行中のため、
# review_log.jsonl は当面空のままでもパイプライン全体が動作するよう、本モジュールは
# 「0件ヒットならヒントなしで先に進む」フォールバック実装にしている。
# データが揃い次第、ReviewMemoryEntry のスキーマに沿って1行1件で追記していけば、
# 以降は自動的に候補生成・critic層のプロンプトに反映される。


def _load_entries() -> list[ReviewMemoryEntry]:
    """
    review_log.jsonl から過去レビュー指摘ログを読み込む（ファイルが無い/空でも空リストを返す）

    Returns
    -----------------
    - entries: list[ReviewMemoryEntry],   読み込んだログエントリのリスト

    """
    if not _REVIEW_LOG_PATH.exists():
        return []

    entries: list[ReviewMemoryEntry] = []
    with _REVIEW_LOG_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(ReviewMemoryEntry(**json.loads(line)))
            except (json.JSONDecodeError, TypeError, ValueError):
                # 壊れた1行があっても全体を止めない
                continue
    return entries


def retrieve_similar_comments(query_text: str, top_k: int = 5) -> list[str]:
    """
    資料全体の要約テキストに対して、類似する過去レビュー指摘を検索する

    ベクトル検索は導入せず、簡易キーワード類似度（SequenceMatcher）で代用する。
    ログが0件の場合は空リストを返し、候補生成層はヒントなしで動作する。

    Args
    -----------------
    - query_text: str,   検索クエリ（資料全体の意図やスライド要約テキスト）
    - top_k: int,        取得する上位件数

    Returns
    -----------------
    - hints: list[str],  「カテゴリ: 指摘文」形式の参考テキストリスト（0件の場合は空リスト）

    """
    entries = _load_entries()
    if not entries or not query_text:
        return []

    scored = [
        (SequenceMatcher(None, query_text, entry.slide_summary).ratio(), entry)
        for entry in entries
    ]
    scored.sort(key=lambda x: x[0], reverse=True)

    return [f"[{entry.category}] {entry.comment}" for _, entry in scored[:top_k]]


def append_entry(entry: ReviewMemoryEntry) -> None:
    """
    過去レビュー指摘ログに1件追記する（データ整備が進んだ際の取り込み口として用意）

    Args
    -----------------
    - entry: ReviewMemoryEntry,   追記するログエントリ

    """
    _REVIEW_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _REVIEW_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry.model_dump(), ensure_ascii=False) + "\n")
