"""Chỉ mục cho kho luật có phiên bản: BM25 (+ dense nếu có embedder) trên chunk của từng phiên bản Điều; lọc theo
khoảng hiệu lực TRƯỚC khi xếp hạng (chấm điểm toàn bộ rồi giữ chunk có hiệu lực giao khoảng mốc), gộp bằng RRF.
Chỉ nạp luật gốc: bỏ VBHN và văn bản chỉ để sửa đổi (nội dung của chúng đã được áp vào luật gốc)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from collections.abc import Callable
from typing import Any, NamedTuple

from rag.index.bm25_index import BM25Index
from rag.index.vector_index import VectorIndex
from rag.legal.chunks import VersionedChunk, export_chunks
from rag.legal.store import LegalStore
from rag.legal.structure import parse_structure
from rag.schema import Chunk, Hit
from rag.temporal.status import is_amendment_only

RRF_K = 60


class _State(NamedTuple):
    """Toàn bộ chỉ mục của một lần build; đổi nguyên khối để search đồng thời luôn thấy một trạng thái nhất quán."""
    chunks: dict[str, VersionedChunk]
    builds: dict[str, str]          # document_key -> build_id đã nạp
    skipped: frozenset[str]         # văn bản chỉ để sửa đổi
    bm25: BM25Index
    dense: VectorIndex | None
    rows: dict[str, Chunk]          # chunk_id -> Chunk (text cho reranker / gộp theo Điều của HybridRetriever)


class ValidityFilteredArm:
    """Bọc một arm (BM25 / Dense): chấm TOÀN BỘ chunk rồi chỉ giữ chunk có hiệu lực giao khoảng mốc, đánh lại rank.
    Nhờ vậy RRF, HyDE, rerank phía sau chỉ thấy ứng viên hợp lệ (lọc trước khi xếp hạng)."""

    def __init__(self, inner: Any, allowed: set[str], arm: str) -> None:
        self.inner, self.allowed, self.arm = inner, allowed, arm
        self.embedder = getattr(inner, "embedder", None)

    def build(self, chunks) -> None:            # chỉ mục do VersionedIndex.build dựng
        return None

    def __len__(self) -> int:
        return len(self.allowed)

    def search(self, query: str, k: int) -> list[Hit]:
        if not self.allowed or len(self.inner) == 0:
            return []
        hits = [h for h in self.inner.search(query, len(self.inner)) if h.chunk_id in self.allowed][:k]
        return [Hit(h.chunk_id, h.score, i, self.arm) for i, h in enumerate(hits, start=1)]


RetrieverFactory = Callable[[Any, Any], Any]      # (bm25_arm, dense_arm) -> HybridRetriever đã cấu hình


class VersionedIndex:
    """`retriever_factory` (vd. `lambda b, d: make_hybrid_retriever(settings, llm, b, d)`): tìm bằng đúng
    HybridRetriever của pipeline chính trên các arm đã lọc hiệu lực. Không có: BM25 (+Dense) gộp RRF đơn giản.
    `vector_dir`: lưu vector Dense bằng Qdrant trên đĩa (khởi động lại không phải embed lại)."""

    def __init__(self, store: LegalStore, embedder: Any = None, *, retriever_factory: RetrieverFactory | None = None,
                 vector_dir: Path | None = None) -> None:
        self.store = store
        self.embedder = embedder
        self.retriever_factory = retriever_factory
        self.vector_dir = vector_dir
        self._state = _State({}, {}, frozenset(), BM25Index(), None, {})

    @property
    def chunks(self) -> dict[str, VersionedChunk]:
        return self._state.chunks

    @property
    def has_dense(self) -> bool:
        return self._state.dense is not None

    def build(self) -> int:
        chunks: dict[str, VersionedChunk] = {}
        builds: dict[str, str] = {}
        skipped: set[str] = set()
        rows: list[Chunk] = []
        for doc in self.store.documents():
            if doc.is_consolidated:
                continue
            run = self.store.latest_build(doc.document_key)
            if run is None:
                continue
            try:
                provisions = parse_structure(Path(doc.raw_text_path).read_text(encoding="utf-8"), doc.document_key)
            except OSError:
                provisions = []
            if provisions and is_amendment_only(provisions):
                skipped.add(doc.document_key)
                continue
            builds[doc.document_key] = run.build_id
            for vc in export_chunks(self.store, doc.document_key):
                chunks[vc.chunk_id] = vc
                rows.append(Chunk(vc.chunk_id, doc.document_key, doc.title, None, None, vc.section, vc.text))
        bm25 = BM25Index()
        bm25.build(rows)
        dense = None
        if self.embedder is not None and rows:
            dense = (self._state.dense if self._state.dense is not None
                     else VectorIndex.open_qdrant(self.vector_dir, self.embedder) if self.vector_dir is not None
                     else VectorIndex(self.embedder))
            dense.build(rows)               # chỉ embed chunk chưa có (cache embedding theo nội dung)
        self._state = _State(chunks, builds, frozenset(skipped), bm25, dense, {r.chunk_id: r for r in rows})
        return len(rows)

    def stale(self) -> bool:
        st = self._state
        for doc in self.store.documents():
            if doc.is_consolidated or doc.document_key in st.skipped:
                continue
            run = self.store.latest_build(doc.document_key)
            if run is not None and st.builds.get(doc.document_key) != run.build_id:
                return True
        return False

    @staticmethod
    def _allowed(chunks: dict[str, VersionedChunk], start: date, end: date) -> set[str]:
        return {cid for cid, c in chunks.items()
                if c.valid_from <= end and (c.valid_to is None or c.valid_to > start)}

    def search(self, query: str, start: date, end: date, k: int) -> list[tuple[VersionedChunk, float]]:
        st = self._state
        if not st.chunks or k < 1:
            return []
        allowed = self._allowed(st.chunks, start, end)
        if self.retriever_factory is not None:
            return self._hybrid_search(st, query, allowed, k)
        scores: dict[str, float] = {}
        arms = [st.bm25.search(query, len(st.bm25))] if len(st.bm25) else []
        if st.dense is not None:
            arms.append(st.dense.search(query, len(st.dense)))
        for hits in arms:
            rank = 0
            for h in hits:
                if h.chunk_id not in allowed:
                    continue
                rank += 1
                scores[h.chunk_id] = scores.get(h.chunk_id, 0.0) + 1.0 / (RRF_K + rank)
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
        return [(st.chunks[cid], score) for cid, score in ranked]

    def _hybrid_search(self, st: _State, query: str, allowed: set[str], k: int) -> list[tuple[VersionedChunk, float]]:
        """HybridRetriever của pipeline chính; trả `k` Điều (mỗi Điều kèm mọi chunk đã gộp, kể cả phiên bản khác
        của cùng Điều khi mốc là một khoảng), theo thứ tự rerank."""
        if not allowed:
            return []
        bm25 = ValidityFilteredArm(st.bm25, allowed, "bm25")
        dense = ValidityFilteredArm(st.dense if st.dense is not None else _EmptyArm(), allowed, "dense")
        retriever = self.retriever_factory(bm25, dense)
        retriever._chunks = st.rows
        result = retriever.retrieve(query, k, arms=None if st.dense is not None else ("bm25",))
        out: list[tuple[VersionedChunk, float]] = []
        seen: set[str] = set()
        for h in result.hits:
            for cid in (h.chunk_id, *h.merged):
                if cid in allowed and cid not in seen:
                    seen.add(cid)
                    out.append((st.chunks[cid], h.score))
        return out

    def versions_of(self, article_id: str, start: date, end: date) -> list[VersionedChunk]:
        chunks = self._state.chunks
        allowed = self._allowed(chunks, start, end)
        return sorted((c for cid, c in chunks.items() if c.article_id == article_id and cid in allowed),
                      key=lambda c: (c.valid_from, c.chunk_id))


class _EmptyArm:
    def __len__(self) -> int:
        return 0

    def search(self, query: str, k: int) -> list[Hit]:
        return []


__all__ = ["ValidityFilteredArm", "VersionedIndex"]
