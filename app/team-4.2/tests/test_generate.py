from types import SimpleNamespace

import pytest

from rag.generate.answer import (
    SYSTEM_PROMPT,
    build_citations,
    build_prompt,
    cited_numbers,
    format_context,
    is_refusal,
)
from rag.generate.llm import LLMCache, OpenAIChatLLM
from rag.schema import REFUSAL, Chunk, ContextBlock, Hit


def _blocks():
    a = Chunk("d:0000", "d", "luat.pdf", 3, 3, "Chương I > Điều 5. Thời hiệu", "Thời hiệu khởi kiện là hai năm.")
    b = Chunk("u:0000", "u", "https://x.vn", None, None, None, "Nội dung trang web.")
    c = Chunk("d:0001", "d", "luat.pdf", 3, 4, None, "Đoạn vắt qua trang.")
    return [ContextBlock(1, a), ContextBlock(2, b), ContextBlock(3, c)]


# --- prompt / context -----------------------------------------------------------------

def test_format_context_labels():
    ctx = format_context(_blocks())
    assert "[1] (luat.pdf, trang 3, Chương I > Điều 5. Thời hiệu)\nThời hiệu khởi kiện là hai năm." in ctx
    assert "[2] (https://x.vn)\n" in ctx
    assert "[3] (luat.pdf, trang 3-4)" in ctx


def test_prompt_contains_rules_question_and_refusal_sentence():
    system, user = build_prompt("  Thời hiệu?  ", _blocks())
    assert system == SYSTEM_PROMPT and REFUSAL in system
    assert user.startswith("TÀI LIỆU:\n[1]") and user.endswith("CÂU HỎI: Thời hiệu?")


# --- citation ---------------------------------------------------------------------------

def test_cited_numbers_formats_and_order():
    assert cited_numbers("A [2]. B [1][3]. C [2, 3] [10]") == [2, 1, 3, 10]


def test_build_citations_maps_valid_numbers_only():
    hits = [Hit("d:0000", 0.9, 1, "rerank")]
    ans = build_citations("Thời hiệu là hai năm [1]. Thêm [7].", _blocks(), hits)
    assert not ans.refused and ans.hits == hits
    assert [(c.n, c.chunk_id, c.source, c.page) for c in ans.citations] == [(1, "d:0000", "luat.pdf", 3)]
    assert ans.citations[0].quote == "Thời hiệu khởi kiện là hai năm."
    assert "[7]" in ans.text   # không sửa text; loại [n] sai là việc của guardrail


def test_refusal_text_becomes_refused_answer():
    assert is_refusal("không có trong tài liệu")
    ans = build_citations(REFUSAL, _blocks())
    assert ans.refused and ans.text == REFUSAL and ans.citations == []


def test_long_quote_is_truncated():
    long = Chunk("d:0002", "d", "a.pdf", 1, 1, None, " ".join(["chữ"] * 200))
    ans = build_citations("x [1]", [ContextBlock(1, long)])
    assert len(ans.citations[0].quote) <= 205 and ans.citations[0].quote.endswith("…")


# --- LLM client -------------------------------------------------------------------------

class FakeChat:
    def __init__(self, fail_times=0):
        self.calls = []
        self.fail_times = fail_times
        self.chat = SimpleNamespace(completions=self)

    def create(self, **params):
        if self.fail_times:
            self.fail_times -= 1
            raise TimeoutError("timeout")
        self.calls.append(params)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=" Trả lời [1] "))])


def _llm(client, **kw):
    return OpenAIChatLLM("m", client=client, retry_on=(TimeoutError,), sleep=lambda s: None, **kw)


def test_llm_sends_messages_and_temperature():
    client = FakeChat()
    assert _llm(client).complete("sys", "user") == "Trả lời [1]"
    params = client.calls[0]
    assert params["temperature"] == 0.0 and params["model"] == "m"
    assert params["messages"] == [{"role": "system", "content": "sys"}, {"role": "user", "content": "user"}]
    client2 = FakeChat()
    _llm(client2, temperature=None).complete("s", "u")
    assert "temperature" not in client2.calls[0]


def test_llm_cache_and_retry():
    client = FakeChat(fail_times=1)
    llm = _llm(client, cache=LLMCache(), max_retries=2)
    assert llm.complete("s", "u") == llm.complete("s", "u")
    assert len(client.calls) == 1
    with pytest.raises(TimeoutError):
        _llm(FakeChat(fail_times=5), max_retries=1).complete("s", "u")
