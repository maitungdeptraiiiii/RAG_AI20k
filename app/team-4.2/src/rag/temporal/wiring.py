"""Dựng chỉ mục kho luật có phiên bản với đúng bộ tìm kiếm của pipeline chính (dùng chung cho server và eval).

    BM25 + Dense (embedder + cache embedding như pipeline chính, HyDE theo ADVANCED) -> RRF -> rerank (RERANK_BACKEND)

Mỗi arm được lọc theo hiệu lực tại mốc trước khi gộp / rerank (xem `ValidityFilteredArm`)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rag.config import Settings
from rag.legal.store import LegalStore
from rag.temporal.index import VersionedIndex


def legal_embedder(settings: Settings):
    from rag.index.embedder import EmbeddingCache, make_embedder

    return make_embedder(settings.embed_model, settings.embed_dim,
                         cache=EmbeddingCache(settings.cache_dir / "embeddings.sqlite"),
                         jina_api_key=settings.jina_api_key)


def legal_vector_dir(settings: Settings) -> Path:
    return settings.data_dir / "legal" / "vector"


def make_versioned_index(settings: Settings, llm: Any, store: LegalStore, *, embedder: Any = None,
                         vector_dir: Path | None = None, reranker: Any = None, dense: Any = None,
                         snapshot_id: str | None = None) -> VersionedIndex:
    """`embedder=None` và `dense=None`: chỉ BM25 (vẫn qua HybridRetriever + rerank). Reranker dùng chung giữa các lần
    tìm. `dense`: `VectorIndex` dùng chung giữa các snapshot (mở một lần); `snapshot_id`: snapshot kho của chỉ mục."""
    from rag.pipeline import make_hybrid_retriever
    from rag.retrieve.rerank import make_reranker

    if reranker is None:
        reranker = make_reranker(settings.rerank_backend, cache_path=settings.cache_dir / "rerank.sqlite")

    def factory(bm25, dense):
        return make_hybrid_retriever(settings, llm, bm25, dense, reranker=reranker)

    return VersionedIndex(store, embedder, retriever_factory=factory, vector_dir=vector_dir, dense=dense,
                          snapshot_id=snapshot_id)


__all__ = ["legal_embedder", "legal_vector_dir", "make_versioned_index"]
