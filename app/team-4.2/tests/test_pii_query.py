"""Che PII trong CÂU HỎI (đường ask) và mở che ở câu trả lời.

Kiểm tra: câu hỏi chứa PII không đi tới HyDE, embedding, rerank, LLM, LLM cache, log, file trên đĩa;
câu trả lời hiển thị cho người hỏi có lại giá trị thật; placeholder của kho tài liệu không bị thay nhầm.
"""

import logging
import re
from types import SimpleNamespace

import pytest

from rag.advanced.hyde import HYDE_SYSTEM, HydeRetriever
from rag.generate.llm import LLMCache, OpenAIChatLLM
from rag.index.bm25_index import BM25Index
from rag.index.embedder import HashEmbedder
from rag.index.store import ChunkStore
from rag.index.vector_index import VectorIndex
from rag.pipeline import PII_NOTE, RAGPipeline
from rag.quality.pii import MaskState, mask_text
from rag.retrieve.hybrid import HybridRetriever
from rag.schema import Page

LAW = (
    "Điều 1. Nghĩa vụ thanh toán\nBên mua phải thanh toán đúng hạn theo hợp đồng.",
    "Điều 2. Phạt chậm thanh toán\nBên chậm thanh toán phải trả lãi trên số tiền chậm trả.",
    "Điều 3. Liên hệ\nĐường dây nóng: 0987 000 111.",          # PII trong kho -> [PHONE_1] lúc ingest
)
QUESTION = ("Họ và tên: Nguyễn Văn An, CCCD 001190000001, SĐT 0912 345 678, email an.nguyen@example.test. "
            "Hợp đồng 84.000.000 đồng chậm thanh toán thì bị phạt thế nào?")
RAW_PII = ["Nguyễn Văn An", "001190000001", "0912 345 678", "an.nguyen@example.test"]


# --- unmask -------------------------------------------------------------------------------

def test_query_placeholders_have_prefix_and_unmask_round_trip():
    state = MaskState(prefix="USER_")
    masked = mask_text("Gọi 0912 345 678 hoặc email a@example.test", state=state).masked_text
    assert masked == "Gọi [USER_PHONE_1] hoặc email [USER_EMAIL_1]"
    assert state.unmask(masked) == "Gọi 0912 345 678 hoặc email a@example.test"
    assert state.counts == {"phone": 1, "email": 1}


def test_unmask_tolerates_llm_spacing_and_case_but_not_other_tokens():
    state = MaskState(prefix="USER_")
    mask_text("SĐT 0912345678", state=state)
    text = "Liên hệ [ USER_PHONE_1 ], [user_phone_1], kho: [PHONE_1], lạ: [USER_PHONE_2]"
    assert state.unmask(text) == "Liên hệ 0912345678, 0912345678, kho: [PHONE_1], lạ: [USER_PHONE_2]"


def test_repr_of_state_does_not_leak_raw_values():
    state = MaskState(prefix="USER_")
    mask_text("CCCD 001190000001, 0912345678", state=state)
    assert "001190000001" not in repr(state) and "0912345678" not in repr(state)


# --- leak test đường ask ------------------------------------------------------------------

class _FakeOpenAI:
    """Giả API chat: ghi lại mọi messages gửi đi; trả đoạn giả cho HyDE, câu trả lời lặp lại placeholder."""

    def __init__(self):
        self.sent: list[str] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, model, messages, temperature=None):
        system, user = messages[0]["content"], messages[1]["content"]
        self.sent += [system, user]
        if system == HYDE_SYSTEM:
            reply = "Bên chậm thanh toán phải trả lãi chậm trả."
        else:
            # như LLM thật: nhắc lại thông tin khách lấy từ câu hỏi (đã che hoặc chưa che)
            question = user.split("CÂU HỎI:", 1)[1]
            customer = question.split(" Hợp đồng", 1)[0].strip()
            reply = f"Khách ({customer}) phải trả lãi chậm trả [1]. Đường dây nóng [PHONE_1]."
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply))])


class _SpyReranker:
    name = "spy"

    def __init__(self):
        self.queries: list[str] = []

    def rerank(self, query, hits, chunks, k):
        self.queries.append(query)
        return list(hits[:k])


def _build(tmp_path, *, mask_queries=True):
    api = _FakeOpenAI()
    cache = LLMCache(tmp_path / "cache" / "llm.sqlite")
    llm = OpenAIChatLLM("fake-model", client=api, cache=cache, retry_on=(RuntimeError,))
    embedder = HashEmbedder(dim=64)
    dense = HydeRetriever(llm, VectorIndex.open_qdrant(tmp_path / "vector", embedder))
    reranker = _SpyReranker()
    retriever = HybridRetriever(BM25Index(), dense, reranker=reranker)
    loader = lambda value, source=None: [Page("law", "luat.txt", i, t) for i, t in enumerate(LAW, start=1)]  # noqa: E731
    pipeline = RAGPipeline(ChunkStore(tmp_path / "chunks.jsonl"), retriever, llm, loader=loader,
                           mask_queries=mask_queries)
    pipeline.ingest("luat.txt")
    return pipeline, api, embedder, reranker, cache


def _leaks(tmp_path, api, embedder, reranker, log_text):
    surfaces = {
        "llm_api (HyDE + trả lời)": "\n".join(api.sent),
        "embedding": "\n".join(t for call in embedder.calls for t in call),
        "rerank": "\n".join(reranker.queries),
        "log": log_text,
    }
    for path in tmp_path.rglob("*"):
        if path.is_file():
            try:
                surfaces[f"file:{path.name}"] = path.read_bytes().decode("utf-8", errors="ignore")
            except PermissionError:      # .lock của Qdrant local trên Windows
                assert path.name == ".lock"
    return [(where, v) for where, text in surfaces.items() for v in RAW_PII if v in text]


def test_ask_masks_question_everywhere_and_unmasks_answer(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    pipeline, api, embedder, reranker, cache = _build(tmp_path)
    trace = pipeline.ask_debug(QUESTION)
    cache.close()

    # 1. không giá trị PII nào đi ra ngoài / xuống đĩa / vào log
    assert _leaks(tmp_path, api, embedder, reranker, caplog.text) == []
    assert any(api_text.startswith("CÂU HỎI:") for api_text in api.sent)            # HyDE đã được gọi
    assert any("[USER_CCCD_1]" in q for q in reranker.queries)

    # 2. câu hỏi đã che giữ nguyên số tiền (không bị che nhầm) và có ghi chú cho LLM
    assert "84.000.000 đồng" in trace.retrieval.query
    assert {"[USER_NAME_1]", "[USER_CCCD_1]", "[USER_PHONE_1]", "[USER_EMAIL_1]"} <= set(
        re.findall(r"\[USER_[A-Z]+_\d+\]", trace.retrieval.query))
    assert any(PII_NOTE.strip() in s for s in api.sent)
    assert trace.query_pii == {"name": 1, "cccd": 1, "phone": 1, "email": 1}

    # 3. câu trả lời cho người hỏi: placeholder của câu hỏi được mở, của kho thì giữ nguyên
    for value in RAW_PII:
        assert value in trace.answer.text
    assert "[PHONE_1]" in trace.answer.text and "0987 000 111" not in trace.answer.text
    assert "[USER_" not in trace.answer.text


def test_leak_test_detects_leaks_when_masking_is_off(tmp_path, caplog):
    """Đối chứng: tắt che câu hỏi thì test phải bắt được rò rỉ ở các bề mặt chính."""
    pipeline, api, embedder, reranker, cache = _build(tmp_path, mask_queries=False)
    pipeline.ask_debug(QUESTION)
    cache.close()
    where = {w for w, _ in _leaks(tmp_path, api, embedder, reranker, caplog.text)}
    assert {"llm_api (HyDE + trả lời)", "embedding", "rerank", "file:llm.sqlite"} <= where


def test_session_state_keeps_same_placeholder_across_turns(tmp_path):
    pipeline, api, *_ = _build(tmp_path)
    session = pipeline.new_query_mask_state()
    first = pipeline.ask_debug("SĐT khách 0912 345 678, chậm thanh toán bị phạt?", mask_state=session)
    second = pipeline.ask_debug("Khách 0912345678 có được gia hạn thanh toán không?", mask_state=session)
    assert "[USER_PHONE_1]" in first.retrieval.query and "[USER_PHONE_1]" in second.retrieval.query
    assert second.query_pii == {}          # không có PII MỚI ở lượt 2 (đã gặp ở lượt 1)


@pytest.mark.parametrize("question", ["Chậm thanh toán bị phạt thế nào?", "Phạt 84.000.000 đồng có đúng không?"])
def test_question_without_pii_keeps_prompt_unchanged(tmp_path, question):
    """Câu hỏi không có PII: không thêm ghi chú vào prompt -> LLM cache / kết quả eval cũ không đổi."""
    pipeline, api, *_ = _build(tmp_path)
    trace = pipeline.ask_debug(question)
    assert trace.retrieval.query == question and trace.query_pii == {}
    assert not any(PII_NOTE.strip() in s for s in api.sent)
