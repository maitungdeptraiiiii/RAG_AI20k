"""Đánh giá toàn bộ, không giữ trạng thái: chuẩn đúng để đối chiếu mọi evaluator khác (spec §7, §10)."""
from __future__ import annotations

from datetime import date

from rag.rules.model import Catalog, Concept, Context
from rag.rules.semantics import Facts, RuleResult, evaluate_rule


def evaluate_concept(concept: Concept, facts: Facts, *, present: bool, evidence=(), day: date,
                     ctx: Context) -> list[RuleResult]:
    return [evaluate_rule(concept.id, r, facts, present, evidence, day, ctx) for r in concept.rules]


def evaluate_all(catalog: Catalog, facts: Facts, present: set[str], evidence: dict[str, list[dict]],
                 day: date) -> list[RuleResult]:
    """Mọi rule của catalog, theo thứ tự concept rồi rule trong catalog."""
    return [r for cid, c in catalog.concepts.items()
            for r in evaluate_concept(c, facts, present=cid in present, evidence=evidence.get(cid, ()), day=day,
                                      ctx=catalog.context)]
