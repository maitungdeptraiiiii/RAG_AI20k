import json

import pytest

from rag.generate.json_stream import AnswerFieldStream


@pytest.mark.parametrize("ensure_ascii", [False, True])
def test_answer_field_stream_handles_every_fragment_boundary_without_metadata(ensure_ascii):
    text = 'Xin chào Huy!\nTrích dẫn [1], dấu "ngoặc", \\ và emoji 😀.'
    raw = json.dumps({"answer_markdown": text, "issues": [{"limitation": "PRIVATE_METADATA"}]},
                     ensure_ascii=ensure_ascii)
    for split in range(len(raw) + 1):
        decoder = AnswerFieldStream()
        result = decoder.feed(raw[:split]) + decoder.feed(raw[split:])
        assert result == text
        assert "PRIVATE_METADATA" not in result
    decoder = AnswerFieldStream()
    assert "".join(decoder.feed(char) for char in raw) == text


def test_streams_before_answer_field_or_metadata_finishes_and_accepts_cached_full_json():
    decoder = AnswerFieldStream()
    assert decoder.feed('{"answer_markdown":"Đang ') == "Đang "
    assert not decoder.closed
    assert decoder.feed('trả lời. [1]","issues":[]}') == "trả lời. [1]"
    assert decoder.closed
    decoder = AnswerFieldStream()
    assert decoder.feed('```json\n{"answer_markdown":"Bản cache","issues":[]}\n```') == "Bản cache"


def test_other_field_order_does_not_leak_raw_json_or_metadata():
    decoder = AnswerFieldStream()
    assert decoder.feed('{"issues":[{"limitation":"INTERNAL"}],"answer_markdown":"Nội dung"}') == ""


@pytest.mark.parametrize("raw", ['{"answer_markdown":"bad\\q',
                                '{"answer_markdown":"bad\\uDC00',
                                '{"answer_markdown":"bad\\uD800\\u0000'])
def test_malformed_escapes_fail_without_emitting_invalid_text(raw):
    with pytest.raises(ValueError):
        AnswerFieldStream().feed(raw)
