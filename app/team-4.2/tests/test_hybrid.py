import pytest

from rag.index.bm25_index import BM25Index, syllable_tokenize
from rag.index.embedder import HashEmbedder
from rag.index.vector_index import VectorIndex
from rag.retrieve.fusion import rrf
from rag.retrieve.hybrid import HybridRetriever, RetrievalError
from rag.retrieve.rerank import FallbackReranker, NoopReranker
from rag.schema import Chunk, Hit


def _hits(arm, *ids):
    return [Hit(cid, 1.0, r, arm) for r, cid in enumerate(ids, start=1)]


def _c(i, text):
    return Chunk(f"d:{i:04d}", "d", "a.pdf", 1, 1, None, text)


# --- RRF --------------------------------------------------------------------------

def test_rrf_formula_and_order():
    out = rrf({"bm25": _hits("bm25", "a", "b"), "dense": _hits("dense", "b", "c")}, k=60)
    assert [h.chunk_id for h in out] == ["b", "a", "c"]
    assert out[0].score == pytest.approx(1 / 62 + 1 / 61)
    assert out[1].score == pytest.approx(1 / 61)
    assert all(h.arm == "fused" for h in out) and [h.rank for h in out] == [1, 2, 3]


def test_rrf_ties_by_chunk_id_and_top_n():
    out = rrf({"bm25": _hits("bm25", "z"), "dense": _hits("dense", "a")}, top_n=1)
    assert [h.chunk_id for h in out] == ["a"]


def test_rrf_duplicate_in_same_arm_counts_once():
    dup = [Hit("a", 1.0, 1, "bm25"), Hit("a", 0.5, 2, "bm25")]
    assert rrf({"bm25": dup})[0].score == pytest.approx(1 / 61)


def test_rrf_empty_and_bad_args():
    assert rrf({"bm25": [], "dense": []}) == []
    with pytest.raises(ValueError):
        rrf({}, k=-1)
    with pytest.raises(ValueError):
        rrf({}, top_n=0)


# --- HybridRetriever ------------------------------------------------------------------

class FixedRetriever:
    def __init__(self, arm, ids, fail=False):
        self.arm, self.ids, self.fail = arm, ids, fail
        self.built = []

    def build(self, chunks):
        self.built.extend(c.chunk_id for c in chunks)

    def search(self, query, k):
        if self.fail:
            raise ConnectionError("down")
        return _hits(self.arm, *self.ids[:k])


class ReverseReranker:
    name = "fake"

    def rerank(self, query, hits, chunks, k):
        assert all(h.chunk_id in chunks for h in hits)
        rev = list(reversed(hits))[:k]
        return [Hit(h.chunk_id, 0.9 - 0.1 * i, i + 1, "rerank") for i, h in enumerate(rev)]


def _retriever(bm25_ids, dense_ids, **kw):
    r = HybridRetriever(FixedRetriever("bm25", bm25_ids, kw.pop("bm25_fail", False)),
                        FixedRetriever("dense", dense_ids, kw.pop("dense_fail", False)), **kw)
    r.build([_c(i, f"t{i}") for i in range(6)])
    return r


def test_hybrid_fuses_both_arms():
    r = _retriever(["d:0000", "d:0001"], ["d:0001", "d:0002"])
    res = r.retrieve("câu hỏi", k=2)
    assert set(res.arms) == {"bm25", "dense"}
    assert [h.chunk_id for h in res.hits] == ["d:0001", "d:0000"]
    assert not res.reranked and res.errors == {}


def test_default_arms_limit_main_flow_only():
    r = _retriever(["d:0000", "d:0001"], ["d:0002"], default_arms=("dense",))
    res = r.retrieve("q", k=5)                                  # luồng chính: chỉ dense, không BM25
    assert list(res.arms) == ["dense"] and [h.chunk_id for h in res.hits] == ["d:0002"]
    assert set(r.retrieve("q", arms=("bm25", "dense")).arms) == {"bm25", "dense"}   # eval vẫn chọn được
    assert list(r.retrieve("q", mode="bm25").arms) == ["bm25"]
    for bad in (("tfidf",), ()):
        with pytest.raises(ValueError):
            _retriever([], [], default_arms=bad)


def test_settings_retrieval_arms():
    from rag.config import Settings

    assert Settings.from_env({"RETRIEVAL_ARMS": " Dense, ,dense"}).retrieval_arm_list == ["dense"]
    assert Settings().retrieval_arm_list is None


def test_single_arm_modes_for_eval():
    r = _retriever(["d:0000", "d:0001"], ["d:0002"])
    assert [h.chunk_id for h in r.retrieve("q", k=5, mode="bm25").hits] == ["d:0000", "d:0001"]
    res = r.retrieve("q", k=5, mode="dense")
    assert list(res.arms) == ["dense"] and res.hits[0].arm == "dense"
    with pytest.raises(ValueError):
        r.retrieve("q", mode="tfidf")


def test_rerank_applied_to_candidates():
    r = _retriever(["d:0000", "d:0001", "d:0002"], [], reranker=ReverseReranker())
    res = r.retrieve("q", k=2)
    assert res.reranked
    assert [h.chunk_id for h in res.hits] == ["d:0002", "d:0001"]
    assert len(res.candidates) == 3          # giữ danh sách fused để đo Recall@20
    assert [h.chunk_id for h in res.ranked] == ["d:0002", "d:0001", "d:0000"]  # toàn bộ, để chọn context
    assert res.hits == res.ranked[:2]
    assert not r.retrieve("q", k=2, rerank=False).reranked


def test_rerank_failure_keeps_fused_order():
    class Boom:
        name = "jev"

        def rerank(self, *a):
            raise ConnectionError("api down")

    r = _retriever(["d:0000", "d:0001"], [], reranker=FallbackReranker(Boom()))
    res = r.retrieve("q", k=2)
    assert [h.arm for h in res.hits] == ["fused", "fused"] and not res.reranked


def test_one_arm_down_still_answers():
    r = _retriever(["d:0000"], ["d:0001"], dense_fail=True)
    res = r.retrieve("q", k=5)
    assert [h.chunk_id for h in res.hits] == ["d:0000"]
    assert "dense" in res.errors
    with pytest.raises(RetrievalError):
        _retriever([], [], bm25_fail=True, dense_fail=True).retrieve("q")
    with pytest.raises(ConnectionError):
        _retriever([], [], dense_fail=True).retrieve("q", mode="dense")


def test_empty_query_returns_nothing():
    res = _retriever(["d:0000"], ["d:0001"]).retrieve("   ")
    assert res.hits == [] and res.top_score is None


def test_build_passes_chunks_to_both_arms_once_registered():
    r = _retriever([], [])
    assert r.arms["bm25"].built == r.arms["dense"].built == [f"d:{i:04d}" for i in range(6)]
    assert "d:0005" in r.chunks


def test_end_to_end_with_real_indexes():
    chunks = [
        _c(0, "Quyền sở hữu tài sản được pháp luật bảo vệ."),
        _c(1, "Thời hiệu khởi kiện về hợp đồng là ba năm."),
        _c(2, "Hợp đồng mua bán nhà ở phải lập thành văn bản."),
    ]
    r = HybridRetriever(
        BM25Index(tokenizer=syllable_tokenize, tokenizer_name="syllable"),
        VectorIndex(HashEmbedder(dim=256)),
        reranker=NoopReranker(),
    )
    r.build(chunks)
    r.build(chunks)  # ingest lại không nhân đôi
    res = r.retrieve("thời hiệu khởi kiện hợp đồng", k=2)
    assert res.hits[0].chunk_id == "d:0001"
    assert len(r.arms["bm25"]) == 3 and len(r.arms["dense"]) == 3
