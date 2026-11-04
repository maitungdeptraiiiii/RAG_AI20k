"""OpenAI Embeddings (text-embedding-3-*) qua SDK `openai`. Key đọc từ OPENAI_API_KEY."""

from __future__ import annotations

import logging
import time
from typing import Any

from rag.index.embedders.base import CachedEmbedder, EmbeddingCache, SleepFn

log = logging.getLogger(__name__)

OPENAI_EMBED_MODEL = "text-embedding-3-small"
OPENAI_EMBED_DIM = 1536


def _openai_retryable() -> tuple[type[BaseException], ...]:
    import openai

    return (
        openai.RateLimitError,
        openai.APITimeoutError,
        openai.APIConnectionError,
        openai.InternalServerError,
    )


class OpenAIEmbedder(CachedEmbedder):
    """Đối xứng: query và chunk embed giống nhau. `client`, `retry_on`, `sleep` cho phép thay khi test."""

    def __init__(
        self,
        model_id: str = OPENAI_EMBED_MODEL,
        dim: int = OPENAI_EMBED_DIM,
        *,
        cache: EmbeddingCache | None = None,
        batch_size: int = 64,
        max_retries: int = 6,
        client: Any = None,
        retry_on: tuple[type[BaseException], ...] | None = None,
        sleep: SleepFn = time.sleep,
    ) -> None:
        if batch_size < 1 or max_retries < 0:
            raise ValueError("batch_size phải >= 1, max_retries phải >= 0")
        self.model_id, self.dim = model_id, dim
        self.cache = cache
        self.batch_size = batch_size
        self.max_retries = max_retries
        self._client = client
        self._retry_on = retry_on
        self._sleep = sleep

    def _cache_ns(self, kind: str) -> str:
        return self.model_id               # key cũ (không có #kind) — giữ để không mất cache đã trả tiền

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI()
        return self._client

    def _call(self, batch: list[str], kind: str) -> list[list[float]]:
        retry_on = self._retry_on if self._retry_on is not None else _openai_retryable()
        client = self._get_client()
        for attempt in range(self.max_retries + 1):
            try:
                resp = client.embeddings.create(model=self.model_id, input=batch)
                break
            except retry_on as e:
                if attempt == self.max_retries:
                    raise
                wait = min(2**attempt, 30)
                log.warning("Embedding lỗi (%r), thử lại sau %ss", e, wait)
                self._sleep(wait)
        return [list(d.embedding) for d in sorted(resp.data, key=lambda d: d.index)]
