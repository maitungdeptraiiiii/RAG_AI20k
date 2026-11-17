"""Kiểm thử Streaming Response cho OpenAIChatLLM, RAGPipeline và Web Server."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from starlette.requests import Request

from rag.generate.llm import LLMCache, OpenAIChatLLM
from rag.index.bm25_index import BM25Index, syllable_tokenize
from rag.index.embedder import HashEmbedder
from rag.index.store import ChunkStore
from rag.index.vector_index import VectorIndex
from rag.pipeline import RAGPipeline
from rag.retrieve.hybrid import HybridRetriever
from rag.schema import Page


class FakeStreamingLLM:
    model_id = "fake-streaming"

    def __init__(self, tokens=("Theo Điều 2, ", "thời giờ làm việc ", "không quá 8 giờ [1].")):
        self.tokens = list(tokens)

    def complete(self, system: str, user: str) -> str:
        return "".join(self.tokens)

    def stream(self, system: str, user: str):
        for t in self.tokens:
            yield t


LAW = (
    "Điều 1. Phạm vi điều chỉnh\nLuật này quy định về hợp đồng lao động.",
    "Điều 2. Thời giờ làm việc\nThời giờ làm việc không quá 8 giờ trong ngày.",
)


def fake_loader(value, source=None):
    return [Page("law", source or "luat_ld.pdf", i, t) for i, t in enumerate(LAW, start=1)]


def _build_test_pipeline(llm=None):
    retriever = HybridRetriever(
        BM25Index(tokenizer=syllable_tokenize, tokenizer_name="syllable"),
        VectorIndex(HashEmbedder(dim=256)),
    )
    store = ChunkStore()
    pipeline = RAGPipeline(store, retriever, llm or FakeStreamingLLM(), loader=fake_loader)
    pipeline.ingest("dummy.pdf")
    return pipeline


def test_openai_chat_llm_stream_with_cache(tmp_path):
    cache = LLMCache(tmp_path / "test_cache.sqlite")
    mock_client = MagicMock()

    # Tạo mock streaming chunks tương tự OpenAI API
    chunk1 = MagicMock()
    chunk1.choices = [MagicMock(delta=MagicMock(content="Xin "))]
    chunk2 = MagicMock()
    chunk2.choices = [MagicMock(delta=MagicMock(content="chào "))]
    chunk3 = MagicMock()
    chunk3.choices = [MagicMock(delta=MagicMock(content="bạn."))]

    mock_client.chat.completions.create.return_value = [chunk1, chunk2, chunk3]

    llm = OpenAIChatLLM("test-model", client=mock_client, cache=cache)

    # Lần 1: Gọi qua API
    events = list(llm.stream("system prompt", "user prompt"))
    assert events == ["Xin ", "chào ", "bạn."]
    assert mock_client.chat.completions.create.call_count == 1

    # Lần 2: Phải lấy từ SQLite cache
    cached_events = list(llm.stream("system prompt", "user prompt"))
    assert cached_events == ["Xin chào bạn."]
    # Không tăng số lần gọi OpenAI client
    assert mock_client.chat.completions.create.call_count == 1


def test_pipeline_ask_stream_yields_expected_events():
    pipeline = _build_test_pipeline()
    events = list(pipeline.ask_stream("thời giờ làm việc bao nhiêu giờ?"))

    types = [e["type"] for e in events]
    assert "sources" in types
    assert "token" in types
    assert "done" in types

    # Kiểm tra event sources
    sources_evt = next(e for e in events if e["type"] == "sources")
    assert len(sources_evt["sources"]) > 0
    assert "condensed_query" in sources_evt

    # Kiểm tra tokens
    tokens = [e["delta"] for e in events if e["type"] == "token"]
    assert len(tokens) == 3
    assert "".join(tokens) == "Theo Điều 2, thời giờ làm việc không quá 8 giờ [1]."

    # Kiểm tra event done
    done_evt = next(e for e in events if e["type"] == "done")
    assert not done_evt["refused"]
    assert len(done_evt["citations"]) > 0
    assert "arms" in done_evt["trace"]
    assert "final_hits" in done_evt["trace"]


@pytest.mark.asyncio
async def test_server_handle_chat_backward_compat_and_stream(monkeypatch):
    import importlib.util
    from pathlib import Path

    server_path = Path(__file__).resolve().parent.parent / "ui" / "server.py"
    spec = importlib.util.spec_from_file_location("server_module", server_path)
    server_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server_module)

    pipeline = _build_test_pipeline()
    monkeypatch.setattr(server_module, "get_pipeline", lambda: (pipeline, MagicMock()))
    # Test này kiểm tra lớp vận chuyển (JSON vs SSE); trả lời luật nay đi qua kho có phiên bản, ở đây thay bằng
    # pipeline test để giữ đúng mục đích kiểm tra định dạng phản hồi.
    monkeypatch.setattr(server_module, "_sync_chat",
                        lambda q, as_of, m, h=None: server_module._sync_ask(q, pipeline, m, h))

    def old_stream(q, as_of, m, h=None):
        for event in pipeline.ask_stream(q, history=h, mask_state=m):
            yield server_module._sse(event)
    monkeypatch.setattr(server_module, "_sync_stream", old_stream)

    # 1. Non-streaming (stream: false hoặc không truyền) -> JSONResponse
    req_json = Request({
        "type": "http",
        "method": "POST",
        "headers": [(b"content-type", b"application/json")],
    })
    async def json_body():
        return {"query": "thời giờ làm việc?", "stream": False}
    req_json.json = json_body

    res_json = await server_module.handle_chat(req_json)
    assert res_json.status_code == 200
    assert res_json.media_type == "application/json"
    data = json.loads(res_json.body)
    assert "answer" in data
    assert "citations" in data

    # 2. Streaming (stream: true) -> StreamingResponse (text/event-stream)
    req_stream = Request({
        "type": "http",
        "method": "POST",
        "headers": [(b"content-type", b"application/json")],
    })
    async def stream_body():
        return {"query": "thời giờ làm việc?", "stream": True}
    req_stream.json = stream_body

    res_stream = await server_module.handle_chat(req_stream)
    assert res_stream.status_code == 200
    assert res_stream.media_type == "text/event-stream"
