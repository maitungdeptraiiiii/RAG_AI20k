import pytest

from rag.retrieve.context import ContextConfig, select_context
from rag.schema import Chunk, Hit


def _chunks(*word_counts):
    return {
        f"d:{i:04d}": Chunk(f"d:{i:04d}", "d", "a.pdf", 1, 1, None, " ".join(["từ"] * n))
        for i, n in enumerate(word_counts)
    }


def _reranked(*probs):
    return [Hit(f"d:{i:04d}", p, i + 1, "rerank") for i, p in enumerate(probs)]


def _fused(n):
    return [Hit(f"d:{i:04d}", 1 / (61 + i), i + 1, "fused") for i in range(n)]


# --- chế độ threshold (có xác suất Jev) ---------------------------------------------

def test_threshold_keeps_only_relevant_blocks_in_order():
    chunks = _chunks(10, 10, 10, 10)
    sel = select_context(_reranked(0.9, 0.7, 0.3, 0.1), chunks, ContextConfig(min_p=0.5))
    assert sel.mode == "threshold"
    assert sel.chunk_ids == ["d:0000", "d:0001"]
    assert [b.n for b in sel.blocks] == [1, 2]
    assert sel.below_threshold == 2 and sel.cut_by_limit == 0


def test_threshold_can_give_more_than_five_for_multi_questions():
    chunks = _chunks(*[10] * 10)
    sel = select_context(_reranked(*[0.9] * 10), chunks, ContextConfig(min_p=0.5, max_blocks=8))
    assert len(sel.blocks) == 8 and sel.cut_by_limit == 2


def test_threshold_nothing_relevant_means_empty_context():
    chunks = _chunks(10, 10)
    sel = select_context(_reranked(0.2, 0.1), chunks, ContextConfig(min_p=0.5))
    assert sel.empty and sel.mode == "threshold" and sel.below_threshold == 2


def test_word_budget_stops_in_rank_order():
    chunks = _chunks(300, 300, 50)
    sel = select_context(_reranked(0.9, 0.8, 0.7), chunks, ContextConfig(max_words=400))
    assert sel.chunk_ids == ["d:0000"]       # không nhảy cóc sang đoạn 3 dù nó ngắn
    assert sel.cut_by_limit == 2


def test_first_block_always_kept_even_if_longer_than_budget():
    chunks = _chunks(1000)
    sel = select_context(_reranked(0.9), chunks, ContextConfig(max_words=400))
    assert sel.chunk_ids == ["d:0000"]


# --- chế độ fixed (không có xác suất) ----------------------------------------------

def test_fixed_mode_when_not_reranked():
    chunks = _chunks(*[10] * 8)
    sel = select_context(_fused(8), chunks, ContextConfig(fixed_k=5, min_p=0.99))
    assert sel.mode == "fixed"
    assert sel.chunk_ids == [f"d:{i:04d}" for i in range(5)]   # ngưỡng không áp dụng cho điểm RRF


def test_fixed_mode_respects_word_budget():
    chunks = _chunks(300, 300, 300)
    sel = select_context(_fused(3), chunks, ContextConfig(max_words=700))
    assert len(sel.blocks) == 2


# --- biên ---------------------------------------------------------------------------

def test_empty_input_and_missing_chunk():
    assert select_context([], {}).empty
    with pytest.raises(KeyError):
        select_context(_reranked(0.9), {})


def test_duplicate_hits_counted_once():
    chunks = _chunks(10)
    dup = [Hit("d:0000", 0.9, 1, "rerank"), Hit("d:0000", 0.8, 2, "rerank")]
    assert select_context(dup, chunks).chunk_ids == ["d:0000"]


def test_config_validation():
    with pytest.raises(ValueError):
        ContextConfig(min_p=1.5)
    with pytest.raises(ValueError):
        ContextConfig(max_blocks=0)
