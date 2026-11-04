import json

import pytest

from rag.advanced.decomposition import QueryDecomposer
from rag.advanced.hyde import HydeRetriever
from rag.config import Settings
from rag.retrieve.hybrid import HybridRetriever
from rag.schema import Chunk, Hit


class LLM:
    def __init__(self, reply):
        self.reply = reply
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


@pytest.mark.parametrize("reply", ['{"subqueries": []}', "invalid", '{"subqueries": [42]}',
                                  ConnectionError("offline"), '{"subqueries": ["q", "Q"]}'])
def test_simple_or_invalid_plan_uses_original(reply):
    assert QueryDecomposer(LLM(reply)).plan("q").queries == ["q"]


def test_plan_limits_deduplicates_and_preserves_original():
    llm = LLM(json.dumps({"subqueries": [" a ", "A", "b", "c", "d"]}))
    assert QueryDecomposer(llm).plan("q").queries == ["q", "a", "b", "c"]
    assert QueryDecomposer(llm, include_original=False).plan("q").queries == ["a", "b", "c"]


class Arm:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def build(self, chunks):
        pass

    def search(self, query, k):
        self.calls.append(query)
        if self.fail or query == "bad":
            raise ConnectionError("offline")
        ids = {"q": [0, 1], "a": [1, 2], "b": [2, 3]}[query]
        return [Hit(f"d:{i:04d}", 1., rank, "dense") for rank, i in enumerate(ids[:k], 1)]


class Reranker:
    def __init__(self):
        self.calls = []

    def rerank(self, query, hits, chunks, k):
        self.calls.append((query, hits))
        return [Hit(h.chunk_id, .9, i, "rerank") for i, h in enumerate(hits, 1)]


def make_retriever(subs=("a", "b")):
    bm25, dense, ranker = Arm(fail=True), Arm(), Reranker()
    r = HybridRetriever(bm25, dense, reranker=ranker, merge_articles=False)
    r.build([Chunk(f"d:{i:04d}", "d", "law", 1, 1, None, str(i)) for i in range(4)])
    llm = LLM(json.dumps({"subqueries": subs}))
    r.decomposer = QueryDecomposer(llm, pool_size=3)
    return r, bm25, dense, ranker, llm


def test_decomposition_fuses_before_one_original_query_rerank_without_bm25():
    r, bm25, dense, ranker, _ = make_retriever()
    result = r.retrieve("q", k=2, mode="dense")
    assert dense.calls == ["q", "a", "b"] and not bm25.calls
    assert len(ranker.calls) == 1 and ranker.calls[0][0] == "q"
    assert len(result.candidates) == 3 and len({h.chunk_id for h in result.candidates}) == 3
    assert {h.chunk_id for h in result.candidates} >= {"d:0001", "d:0002"}
    assert len(result.hits) == 2 and result.reranked
    assert result.queries == ["q", "a", "b"]


def test_disabled_does_not_call_decomposition_llm():
    r, _, dense, ranker, llm = make_retriever()
    r.decomposer = None
    r.retrieve("q", mode="dense")
    assert dense.calls == ["q"] and len(ranker.calls) == 1 and llm.calls == 0


def test_simple_question_keeps_baseline_pool_and_branch_failure_is_visible():
    r, _, dense, _, _ = make_retriever(())
    assert r.retrieve("q", mode="dense").queries == ["q"]
    assert dense.calls == ["q"]
    r, _, _, _, _ = make_retriever(("a", "bad"))
    result = r.retrieve("q", mode="dense")
    assert "q2" in result.errors and result.hits


def test_settings_toggle_and_limits():
    assert not Settings().decomp_enabled
    assert Settings.from_env({"DECOMP_ENABLED": "true"}).decomp_enabled
    with pytest.raises(ValueError):
        Settings(decomp_pool_size=0)


def test_hyde_runs_for_each_query_and_bm25_receives_no_hypothetical_text():
    class Dense(Arm):
        def search(self, query, k):
            self.calls.append(query)
            return [Hit("d:0000", 1., 1, "dense")]

    r, bm25, _, ranker, _ = make_retriever()
    bm25.fail = False
    dense = Dense()
    hyde_llm = LLM("hypothetical")
    r.arms["dense"] = HydeRetriever(hyde_llm, dense)
    r.retrieve("q", mode="hybrid")
    assert bm25.calls == ["q", "a", "b"]
    assert dense.calls == ["q\nhypothetical", "a\nhypothetical", "b\nhypothetical"]
    assert hyde_llm.calls == 3 and len(ranker.calls) == 1


def test_decomposition_preserves_chunks_of_selected_articles():
    r, _, _, ranker, _ = make_retriever()
    r.merge_articles = True
    r._chunks = {
        f"d:{i:04d}": Chunk(f"d:{i:04d}", "d", "law", 1, 1,
                              f"Điều {i // 2 + 1}. Title", str(i))
        for i in range(4)
    }
    r.decomposer.pool_size = 1
    result = r.retrieve("q", k=1, mode="dense")
    candidates = ranker.calls[0][1]
    assert len(candidates) == 2
    assert len(result.hits) == 1 and len(result.hits[0].merged) == 1


@pytest.mark.parametrize("original_count,new_limit", [(20, 10), (2, 10), (20, 0)])
def test_anchor_entire_original_pool_and_cap_only_novel_articles(original_count, new_limit):
    class ManyArticles(Arm):
        def search(self, query, k):
            self.calls.append(query)
            original = list(range(original_count * 2))
            overlap = original[-2:]
            ids = {"q": original, "a": overlap + list(range(40, 58)),
                   "b": overlap + list(range(58, 76))}[query]
            return [Hit(f"d:{i:04d}", 1., rank, "dense") for rank, i in enumerate(ids[:k], 1)]

    ranker = Reranker()
    r = HybridRetriever(Arm(fail=True), ManyArticles(), reranker=ranker)
    r.build([Chunk(f"d:{i:04d}", "d", "law", 1, 1, f"Điều {i // 2 + 1}. Title", str(i))
             for i in range(80)])
    r.decomposer = QueryDecomposer(LLM('{"subqueries": ["a", "b"]}'), max_new_articles=new_limit)
    result = r.retrieve("q", mode="dense")
    ids = [h.chunk_id for h in result.candidates]
    assert ids[:original_count * 2] == [f"d:{i:04d}" for i in range(original_count * 2)]
    assert len(ids) == len(set(ids)) == (original_count + new_limit) * 2
    assert len({r.chunks[cid].section for cid in ids}) == original_count + new_limit
    assert len(ranker.calls) == 1 and ranker.calls[0][0] == "q"
