"""Embedding cho Dense retrieval — TV3.

    OpenAIEmbedder  text-embedding-3-small (1536 chiều) qua SDK `openai`; chia batch,
                    retry khi bị rate limit / timeout / lỗi kết nối, cache SQLite.
    HashEmbedder    embedder giả, tất định, không gọi mạng — dùng cho unit test của mọi module.

Query và chunk dùng CÙNG một embedder, đưa text gốc (NFC), không đưa text đã tách từ bằng pyvi.
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

DEFAULT_EMBED_MODEL = "text-embedding-3-small"
DEFAULT_EMBED_DIM = 1536


class Embedder(Protocol):
    model_id: str
    dim: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


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
        model_id: str = DEFAULT_EMBED_MODEL,
        dim: int = DEFAULT_EMBED_DIM,
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
    "OpenAIEmbedder",
]
