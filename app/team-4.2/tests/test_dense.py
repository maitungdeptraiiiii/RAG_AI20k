import json
import math
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from rag.index.embedder import EmbeddingCache, HashEmbedder, OpenAIEmbedder
from rag.index.vector_index import IndexMismatchError, InMemoryVectorStore, VectorIndex
from rag.schema import Chunk


def _c(i, text):
    return Chunk(f"d:{i:04d}", "d", "a.pdf", 1, 1, None, text)


# --- HashEmbedder -----------------------------------------------------------------

def test_hash_embedder_is_deterministic_and_unit_length():
    e = HashEmbedder(dim=32)
    a, b = e.embed(["quyền sở hữu", "quyền sở hữu"])
    assert a == b
    assert math.isclose(sum(x * x for x in a), 1.0, rel_tol=1e-9)


# --- OpenAIEmbedder (client giả) -----------------------------------------------------

class FakeOpenAI:
    def __init__(self, dim, fail_times=0):
        self.dim = dim
        self.fail_times = fail_times
        self.batches = []
        self.embeddings = self

    def create(self, model, input):
        if self.fail_times:
            self.fail_times -= 1
            raise TimeoutError("timeout")
        self.batches.append(list(input))
        data = [SimpleNamespace(index=i, embedding=[float(len(t))] * self.dim) for i, t in enumerate(input)]
        return SimpleNamespace(data=list(reversed(data)))   # cố ý đảo thứ tự: phải sắp lại theo index


def _openai(client, **kw):
    return OpenAIEmbedder("m", 4, client=client, retry_on=(TimeoutError,), sleep=lambda s: None, **kw)


def test_openai_embedder_batches_and_keeps_order():
    client = FakeOpenAI(4)
    vecs = _openai(client, batch_size=2).embed(["a", "bb", "ccc"])
    assert [v[0] for v in vecs] == [1.0, 2.0, 3.0]
    assert client.batches == [["a", "bb"], ["ccc"]]


def test_openai_embedder_retries_then_gives_up():
    client = FakeOpenAI(4, fail_times=2)
    assert _openai(client, max_retries=2).embed(["a"])[0][0] == 1.0
    with pytest.raises(TimeoutError):
        _openai(FakeOpenAI(4, fail_times=5), max_retries=2).embed(["a"])


def test_openai_embedder_checks_dim_and_empty_text():
    with pytest.raises(RuntimeError):
        OpenAIEmbedder("m", 8, client=FakeOpenAI(4), retry_on=(TimeoutError,)).embed(["a"])
    with pytest.raises(ValueError):
        _openai(FakeOpenAI(4)).embed(["  "])


def test_embedding_cache_avoids_second_call():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "emb.sqlite"
        client = FakeOpenAI(4)
        _openai(client, cache=EmbeddingCache(path)).embed(["a", "bb"])
        client2 = FakeOpenAI(4)
        vecs = _openai(client2, cache=EmbeddingCache(path)).embed(["bb", "a", "ccc"])
        assert client2.batches == [["ccc"]]
        assert [v[0] for v in vecs] == [2.0, 1.0, 3.0]


# --- VectorIndex --------------------------------------------------------------------

def test_vector_index_returns_most_similar_first():
    idx = VectorIndex(HashEmbedder(dim=256))
    idx.build([_c(0, "quyền sở hữu tài sản"), _c(1, "thời hiệu khởi kiện"), _c(2, "hợp đồng thuê nhà")])
    hits = idx.search("thời hiệu khởi kiện là bao lâu", k=2)
    assert hits[0].chunk_id == "d:0001"
    assert [h.rank for h in hits] == [1, 2] and all(h.arm == "dense" for h in hits)


def test_vector_index_build_is_idempotent():
    emb = HashEmbedder()
    idx = VectorIndex(emb)
    assert idx.build([_c(0, "a"), _c(1, "b"), _c(0, "a")]) == 2
    assert idx.build([_c(0, "a"), _c(2, "c")]) == 1
    assert len(idx) == 3
    assert emb.calls[-1] == ["c"]   # chỉ embed chunk mới


def test_vector_index_empty_cases():
    idx = VectorIndex(HashEmbedder())
    assert idx.search("x", k=3) == []
    idx.build([_c(0, "a")])
    assert idx.search("   ", k=3) == []
    with pytest.raises(ValueError):
        idx.search("a", k=0)


def test_meta_mismatch_is_rejected():
    with tempfile.TemporaryDirectory() as d:
        meta = Path(d) / "meta.json"
        VectorIndex(HashEmbedder(dim=16), InMemoryVectorStore(), meta_path=meta)
        assert json.loads(meta.read_text()) == {"embed_model": "hash-16", "dim": 16}
        VectorIndex(HashEmbedder(dim=16), InMemoryVectorStore(), meta_path=meta)  # cùng model: OK
        with pytest.raises(IndexMismatchError):
            VectorIndex(HashEmbedder(dim=32), InMemoryVectorStore(), meta_path=meta)
