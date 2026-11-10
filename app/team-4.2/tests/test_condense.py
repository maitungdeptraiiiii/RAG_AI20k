from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from rag.advanced.condense import QueryCondenser
from rag.index.bm25_index import BM25Index, syllable_tokenize
from rag.index.embedder import HashEmbedder
from rag.index.store import ChunkStore
from rag.index.vector_index import VectorIndex
from rag.pipeline import RAGPipeline
from rag.retrieve.hybrid import HybridRetriever
from rag.schema import Page


class MockLLM:
    def __init__(self, reply: str = ""):
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.reply


def test_condense_empty_history_returns_original_without_calling_llm():
    mock_llm = MockLLM(reply="something else")
    condenser = QueryCondenser(mock_llm)

    # Trường hợp history là None
    res1 = condenser.condense("Thời gian thử việc tối đa là bao lâu?", history=None)
    assert res1 == "Thời gian thử việc tối đa là bao lâu?"
    assert len(mock_llm.calls) == 0

    # Trường hợp history rỗng
    res2 = condenser.condense("Quy định ở đâu?", history=[])
    assert res2 == "Quy định ở đâu?"
    assert len(mock_llm.calls) == 0

    # Trường hợp history có các turn rỗng
    res3 = condenser.condense("Thế còn lương?", history=[{"query": "", "answer": ""}])
    assert res3 == "Thế còn lương?"
    assert len(mock_llm.calls) == 0


def test_condense_with_pronoun_or_ellipsis_returns_rewritten_query():
    mock_llm = MockLLM(
        reply=json.dumps(
            {
                "standalone_query": "Thời gian thử việc tối đa đối với người lao động có trình độ trung cấp là bao lâu?"
            },
            ensure_ascii=False,
        )
    )
    condenser = QueryCondenser(mock_llm)
    history = [
        {
            "query": "Thời gian thử việc tối đa của người lao động là bao lâu?",
            "answer": "Theo Điều 25 Bộ luật Lao động, tối đa 180 ngày đối với quản lý doanh nghiệp.",
        }
    ]

    result = condenser.condense("Thế còn với lao động có trình độ trung cấp?", history=history)

    assert (
        result
        == "Thời gian thử việc tối đa đối với người lao động có trình độ trung cấp là bao lâu?"
    )
    assert len(mock_llm.calls) == 1
    # Kiểm tra prompt gửi tới LLM có chứa câu hỏi trước đó và câu hỏi mới
    system_arg, user_arg = mock_llm.calls[0]
    assert "Thời gian thử việc tối đa của người lao động" in user_arg
    assert "Thế còn với lao động có trình độ trung cấp?" in user_arg


def test_condense_strips_markdown_code_fences():
    reply_with_markdown = """```json
{
  "standalone_query": "Mức xử phạt hành vi thử việc quá thời hạn quy định là bao nhiêu?"
}
```"""
    mock_llm = MockLLM(reply=reply_with_markdown)
    condenser = QueryCondenser(mock_llm)
    history = [
        {"query": "Thời gian thử việc", "answer": "Tối đa 180 ngày theo Điều 25 BLLĐ."}
    ]

    result = condenser.condense("Nếu làm quá thời hạn này thì bị phạt bao nhiêu?", history=history)
    assert result == "Mức xử phạt hành vi thử việc quá thời hạn quy định là bao nhiêu?"


def test_condense_fallback_to_original_on_invalid_json_or_exception():
    # LLM trả về văn bản không phải JSON hợp lệ
    mock_llm = MockLLM(reply="Tôi không hiểu câu hỏi của bạn.")
    condenser = QueryCondenser(mock_llm)
    history = [{"query": "Hợp đồng lao động", "answer": "Có 2 loại hợp đồng..."}]

    result = condenser.condense("Thế còn phụ lục hợp đồng?", history=history)
    assert result == "Thế còn phụ lục hợp đồng?"

    # LLM ném ngoại lệ
    class FailingLLM:
        def complete(self, s: str, u: str) -> str:
            raise ConnectionError("API connection timeout")

    failing_condenser = QueryCondenser(FailingLLM())
    safe_result = failing_condenser.condense("Thế còn phụ lục hợp đồng?", history=history)
    assert safe_result == "Thế còn phụ lục hợp đồng?"


def test_condense_limits_history_turns():
    mock_llm = MockLLM(reply='{"standalone_query": "Câu hỏi số 6"}')
    condenser = QueryCondenser(mock_llm, max_history_turns=2)
    history = [
        {"query": f"Câu hỏi {i}", "answer": f"Trả lời {i}"} for i in range(1, 6)
    ]

    condenser.condense("Câu hỏi 6 cộc lốc?", history=history)

    assert len(mock_llm.calls) == 1
    _, user_arg = mock_llm.calls[0]
    # Chỉ chứa 2 turn gần nhất: Câu hỏi 4 và Câu hỏi 5
    assert "Câu hỏi 4" in user_arg
    assert "Câu hỏi 5" in user_arg
    assert "Câu hỏi 1" not in user_arg
    assert "Câu hỏi 2" not in user_arg


def test_pipeline_ask_debug_with_history():
    def mock_loader(val, source=None):
        return [
            Page("law", "luat.txt", 1, "Điều 1. Thời gian thử việc không quá 30 ngày đối với trung cấp.")
        ]

    # Mock LLM dùng chung cho cả Condenser và Answer
    def mock_complete(sys_prompt, user_prompt):
        if "giải nén ngữ cảnh" in sys_prompt:
            return '{"standalone_query": "Thời gian thử việc của lao động trung cấp?"}'
        return "Theo tài liệu, không quá 30 ngày [1]."

    llm = SimpleNamespace(complete=mock_complete)
    retriever = HybridRetriever(
        BM25Index(tokenizer=syllable_tokenize, tokenizer_name="syllable"),
        VectorIndex(HashEmbedder(dim=64)),
    )
    store = ChunkStore()
    pipeline = RAGPipeline(store, retriever, llm, loader=mock_loader)
    pipeline.ingest("dummy_path")

    history = [{"query": "Thử việc tối đa bao lâu?", "answer": "Tối đa 180 ngày."}]
    trace = pipeline.ask_debug("Thế còn trung cấp?", history=history)

    assert trace.condensed_query == "Thời gian thử việc của lao động trung cấp?"
    assert trace.answer.text == "Theo tài liệu, không quá 30 ngày [1]."
    assert len(trace.answer.citations) >= 1
