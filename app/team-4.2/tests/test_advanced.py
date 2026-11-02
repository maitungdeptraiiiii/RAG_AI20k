import tempfile
import threading
from pathlib import Path

import pytest

from rag.advanced import REGISTRY, Components, build_enhancements, parse_names
from rag.advanced.base import add_context
from rag.advanced.contextual import LLMContextEnricher, SectionHeaderEnricher
from rag.advanced.hyde import HYDE_SYSTEM, HydeRetriever
from rag.config import Settings
from rag.eval.runner import retrieval_rows
from rag.index.bm25_index import BM25Index, syllable_tokenize
from rag.index.embedder import HashEmbedder
from rag.index.store import ChunkStore
from rag.index.vector_index import VectorIndex
from rag.pipeline import IndexConfigMismatchError, RAGPipeline, check_index_config, index_signature
from rag.retrieve.hybrid import HybridRetriever
from rag.schema import Chunk, GoldRef, Page, Question


class EchoLLM:
    """LLM giả: trả lời theo hàm `reply(system, user)`, ghi lại các lần gọi (an toàn đa luồng)."""

    model_id = "echo"

    def __init__(self, reply):
        self.reply = reply
        self.calls = []
        self.lock = threading.Lock()

    def complete(self, system, user):
        with self.lock:
            self.calls.append((system, user))
        return self.reply(system, user)


def _c(i, text, section=None, context=None):
    return Chunk(f"d:{i:04d}", "d", "luat_lao_dong.pdf", i + 1, i + 1, section, text, context)


def _components(llm=None, dense=None):
    return Components(Settings(), llm or EchoLLM(lambda s, u: "x"), HashEmbedder(), dense or VectorIndex(HashEmbedder()))


# --- registry ---------------------------------------------------------------------------

def test_registry_has_methods_and_rejects_unknown():
    assert {"hyde", "contextual", "contextual_header"} <= set(REGISTRY)
    assert parse_names(" HyDE, contextual,,hyde ") == ["hyde", "contextual"]
    with pytest.raises(ValueError):
        build_enhancements("hyde,colbert", _components())
    assert build_enhancements("", _components()) == []


def test_enhancements_expose_the_right_hook():
    hyde, ctx, header = build_enhancements("hyde,contextual,contextual_header", _components())
    assert set(hyde.arms) == {"hyde"} and hyde.index_enhancer is None
    assert ctx.index_enhancer.name == "contextual" and not ctx.arms
    assert header.index_enhancer.name == "contextual_header"


# --- schema: context chỉ dùng để index ----------------------------------------------------

def test_index_text_includes_context_but_text_does_not():
    c = _c(0, "Thời hạn là 30 ngày.", context="Luật lao động, thời hạn báo trước khi nghỉ việc")
    assert c.index_text.startswith("Luật lao động") and c.text == "Thời hạn là 30 ngày."
    assert Chunk.from_dict(c.to_dict()) == c
    assert add_context(add_context(_c(1, "t"), "A"), "B").context == "A\nB"
    assert add_context(_c(1, "t"), "  ").context is None


def test_bm25_and_dense_search_context_words():
    chunks = [_c(0, "Thời hạn là 30 ngày.", context="báo trước nghỉ việc"), _c(1, "Tiền lương trả hằng tháng.")]
    bm25 = BM25Index(tokenizer=syllable_tokenize, tokenizer_name="syllable")
    bm25.build(chunks)
    assert bm25.search("báo trước", 5)[0].chunk_id == "d:0000"
    emb = HashEmbedder(dim=256)
    VectorIndex(emb).build(chunks)
    assert emb.calls[-1][0].startswith("báo trước nghỉ việc\n")


# --- HyDE ---------------------------------------------------------------------------------

def test_hyde_searches_dense_with_hypothetical_passage():
    dense = VectorIndex(HashEmbedder(dim=256))
    dense.build([_c(0, "Người lao động được nghỉ hằng năm 12 ngày làm việc."), _c(1, "Tiền lương trả bằng tiền mặt.")])
    llm = EchoLLM(lambda s, u: "Người lao động được nghỉ hằng năm hưởng nguyên lương.")
    hits = HydeRetriever(llm, dense).search("nghỉ phép mấy ngày", 2)
    assert hits[0].chunk_id == "d:0000" and all(h.arm == "hyde" for h in hits)
    assert llm.calls[0] == (HYDE_SYSTEM, "CÂU HỎI: nghỉ phép mấy ngày")


def test_hyde_empty_passage_is_an_error():
    with pytest.raises(RuntimeError):
        HydeRetriever(EchoLLM(lambda s, u: "  "), VectorIndex(HashEmbedder())).search("q", 3)


def test_hybrid_with_hyde_arm_and_ablation_subsets():
    dense = VectorIndex(HashEmbedder(dim=256))
    r = HybridRetriever(
        BM25Index(tokenizer=syllable_tokenize, tokenizer_name="syllable"), dense,
        extra_arms={"hyde": HydeRetriever(EchoLLM(lambda s, u: "nghỉ hằng năm"), dense)},
    )
    r.build([_c(0, "nghỉ hằng năm 12 ngày"), _c(1, "tiền lương")])
    assert set(r.retrieve("nghỉ phép").arms) == {"bm25", "dense", "hyde"}
    assert set(r.retrieve("nghỉ phép", arms=("bm25", "dense")).arms) == {"bm25", "dense"}
    assert list(r.retrieve("nghỉ phép", mode="hyde").arms) == ["hyde"]
    with pytest.raises(ValueError):
        HybridRetriever(BM25Index(), dense, extra_arms={"dense": dense})


def test_hyde_failure_keeps_other_arms():
    def boom(s, u):
        raise TimeoutError("llm down")

    dense = VectorIndex(HashEmbedder())
    r = HybridRetriever(BM25Index(tokenizer=syllable_tokenize, tokenizer_name="s"), dense,
                        extra_arms={"hyde": HydeRetriever(EchoLLM(boom), dense)})
    r.build([_c(0, "nghỉ hằng năm")])
    res = r.retrieve("nghỉ hằng năm")
    assert "hyde" in res.errors and res.hits


# --- Contextual Retrieval -----------------------------------------------------------------

def _pages():
    return [Page("d", "luat_lao_dong.pdf", 1, "BỘ LUẬT LAO ĐỘNG\nĐiều 1. Phạm vi"), Page("d", "luat_lao_dong.pdf", 2, "...")]


def test_section_header_enricher():
    out = SectionHeaderEnricher().enrich([_c(0, "t", section="Chương I > Điều 1. Phạm vi"), _c(1, "u")], _pages())
    assert out[0].context == "Tài liệu: luat lao dong. Mục: Chương I > Điều 1. Phạm vi"
    assert out[1].context == "Tài liệu: luat lao dong" and out[0].text == "t"


def test_llm_context_enricher_prompt_and_parallel_order():
    llm = EchoLLM(lambda s, u: "Bối cảnh của " + u.split("<đoạn_trích>\n")[1].split("\n")[0])
    chunks = [_c(i, f"đoạn {i}", section="Chương I") for i in range(10)]
    out = LLMContextEnricher(llm, max_workers=4).enrich(chunks, _pages())
    assert [c.context for c in out] == [f"Bối cảnh của đoạn {i}" for i in range(10)]
    prompt = next(u for s, u in llm.calls if "<đoạn_trích>\nđoạn 5\n" in u)
    assert prompt.startswith('<tài_liệu nguồn="luat_lao_dong.pdf">\nBỘ LUẬT LAO ĐỘNG')   # phần chung đứng đầu
    assert "Heading của đoạn: Chương I" in prompt
    assert "Đoạn liền trước:\nđoạn 4" in prompt and "Đoạn liền sau:\nđoạn 6" in prompt


def test_llm_context_enricher_partial_and_total_failure():
    def flaky(s, u):
        if "<đoạn_trích>\nđoạn 1\n" in u:   # chỉ chunk 1 lỗi (chunk 0 cũng nhắc "đoạn 1" ở phần đoạn liền sau)
            raise TimeoutError("x")
        return "ctx"

    out = LLMContextEnricher(EchoLLM(flaky), max_workers=1).enrich([_c(0, "đoạn 0"), _c(1, "đoạn 1")], _pages())
    assert [c.context for c in out] == ["ctx", None]

    def down(s, u):
        raise TimeoutError("x")

    with pytest.raises(RuntimeError):
        LLMContextEnricher(EchoLLM(down)).enrich([_c(0, "a")], _pages())


# --- pipeline -----------------------------------------------------------------------------

def _loader(value, source=None):
    return [Page("law", "luat_ld.pdf", 1, "Điều 1. Nghỉ hằng năm\nNgười lao động được nghỉ 12 ngày."),
            Page("law", "luat_ld.pdf", 2, "Điều 2. Tiền lương\nTiền lương trả hằng tháng.")]


def test_pipeline_applies_index_enhancers_and_persists_context():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "chunks.jsonl"

        def make():
            r = HybridRetriever(BM25Index(tokenizer=syllable_tokenize, tokenizer_name="s"), VectorIndex(HashEmbedder()))
            return RAGPipeline(ChunkStore(path), r, EchoLLM(lambda s, u: "x [1]"), loader=_loader,
                               index_enhancers=[SectionHeaderEnricher()])

        make().ingest("luat_ld.pdf")
        p2 = make()                                   # khởi động lại: context đọc từ chunks.jsonl
        assert all(c.context and "Tài liệu: luat ld" in c.context for c in p2.store.all())
        assert all(c.context for c in p2.retriever.chunks.values())


def test_index_config_guard():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "indexes" / "index_config.json"
        s = Settings()
        check_index_config(path, index_signature(s, []))
        check_index_config(path, index_signature(s, []))                # cùng cấu hình: OK
        with pytest.raises(IndexConfigMismatchError):
            check_index_config(path, index_signature(s, ["contextual"]))  # bật contextual trên index cũ


def test_settings_advanced_methods():
    assert Settings.from_env({"ADVANCED": "hyde, Contextual"}).advanced_methods == ["hyde", "contextual"]
    assert Settings().advanced_methods == []


def test_eval_configs_with_hyde():
    dense = VectorIndex(HashEmbedder(dim=256))
    r = HybridRetriever(BM25Index(tokenizer=syllable_tokenize, tokenizer_name="s"), dense,
                        extra_arms={"hyde": HydeRetriever(EchoLLM(lambda s, u: "nghỉ hằng năm"), dense)})
    r.build([_c(0, "nghỉ hằng năm 12 ngày")])
    q = Question("q1", "nghỉ phép", "paraphrase", "TV1", (GoldRef("luat_lao_dong.pdf", 1),))
    rows = retrieval_rows([q], r, ("hybrid", "hybrid+hyde", "hyde"))
    assert [row["config"] for row in rows] == ["hybrid", "hybrid+hyde", "hyde"]
    plain = HybridRetriever(BM25Index(tokenizer=syllable_tokenize, tokenizer_name="s"), dense)
    with pytest.raises(ValueError):
        retrieval_rows([q], plain, ("hybrid+hyde",))   # chưa bật hyde
