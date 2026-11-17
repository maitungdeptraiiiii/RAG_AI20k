"""W02-04: chunk cố định (fixed-size) để so với chunk theo cấu trúc."""

import pytest

from rag.config import Settings
from rag.ingest.chunker import chunk_fixed
from rag.schema import Page

TEXT = "Chương I\nQUY ĐỊNH CHUNG\nĐiều 1. Phạm vi\n" + " ".join(f"a{i}" for i in range(250)) + \
       "\nĐiều 2. Đối tượng\n" + " ".join(f"b{i}" for i in range(250))


def page(text=TEXT):
    return Page("doc", "luat.txt", None, text)


def test_fixed_windows_ignore_article_boundaries_and_overlap():
    chunks = chunk_fixed([page()], max_syllables=100, overlap=20)
    words = TEXT.split()
    assert [c.text.split() for c in chunks][0] == words[:100]
    assert chunks[1].text.split()[:20] == words[80:100]             # chồng lấp 20 âm tiết
    assert any("a249" in c.text and "Điều 2." in c.text for c in chunks)   # cắt ngang ranh giới Điều
    assert chunks[-1].text.split()[-1] == words[-1]
    assert [c.chunk_id for c in chunks] == [f"doc:{i:04d}" for i in range(len(chunks))] or len({c.chunk_id for c in chunks}) == len(chunks)


def test_fixed_chunks_have_no_article_section():
    assert all(c.section is None for c in chunk_fixed([page()], max_syllables=100, overlap=20))


def test_fixed_rejects_bad_overlap():
    with pytest.raises(ValueError):
        chunk_fixed([page()], max_syllables=50, overlap=50)


def test_settings_chunk_strategy(monkeypatch):
    monkeypatch.setenv("CHUNK_STRATEGY", "fixed")
    monkeypatch.setenv("CHUNK_OVERLAP", "40")
    s = Settings.from_env()
    assert s.chunk_strategy == "fixed" and s.chunk_overlap == 40
    monkeypatch.setenv("CHUNK_STRATEGY", "random")
    with pytest.raises(ValueError):
        Settings.from_env()
