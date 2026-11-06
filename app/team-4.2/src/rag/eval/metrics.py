"""Metric retrieval — TV3 (dùng chung với TV2).

Gold trỏ tới source + page (hoặc section), KHÔNG trỏ tới chunk_id. Lúc chấm mới quy đổi:
một chunk là "đúng" với một GoldRef nếu cùng source và chứa trang đó (Question.is_relevant).

    recall_at_k  = số GoldRef có ít nhất 1 chunk khớp trong top-k / tổng số GoldRef
                   (câu "multi" cần nhiều đoạn -> phải tìm đủ mới được 1.0)
    hit_at_k     = 1 nếu top-k có ít nhất 1 chunk khớp bất kỳ GoldRef nào
    mrr_at_k     = 1 / rank của chunk khớp đầu tiên trong top-k, không có thì 0

Câu out_of_scope không có gold -> trả None, không tính vào trung bình.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from rag.schema import Chunk, Question


def load_questions(path: Path | str) -> list[Question]:
    questions: list[Question] = []
    seen: set[str] = set()
    with Path(path).open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                q = Question.from_dict(json.loads(line))
            except (ValueError, KeyError, TypeError) as e:
                raise ValueError(f"{path}:{lineno}: dòng không hợp lệ: {e}") from e
            if q.id in seen:
                raise ValueError(f"{path}:{lineno}: trùng id {q.id!r}")
            seen.add(q.id)
            questions.append(q)
    return questions


def _chunks(ids: Sequence[str], chunks: Mapping[str, Chunk], k: int) -> list[Chunk]:
    return [chunks[c] for c in ids[:k] if c in chunks]


def recall_at_k(q: Question, ranked_ids: Sequence[str], chunks: Mapping[str, Chunk], k: int) -> float | None:
    if not q.gold:
        return None
    top = _chunks(ranked_ids, chunks, k)
    found = sum(1 for g in q.gold if any(g.matches(c) for c in top))
    return found / len(q.gold)


def hit_at_k(q: Question, ranked_ids: Sequence[str], chunks: Mapping[str, Chunk], k: int) -> float | None:
    if not q.gold:
        return None
    return 1.0 if any(q.is_relevant(c) for c in _chunks(ranked_ids, chunks, k)) else 0.0


def mrr_at_k(q: Question, ranked_ids: Sequence[str], chunks: Mapping[str, Chunk], k: int) -> float | None:
    if not q.gold:
        return None
    for rank, c in enumerate(_chunks(ranked_ids, chunks, k), start=1):
        if q.is_relevant(c):
            return 1.0 / rank
    return 0.0


def mean(values: Iterable[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def unmatched_gold(questions: Iterable[Question], chunks: Iterable[Chunk]) -> dict[str, list[str]]:
    """GoldRef không khớp chunk nào trong toàn bộ index — thường do sai tên file / số trang khi gán nhãn.

    Chạy trước khi eval: gold sai thì Recall thấp mà không phải lỗi retrieval.
    """
    chunks = list(chunks)
    out: dict[str, list[str]] = {}
    for q in questions:
        bad = [f"{g.source}#p{g.page}" if g.page is not None else f"{g.source}#{g.section}"
               for g in q.gold if not any(g.matches(c) for c in chunks)]
        if bad:
            out[q.id] = bad
    return out


__all__ = ["hit_at_k", "load_questions", "mean", "mrr_at_k", "recall_at_k", "unmatched_gold"]
