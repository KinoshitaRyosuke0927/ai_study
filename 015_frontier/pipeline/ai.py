"""Azure OpenAI による埋め込み生成。

各機能(Mattermost / Trello / 変更履歴 / GitHub 活動)がチャンクをベクトル化して
embeddings テーブルへ蓄積する際に使う。Azure OpenAI が未設定の環境では、
決定的なハッシュ埋め込みへフォールバックする。
"""

from __future__ import annotations

import logging

from config.settings import Settings
from common.vectors import hash_embedding

logger = logging.getLogger(__name__)


class AiAnalyzer:
    """Azure OpenAI の埋め込み呼び出しをまとめたクラス(未設定時はフォールバック)。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.enabled = settings.ai_enabled
        self._embed_model = settings.azure_openai_embedding_deployment
        self._client = None
        if self.enabled:
            try:
                from openai import AzureOpenAI

                self._client = AzureOpenAI(
                    azure_endpoint=settings.azure_openai_endpoint,
                    api_key=settings.azure_openai_api_key,
                    api_version=settings.azure_openai_api_version,
                )
                logger.info("Azure OpenAI クライアント初期化完了")
            except Exception as exc:  # pragma: no cover - 初期化失敗時
                logger.error("Azure OpenAI 初期化失敗。フォールバックへ: %s", exc)
                self.enabled = False

    def embed_texts(self, texts: list[str]) -> tuple[list[list[float]], str]:
        """テキスト群を埋め込みベクトルへ変換する。

        Returns:
            (ベクトルのリスト, 使用モデル名)。
        """
        if not texts:
            return [], self._embed_model if self.enabled else "hash-fallback"
        if self.enabled:
            for attempt in range(2):  # 初回 + リトライ 1 回
                try:
                    resp = self._client.embeddings.create(  # type: ignore[union-attr]
                        model=self._embed_model, input=texts
                    )
                    return [d.embedding for d in resp.data], self._embed_model
                except Exception as exc:
                    logger.error("埋め込み呼び出し失敗 (attempt=%d): %s", attempt + 1, exc)
        # フォールバック: 決定的なハッシュ埋め込み
        return [hash_embedding(t) for t in texts], "hash-fallback"
