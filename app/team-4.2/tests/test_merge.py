from rag.retrieve.context import ContextConfig, select_context
from rag.retrieve.hybrid import HybridRetriever
from rag.retrieve.merge import GAP, article_key, merge_by_article, merged_chunk
from rag.schema import Chunk, Hit

A134 = "Chương XIV > Điều 134. Tội cố ý gây thương tích"
A13 = "Chương III > Điều 13. Phạm tội do dùng rượu, bia"
CONG_BAO = "PHẦN VĂN BẢN QUY PHẠM PHÁP LUẬT CHỦ TỊCH NƯỚC - QUỐC HỘI"


def _c(doc, i, section, text, page=1):
    return Chunk(f"{doc}:{i:04d}", doc, f"{doc}.txt", page, page, section, text)


CHUNKS = {c.chunk_id: c for c in [
    _c("hs", 10, A13, "Điều 13. Phạm tội do dùng rượu\nNgười phạm tội trong tình trạng say..."),
    _c("hs", 20, A134, "Điều 134. Tội cố ý gây thương tích\n1. Người nào cố ý...\na) Dùng hung khí", page=5),
    _c("hs", 21, A134, "a) Dùng hung khí\nb) Gây cố tật nhẹ\n2. Phạm tội...", page=5),     # overlap dòng "a)"
    _c("hs", 22, A134, "3. Phạm tội gây thương tích 61%\n4. Phạm tội làm chết người", page=6),  # không overlap
    _c("hs", 24, A134, "6. Người chuẩn bị phạm tội...", page=6),                            # không liền kề 22
    _c("hs", 50, CONG_BAO, "Luật số 100/2015/QH13 (Tiếp theo Công báo số 126)"),
    _c("hs", 90, CONG_BAO, "Luật số 100/2015/QH13"),
    _c("ld", 20, A134, "Điều 134. (bộ luật khác, cùng tên section)"),
    _c("hs", 0, None, "QUỐC HỘI / Luật số: 100/2015/QH13"),
]}


def _hits(*ids, arm="rerank"):
    return [Hit(cid, 1.0 - i * 0.1, i + 1, arm) for i, cid in enumerate(ids)]


def test_chunks_of_same_article_count_as_one_candidate():
    out = merge_by_article(_hits("hs:0021", "hs:0020", "hs:0010", "hs:0022"), CHUNKS)
    assert [h.chunk_id for h in out] == ["hs:0021", "hs:0010"]
    assert out[0].merged == ("hs:0020", "hs:0022")
    assert [h.rank for h in out] == [1, 2]
    assert out[0].score == 1.0 and out[0].arm == "rerank"     # giữ score của chunk xếp cao nhất


def test_only_real_articles_are_merged():
    # header Công báo bị nhận nhầm là "Phần ...": cùng section nhưng KHÔNG phải một Điều
    assert article_key(CHUNKS["hs:0050"]) != article_key(CHUNKS["hs:0090"])
    assert article_key(CHUNKS["hs:0000"]) == ("chunk", "hs:0000")
    out = merge_by_article(_hits("hs:0050", "hs:0090", "hs:0000"), CHUNKS)
    assert [h.chunk_id for h in out] == ["hs:0050", "hs:0090", "hs:0000"]


def test_same_section_in_different_documents_is_not_merged():
    out = merge_by_article(_hits("hs:0020", "ld:0020"), CHUNKS)
    assert [h.chunk_id for h in out] == ["hs:0020", "ld:0020"]


def test_merge_is_idempotent():
    once = merge_by_article(_hits("hs:0020", "hs:0021", "hs:0010"), CHUNKS)
    assert merge_by_article(once, CHUNKS) == once


def test_merged_chunk_drops_overlap_and_marks_gaps():
    hit = merge_by_article(_hits("hs:0022", "hs:0020", "hs:0024", "hs:0021"), CHUNKS)[0]
    c = merged_chunk(hit, CHUNKS)
    lines = c.text.split("\n")
    assert lines[0] == "Điều 134. Tội cố ý gây thương tích"        # theo thứ tự văn bản, không theo rank
    assert lines.count("a) Dùng hung khí") == 1                    # overlap 20->21 bị bỏ
    assert "3. Phạm tội gây thương tích 61%" in lines              # 21->22 không overlap: giữ nguyên
    assert lines[lines.index("4. Phạm tội làm chết người") + 1] == GAP   # 22 -> 24 có khoảng trống
    assert lines[-1] == "6. Người chuẩn bị phạm tội..."
    assert (c.chunk_id, c.section, c.page_start, c.page_end) == ("hs:0022", A134, 5, 6)


def test_unmerged_hit_returns_original_chunk():
    assert merged_chunk(Hit("hs:0010", 1.0, 1, "rerank"), CHUNKS) is CHUNKS["hs:0010"]


def test_context_gets_one_block_per_article():
    ranked = merge_by_article(_hits("hs:0020", "hs:0021", "hs:0010"), CHUNKS)
    sel = select_context(ranked, CHUNKS, ContextConfig(min_p=0.0, max_blocks=8))
    assert [b.chunk.chunk_id for b in sel.blocks] == ["hs:0020", "hs:0010"]
    assert sel.blocks[0].chunk.text.count("a) Dùng hung khí") == 1


class _Arm:
    def __init__(self, ids):
        self.ids = ids

    def build(self, chunks):
        pass

    def search(self, query, k):
        return [Hit(c, 1.0 / (i + 1), i + 1, "dense") for i, c in enumerate(self.ids[:k])]


def test_retriever_merges_by_default_and_can_be_disabled():
    ids = ["hs:0020", "hs:0021", "hs:0022", "hs:0010", "ld:0020"]
    on = HybridRetriever(_Arm([]), _Arm(ids))
    on.build(CHUNKS.values())
    res = on.retrieve("q", 2, mode="dense")
    assert [h.chunk_id for h in res.hits] == ["hs:0020", "hs:0010"]   # Điều 13 không bị đẩy ra
    assert [h.chunk_id for h in res.ranked] == ["hs:0020", "hs:0010", "ld:0020"]
    off = HybridRetriever(_Arm([]), _Arm(ids), merge_articles=False)
    off.build(CHUNKS.values())
    assert [h.chunk_id for h in off.retrieve("q", 2, mode="dense").hits] == ["hs:0020", "hs:0021"]


def test_take_articles_keeps_all_chunks_of_first_n_articles():
    from rag.retrieve.merge import take_articles
    hits = _hits("hs:0020", "hs:0021", "hs:0010", "ld:0020", "hs:0022")
    assert [h.chunk_id for h in take_articles(hits, CHUNKS, 2)] == ["hs:0020", "hs:0021", "hs:0010", "hs:0022"]


def test_pool_is_counted_in_articles_not_chunks():
    ids = ["hs:0020", "hs:0021", "hs:0022", "hs:0024", "hs:0010", "ld:0020"]
    r = HybridRetriever(_Arm([]), _Arm(ids), arm_k=3, rerank_n=2, article_pool_factor=2)
    r.build(CHUNKS.values())
    res = r.retrieve("q", 2, mode="dense")
    # 4 chunk đầu cùng Điều 134 -> pool 2 chunk sẽ chỉ có 1 Điều; lấy dư (x2) để có đủ 2 Điều
    assert [h.chunk_id for h in res.ranked] == ["hs:0020", "hs:0010"]
