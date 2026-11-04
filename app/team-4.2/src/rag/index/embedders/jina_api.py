"""Jina Embeddings API. Chunk embed với task `retrieval.passage`, câu hỏi với `retrieval.query`."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Sequence
from typing import Any

from rag.index.embedders.base import CachedEmbedder, EmbeddingCache, SleepFn

log = logging.getLogger(__name__)

JINA_URL = "https://api.jina.ai/v1/embeddings"


class JinaHTTPError(RuntimeError):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"Jina API trả HTTP {status}: {body[:300]}")
        self.status = status


def _jina_post(url: str, payload: dict[str, Any], api_key: str, timeout: float) -> dict[str, Any]:
    import requests

    resp = requests.post(
        url, json=payload, timeout=timeout,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    if resp.status_code != 200:
        raise JinaHTTPError(resp.status_code, resp.text)
    return resp.json()


class JinaEmbedder(CachedEmbedder):
    """Key: tham số `api_key` hoặc biến môi trường JINA_API_KEY. `post`, `sleep` cho phép thay khi test.

    Cache key gồm cả task, nên vector query và passage của cùng một text không lẫn nhau.
    """

    PASSAGE_TASK = "retrieval.passage"
    QUERY_TASK = "retrieval.query"
    RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
    _TASKS = {"passage": PASSAGE_TASK, "query": QUERY_TASK}

    def __init__(
        self,
        model_id: str = "jina-embeddings-v5-text-small",
        dim: int = 1024,
        *,
        cache: EmbeddingCache | None = None,
        api_key: str | None = None,
        batch_size: int = 32,
        max_retries: int = 6,
        timeout: float = 120.0,
        post: Callable[[str, dict[str, Any], str, float], dict[str, Any]] | None = None,
        sleep: SleepFn = time.sleep,
    ) -> None:
        if batch_size < 1 or max_retries < 0:
            raise ValueError("batch_size phải >= 1, max_retries phải >= 0")
        self.model_id, self.dim = model_id, dim
        self.cache = cache
        self._api_key = api_key
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.timeout = timeout
        self._post = post or _jina_post
        self._sleep = sleep

    def _key(self) -> str:
        key = self._api_key or os.environ.get("JINA_API_KEY")
        if not key:
            raise RuntimeError("Thiếu JINA_API_KEY (đặt trong .env) cho embedder Jina")
        return key

    def embed_query(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed(texts, "query")

    def _cache_ns(self, kind: str) -> str:
        return f"{self.model_id}#{self._TASKS[kind]}"      # giữ key cũ: "<model>#retrieval.passage"

    def _call(self, batch: list[str], kind: str) -> list[list[float]]:
        task = self._TASKS[kind]
        payload = {"model": self.model_id, "task": task, "input": batch, "normalized": True}
        for attempt in range(self.max_retries + 1):
            try:
                data = self._post(JINA_URL, payload, self._key(), self.timeout)
                break
            except JinaHTTPError as e:
                if e.status not in self.RETRY_STATUS or attempt == self.max_retries:
                    raise
                wait = min(3 * 2**attempt, 60)
                log.warning("Jina lỗi (%s), thử lại sau %ss", e.status, wait)
                self._sleep(wait)
        return [list(d["embedding"]) for d in sorted(data["data"], key=lambda d: d["index"])]
