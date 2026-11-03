import json
import unicodedata

import pytest

from rag.schema import (
    REFUSAL,
    Answer,
    Chunk,
    Citation,
    ContextBlock,
    GoldRef,
    Hit,
    Page,
    Question,
    make_chunk_id,
    make_doc_id,
    nfc,
)


def _chunk(cid="d:0000", page_start=3, page_end=4, section="Chương I", source="a.pdf"):
    return Chunk(cid, "d", source, page_start, page_end, section, "nội dung")


# --- quy ước chung ----------------------------------------------------------

def test_doc_id_stable_and_nfc_insensitive():
    nfd = unicodedata.normalize("NFD", "Điều 1. Phạm vi")
    assert make_doc_id(nfd) == make_doc_id(nfc(nfd))
    assert make_doc_id(b"abc") == make_doc_id(b"abc")
    assert make_doc_id(b"abc") != make_doc_id(b"abd")


def test_chunk_id_format():
    assert make_chunk_id("abc", 7) == "abc:0007"
    with pytest.raises(ValueError):
        make_chunk_id("abc", -1)


# --- Page / Chunk -----------------------------------------------------------

def test_page_normalizes_nfc_and_detects_empty():
    p = Page("d", "a.pdf", 1, unicodedata.normalize("NFD", "tiếng Việt"))
    assert p.text == nfc("tiếng Việt")
    assert Page("d", "a.pdf", 2, "  \n").is_empty


def test_page_number_starts_at_one():
    with pytest.raises(ValueError):
        Page("d", "a.pdf", 0, "x")


def test_chunk_page_range_validation():
    with pytest.raises(ValueError):
        _chunk(page_start=5, page_end=3)
    with pytest.raises(ValueError):
        _chunk(page_start=3, page_end=None)
    url_chunk = _chunk(page_start=None, page_end=None)
    assert not url_chunk.covers_page(1)


def test_chunk_roundtrip_jsonl():
    c = _chunk()
    assert Chunk.from_dict(json.loads(json.dumps(c.to_dict()))) == c


# --- Hit --------------------------------------------------------------------

def test_hit_rank_and_arm_validation():
    Hit("d:0000", 1.2, 1, "bm25")
    with pytest.raises(ValueError):
        Hit("d:0000", 1.2, 0, "bm25")
    with pytest.raises(ValueError):
        Hit("d:0000", 1.2, 1, "TF IDF")


# --- Citation / Answer ------------------------------------------------------

def test_citation_from_block_uses_page_start():
    cit = Citation.from_block(ContextBlock(2, _chunk()))
    assert (cit.n, cit.chunk_id, cit.page, cit.source) == (2, "d:0000", 3, "a.pdf")


def test_refusal_answer_invariants():
    hits = [Hit("d:0000", 0.01, 1, "fused")]
    a = Answer.refusal(hits)
    assert a.refused and a.text == REFUSAL and a.citations == [] and a.hits == hits
    with pytest.raises(ValueError):
        Answer(text="bịa", citations=[], refused=True)


def test_answer_roundtrip():
    a = Answer(
        text="Câu trả lời [1].",
        citations=[Citation.from_block(ContextBlock(1, _chunk()))],
        refused=False,
        hits=[Hit("d:0000", 0.03, 1, "fused")],
    )
    assert Answer.from_dict(json.loads(json.dumps(a.to_dict()))) == a


# --- Eval -------------------------------------------------------------------

def test_question_from_jsonl_line_and_gold_matching():
    line = (
        '{"id": "q01", "question": "...", "type": "lookup", "author": "TV1",'
        ' "gold": [{"source": "a.pdf", "page": 4}, {"source": "a.pdf", "page": 12}]}'
    )
    q = Question.from_dict(json.loads(line))
    assert q.in_scope
    assert q.is_relevant(_chunk(page_start=3, page_end=4))
    assert not q.is_relevant(_chunk(page_start=5, page_end=6))
    assert not q.is_relevant(_chunk(source="b.pdf"))
    assert Question.from_dict(q.to_dict()) == q


def test_gold_by_section():
    g = GoldRef("page.html", section="Chương I")
    assert g.matches(_chunk(source="page.html", page_start=None, page_end=None))


def test_question_gold_rules():
    with pytest.raises(ValueError):
        Question("q1", "?", "lookup", "TV1")  # thiếu gold
    with pytest.raises(ValueError):
        Question("q2", "?", "out_of_scope", "TV1", (GoldRef("a.pdf", 1),))
    with pytest.raises(ValueError):
        Question("q3", "?", "khac", "TV1", (GoldRef("a.pdf", 1),))
    assert not Question("q4", "?", "out_of_scope", "TV2").in_scope


def test_question_reference_rules_and_roundtrip():
    gold = (GoldRef("a.pdf", 1),)
    q = Question("q5", "?", "lookup", "TV1", gold, reference="Đáp án mẫu.")
    assert Question.from_dict(json.loads(json.dumps(q.to_dict()))) == q
    no_ref = Question("q6", "?", "lookup", "TV1", gold)
    assert "reference" not in no_ref.to_dict()
    with pytest.raises(ValueError):
        Question("q7", "?", "lookup", "TV1", gold, reference="  ")
    with pytest.raises(ValueError):
        Question("q8", "?", "out_of_scope", "TV1", reference="Không có.")
