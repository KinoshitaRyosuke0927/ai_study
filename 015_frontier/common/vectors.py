"""埋め込みベクトルのシリアライズとコサイン類似度計算。

MySQL には pgvector 相当が無いため、float32 配列を BLOB 化して保存し、
類似検索はアプリ側で行う。
"""

from __future__ import annotations

import hashlib
import math
from array import array

_HASH_DIM = 512  # フォールバック埋め込みの次元数


def to_blob(vec: list[float]) -> bytes:
    """float のリストを float32 のバイト列へ変換する。"""
    return array("f", vec).tobytes()


def from_blob(blob: bytes) -> list[float]:
    """float32 バイト列を float のリストへ復元する。"""
    a = array("f")
    a.frombytes(blob)
    return list(a)


def cosine(a: list[float], b: list[float]) -> float:
    """2 ベクトルのコサイン類似度([-1, 1])。長さ不一致や 0 ベクトルは 0。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def hash_embedding(text: str, dim: int = _HASH_DIM) -> list[float]:
    """AI が使えない環境向けの決定的な擬似埋め込み。

    文字 3-gram を SHA1 でハッシュして次元へ振り分け、L2 正規化する。
    厳密な意味は捉えられないが、語の重なりに応じた類似度は得られる。
    """
    vec = [0.0] * dim
    normalized = text.lower()
    grams = [normalized[i : i + 3] for i in range(max(len(normalized) - 2, 1))]
    for gram in grams:
        h = int(hashlib.sha1(gram.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 8) & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec
