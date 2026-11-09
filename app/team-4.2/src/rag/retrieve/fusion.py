"""Reciprocal Rank Fusion — TV2.

    score(d) = Σ_arm weight_arm / (k + rank_arm(d)), rank tính từ 1, k = 60

Chỉ dùng THỨ HẠNG, không dùng điểm gốc: điểm BM25 (0..∞) và cosine (−1..1) khác thang đo,
cộng thẳng vào nhau là vô nghĩa. Chunk xuất hiện ở cả hai arm được cộng hai lần nên nổi lên.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
import math

from rag.schema import Hit

DEFAULT_RRF_K = 60


def rrf(
    ranked: Mapping[str, Sequence[Hit]], *, k: int = DEFAULT_RRF_K, top_n: int | None = None,
    weights: Mapping[str, float] | None = None,
) -> list[Hit]:
    """Gộp các danh sách xếp hạng thành list[Hit] (arm="fused").

    - Một chunk lặp lại trong cùng một arm chỉ tính ở thứ hạng tốt nhất.
    - Trọng số mặc định 1; arm có trọng số 0 không đóng góp ứng viên.
    - Hoà điểm thì xếp theo chunk_id để kết quả tất định.
    """
    if k < 0:
        raise ValueError(f"k phải >= 0, nhận {k}")
    if top_n is not None and top_n < 1:
        raise ValueError(f"top_n phải >= 1, nhận {top_n}")
    if any(not math.isfinite(w) or w < 0 for w in (weights or {}).values()):
        raise ValueError('RRF weights must be finite and nonnegative')

    scores: dict[str, float] = defaultdict(float)
    for name, hits in ranked.items():
        weight = (weights or {}).get(name, 1.0)
        if weight == 0:
            continue
        best: dict[str, int] = {}
        for h in hits:
            if h.chunk_id not in best or h.rank < best[h.chunk_id]:
                best[h.chunk_id] = h.rank
        for cid, rank in best.items():
            scores[cid] += weight / (k + rank)

    order = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    if top_n is not None:
        order = order[:top_n]
    return [Hit(cid, s, r, "fused") for r, (cid, s) in enumerate(order, start=1)]


__all__ = ["DEFAULT_RRF_K", "rrf"]
