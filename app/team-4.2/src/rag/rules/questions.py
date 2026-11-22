"""Câu hỏi gợi ý (spec §8): hỏi dữ kiện nào để giải quyết được nhiều kết quả UNKNOWN nhất.

Với mỗi dữ kiện người dùng đang thiếu, có miền giá trị khai trong pack (`user_fact_questions`) và nằm trong `missing_facts`
của ít nhất một kết quả UNKNOWN: với từng giá trị khả dĩ, `fork()` + `update()` rồi đếm kết quả UNKNOWN thành xác định.
Đây là chỗ cập nhật tăng dần của mạng có ích trực tiếp: nhiều lần fork + update trên một hợp đồng."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rag.rules.model import Catalog
from rag.rules.semantics import Fact


@dataclass(frozen=True)
class Question:
    fact: str
    question: str
    unit: str | None
    guaranteed: int                       # số kết quả UNKNOWN chắc chắn thành xác định, bất kể người dùng trả lời gì
    possible: int                         # tối đa qua các giá trị
    outcomes: tuple[tuple[Any, int], ...]  # (giá trị, số kết quả UNKNOWN thành xác định)


def next_questions(catalog: Catalog, session) -> list[Question]:
    """Xếp theo (guaranteed, possible) giảm dần rồi theo tên; bỏ câu hỏi không giải quyết được kết quả nào."""
    ctx = catalog.context
    results = session.results()
    unknown = {(r.concept_id, r.rule_id) for r in results if r.status == "UNKNOWN"}
    candidates = list(dict.fromkeys(f for r in results if r.status == "UNKNOWN" for f in r.missing_facts
                                    if f in ctx.questions))
    out = []
    for name in candidates:
        spec = ctx.questions[name]
        outcomes = []
        for value in spec.values:
            fork = session.fork()
            fork.update({name: Fact(value, spec.unit, "user")})
            after = {(r.concept_id, r.rule_id): r.status for r in fork.results()}
            outcomes.append((value, sum(1 for key in unknown if after[key] != "UNKNOWN")))
        counts = [n for _, n in outcomes]
        if max(counts) > 0:
            out.append(Question(name, spec.question, spec.unit, min(counts), max(counts), tuple(outcomes)))
    return sorted(out, key=lambda q: (-q.guaranteed, -q.possible, q.fact))
