"""Phần chung cho mọi embedder: Protocol, cache SQLite, lớp cơ sở có cache + chia batch."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from array import array
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from rag.schema import nfc


class Embedder(Protocol):
    """`embed` dùng cho chunk. Embedder bất đối xứng (Jina, E5) có thêm `embed_query` cho câu hỏi."""

    model_id: str
    dim: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def embed_queries(embedder: Embedder, texts: Sequence[str]) -> list[list[float]]:
    """Embed câu hỏi: dùng `embed_query` nếu embedder có, không thì `embed`."""
    fn = getattr(embedder, "embed_query", None)
    return fn(texts) if callable(fn) else embedder.embed(texts)


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


class CachedEmbedder:
    """Lớp cơ sở: chuẩn hoá NFC, tra cache, chia batch phần còn thiếu, kiểm tra số chiều.

    Lớp con chỉ cần cài `_call(batch, kind) -> list[vector]`; `kind` là "passage" hoặc "query".
    Lớp con đặt `_cache_ns(kind)` để quyết định namespace cache (giữ nguyên key cũ của từng backend).
    """

    model_id: str
    dim: int
    cache: EmbeddingCache | None
    batch_size: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed(texts, "passage")

    def _cache_ns(self, kind: str) -> str:
        return f"{self.model_id}#{kind}"

    def _call(self, batch: list[str], kind: str) -> list[list[float]]:
        raise NotImplementedError

    def _embed(self, texts: Sequence[str], kind: str) -> list[list[float]]:
        texts = [nfc(t) for t in texts]
        if any(not t.strip() for t in texts):
            raise ValueError("Không embed được text rỗng")
        if not texts:
            return []
        ns = self._cache_ns(kind)
        keys = [EmbeddingCache.key(ns, t) for t in texts]
        found = self.cache.get_many(keys) if self.cache else {}
        todo = [i for i, k in enumerate(keys) if k not in found]
        for start in range(0, len(todo), self.batch_size):
            idxs = todo[start : start + self.batch_size]
            vectors = self._call([texts[i] for i in idxs], kind)
            self._check(vectors, len(idxs))
            fresh = dict(zip((keys[i] for i in idxs), vectors))
            if self.cache:
                self.cache.put_many(fresh)    # ghi theo từng batch: lỗi giữa chừng không mất phần đã làm
            found.update(fresh)
        return [found[k] for k in keys]

    def _check(self, vectors: list[list[float]], n: int) -> None:
        if len(vectors) != n:
            raise RuntimeError(f"{self.model_id} trả {len(vectors)} vector cho {n} text")
        bad = {len(v) for v in vectors if len(v) != self.dim}
        if bad:
            raise RuntimeError(f"Vector có số chiều {bad}, cấu hình dim={self.dim}")


SleepFn = Callable[[float], None]
