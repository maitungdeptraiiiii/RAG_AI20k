"""HybridRetriever: BM25 + Dense (+ arm nâng cao) -> RRF -> (rerank Jev) — TV2.

    retrieve(query, k=5)                          -> mọi arm đang bật, gộp bằng RRF
    retrieve(query, k=5, mode="bm25")             -> chỉ một arm (dùng cho eval BM25 / Dense riêng)
    retrieve(query, k=5, arms=("bm25", "dense"))  -> chọn tập arm (ablation: có / không có HyDE)
    search(query, k)                              -> list[Hit] cuối (thoả interface Retriever)

Arm lõi: "bm25", "dense". Phương pháp nâng cao thêm arm qua `extra_arms` (vd. {"hyde": ...}),
xem src/rag/advanced/. Gọi nhiều arm mà một arm lỗi (vd. mất mạng) thì vẫn trả kết quả các arm còn
lại và ghi lỗi vào `RetrievalResult.errors`; mọi arm đều lỗi thì ném RetrievalError.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from rag.retrieve.fusion import DEFAULT_RRF_K, rrf
from rag.schema import Chunk, Hit, Reranker, Retriever, nfc

log = logging.getLogger(__name__)

Mode = str            # "hybrid" | tên một arm ("bm25", "dense", "hyde", ...)
CORE_ARMS = ("bm25", "dense")
MODES: tuple[str, ...] = ("hybrid", *CORE_ARMS)


class RetrievalError(RuntimeError):
    """Không arm nào trả được kết quả."""


@dataclass
class RetrievalResult:
    query: str
    mode: str
    arms: dict[str, list[Hit]] = field(default_factory=dict)   # kết quả từng arm (top arm_k)
    candidates: list[Hit] = field(default_factory=list)        # fused (nhiều arm) hoặc hit của arm duy nhất
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
        extra_arms: Mapping[str, Retriever] | None = None,
        reranker: Reranker | None = None,
        arm_k: int = 20,
        rrf_k: int = DEFAULT_RRF_K,
        rerank_n: int = 20,
    ) -> None:
        if arm_k < 1 or rerank_n < 1:
            raise ValueError("arm_k và rerank_n phải >= 1")
        clash = set(extra_arms or {}) & {*CORE_ARMS, "hybrid", "fused", "rerank"}
        if clash:
            raise ValueError(f"Tên arm nâng cao trùng tên dành riêng: {sorted(clash)}")
        self.arms: dict[str, Retriever] = {"bm25": bm25, "dense": dense, **(extra_arms or {})}
        self.reranker = reranker
        self.arm_k, self.rrf_k, self.rerank_n = arm_k, rrf_k, rerank_n
        self._chunks: dict[str, Chunk] = {}

    # --- build ---------------------------------------------------------------

    def build(self, chunks: Iterable[Chunk]) -> None:
        """Index chunk vào mọi arm và nhớ nội dung chunk (reranker, context cần text).

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

    @property
    def modes(self) -> tuple[str, ...]:
        return ("hybrid", *self.arms)

    # --- retrieve ------------------------------------------------------------

    def _resolve_arms(self, mode: str, arms: Sequence[str] | None) -> list[str]:
        if arms is not None:
            names = list(dict.fromkeys(arms))
        elif mode == "hybrid":
            names = list(self.arms)
        else:
            names = [mode]
        unknown = [n for n in names if n not in self.arms]
        if unknown or not names:
            raise ValueError(f"Arm/mode không hợp lệ: {unknown or names}; đang có {self.modes}")
        return names

    def retrieve(
        self,
        query: str,
        k: int = 5,
        *,
        mode: Mode = "hybrid",
        arms: Sequence[str] | None = None,
        rerank: bool = True,
    ) -> RetrievalResult:
        if k < 1:
            raise ValueError(f"k phải >= 1, nhận {k}")
        names = self._resolve_arms(mode, arms)
        q = nfc(query).strip()
        result = RetrievalResult(query=q, mode="+".join(names) if arms is not None else mode)
        if not q:
            return result

        for name in names:
            try:
                result.arms[name] = self.arms[name].search(q, self.arm_k)
            except Exception as e:
                if len(names) == 1:
                    raise
                log.warning("Arm %s lỗi, tiếp tục với arm còn lại: %r", name, e)
                result.errors[name] = repr(e)
        if not result.arms:
            raise RetrievalError(f"Mọi arm đều lỗi: {result.errors}")

        pool = max(self.rerank_n, k)
        if len(names) > 1:
            result.candidates = rrf(result.arms, k=self.rrf_k, top_n=pool)
        else:
            result.candidates = result.arms[names[0]][:pool]

        if rerank and self.reranker is not None and result.candidates:
            # chấm TOÀN BỘ candidates (Jev vốn phải chấm hết để sắp xếp), giữ lại để chọn context
            result.ranked = self.reranker.rerank(q, result.candidates, self._chunks, len(result.candidates))
        else:
            result.ranked = list(result.candidates)
        result.hits = result.ranked[:k]
        return result

    def search(self, query: str, k: int) -> list[Hit]:
        return self.retrieve(query, k).hits


__all__ = ["CORE_ARMS", "MODES", "HybridRetriever", "Mode", "RetrievalError", "RetrievalResult"]
