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
        cache1 = EmbeddingCache(path)
        _openai(client, cache=cache1).embed(["a", "bb"])
        cache1.close()
        client2 = FakeOpenAI(4)
        cache2 = EmbeddingCache(path)
        vecs = _openai(client2, cache=cache2).embed(["bb", "a", "ccc"])
        cache2.close()
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


# --- JinaEmbedder (HTTP giả) -----------------------------------------------------------

from rag.index.embedder import JinaEmbedder, JinaHTTPError, make_embedder  # noqa: E402


class FakeJina:
    def __init__(self, dim=4, fail=()):
        self.dim, self.fail, self.calls = dim, list(fail), []

    def __call__(self, url, payload, key, timeout):
        if self.fail:
            raise JinaHTTPError(self.fail.pop(0), "err")
        self.calls.append((payload["task"], list(payload["input"]), key))
        bias = 1.0 if payload["task"] == "retrieval.query" else 0.0
        data = [{"index": i, "embedding": [float(len(t)) + bias] * self.dim} for i, t in enumerate(payload["input"])]
        return {"data": list(reversed(data))}


def _jina(post, **kw):
    return JinaEmbedder("jina-x", 4, api_key="k", post=post, sleep=lambda s: None, **kw)


def test_jina_uses_passage_for_chunks_and_query_for_questions():
    post = FakeJina()
    e = _jina(post, batch_size=2)
    assert [v[0] for v in e.embed(["a", "bb", "ccc"])] == [1.0, 2.0, 3.0]
    assert e.embed_query(["a"])[0][0] == 2.0
    assert [(t, b) for t, b, _ in post.calls] == [
        ("retrieval.passage", ["a", "bb"]), ("retrieval.passage", ["ccc"]), ("retrieval.query", ["a"])]


def test_jina_cache_separates_tasks():
    post = FakeJina()
    e = _jina(post, cache=EmbeddingCache())
    e.embed(["a"]); e.embed(["a"]); e.embed_query(["a"]); e.embed_query(["a"])
    assert [t for t, _, _ in post.calls] == ["retrieval.passage", "retrieval.query"]


def test_jina_retries_on_429_but_not_on_400():
    assert _jina(FakeJina(fail=[429, 503])).embed(["a"])[0][0] == 1.0
    with pytest.raises(JinaHTTPError):
        _jina(FakeJina(fail=[400])).embed(["a"])


def test_jina_rejects_wrong_dim_and_missing_key(monkeypatch):
    with pytest.raises(RuntimeError, match="số chiều"):
        JinaEmbedder("jina-x", 8, api_key="k", post=FakeJina(4)).embed(["a"])
    monkeypatch.delenv("JINA_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="JINA_API_KEY"):
        JinaEmbedder("jina-x", 4, post=FakeJina(4)).embed(["a"])


def test_make_embedder_picks_backend():
    assert isinstance(make_embedder("jina-embeddings-v5-text-small", 1024), JinaEmbedder)
    assert isinstance(make_embedder("text-embedding-3-small", 1536), OpenAIEmbedder)


def test_vector_index_embeds_query_with_query_task():
    post = FakeJina()
    idx = VectorIndex(_jina(post))
    idx.build([_c(0, "a")])
    idx.search("bb", 1)
    assert [t for t, _, _ in post.calls] == ["retrieval.passage", "retrieval.query"]


# --- Registry + embedder local ----------------------------------------------------------

from rag.config import Settings  # noqa: E402
from rag.index.embedders import (  # noqa: E402
    KNOWN_MODELS,
    EmbedSpec,
    SentenceTransformerEmbedder,
    model_slug,
    register_backend,
    resolve_spec,
)
from rag.index.embedders.registry import BACKENDS  # noqa: E402


class FakeST:
    """Giống SentenceTransformer.encode: vector = [len(text)] * dim, ghi lại input."""

    def __init__(self, dim=3):
        self.dim, self.inputs = dim, []

    def get_sentence_embedding_dimension(self):
        return self.dim

    def encode(self, texts, **kw):
        assert kw["normalize_embeddings"] is True
        self.inputs.append(list(texts))
        return [[float(len(t))] * self.dim for t in texts]


def test_registry_known_model_fills_dim_and_prefixes():
    spec = resolve_spec("bqbbao6/vietnamese-legal-embedding")
    assert (spec.backend, spec.dim, spec.query_prefix, spec.passage_prefix) == ("local", 768, "query: ", "passage: ")
    assert resolve_spec("jina-embeddings-v5-text-small").dim == 1024


def test_registry_rejects_wrong_dim_for_known_model():
    with pytest.raises(ValueError, match="không khớp"):
        resolve_spec("bqbbao6/vietnamese-legal-embedding", dim=1024)


def test_registry_guesses_backend_for_unknown_models():
    assert resolve_spec("someone/new-model").backend == "local"
    assert resolve_spec("jina-embeddings-v9").backend == "jina"
    assert resolve_spec("text-embedding-9", dim=8).backend == "openai"
    with pytest.raises(ValueError, match="EMBED_BACKEND"):
        resolve_spec("mystery")
    with pytest.raises(ValueError, match="EMBED_DIM"):
        make_embedder("jina-embeddings-v9")          # model API lạ phải có dim


def test_register_backend_plugs_in_new_provider(monkeypatch):
    monkeypatch.setitem(BACKENDS, "fake", lambda m, spec, *, cache, **o: HashEmbedder(spec.dim, m))
    monkeypatch.setitem(KNOWN_MODELS, "fake-model", EmbedSpec("fake", 12))
    e = make_embedder("fake-model")
    assert (e.model_id, e.dim) == ("fake-model", 12)


def test_local_embedder_adds_e5_prefixes_and_caches_by_kind():
    model = FakeST(dim=3)
    e = SentenceTransformerEmbedder("m", 3, cache=EmbeddingCache(), query_prefix="query: ",
                                    passage_prefix="passage: ", model=model, batch_size=2)
    assert e.embed(["a", "bb", "c"])[1] == [11.0] * 3          # len("passage: bb")
    assert e.embed_query(["a"])[0] == [8.0] * 3                # len("query: a")
    e.embed(["a"]); e.embed_query(["a"])                       # cache, không gọi model nữa
    assert model.inputs == [["passage: a", "passage: bb"], ["passage: c"], ["query: a"]]


def test_local_embedder_probes_dim_when_unknown():
    assert SentenceTransformerEmbedder("m", model=FakeST(dim=5)).dim == 5


def test_settings_vector_dir_is_per_model_with_legacy_fallback(tmp_path):
    s = Settings(data_dir=tmp_path, embed_model="bqbbao6/vietnamese-legal-embedding")
    assert s.vector_dir == tmp_path / "indexes" / "vector" / "bqbbao6__vietnamese-legal-embedding"
    legacy = tmp_path / "indexes" / "vector"
    legacy.mkdir(parents=True)
    (legacy / "meta.json").write_text(json.dumps({"embed_model": "jina-embeddings-v5-text-small", "dim": 1024}))
    assert Settings(data_dir=tmp_path).vector_dir == legacy                  # index cũ, đúng model
    assert s.vector_dir == legacy / model_slug(s.embed_model)                 # model khác -> thư mục riêng


def test_settings_embed_dim_auto_from_env():
    assert Settings.from_env({"EMBED_DIM": "auto"}).embed_dim is None
    assert Settings.from_env({"EMBED_DIM": "768"}).embed_dim == 768
    assert Settings.from_env({"EMBED_QUERY_PREFIX": "query: "}).embed_query_prefix == "query: "
