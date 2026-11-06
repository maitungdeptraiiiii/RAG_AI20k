"""Rerank bằng TypeSafe Jev — phần thêm ngoài yêu cầu sprint 1.

    RRF top-20 Hit(fused) -> JevReranker -> top-5 Hit(rerank, score = xác suất liên quan [0, 1])

- Mỗi cặp (câu hỏi, chunk) được Noul chấm mức hỗ trợ ít nhất một phần quan trọng của câu hỏi;
  các cặp gọi song song bằng thread.
- Cache điểm trong SQLite theo phiên bản schema, model, toàn bộ instructions/state và chunk_id.
  Khoá legacy được giữ cho audit offline; live scoring không dùng lại điểm legacy.
- Hoà điểm thì xếp theo rank RRF cũ, để kết quả tất định.
- Được bọc trong FallbackReranker: lỗi API / mạng -> giữ nguyên thứ tự RRF (Hit vẫn arm="fused"),
  demo không bị crash và guardrail tự dùng ngưỡng RRF.

`typesafe_sdk` chỉ được import khi thật sự gọi Jev, nên module này import và test được
trên máy chưa cài SDK. Key đọc từ biến môi trường TYPESAFE_API_KEY (SDK tự đọc).
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from rag.schema import Chunk, Hit, Reranker

log = logging.getLogger(__name__)

DEFAULT_JEV_MODEL = "jev-1.13.0"            # chốt version, KHÔNG dùng "jev-latest"
JEV_INSTRUCTIONS = (
    "Đoạn văn cung cấp bằng chứng cụ thể để trả lời ít nhất một phần quan trọng của câu hỏi. "
    "Bằng chứng phải phù hợp với chủ thể, hành vi, đối tượng và các điều kiện đã nêu trong câu hỏi. "
    "Đoạn văn có thể làm rõ một điều kiện áp dụng, quyền hoặc nghĩa vụ, hậu quả hoặc biện pháp "
    "giải quyết thuộc vấn đề thực sự được hỏi; không cần trả lời toàn bộ các ý của câu hỏi. "
    "Một đoạn chỉ trùng chủ đề hoặc từ khóa, nhưng không cung cấp căn cứ cho bất kỳ phần quan "
    "trọng nào, không được xem là có bằng chứng. Không tự thêm dữ kiện hoặc giả định điều kiện "
    "chưa được nêu để làm cho đoạn văn trở nên phù hợp."
)
SCORE_CACHE_SCHEMA = "jev-full-input-v2"

BACKENDS = ("none", "jev")


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
    def key(
        model_id: str, query: str, chunk: Chunk, *,
        instructions: str | None = None, state: str | None = None,
    ) -> str:
        # The three-argument legacy form is retained for offline historical audits.
        # Live scoring MUST supply the exact instructions and state sent to Jev.
        if instructions is None and state is None:
            raw = "\x00".join((model_id, query, chunk.chunk_id, chunk.text))
        else:
            raw = json.dumps([SCORE_CACHE_SCHEMA, model_id, instructions, state, chunk.chunk_id],
                             ensure_ascii=False, separators=(",", ":"))
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
# Jev
# ---------------------------------------------------------------------------


class JevReranker:
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

    # --- rerank --------------------------------------------------------------

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
        keys = [ScoreCache.key(self.model_id, query, c, instructions=self.instructions,
                               state=self.build_state(query, c)) for c in cands]
        found = self.cache.get_many(keys)
        todo = [i for i, key in enumerate(keys) if key not in found]
        if todo:
            fresh = self.score_pairs(query, [cands[i] for i in todo])
            new_items = {keys[i]: s for i, s in zip(todo, fresh)}
            self.cache.put_many(new_items)
            found.update(new_items)
        return [found[key] for key in keys]

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
    """Tạo reranker theo RERANK_BACKEND = none | jev. Không gọi API ở đây."""
    if backend not in BACKENDS:
        raise ValueError(f"RERANK_BACKEND phải thuộc {BACKENDS}, nhận {backend!r}")
    if backend == "none":
        return NoopReranker()
    cache = ScoreCache(cache_path) if cache_path is not None else None
    jev = JevReranker(model_id or DEFAULT_JEV_MODEL, cache=cache)
    return FallbackReranker(jev) if fallback else jev


__all__ = [
    "BACKENDS",
    "DEFAULT_JEV_MODEL",
    "FallbackReranker",
    "JevReranker",
    "NoopReranker",
    "RerankInputError",
    "ScoreCache",
    "make_reranker",
]
