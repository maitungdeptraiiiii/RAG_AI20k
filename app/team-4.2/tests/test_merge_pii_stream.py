"""Gộp nhánh integration: che PII câu hỏi (W02-02f) phải đi TRƯỚC condense lịch sử chat và streaming (SSE)."""

from __future__ import annotations

from rag.index.bm25_index import BM25Index, syllable_tokenize
from rag.index.embedder import HashEmbedder
from rag.index.store import ChunkStore
from rag.index.vector_index import VectorIndex
from rag.pipeline import RAGPipeline, _StreamUnmasker
from rag.retrieve.hybrid import HybridRetriever
from rag.schema import Page

PHONE = "0912345678"
LAW = ("Điều 2. Thời giờ làm việc\nThời giờ làm việc không quá 8 giờ trong ngày.",)


class SpyLLM:
    """Ghi lại mọi prompt gửi ra ngoài; condense trả câu độc lập, answer stream placeholder bị cắt đôi."""

    model_id = "spy"

    def __init__(self, tokens):
        self.tokens = list(tokens)
        self.prompts: list[str] = []

    def complete(self, system: str, user: str) -> str:
        self.prompts.append(user)
        if "[CÂU HỎI MỚI]" in user:
            return '{"standalone_query": "Người có số [USER_PHONE_1] làm việc tối đa bao nhiêu giờ?"}'
        return "".join(self.tokens)

    def stream(self, system: str, user: str):
        self.prompts.append(user)
        yield from self.tokens


def _pipeline(llm) -> RAGPipeline:
    retriever = HybridRetriever(BM25Index(tokenizer=syllable_tokenize, tokenizer_name="syllable"),
                                VectorIndex(HashEmbedder(dim=64)))
    p = RAGPipeline(ChunkStore(), retriever, llm,
                    loader=lambda v, source=None: [Page("law", "luat.pdf", 1, LAW[0])])
    p.ingest("luat.pdf")
    return p


HISTORY = [{"query": f"Tôi tên An, số {PHONE}", "answer": f"Chào bạn, số {PHONE} đã ghi nhận."}]


def test_history_pii_is_masked_before_condense_and_answer_is_unmasked():
    llm = SpyLLM(["Số [USER_PHONE_1] làm tối đa 8 giờ [1]."])
    p = _pipeline(llm)
    trace = p.ask_debug("Còn thời giờ làm việc thì sao?", history=HISTORY)
    assert llm.prompts and all(PHONE not in u for u in llm.prompts)
    assert trace.condensed_query and PHONE not in trace.condensed_query
    assert PHONE in trace.answer.text and "[USER_PHONE_1]" not in trace.answer.text


def test_stream_unmasks_placeholder_split_across_tokens():
    llm = SpyLLM(["Số [USER_PH", "ONE_1] làm tối đa ", "8 giờ [1]."])
    p = _pipeline(llm)
    state = p.new_query_mask_state()
    events = list(p.ask_stream(f"Số {PHONE} làm thời giờ làm việc bao nhiêu?", mask_state=state))
    shown = "".join(e["delta"] for e in events if e["type"] == "token")
    assert shown == f"Số {PHONE} làm tối đa 8 giờ [1]."
    assert all("[USER_" not in e["delta"] for e in events if e["type"] == "token")
    done = next(e for e in events if e["type"] == "done")
    assert PHONE in done["answer"] and done["query_pii"] == {"phone": 1}
    assert all(PHONE not in u for u in llm.prompts)


def test_stream_unmasker_does_not_hold_ordinary_brackets_forever():
    u = _StreamUnmasker(RAGPipeline.new_query_mask_state())
    assert u.feed("xem [1") == "xem "
    assert u.feed("] và") == "[1] và"
    assert u.feed("[" + "x" * 60) == "[" + "x" * 60       # "[" mở quá xa: không phải placeholder, nhả ra
    assert u.flush() == ""
