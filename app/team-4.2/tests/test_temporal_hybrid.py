"""Kho luật có phiên bản tìm bằng đúng HybridRetriever của pipeline cũ (BM25 + Dense [+HyDE] -> RRF -> rerank),
mỗi arm lọc theo hiệu lực TRƯỚC khi gộp/rerank."""

from datetime import date

import pytest

from rag.config import Settings
from rag.index.embedder import HashEmbedder
from rag.pipeline import make_hybrid_retriever
from rag.schema import Hit
from rag.temporal.index import VersionedIndex
from tests.test_temporal_index import QUERY, realestate_service


class SpyReranker:
    """Đảo thứ tự ứng viên và ghi lại mọi chunk được đưa vào rerank."""
    name = "spy"

    def __init__(self):
        self.seen: list[str] = []

    def rerank(self, query, hits, chunks, k):
        self.seen += [h.chunk_id for h in hits]
        out = list(reversed(hits))[:k]
        return [Hit(h.chunk_id, 1.0 / (i + 1), i + 1, "rerank") for i, h in enumerate(out)]


class FakeLLM:
    def __init__(self):
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        return "Chủ đầu tư dự án xây dựng nhà ở thương mại phải là doanh nghiệp kinh doanh bất động sản."


def settings(**kw):
    from dataclasses import replace
    return replace(Settings.load(), **{"advanced": "hyde", "arm_k": 20, "rerank_n": 20, "merge_articles": True,
                                       "query_rewrite_enabled": False, "decomp_enabled": False,
                                       "listwise_enabled": False, "coverage_enabled": False, **kw})


@pytest.fixture(scope="module")
def hybrid(tmp_path_factory):
    svc = realestate_service(tmp_path_factory.mktemp("thybrid"))
    reranker, llm = SpyReranker(), FakeLLM()
    index = VersionedIndex(svc.store, HashEmbedder(dim=64),
                           retriever_factory=lambda bm25, dense: make_hybrid_retriever(
                               settings(), llm, bm25, dense, reranker=reranker))
    index.build()
    return index, reranker, llm


def valid_at(c, start, end):
    return c.valid_from <= end and (c.valid_to is None or c.valid_to > start)


def test_make_hybrid_retriever_uses_pipeline_settings():
    s = settings(arm_k=7, rerank_n=9)
    from rag.index.bm25_index import BM25Index
    from rag.index.vector_index import VectorIndex
    r = make_hybrid_retriever(s, FakeLLM(), BM25Index(), VectorIndex(HashEmbedder(dim=8)), reranker=SpyReranker())
    assert (r.arm_k, r.rerank_n, r.merge_articles) == (7, 9, True)
    assert type(r.arms["dense"]).__name__ == "HydeRetriever"          # ADVANCED=hyde bọc arm dense như pipeline cũ


def test_reranker_only_sees_versions_valid_at_anchor(hybrid):
    index, reranker, _ = hybrid
    reranker.seen.clear()
    day = date(2023, 6, 15)
    results = index.search(QUERY, day, day, k=5)
    assert results and reranker.seen
    assert all(valid_at(index.chunks[cid], day, day) for cid in reranker.seen)
    assert all(valid_at(c, day, day) for c, _ in results)
    assert "luat:27/2023/QH15" not in {c.document_key for c, _ in results}


def test_result_follows_reranker_order(hybrid):
    index, reranker, _ = hybrid
    reranker.seen.clear()
    day = date(2025, 6, 15)
    results = index.search(QUERY, day, day, k=3)
    scores = [s for _, s in results]
    assert scores == sorted(scores, reverse=True) and scores[0] == 1.0     # điểm của SpyReranker, không phải RRF


def test_year_range_keeps_both_versions_of_merged_article(hybrid):
    index, _, _ = hybrid
    results = index.search(QUERY, date(2024, 1, 1), date(2024, 12, 31), k=8)
    docs = {c.document_key for c, _ in results}
    assert {"luat:65/2014/QH13", "luat:27/2023/QH15"} <= docs


def test_hyde_called_and_dense_arm_filtered(hybrid):
    index, _, llm = hybrid
    before = llm.calls
    day = date(2019, 1, 1)
    results = index.search("điều kiện kinh doanh bất động sản", day, day, k=5)
    assert llm.calls > before
    assert results and all(valid_at(c, day, day) for c, _ in results)
