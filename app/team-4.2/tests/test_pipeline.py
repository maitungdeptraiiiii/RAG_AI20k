import os
import tempfile
from pathlib import Path

import pytest

from rag.config import Settings, parse_env_file
from rag.eval.metrics import hit_at_k, load_questions, mean, mrr_at_k, recall_at_k, unmatched_gold
from rag.eval.runner import (
    answer_rows,
    draft_reference,
    ragas_rows,
    refusal_summary,
    retrieval_rows,
    summary_markdown,
    write_csv,
)
from rag.index.bm25_index import BM25Index, syllable_tokenize
from rag.index.embedder import HashEmbedder
from rag.index.store import ChunkStore
from rag.index.vector_index import VectorIndex
from rag.pipeline import RAGPipeline
from rag.retrieve.context import ContextConfig
from rag.retrieve.hybrid import HybridRetriever
from rag.schema import REFUSAL, Chunk, GoldRef, Page, Question

LAW = (
    "Điều 1. Phạm vi điều chỉnh\nLuật này quy định về hợp đồng lao động và tiền lương.",
    "Điều 2. Thời giờ làm việc\nThời giờ làm việc bình thường không quá 8 giờ trong một ngày.",
    "Điều 3. Nghỉ hằng năm\nNgười lao động được nghỉ hằng năm 12 ngày làm việc.",
)


class FakeLLM:
    model_id = "fake"

    def __init__(self, reply="Theo tài liệu, không quá 8 giờ một ngày [1]."):
        self.reply = reply
        self.calls = []

    def complete(self, system, user):
        self.calls.append((system, user))
        return self.reply


def fake_loader(value, source=None):
    return [Page("law", source or "luat_ld.pdf", i, t) for i, t in enumerate(LAW, start=1)]


def _pipeline(llm=None, store=None, **kw):
    retriever = HybridRetriever(
        BM25Index(tokenizer=syllable_tokenize, tokenizer_name="syllable"), VectorIndex(HashEmbedder(dim=256))
    )
    store = store if store is not None else ChunkStore()   # ChunkStore rỗng có len 0 -> falsy, không dùng `or`
    return RAGPipeline(store, retriever, llm or FakeLLM(), loader=fake_loader, **kw)


# --- config ---------------------------------------------------------------------------

def test_settings_from_env_and_env_file():
    s = Settings.from_env({"TOP_K": "7", "RERANK_BACKEND": "jev", "LLM_TEMPERATURE": "none",
                           "DATA_DIR": "data/x", "CONTEXT_MIN_P": "0.6", "LLM_BASE_URL": ""})
    assert (s.top_k, s.rerank_backend, s.llm_temperature, s.context_min_p) == (7, "jev", None, 0.6)
    assert s.chunks_path == Path("data/x/processed/chunks.jsonl") and s.llm_base_url is None
    with pytest.raises(ValueError):
        Settings.from_env({"RERANK_BACKEND": "bge"})
    with tempfile.TemporaryDirectory() as d:
        env = Path(d) / ".env"
        env.write_text('# c\nTOP_K=3   # ghi chú\nLLM_MODEL="gpt-x"\nexport RRF_K=10\nBAD\n', encoding="utf-8")
        assert parse_env_file(env) == {"TOP_K": "3", "LLM_MODEL": "gpt-x", "RRF_K": "10"}


def test_settings_load_does_not_override_existing_env():
    with tempfile.TemporaryDirectory() as d:
        env = Path(d) / ".env"
        env.write_text("ARM_K=11\nMAX_SYLLABLES=123\n", encoding="utf-8")
        os.environ["ARM_K"] = "9"
        try:
            s = Settings.load(env)
            assert s.arm_k == 9 and s.max_syllables == 123
        finally:
            os.environ.pop("ARM_K", None)
            os.environ.pop("MAX_SYLLABLES", None)


# --- pipeline ---------------------------------------------------------------------------

def test_ingest_then_ask_end_to_end():
    llm = FakeLLM()
    p = _pipeline(llm)
    report = p.ingest("luat_ld.pdf")
    assert report.n_chunks == 3 and not report.skipped
    trace = p.ask_debug("Thời giờ làm việc bình thường một ngày là bao nhiêu giờ?")
    assert trace.llm_called and not trace.answer.refused
    assert trace.retrieval.hits[0].chunk_id == "law:0001"
    assert trace.answer.citations[0].chunk_id == trace.context.blocks[0].chunk.chunk_id
    assert "TÀI LIỆU:\n[1] (luat_ld.pdf, trang 2" in llm.calls[0][1]


def test_ingest_same_document_twice_is_skipped():
    p = _pipeline()
    p.ingest("luat_ld.pdf")
    again = p.ingest("luat_ld.pdf")
    assert again.skipped and len(p.store) == 3


def test_restart_rebuilds_retriever_from_store():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "chunks.jsonl"
        _pipeline(store=ChunkStore(path)).ingest("luat_ld.pdf")
        p2 = _pipeline(store=ChunkStore(path))
        assert len(p2.retriever.chunks) == 3
        assert not p2.ask("nghỉ hằng năm bao nhiêu ngày").refused


def test_empty_context_refuses_without_calling_llm():
    llm = FakeLLM()
    p = _pipeline(llm)            # chưa ingest gì
    trace = p.ask_debug("câu hỏi bất kỳ")
    assert trace.answer.refused and trace.answer.text == REFUSAL and not trace.llm_called
    assert llm.calls == []


def test_llm_refusal_is_passed_through():
    p = _pipeline(FakeLLM(reply=REFUSAL))
    p.ingest("luat_ld.pdf")
    assert p.ask("Thuế thu nhập cá nhân?").refused


# --- eval -------------------------------------------------------------------------------

def _q(id_, page, type_="lookup", text="thời giờ làm việc bình thường"):
    gold = (GoldRef("luat_ld.pdf", page),) if page else ()
    return Question(id_, text, type_, "TV3", gold)


def test_metrics():
    chunks = {f"law:{i:04d}": Chunk(f"law:{i:04d}", "law", "luat_ld.pdf", i + 1, i + 1, None, "t") for i in range(3)}
    q = Question("q", "?", "multi", "TV1", (GoldRef("luat_ld.pdf", 2), GoldRef("luat_ld.pdf", 3)))
    ranked = ["law:0000", "law:0001", "law:0002"]
    assert recall_at_k(q, ranked, chunks, 2) == 0.5
    assert hit_at_k(q, ranked, chunks, 1) == 0.0
    assert mrr_at_k(q, ranked, chunks, 5) == 0.5
    oos = Question("o", "?", "out_of_scope", "TV1")
    assert recall_at_k(oos, ranked, chunks, 5) is None and mean([None, 1.0, 0.0]) == 0.5
    assert unmatched_gold([q, _q("x", 9)], chunks.values()) == {"x": ["luat_ld.pdf#p9"]}


def test_load_questions_validates():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "q.jsonl"
        path.write_text(
            '{"id":"q1","question":"?","type":"lookup","author":"TV1","gold":[{"source":"a.pdf","page":1}]}\n'
            '{"id":"q1","question":"?","type":"out_of_scope","author":"TV1"}\n', encoding="utf-8")
        with pytest.raises(ValueError):
            load_questions(path)


def test_retrieval_rows_and_summary():
    p = _pipeline()
    p.ingest("luat_ld.pdf")
    qs = [_q("q1", 2), _q("q2", None, "out_of_scope", "giá vàng hôm nay")]
    rows = retrieval_rows(qs, p.retriever, ("bm25", "dense", "hybrid"))
    assert len(rows) == 3 and {r["config"] for r in rows} == {"bm25", "dense", "hybrid"}
    assert next(r for r in rows if r["config"] == "bm25")["mrr@5"] == 1.0
    md = summary_markdown(rows)
    assert "| config | n | recall@5 | hit@5 | mrr@5 | recall@20 |" in md and "| bm25 | 1 |" in md
    with tempfile.TemporaryDirectory() as d:
        write_csv(rows, Path(d) / "r.csv")
        assert (Path(d) / "r.csv").read_text(encoding="utf-8").startswith("id,type,author,config")
    with pytest.raises(ValueError):
        retrieval_rows(qs, p.retriever, ("tfidf",))


def test_answer_rows_refusal_summary_and_ragas_rows():
    p = _pipeline()
    p.ingest("luat_ld.pdf")
    q1 = Question("q1", "thời giờ làm việc bình thường", "lookup", "TV1",
                  (GoldRef("luat_ld.pdf", 2),), reference="Không quá 8 giờ một ngày.")
    rows = answer_rows([q1, _q("q2", None, "out_of_scope", "giá vàng")], p)
    assert rows[0]["context_has_gold"] is True and rows[1]["context_has_gold"] is None
    s = refusal_summary(rows)
    assert s["context_has_gold"] == 1.0 and s["refuse_rate_in_scope"] == 0.0
    rr = ragas_rows([q1], p)
    assert rr[0]["reference"] == "Không quá 8 giờ một ngày." and rr[0]["retrieved_contexts"]


def test_draft_reference_uses_gold_pages_only():
    llm = FakeLLM(reply=" Không quá 8 giờ. ")
    p = _pipeline(llm)
    p.ingest("luat_ld.pdf")
    assert draft_reference(_q("q1", 2), p.store, llm) == "Không quá 8 giờ."
    user = llm.calls[-1][1]
    assert "8 giờ" in user and "12 ngày" not in user          # chỉ text trang gold
    assert draft_reference(_q("q2", None, "out_of_scope"), p.store, llm) is None
    assert draft_reference(_q("q3", 9), p.store, llm) is None  # gold không khớp chunk nào
