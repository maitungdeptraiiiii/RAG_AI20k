"""Đánh giá toàn bộ, không giữ trạng thái: chuẩn đúng để đối chiếu mọi evaluator khác (spec §7, §10)."""
from __future__ import annotations

from datetime import date

from typing import Sequence

from rag.rules.derived import derive_all
from rag.rules.exceptions import ExceptionIndex, apply_exceptions, exception_open, rule_state
from rag.rules.model import Catalog, Concept, Context, Rule
from rag.rules.objects import WorkingObject, object_facts, rule_object_results
from rag.rules.semantics import Facts, RuleResult, decide_rule, rule_inputs


def evaluate_rules(items: Sequence[tuple[str, Rule, bool, Sequence[dict]]], facts: Facts, day: date,
                   ctx: Context, objects: Sequence[WorkingObject] = ()) -> list[RuleResult]:
    """`items` = `(concept_id, rule, present, evidence)`; kết quả theo thứ tự `items` (rule xuyên đối tượng cho một kết
    quả mỗi nhóm, §5.6). Dữ kiện suy ra được tính trước (§5.3); ngoại lệ giữa rule được áp dụng sau cùng (§5.4)."""
    table = derive_all(ctx, facts)
    tables = {o.id: object_facts(o, ctx, day) for o in objects}
    inputs = [rule_inputs(rule, table, day, ctx) for _, rule, _, _ in items]
    bases: list = []
    for (cid, rule, present, evidence), inp in zip(items, inputs):
        if rule.over is None:
            bases.append(decide_rule(cid, rule, table, present, evidence, inp, ctx))
        else:
            bases.append(rule_object_results(cid, rule, table, evidence, inp, objects, tables, day, ctx))
    index = ExceptionIndex.build([(cid, rule) for cid, rule, _, _ in items])
    final = {} if not index.involved else apply_exceptions(index, bases, [rule_state(inp) for inp in inputs],
                                                           lambda i: exception_open(items[i][1], table, ctx))
    out: list[RuleResult] = []
    for i, base in enumerate(bases):
        if isinstance(base, list):                  # rule xuyên đối tượng không tham gia ngoại lệ (bộ nạp chặn)
            out += base
        else:
            out.append(final.get(i, base))
    return out


def evaluate_concept(concept: Concept, facts: Facts, *, present: bool, evidence=(), day: date,
                     ctx: Context) -> list[RuleResult]:
    """Các rule của một concept. Chỉ áp dụng ngoại lệ giữa các rule cùng concept; ngoại lệ chéo concept chỉ có ở
    `evaluate_all` và ở phiên (spec §5.4)."""
    return evaluate_rules([(concept.id, r, present, evidence) for r in concept.rules], facts, day, ctx)


def evaluate_all(catalog: Catalog, facts: Facts, present: set[str], evidence: dict[str, list[dict]],
                 day: date, objects: Sequence[WorkingObject] = ()) -> list[RuleResult]:
    """Mọi rule của catalog, theo thứ tự concept rồi rule trong catalog."""
    return evaluate_rules([(cid, r, cid in present, evidence.get(cid, ())) for cid, c in catalog.concepts.items()
                           for r in c.rules], facts, day, catalog.context, objects)
