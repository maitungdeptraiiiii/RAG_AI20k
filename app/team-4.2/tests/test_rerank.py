import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from rag.retrieve.rerank import (
    FallbackReranker,
    JevReranker,
    NoopReranker,
    RerankInputError,
    ScoreCache,
    make_reranker,
)
from rag.schema import Chunk, Hit


def _chunks(*texts):
    return {f"d:{i:04d}": Chunk(f"d:{i:04d}", "d", "a.pdf", 1, 1, None, t) for i, t in enumerate(texts)}


def _fused(chunks):
    return [Hit(cid, 1.0 / (60 + r), r, "fused") for r, cid in enumerate(chunks, start=1)]


class FakeJevClient:
    """Trả xác suất theo text chunk xuất hiện trong state; ghi lại các state đã nhận."""

    def __init__(self, by_text):
        self.by_text = by_text
        self.states = []
        self.lock = threading.Lock()

    def system_one(self, state, questions):
        assert set(questions) == {"relevant"}
        with self.lock:
            self.states.append(state)
        p = next(p for text, p in self.by_text.items() if state.endswith(text))
        return SimpleNamespace(answers={"relevant": SimpleNamespace(noul=p)})


def _jev(by_text, **kw):
    client = FakeJevClient(by_text)
    return JevReranker(client=client, question="noul", **kw), client


# --- sắp xếp ------------------------------------------------------------------

def test_rerank_sorts_by_probability_and_truncates():
    chunks = _chunks("a", "b", "c")
    jev, _ = _jev({"a": 0.1, "b": 0.9, "c": 0.5})
    out = jev.rerank("q", _fused(chunks), chunks, k=2)
    assert [h.chunk_id for h in out] == ["d:0001", "d:0002"]
    assert [h.rank for h in out] == [1, 2]
    assert all(h.arm == "rerank" for h in out)
    assert out[0].score == 0.9


def test_ties_keep_fused_order():
    chunks = _chunks("a", "b", "c")
    jev, _ = _jev({"a": 0.5, "b": 0.5, "c": 0.5})
    out = jev.rerank("q", _fused(chunks), chunks, k=3)
    assert [h.chunk_id for h in out] == ["d:0000", "d:0001", "d:0002"]


def test_parallel_calls_keep_input_order():
    texts = [f"đoạn {i:02d}" for i in range(12)]
    chunks = _chunks(*texts)
    jev, client = _jev({t: i / 20 for i, t in enumerate(texts)}, max_workers=4)
    out = jev.rerank("Thời hiệu khởi kiện?", _fused(chunks), chunks, k=12)
    assert len(client.states) == 12
    assert all(s.startswith("Câu hỏi: Thời hiệu khởi kiện?") for s in client.states)
    assert [h.chunk_id for h in out] == [f"d:{i:04d}" for i in reversed(range(12))]


def test_state_includes_section():
    c = Chunk("d:0000", "d", "a.pdf", 1, 1, "Chương II", "nội dung")
    assert "Mục: Chương II\nnội dung" in JevReranker.build_state("q", c)


# --- đầu vào sai ----------------------------------------------------------------

def test_empty_hits_and_bad_input():
    jev, _ = _jev({})
    assert jev.rerank("q", [], {}, k=5) == []
    with pytest.raises(RerankInputError):
        jev.rerank("q", [Hit("missing", 1.0, 1, "fused")], {}, k=5)
    with pytest.raises(RerankInputError):
        jev.rerank("q", [], {}, k=0)


def test_out_of_range_probability_is_error():
    chunks = _chunks("a")
    jev, _ = _jev({"a": 3.0})
    with pytest.raises(RuntimeError):
        jev.rerank("q", _fused(chunks), chunks, k=1)


# --- cache ------------------------------------------------------------------------

def test_cache_skips_already_scored_pairs():
    chunks = _chunks("a", "b")
    cache = ScoreCache()
    jev, client = _jev({"a": 0.2, "b": 0.8}, cache=cache)
    first = jev.rerank("q", _fused(chunks), chunks, k=2)
    assert len(client.states) == 2
    assert jev.rerank("q", _fused(chunks), chunks, k=2) == first
    assert len(client.states) == 2  # lần 2 lấy hoàn toàn từ cache
    other, other_client = _jev({"a": 0.2, "b": 0.8}, cache=cache, model_id="jev-9.9.9")
    other.rerank("q", _fused(chunks), chunks, k=2)
    assert len(other_client.states) == 2  # khác model thì không dùng chung cache


def test_cache_persists_on_disk():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "sub" / "rerank.sqlite"
        chunks = _chunks("a")
        cache1 = ScoreCache(path)
        jev, _ = _jev({"a": 0.4}, cache=cache1)
        jev.rerank("q", _fused(chunks), chunks, k=1)
        cache1.close()
        cache2 = ScoreCache(path)
        again, client = _jev({"a": 0.4}, cache=cache2)
        again.rerank("q", _fused(chunks), chunks, k=1)
        cache2.close()
        assert client.states == []


# --- Noop / Fallback --------------------------------------------------------------

def test_noop_keeps_fused_hits():
    chunks = _chunks("a", "b", "c")
    fused = _fused(chunks)
    assert NoopReranker().rerank("q", fused, chunks, k=2) == fused[:2]


def test_api_error_falls_back_to_fused_order():
    class Down:
        def system_one(self, state, questions):
            raise TimeoutError("timeout")

    chunks = _chunks("a", "b")
    fused = _fused(chunks)
    fb = FallbackReranker(JevReranker(client=Down(), question="noul"))
    out = fb.rerank("q", fused, chunks, k=2)
    assert out == fused and all(h.arm == "fused" for h in out)
    assert isinstance(fb.last_error, TimeoutError)
    assert fb.name == "jev"


def test_fallback_does_not_hide_input_bugs():
    jev, _ = _jev({})
    with pytest.raises(RerankInputError):
        FallbackReranker(jev).rerank("q", [Hit("missing", 1.0, 1, "fused")], {}, k=1)


# --- factory ----------------------------------------------------------------------

def test_make_reranker():
    assert isinstance(make_reranker("none"), NoopReranker)
    r = make_reranker("jev")
    assert isinstance(r, FallbackReranker) and isinstance(r.primary, JevReranker)
    assert r.primary.model_id == "jev-1.13.0"
    assert isinstance(make_reranker("jev", fallback=False), JevReranker)
    with pytest.raises(ValueError):
        make_reranker("bge")
