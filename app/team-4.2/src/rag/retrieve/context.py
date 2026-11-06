"""Chọn context đưa cho LLM — tách khỏi top-k dùng để chấm điểm.

    Chấm retrieval : RetrievalResult.hits   = top-k CỐ ĐỊNH (k=5) -> Recall@5, MRR@5 (sprint bắt buộc)
    Context cho LLM: select_context(ranked) = số đoạn THAY ĐỔI theo câu hỏi

Hai chế độ, tự chọn theo arm của hit:

    "threshold"  hit đã được Jev chấm (arm="rerank", score = xác suất liên quan):
                 giữ các đoạn có p >= min_p, theo thứ tự, tối đa max_blocks đoạn và max_words từ.
                 Không đoạn nào đạt ngưỡng -> không có context -> guardrail từ chối, KHÔNG gọi LLM.
    "fixed"      không rerank hoặc Jev lỗi (arm="fused" | "bm25" | "dense"): điểm RRF không phải
                 xác suất nên không đặt ngưỡng được -> lấy top fixed_k như baseline. Việc từ chối
                 theo ngưỡng RRF là của guardrail (TV5), không làm ở đây.

Ý tưởng từ thread Reddit đã đọc khi lên kế hoạch (_local/references, không commit):
"keep top-5 for scoring", context cho model chọn riêng;
"retrieve wide and let the filter pick" — Jev đóng vai bộ lọc, rẻ hơn gọi LLM.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from rag.retrieve.merge import merged_chunk
from rag.schema import Chunk, ContextBlock, Hit

ContextMode = Literal["threshold", "fixed", "empty"]


@dataclass(frozen=True)
class ContextConfig:
    min_p: float = 0.7        # CONTEXT_MIN_P — ngưỡng xác suất Jev, chọn trên tập dev
    max_blocks: int = 8       # CONTEXT_MAX_BLOCKS — trần số đoạn
    max_words: int = 2400     # CONTEXT_MAX_WORDS — trần độ dài (đếm theo từ/âm tiết cách nhau khoảng trắng)
    fixed_k: int = 5          # TOP_K — số đoạn khi không có xác suất Jev

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_p <= 1.0:
            raise ValueError(f"min_p phải trong [0, 1], nhận {self.min_p}")
        if self.max_blocks < 1 or self.fixed_k < 1 or self.max_words < 1:
            raise ValueError("max_blocks, fixed_k, max_words phải >= 1")


@dataclass
class ContextSelection:
    blocks: list[ContextBlock] = field(default_factory=list)
    mode: ContextMode = "empty"
    below_threshold: int = 0   # số đoạn bị loại vì p < min_p (chế độ threshold)
    cut_by_limit: int = 0      # số đoạn đủ điều kiện nhưng bị cắt vì max_blocks / max_words

    @property
    def empty(self) -> bool:
        return not self.blocks

    @property
    def chunk_ids(self) -> list[str]:
        return [b.chunk.chunk_id for b in self.blocks]


def _words(chunk: Chunk) -> int:
    return len(chunk.text.split())


def select_context(
    ranked: Sequence[Hit], chunks: Mapping[str, Chunk], config: ContextConfig | None = None
) -> ContextSelection:
    """Chọn các đoạn đưa cho LLM, đánh số [1], [2], ... theo thứ tự xếp hạng.

    `ranked`: RetrievalResult.ranked (toàn bộ candidates đã sắp xếp, đã rerank nếu có).
    """
    cfg = config or ContextConfig()
    if not ranked:
        return ContextSelection()

    missing = [c for h in ranked for c in (h.chunk_id, *h.merged) if c not in chunks]
    if missing:
        raise KeyError(f"Không tìm thấy chunk cho các hit: {missing[:5]}")

    if ranked[0].arm == "rerank":
        mode: ContextMode = "threshold"
        eligible = [h for h in ranked if h.score >= cfg.min_p]
        below = len(ranked) - len(eligible)
        limit = cfg.max_blocks
    else:
        mode = "fixed"
        eligible = list(ranked)
        below = 0
        limit = cfg.fixed_k

    picked: list[Chunk] = []
    seen: set[str] = set()
    used = 0
    for h in eligible:
        if h.chunk_id in seen:
            continue
        chunk = merged_chunk(h, chunks)  # hit đã gộp nhiều chunk cùng Điều -> MỘT block, bỏ overlap
        n = _words(chunk)
        if len(picked) >= limit or (picked and used + n > cfg.max_words):
            break                        # giữ đúng thứ tự xếp hạng: không nhảy cóc sang đoạn ngắn hơn
        picked.append(chunk)             # đoạn đầu tiên luôn được lấy, kể cả khi dài hơn max_words
        seen.update((h.chunk_id, *h.merged))
        used += n

    if not picked:
        return ContextSelection(mode=mode, below_threshold=below)
    unique_eligible = len({h.chunk_id for h in eligible})
    cut = unique_eligible - len(picked) if mode == "threshold" else 0
    return ContextSelection(
        blocks=[ContextBlock(n=i, chunk=c) for i, c in enumerate(picked, start=1)],
        mode=mode,
        below_threshold=below,
        cut_by_limit=cut,
    )


__all__ = ["ContextConfig", "ContextMode", "ContextSelection", "select_context"]
