"""Chỉ mục cho kho luật có phiên bản: BM25 (+ dense nếu có embedder) trên chunk của từng phiên bản Điều; lọc theo
khoảng hiệu lực TRƯỚC khi xếp hạng (chấm điểm toàn bộ rồi giữ chunk có hiệu lực giao khoảng mốc), gộp bằng RRF.
Chỉ nạp luật gốc: bỏ VBHN và văn bản chỉ để sửa đổi (nội dung của chúng đã được áp vào luật gốc)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from rag.index.bm25_index import BM25Index
from rag.index.vector_index import VectorIndex
from rag.legal.chunks import VersionedChunk, export_chunks
from rag.legal.store import LegalStore
from rag.legal.structure import parse_structure
from rag.schema import Chunk
from rag.temporal.status import is_amendment_only

RRF_K = 60


class VersionedIndex:
    def __init__(self, store: LegalStore, embedder: Any = None) -> None:
        self.store = store
        self.embedder = embedder
        self.chunks: dict[str, VersionedChunk] = {}
        self._builds: dict[str, str] = {}          # document_key -> build_id đã nạp
        self._skipped: set[str] = set()            # văn bản chỉ để sửa đổi
        self._bm25 = BM25Index()
        self._dense: VectorIndex | None = None

    def build(self) -> int:
        self.chunks, self._builds, self._skipped = {}, {}, set()
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
                self._skipped.add(doc.document_key)
                continue
            self._builds[doc.document_key] = run.build_id
            for vc in export_chunks(self.store, doc.document_key):
                self.chunks[vc.chunk_id] = vc
                rows.append(Chunk(vc.chunk_id, doc.document_key, doc.title, None, None, vc.section, vc.text))
        self._bm25 = BM25Index()
        self._bm25.build(rows)
        self._dense = None
        if self.embedder is not None and rows:
            self._dense = VectorIndex(self.embedder)
            self._dense.build(rows)
        return len(rows)

    def stale(self) -> bool:
        for doc in self.store.documents():
            if doc.is_consolidated or doc.document_key in self._skipped:
                continue
            run = self.store.latest_build(doc.document_key)
            if run is not None and self._builds.get(doc.document_key) != run.build_id:
                return True
        return False

    def _allowed(self, start: date, end: date) -> set[str]:
        return {cid for cid, c in self.chunks.items()
                if c.valid_from <= end and (c.valid_to is None or c.valid_to > start)}

    def search(self, query: str, start: date, end: date, k: int) -> list[tuple[VersionedChunk, float]]:
        if not self.chunks or k < 1:
            return []
        allowed = self._allowed(start, end)
        scores: dict[str, float] = {}
        arms = [self._bm25.search(query, len(self._bm25))] if len(self._bm25) else []
        if self._dense is not None:
            arms.append(self._dense.search(query, len(self._dense)))
        for hits in arms:
            rank = 0
            for h in hits:
                if h.chunk_id not in allowed:
                    continue
                rank += 1
                scores[h.chunk_id] = scores.get(h.chunk_id, 0.0) + 1.0 / (RRF_K + rank)
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
        return [(self.chunks[cid], score) for cid, score in ranked]

    def versions_of(self, article_id: str, start: date, end: date) -> list[VersionedChunk]:
        allowed = self._allowed(start, end)
        return sorted((c for cid, c in self.chunks.items() if c.article_id == article_id and cid in allowed),
                      key=lambda c: (c.valid_from, c.chunk_id))


__all__ = ["VersionedIndex"]
