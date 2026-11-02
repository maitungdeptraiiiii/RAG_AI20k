"""HybridRetriever: BM25 + Dense -> RRF -> (rerank Jev) — TV2.

    retrieve(query, k=5, mode="hybrid")  -> RetrievalResult (giữ cả kết quả từng arm để eval)
    search(query, k)                     -> list[Hit] cuối (thoả interface Retriever)

mode="bm25" / "dense" chạy riêng một arm — dùng cho bảng so sánh BM25 / Dense / Hybrid khi eval.
Ở mode="hybrid", nếu một arm lỗi (vd. API embedding mất mạng) thì vẫn trả kết quả của arm còn lại
và ghi lỗi vào `RetrievalResult.errors`; cả hai arm cùng lỗi thì ném RetrievalError.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Literal

from rag.retrieve.fusion import DEFAULT_RRF_K, rrf
from rag.schema import Chunk, Hit, Reranker, Retriever, nfc

log = logging.getLogger(__name__)

Mode = Literal["bm25", "dense", "hybrid"]
MODES: tuple[str, ...] = ("bm25", "dense", "hybrid")


class RetrievalError(RuntimeError):
    """Không arm nào trả được kết quả."""


@dataclass
class RetrievalResult:
    query: str
    mode: str
    arms: dict[str, list[Hit]] = field(default_factory=dict)   # kết quả từng arm (top arm_k)
    candidates: list[Hit] = field(default_factory=list)        # fused (hybrid) hoặc hit của arm duy nhất
    ranked: list[Hit] = field(default_factory=list)            # toàn bộ candidates sau rerank (= candidates nếu không rerank);
                                                               # dùng để chọn context theo ngưỡng (retrieve/context.py)
    hits: list[Hit] = field(default_factory=list)              # = ranked[:k]: cố định k để chấm Recall@k, MRR@k
    errors: dict[str, str] = field(default_factory=dict)       # arm -> lỗi (nếu có)

    @property
    def reranked(self) -> bool:
        return bool(self.hits) and self.hits[0].arm == "rerank"

    @property
    def top_score(self) -> float | None:
        return self.hits[0].score if self.hits else None


class HybridRetriever:
    def __init__(
        self,
        bm25: Retriever,
        dense: Retriever,
        *,
        reranker: Reranker | None = None,
        arm_k: int = 20,
        rrf_k: int = DEFAULT_RRF_K,
        rerank_n: int = 20,
    ) -> None:
        if arm_k < 1 or rerank_n < 1:
            raise ValueError("arm_k và rerank_n phải >= 1")
        self.arms: dict[str, Retriever] = {"bm25": bm25, "dense": dense}
        self.reranker = reranker
        self.arm_k, self.rrf_k, self.rerank_n = arm_k, rrf_k, rerank_n
        self._chunks: dict[str, Chunk] = {}

    # --- build ---------------------------------------------------------------

    def build(self, chunks: Iterable[Chunk]) -> None:
        """Index chunk vào cả hai arm và nhớ nội dung chunk (reranker cần text).

        Gọi lại với chunk đã có thì không nhân đôi. Khi mở index có sẵn trên đĩa, vẫn gọi
        build(toàn bộ chunk) để retriever có text chunk cho reranker.
        """
        chunks = list(chunks)
        for c in chunks:
            self._chunks.setdefault(c.chunk_id, c)
        for retriever in self.arms.values():
            retriever.build(chunks)

    @property
    def chunks(self) -> Mapping[str, Chunk]:
        return self._chunks

    # --- retrieve ------------------------------------------------------------

    def retrieve(
        self, query: str, k: int = 5, *, mode: Mode = "hybrid", rerank: bool = True
    ) -> RetrievalResult:
        if k < 1:
            raise ValueError(f"k phải >= 1, nhận {k}")
        if mode not in MODES:
            raise ValueError(f"mode phải thuộc {MODES}, nhận {mode!r}")
        q = nfc(query).strip()
        result = RetrievalResult(query=q, mode=mode)
        if not q:
            return result

        names = ["bm25", "dense"] if mode == "hybrid" else [mode]
        for name in names:
            try:
                result.arms[name] = self.arms[name].search(q, self.arm_k)
            except Exception as e:
                if mode != "hybrid":
                    raise
                log.warning("Arm %s lỗi, tiếp tục với arm còn lại: %r", name, e)
                result.errors[name] = repr(e)
        if mode == "hybrid" and not result.arms:
            raise RetrievalError(f"Cả hai arm đều lỗi: {result.errors}")

        pool = max(self.rerank_n, k)
        if mode == "hybrid":
            result.candidates = rrf(result.arms, k=self.rrf_k, top_n=pool)
        else:
            result.candidates = result.arms[mode][:pool]

        if rerank and self.reranker is not None and result.candidates:
            # chấm TOÀN BỘ candidates (Jev vốn phải chấm hết để sắp xếp), giữ lại để chọn context
            result.ranked = self.reranker.rerank(q, result.candidates, self._chunks, len(result.candidates))
        else:
            result.ranked = list(result.candidates)
        result.hits = result.ranked[:k]
        return result

    def search(self, query: str, k: int) -> list[Hit]:
        return self.retrieve(query, k).hits


__all__ = ["MODES", "HybridRetriever", "Mode", "RetrievalError", "RetrievalResult"]
