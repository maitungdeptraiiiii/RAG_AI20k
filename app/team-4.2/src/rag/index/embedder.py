"""Embedding cho Dense retrieval — TV3.

    JinaEmbedder    jina-embeddings-v5-text-small (1024 chiều) qua Jina API — MẶC ĐỊNH. Embed
                    query (task retrieval.query) và chunk (retrieval.passage) khác nhau; chia batch,
                    retry khi 429/5xx, cache SQLite. Key đọc từ JINA_API_KEY.
    OpenAIEmbedder  text-embedding-3-small (1536 chiều) qua SDK `openai`; chia batch,
                    retry khi bị rate limit / timeout / lỗi kết nối, cache SQLite.
    HashEmbedder    embedder giả, tất định, không gọi mạng — dùng cho unit test của mọi module.
    make_embedder   chọn embedder theo tên model ("jina-*" -> Jina, còn lại -> OpenAI).

Query và chunk dùng CÙNG một model, đưa text gốc (NFC), không đưa text đã tách từ bằng pyvi.
Embedder nào có `embed_query` thì VectorIndex dùng nó cho câu hỏi, `embed` cho chunk.

Vì sao Jina: trên 40 câu benchmark_6_bo_luat, dense-only recall@5 0.600 -> 0.871 (paraphrase
0.375 -> 0.938); trên 20 câu văn nói benchmark_doi_thuong 0.100 -> 0.425.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import sqlite3
import threading
import time
from array import array
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

from rag.schema import nfc

log = logging.getLogger(__name__)

DEFAULT_EMBED_MODEL = "jina-embeddings-v5-text-small"
DEFAULT_EMBED_DIM = 1024
OPENAI_EMBED_MODEL = "text-embedding-3-small"
OPENAI_EMBED_DIM = 1536
JINA_URL = "https://api.jina.ai/v1/embeddings"


class Embedder(Protocol):
    """`embed` dùng cho chunk. Embedder bất đối xứng (Jina) có thêm `embed_query` cho câu hỏi."""

    model_id: str
    dim: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def embed_queries(embedder: Embedder, texts: Sequence[str]) -> list[list[float]]:
    """Embed câu hỏi: dùng `embed_query` nếu embedder có, không thì `embed`."""
    fn = getattr(embedder, "embed_query", None)
    return fn(texts) if callable(fn) else embedder.embed(texts)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class EmbeddingCache:
    """SQLite: key = sha256(model, text) -> vector float32. Chạy lại ingest/eval không tốn tiền."""

    def __init__(self, path: Path | str = ":memory:") -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS embeddings (key TEXT PRIMARY KEY, vec BLOB NOT NULL)"
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @staticmethod
    def key(model_id: str, text: str) -> str:
        return hashlib.sha256(f"{model_id}\x00{text}".encode("utf-8")).hexdigest()

    def get_many(self, keys: Sequence[str]) -> dict[str, list[float]]:
        out: dict[str, list[float]] = {}
        for start in range(0, len(keys), 500):           # giới hạn số tham số của SQLite
            part = list(keys[start : start + 500])
            marks = ",".join("?" * len(part))
            with self._lock:
                rows = self._conn.execute(
                    f"SELECT key, vec FROM embeddings WHERE key IN ({marks})", part
                ).fetchall()
            for key, blob in rows:
                out[key] = array("f", blob).tolist()
        return out

    def put_many(self, items: dict[str, list[float]]) -> None:
        if not items:
            return
        rows = [(k, array("f", v).tobytes()) for k, v in items.items()]
        with self._lock:
            self._conn.executemany("INSERT OR REPLACE INTO embeddings (key, vec) VALUES (?, ?)", rows)
            self._conn.commit()


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------


def _openai_retryable() -> tuple[type[BaseException], ...]:
    import openai

    return (
        openai.RateLimitError,
        openai.APITimeoutError,
        openai.APIConnectionError,
        openai.InternalServerError,
    )


class OpenAIEmbedder:
    """Key đọc từ OPENAI_API_KEY (SDK tự đọc). `client`, `retry_on`, `sleep` cho phép thay khi test."""

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
        sleep: Callable[[float], None] = time.sleep,
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

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI()
        return self._client

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        texts = [nfc(t) for t in texts]
        if any(not t.strip() for t in texts):
            raise ValueError("Không embed được text rỗng")
        if not texts:
            return []

        keys = [EmbeddingCache.key(self.model_id, t) for t in texts]
        found = self.cache.get_many(keys) if self.cache else {}
        todo = [i for i, k in enumerate(keys) if k not in found]

        fresh: dict[str, list[float]] = {}
        for start in range(0, len(todo), self.batch_size):
            idxs = todo[start : start + self.batch_size]
            vectors = self._call([texts[i] for i in idxs])
            for i, v in zip(idxs, vectors):
                fresh[keys[i]] = v
        if self.cache:
            self.cache.put_many(fresh)
        found.update(fresh)
        return [found[k] for k in keys]

    def _call(self, batch: list[str]) -> list[list[float]]:
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
        data = sorted(resp.data, key=lambda d: d.index)
        vectors = [list(d.embedding) for d in data]
        if len(vectors) != len(batch):
            raise RuntimeError(f"OpenAI trả {len(vectors)} vector cho {len(batch)} text")
        bad = {len(v) for v in vectors if len(v) != self.dim}
        if bad:
            raise RuntimeError(f"Vector có số chiều {bad}, cấu hình dim={self.dim}")
        return vectors


# ---------------------------------------------------------------------------
# Jina
# ---------------------------------------------------------------------------


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


class JinaEmbedder:
    """Jina Embeddings API. Chunk embed với task `retrieval.passage`, câu hỏi với `retrieval.query`.

    Key: tham số `api_key` hoặc biến môi trường JINA_API_KEY. `post`, `sleep` cho phép thay khi test.
    Cache key gồm cả task, nên vector query và passage của cùng một text không lẫn nhau.
    """

    PASSAGE_TASK = "retrieval.passage"
    QUERY_TASK = "retrieval.query"
    RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
    _rate_lock = threading.Lock()
    _last_req_time: float = 0.0

    def __init__(
        self,
        model_id: str = DEFAULT_EMBED_MODEL,
        dim: int = DEFAULT_EMBED_DIM,
        *,
        cache: EmbeddingCache | None = None,
        api_key: str | None = None,
        batch_size: int = 32,
        max_retries: int = 6,
        timeout: float = 120.0,
        min_interval: float = 0.35,
        post: Callable[[str, dict[str, Any], str, float], dict[str, Any]] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if batch_size < 1 or max_retries < 0:
            raise ValueError("batch_size phải >= 1, max_retries phải >= 0")
        self.model_id, self.dim = model_id, dim
        self.cache = cache
        self._api_key = api_key
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.timeout = timeout
        self.min_interval = min_interval
        self._post = post or _jina_post
        self._sleep = sleep

    def _key(self) -> str:
        import os

        key = self._api_key or os.environ.get("JINA_API_KEY")
        if not key:
            raise RuntimeError("Thiếu JINA_API_KEY (đặt trong .env) cho embedder Jina")
        return key

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed(texts, self.PASSAGE_TASK)

    def embed_query(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed(texts, self.QUERY_TASK)

    def _embed(self, texts: Sequence[str], task: str) -> list[list[float]]:
        texts = [nfc(t) for t in texts]
        if any(not t.strip() for t in texts):
            raise ValueError("Không embed được text rỗng")
        if not texts:
            return []
        keys = [EmbeddingCache.key(f"{self.model_id}#{task}", t) for t in texts]
        found = self.cache.get_many(keys) if self.cache else {}
        todo = [i for i, k in enumerate(keys) if k not in found]
        for start in range(0, len(todo), self.batch_size):
            idxs = todo[start : start + self.batch_size]
            fresh = dict(zip((keys[i] for i in idxs), self._call([texts[i] for i in idxs], task)))
            if self.cache:
                self.cache.put_many(fresh)    # ghi theo từng batch: lỗi giữa chừng không mất phần đã trả tiền
            found.update(fresh)
        return [found[k] for k in keys]

    def _call(self, batch: list[str], task: str) -> list[list[float]]:
        payload = {"model": self.model_id, "task": task, "input": batch, "normalized": True}
        for attempt in range(self.max_retries + 1):
            try:
                with JinaEmbedder._rate_lock:
                    if self.min_interval > 0:
                        elapsed = time.time() - JinaEmbedder._last_req_time
                        if elapsed < self.min_interval:
                            self._sleep(self.min_interval - elapsed)
                    data = self._post(JINA_URL, payload, self._key(), self.timeout)
                    JinaEmbedder._last_req_time = time.time()
                break
            except JinaHTTPError as e:
                if e.status not in self.RETRY_STATUS or attempt == self.max_retries:
                    raise
                wait = min(3 * 2**attempt, 60)
                log.warning("Jina lỗi (%s), thử lại sau %ss", e.status, wait)
                self._sleep(wait)
        items = sorted(data["data"], key=lambda d: d["index"])
        vectors = [list(d["embedding"]) for d in items]
        if len(vectors) != len(batch):
            raise RuntimeError(f"Jina trả {len(vectors)} vector cho {len(batch)} text")
        bad = {len(v) for v in vectors if len(v) != self.dim}
        if bad:
            raise RuntimeError(f"Vector có số chiều {bad}, cấu hình dim={self.dim}")
        return vectors


def make_embedder(model_id: str, dim: int, *, cache: EmbeddingCache | None = None,
                  jina_api_key: str | None = None) -> Embedder:
    """`jina-*` -> JinaEmbedder, còn lại -> OpenAIEmbedder (text-embedding-3-*)."""
    if model_id.startswith("jina-"):
        return JinaEmbedder(model_id, dim, cache=cache, api_key=jina_api_key)
    return OpenAIEmbedder(model_id, dim, cache=cache)


# ---------------------------------------------------------------------------
# Embedder giả cho test
# ---------------------------------------------------------------------------


class HashEmbedder:
    """Băm từng âm tiết vào `dim` chiều rồi chuẩn hoá L2. Chung nhiều âm tiết -> cosine cao.

    Không hiểu nghĩa (không phải embedding thật); chỉ để test luồng dữ liệu không cần mạng.
    """

    def __init__(self, dim: int = 64, model_id: str | None = None) -> None:
        self.dim = dim
        self.model_id = model_id or f"hash-{dim}"
        self.calls: list[list[str]] = []   # để test kiểm tra số lần gọi

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for tok in re.findall(r"\w+", nfc(text).lower()):
            h = int(hashlib.sha1(tok.encode("utf-8")).hexdigest()[:8], 16)
            v[h % self.dim] += 1.0 if (h >> 16) & 1 else -1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]


__all__ = [
    "DEFAULT_EMBED_DIM",
    "DEFAULT_EMBED_MODEL",
    "Embedder",
    "EmbeddingCache",
    "HashEmbedder",
    "JinaEmbedder",
    "JinaHTTPError",
    "OPENAI_EMBED_DIM",
    "OPENAI_EMBED_MODEL",
    "OpenAIEmbedder",
    "embed_queries",
    "make_embedder",
]
