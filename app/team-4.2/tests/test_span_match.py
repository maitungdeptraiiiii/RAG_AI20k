"""W02-04: chấm trúng Điều theo vị trí văn bản (dùng chung cho chunk cố định và chunk theo cấu trúc)."""

from rag.eval.span_match import ArticleIndex, gold_article
from rag.schema import Chunk

RAW = ("Chương I\nQUY ĐỊNH CHUNG\nĐiều 1. Phạm vi\nLuật này quy định theo Điều 2. về việc khác.\n"
       "Điều 2. Đối tượng\n1. Cơ quan.\n2. Tổ chức.\nChương II\nĐiều 3. Giải thích\nTừ ngữ.\n")


def ch(i, text, section=None):
    return Chunk(f"d:{i}", "d", "luat.txt", None, None, section, text)


def test_gold_article_label():
    assert gold_article("Chương I > Điều 260. Tội vi phạm") == "260"
    assert gold_article("Chương I") is None


def test_article_spans_use_line_headings_not_references():
    idx = ArticleIndex(RAW, [])
    assert sorted(idx.articles) == ["1", "2", "3"]


def test_structural_chunk_matches_only_its_article():
    chunks = [ch(0, "Điều 1. Phạm vi\nLuật này quy định theo Điều 2. về việc khác.", "Điều 1. Phạm vi"),
              ch(1, "Điều 2. Đối tượng\n1. Cơ quan.\n2. Tổ chức.", "Điều 2. Đối tượng")]
    idx = ArticleIndex(RAW, chunks)
    assert idx.covers("d:0", "1") and not idx.covers("d:0", "2")
    assert idx.covers("d:1", "2") and not idx.covers("d:1", "3")
    assert not idx.covers("d:1", "1")                     # chunk bắt đầu đúng tại "Điều 2." không chạm Điều 1


def test_fixed_chunk_spanning_two_articles_matches_both():
    text = " ".join(RAW.split()[8:22])      # từ giữa Điều 1 sang Điều 2
    idx = ArticleIndex(RAW, [ch(0, text)])
    assert idx.covers("d:0", "1") and idx.covers("d:0", "2") and not idx.covers("d:0", "3")


def test_unlocatable_chunk_matches_nothing():
    idx = ArticleIndex(RAW, [ch(0, "văn bản không có trong nguồn")])
    assert not idx.covers("d:0", "1")
