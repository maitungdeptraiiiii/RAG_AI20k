import json
import tempfile
import unicodedata
from pathlib import Path

import pytest

from rag.index.bm25_index import BM25Index, syllable_tokenize, tokenize_with
from rag.schema import Chunk

# Giả lập pyvi: nối một số từ ghép bằng "_" (không cần cài pyvi khi test).
_COMPOUNDS = {"tài sản": "tài_sản", "sở hữu": "sở_hữu", "hợp đồng": "hợp_đồng"}


def _fake_pyvi(text):
    for a, b in _COMPOUNDS.items():
        text = text.replace(a, b).replace(a.capitalize(), b.capitalize())
    return text


fake_vi_tokenize = tokenize_with(_fake_pyvi)


def _c(i, text):
    return Chunk(f"d:{i:04d}", "d", "a.pdf", 1, 1, None, text)


def _index(*texts, tokenizer=syllable_tokenize, name="syllable"):
    idx = BM25Index(tokenizer=tokenizer, tokenizer_name=name)
    idx.build([_c(i, t) for i, t in enumerate(texts)])
    return idx


# --- tokenizer ------------------------------------------------------------------

def test_tokenizer_lowercases_strips_punct_and_keeps_compounds():
    assert fake_vi_tokenize("Quyền sở hữu tài sản, theo Điều 158.") == [
        "quyền", "sở_hữu", "tài_sản", "theo", "điều", "158"
    ]


def test_tokenizer_normalizes_nfd():
    nfd = unicodedata.normalize("NFD", "Điều")
    assert syllable_tokenize(nfd) == ["điều"]


# --- search -------------------------------------------------------------------

def test_relevant_chunk_ranks_first():
    idx = _index(
        "Hợp đồng mua bán nhà ở phải lập thành văn bản.",
        "Quyền sở hữu tài sản được pháp luật bảo vệ.",
        "Thời hiệu khởi kiện là hai năm.",
    )
    hits = idx.search("quyền sở hữu tài sản", k=3)
    assert hits[0].chunk_id == "d:0001"
    assert hits[0].arm == "bm25" and hits[0].rank == 1


def test_only_positive_scores_returned():
    idx = _index("tài sản chung", "hợp đồng thuê nhà")
    hits = idx.search("tài sản", k=5)
    assert [h.chunk_id for h in hits] == ["d:0000"]
    assert all(h.score > 0 for h in hits)
    assert idx.search("không khớp gì", k=5) == []


def test_term_in_every_chunk_still_scores_on_tiny_corpus():
    # rank_bm25.BM25Okapi cho idf <= 0 trường hợp này; công thức ln(1 + ...) thì không.
    idx = _index("điều một", "điều hai")
    assert len(idx.search("điều", k=5)) == 2


def test_word_segmentation_separates_compound_from_syllables():
    idx = _index("tài sản chung", "tài năng và sản lượng", tokenizer=fake_vi_tokenize, name="fake")
    assert [h.chunk_id for h in idx.search("tài sản", k=5)] == ["d:0000"]
    syl = _index("tài sản chung", "tài năng và sản lượng")
    assert len(syl.search("tài sản", k=5)) == 2   # tách âm tiết thì chunk 2 cũng khớp


def test_ties_broken_by_chunk_id_and_k_limits():
    idx = BM25Index(tokenizer=syllable_tokenize, tokenizer_name="syllable")
    idx.build([_c(2, "luật đất đai"), _c(1, "luật đất đai"), _c(3, "khác")])
    hits = idx.search("đất đai", k=1)
    assert [h.chunk_id for h in hits] == ["d:0001"]
    with pytest.raises(ValueError):
        idx.search("x", k=0)


def test_empty_index_and_empty_query():
    assert BM25Index(tokenizer=syllable_tokenize).search("x", k=5) == []
    assert _index("a b c").search("  ...  ", k=5) == []


# --- build idempotent / tăng dần --------------------------------------------------

def test_build_twice_does_not_duplicate():
    idx = _index("tài sản")
    assert idx.build([_c(0, "tài sản")]) == 0
    assert len(idx) == 1


def test_incremental_build_equals_full_build():
    texts = ["tài sản chung", "hợp đồng thuê", "tài sản riêng của vợ chồng"]
    full = _index(*texts)
    inc = BM25Index(tokenizer=syllable_tokenize, tokenizer_name="syllable")
    for i, t in enumerate(texts):
        inc.build([_c(i, t)])
    assert inc.search("tài sản riêng", 3) == full.search("tài sản riêng", 3)


# --- lưu / tải ----------------------------------------------------------------------

def test_save_load_roundtrip_and_tokenizer_check():
    idx = _index("quyền sở hữu tài sản", "thời hiệu khởi kiện")
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "index" / "bm25.json"
        idx.save(path)
        loaded = BM25Index.load(path, tokenizer=syllable_tokenize, tokenizer_name="syllable")
        assert loaded.search("tài sản", 2) == idx.search("tài sản", 2)
        assert "d:0001" in loaded and len(loaded) == 2
        with pytest.raises(ValueError):
            BM25Index.load(path, tokenizer=syllable_tokenize, tokenizer_name="pyvi")
        assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1
