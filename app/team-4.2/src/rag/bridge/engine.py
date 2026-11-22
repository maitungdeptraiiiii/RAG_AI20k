"""Rule engine ba trị trên danh mục khái niệm: lớp tương thích trên `rag.rules` (spec 2026-11-22-rete-rule-engine-design §3).

Logic nằm ở `rag.rules.semantics` / `rag.rules.reference`. File này giữ các tên công khai cũ; nơi nào không có `ctx`
thì dùng bảng đơn vị của gói `labor` (nạp lười, lần gọi đầu tiên)."""
from __future__ import annotations

from datetime import date

from rag.bridge.catalog import labor_context
from rag.rules import reference, semantics
from rag.rules.model import Catalog, Concept, Context, Rule
from rag.rules.semantics import CONFLICT, UNKNOWN, Fact, Facts, RuleResult, Tri, _Conflict  # noqa: F401


def convert(value: float, unit: str | None, to: str | None) -> float | None:
    return labor_context().units.convert(value, unit, to)


def compare(left, left_unit: str | None, op: str, right, right_unit: str | None) -> Tri:
    return semantics.compare(left, left_unit, op, right, right_unit, labor_context().units)


def eval_cond(cond: dict | None, facts: Facts) -> Tri:
    return semantics.eval_cond(cond, facts, labor_context())


def resolve_law(rule: Rule, facts: Facts, day: date):
    return semantics.resolve_law(rule, facts, day, labor_context())


def evaluate_concept(concept: Concept, facts: Facts, *, present: bool, evidence=(), day: date,
                     ctx: Context | None = None) -> list[RuleResult]:
    return reference.evaluate_concept(concept, facts, present=present, evidence=evidence, day=day,
                                      ctx=ctx if ctx is not None else labor_context())


def evaluate(catalog: Catalog, facts: Facts, present: set[str], evidence: dict[str, list[dict]],
             day: date) -> list[RuleResult]:
    return reference.evaluate_all(catalog, facts, present, evidence, day)


__all__ = ["CONFLICT", "Fact", "Facts", "RuleResult", "Tri", "compare", "convert", "eval_cond", "evaluate",
           "evaluate_concept", "resolve_law"]
