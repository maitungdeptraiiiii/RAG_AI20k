"""Rerank bằng TypeSafe Jev hoặc Jina Reranker — phần thêm ngoài yêu cầu sprint 1.

    RERANK_BACKEND=jev    TypeSafe Jev (mỗi cặp câu hỏi-chunk một lần gọi, điểm = xác suất [0, 1])
    RERANK_BACKEND=jina   Jina Reranker API (cross-encoder, một request cho cả pool; cần JINA_API_KEY),
                          model mặc định jina-reranker-v2-base-multilingual, đổi bằng RERANK_MODEL.
                          Điểm là relevance_score của Jina — thang KHÁC Jev, phải chọn lại CONTEXT_MIN_P.

    RRF top-20 Hit(fused) -> JevReranker -> top-5 Hit(rerank, score = xác suất liên quan [0, 1])

- Mỗi cặp (câu hỏi, chunk) là một câu hỏi Noul "Đoạn văn chứa thông tin trả lời trực tiếp câu hỏi";
  các cặp gọi song song bằng thread.
- Cache điểm trong SQLite theo (model, câu hỏi, chunk_id, text chunk).
- Hoà điểm thì xếp theo rank RRF cũ, để kết quả tất định.
- Được bọc trong FallbackReranker: lỗi API / mạng -> giữ nguyên thứ tự RRF (Hit vẫn arm="fused"),
  demo không bị crash và guardrail tự dùng ngưỡng RRF.

`typesafe_sdk` chỉ được import khi thật sự gọi Jev, nên module này import và test được
trên máy chưa cài SDK. Key đọc từ biến môi trường TYPESAFE_API_KEY (SDK tự đọc).
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
import sqlite3
import threading
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from rag.schema import Chunk, Hit, Reranker

log = logging.getLogger(__name__)

DEFAULT_JEV_MODEL = "jev-1.13.0"            # chốt version, KHÔNG dùng "jev-latest"
JEV_INSTRUCTIONS = "Đoạn văn chứa thông tin trả lời trực tiếp câu hỏi"

DEFAULT_JINA_RERANK_MODEL = "jina-reranker-v2-base-multilingual"
JINA_RERANK_URL = "https://api.jina.ai/v1/rerank"

BACKENDS = ("none", "jev", "jina")


class RerankInputError(ValueError):
    """Lỗi do đầu vào sai (bug của code gọi). FallbackReranker không nuốt lỗi này."""


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class ScoreCache:
    """Cache điểm rerank trong SQLite. Dùng chung được giữa nhiều thread (Streamlit)."""

    def __init__(self, path: Path | str = ":memory:") -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS rerank_scores (key TEXT PRIMARY KEY, score REAL NOT NULL)"
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @staticmethod
    def key(model_id: str, query: str, chunk: Chunk) -> str:
        raw = "\x00".join((model_id, query, chunk.chunk_id, chunk.text))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get_many(self, keys: Sequence[str]) -> dict[str, float]:
        if not keys:
            return {}
        marks = ",".join("?" * len(keys))
        with self._lock:
            rows = self._conn.execute(
                f"SELECT key, score FROM rerank_scores WHERE key IN ({marks})", list(keys)
            ).fetchall()
        return dict(rows)

    def put_many(self, items: Mapping[str, float]) -> None:
        if not items:
            return
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO rerank_scores (key, score) VALUES (?, ?)", list(items.items())
            )
            self._conn.commit()


# ---------------------------------------------------------------------------
# Khung chung: chấm điểm từng chunk + cache + sắp xếp
# ---------------------------------------------------------------------------


class ScoringReranker:
    """Lớp con chỉ cần `model_id`, `cache` và `score_pairs(query, chunks) -> list[float]`."""

    name = "base"
    model_id: str
    cache: ScoreCache | None = None

    def score_pairs(self, query: str, chunks: Sequence[Chunk]) -> list[float]:
        raise NotImplementedError

    def rerank(
        self, query: str, hits: list[Hit], chunks: Mapping[str, Chunk], k: int
    ) -> list[Hit]:
        if k < 1:
            raise RerankInputError(f"k phải >= 1, nhận {k}")
        if not hits:
            return []
        missing = [h.chunk_id for h in hits if h.chunk_id not in chunks]
        if missing:
            raise RerankInputError(f"Không tìm thấy chunk cho các hit: {missing[:5]}")

        cands = [chunks[h.chunk_id] for h in hits]
        scores = self._scores_with_cache(query, cands)
        order = sorted(range(len(hits)), key=lambda i: (-scores[i], hits[i].rank))
        return [
            Hit(chunk_id=hits[i].chunk_id, score=scores[i], rank=r, arm="rerank")
            for r, i in enumerate(order[:k], start=1)
        ]

    def _scores_with_cache(self, query: str, cands: list[Chunk]) -> list[float]:
        if self.cache is None:
            return self.score_pairs(query, cands)
        keys = [ScoreCache.key(self.model_id, query, c) for c in cands]
        found = self.cache.get_many(keys)
        todo = [i for i, key in enumerate(keys) if key not in found]
        if todo:
            fresh = self.score_pairs(query, [cands[i] for i in todo])
            new_items = {keys[i]: s for i, s in zip(todo, fresh)}
            self.cache.put_many(new_items)
            found.update(new_items)
        return [found[key] for key in keys]


# ---------------------------------------------------------------------------
# Jev
# ---------------------------------------------------------------------------


class JevReranker(ScoringReranker):
    """`client` và `question` cho phép truyền đối tượng giả khi test."""

    name = "jev"

    def __init__(
        self,
        model_id: str = DEFAULT_JEV_MODEL,
        *,
        cache: ScoreCache | None = None,
        instructions: str = JEV_INSTRUCTIONS,
        max_workers: int = 8,
        client: Any = None,
        question: Any = None,
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers phải >= 1")
        self.model_id = model_id
        self.cache = cache
        self.instructions = instructions
        self.max_workers = max_workers
        self._client = client
        self._question = question

    # --- gọi Jev -------------------------------------------------------------

    def _get_client(self) -> Any:
        if self._client is None:
            from typesafe_sdk import TypeSafeClient

            self._client = TypeSafeClient(model=self.model_id)
        return self._client

    def _get_question(self) -> Any:
        if self._question is None:
            from typesafe_sdk import Noul

            self._question = Noul(instructions=self.instructions)
        return self._question

    @staticmethod
    def build_state(query: str, chunk: Chunk) -> str:
        head = f"Mục: {chunk.section}\n" if chunk.section else ""
        return f"Câu hỏi: {query}\n\nĐoạn văn:\n{head}{chunk.text}"

    def _score_one(self, client: Any, question: Any, query: str, chunk: Chunk) -> float:
        resp = client.system_one(
            state=self.build_state(query, chunk), questions={"relevant": question}
        )
        p = float(resp.answers["relevant"].noul)
        if not 0.0 <= p <= 1.0:
            raise RuntimeError(f"Jev trả xác suất ngoài [0, 1]: {p}")
        return p

    def score_pairs(self, query: str, chunks: Sequence[Chunk]) -> list[float]:
        """Xác suất liên quan cho từng chunk, đúng thứ tự đầu vào."""
        client, question = self._get_client(), self._get_question()
        workers = min(self.max_workers, len(chunks))
        if workers <= 1:
            return [self._score_one(client, question, query, c) for c in chunks]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            # map giữ đúng thứ tự đầu vào; lỗi ở bất kỳ cặp nào sẽ được ném ra ở đây
            return list(pool.map(lambda c: self._score_one(client, question, query, c), chunks))


# ---------------------------------------------------------------------------
# Jina Reranker
# ---------------------------------------------------------------------------


class JinaReranker(ScoringReranker):
    """Gọi https://api.jina.ai/v1/rerank: một request cho cả pool. `post`, `sleep` thay được khi test."""

    name = "jina"
    RETRY_STATUS = frozenset({429, 500, 502, 503, 504})

    def __init__(
        self,
        model_id: str = DEFAULT_JINA_RERANK_MODEL,
        *,
        cache: ScoreCache | None = None,
        api_key: str | None = None,
        max_retries: int = 6,
        timeout: float = 60.0,
        post: Any = None,
        sleep: Any = time.sleep,
    ) -> None:
        self.model_id = model_id
        self.cache = cache
        self._api_key = api_key
        self.max_retries = max_retries
        self.timeout = timeout
        self._post = post
        self._sleep = sleep

    @staticmethod
    def build_document(chunk: Chunk) -> str:
        head = f"{chunk.section}\n" if chunk.section else ""
        return f"{head}{chunk.text}"

    def _key(self) -> str:
        key = self._api_key or os.environ.get("JINA_API_KEY")
        if not key:
            raise RuntimeError("Thiếu JINA_API_KEY (đặt trong .env) cho RERANK_BACKEND=jina")
        return key

    def score_pairs(self, query: str, chunks: Sequence[Chunk]) -> list[float]:
        from rag.index.embedders.jina_api import JinaHTTPError, _jina_post

        post = self._post or _jina_post
        payload = {
            "model": self.model_id,
            "query": query,
            "documents": [self.build_document(c) for c in chunks],
            "top_n": len(chunks),
            "return_documents": False,
        }
        for attempt in range(self.max_retries + 1):
            try:
                data = post(JINA_RERANK_URL, payload, self._key(), self.timeout)
                break
            except JinaHTTPError as e:
                if e.status not in self.RETRY_STATUS or attempt == self.max_retries:
                    raise
                wait = min(3 * 2**attempt, 60)
                log.warning("Jina rerank lỗi (%s), thử lại sau %ss", e.status, wait)
                self._sleep(wait)
        scores: list[float | None] = [None] * len(chunks)
        for r in data["results"]:
            scores[r["index"]] = float(r["relevance_score"])
        if any(x is None for x in scores):
            raise RuntimeError("Jina rerank trả thiếu điểm cho một số đoạn")
        return scores  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Tắt rerank / fallback
# ---------------------------------------------------------------------------


class NoopReranker:
    """Tắt rerank: giữ nguyên thứ tự RRF (arm="fused"). Dùng cho ablation và làm fallback."""

    name = "none"

    def rerank(
        self, query: str, hits: list[Hit], chunks: Mapping[str, Chunk], k: int
    ) -> list[Hit]:
        if k < 1:
            raise RerankInputError(f"k phải >= 1, nhận {k}")
        return list(hits[:k])


class FallbackReranker:
    """Bọc reranker chính: lỗi (mạng, API, SDK...) thì dùng fallback.

    RerankInputError (bug của code gọi) vẫn được ném ra, không bị che.
    """

    def __init__(self, primary: Reranker, fallback: Reranker | None = None) -> None:
        self.primary = primary
        self.fallback = fallback or NoopReranker()
        self.name = primary.name
        self.last_error: Exception | None = None   # để UI hiện cảnh báo nếu muốn

    def rerank(
        self, query: str, hits: list[Hit], chunks: Mapping[str, Chunk], k: int
    ) -> list[Hit]:
        try:
            result = self.primary.rerank(query, hits, chunks, k)
            self.last_error = None
            return result
        except RerankInputError:
            raise
        except Exception as e:  # noqa: BLE001 — cố ý: demo không được crash vì reranker
            self.last_error = e
            log.warning("Reranker %s lỗi, dùng %s: %r", self.primary.name, self.fallback.name, e)
            return self.fallback.rerank(query, hits, chunks, k)


def make_reranker(
    backend: str,
    *,
    model_id: str | None = None,
    cache_path: Path | str | None = None,
    fallback: bool = True,
) -> Reranker:
    """Tạo reranker theo RERANK_BACKEND = none | jev | jina. Không gọi API ở đây.

    Cache dùng chung một file: key gồm model_id nên điểm Jev và Jina không lẫn nhau.
    """
    if backend not in BACKENDS:
        raise ValueError(f"RERANK_BACKEND phải thuộc {BACKENDS}, nhận {backend!r}")
    if backend == "none":
        return NoopReranker()
    cache = ScoreCache(cache_path) if cache_path is not None else None
    if backend == "jina":
        primary: Reranker = JinaReranker(model_id or DEFAULT_JINA_RERANK_MODEL, cache=cache)
    else:
        primary = JevReranker(model_id or DEFAULT_JEV_MODEL, cache=cache)
    return FallbackReranker(primary) if fallback else primary


__all__ = [
    "BACKENDS",
    "DEFAULT_JEV_MODEL",
    "DEFAULT_JINA_RERANK_MODEL",
    "FallbackReranker",
    "JevReranker",
    "JinaReranker",
    "NoopReranker",
    "RerankInputError",
    "ScoreCache",
    "ScoringReranker",
    "make_reranker",
]
