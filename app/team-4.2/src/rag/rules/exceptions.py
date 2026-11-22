"""Ngoại lệ giữa rule (spec §5.4). Logic thuần, dùng chung cho Reference và Network.

Rule ngoại lệ khai `exception_of: <concept_id>/<rule_id>`. Rule "áp dụng" khi chính nó áp dụng hoặc bất kỳ ngoại lệ (kể
cả gián tiếp) của nó áp dụng (như cây ngoại lệ Catala). Kết quả cơ sở của rule gốc được điều chỉnh theo bảng ba hàng."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from rag.rules.derived import missing_inputs
from rag.rules.model import Context, Rule
from rag.rules.semantics import Facts, RuleInputs, RuleResult, Tri, fact_names


def rule_key(concept_id: str, rule: Rule) -> str:
    return f"{concept_id}/{rule.id}"


@dataclass(frozen=True)
class ExceptionIndex:
    keys: tuple[str, ...]                          # `<concept>/<rule>` theo vị trí rule
    children: tuple[tuple[int, ...], ...]          # ngoại lệ trực tiếp của rule i
    ancestors: tuple[tuple[int, ...], ...]         # mọi rule mà kết quả phụ thuộc rule i (gián tiếp cũng tính)
    order: tuple[int, ...]                         # chỉ rule có tham gia quan hệ ngoại lệ, con đứng trước cha
    involved: frozenset[int]

    @staticmethod
    def build(items: Sequence[tuple[str, Rule]]) -> "ExceptionIndex":
        """`items` = `(concept_id, rule)` theo thứ tự catalog. Đích `exception_of` không có trong `items` thì bỏ qua."""
        keys = tuple(rule_key(c, r) for c, r in items)
        at = {k: i for i, k in enumerate(keys)}
        parent = [at.get(r.exception_of) if r.exception_of else None for _, r in items]
        children: list[list[int]] = [[] for _ in items]
        for i, p in enumerate(parent):
            if p is not None:
                children[p].append(i)
        ancestors = []
        for i in range(len(items)):
            chain, p = [], parent[i]
            while p is not None and p not in chain and p != i:
                chain.append(p)
                p = parent[p]
            ancestors.append(tuple(chain))
        involved = frozenset(i for i in range(len(items)) if children[i] or parent[i] is not None)
        order: list[int] = []
        seen: set[int] = set()

        def visit(i: int) -> None:
            if i in seen:
                return
            seen.add(i)
            for c in children[i]:
                visit(c)
            order.append(i)

        for i in sorted(involved):
            if parent[i] is None:
                visit(i)
        for i in sorted(involved):                 # vòng (bộ nạp đã chặn): vẫn không bỏ sót
            visit(i)
        return ExceptionIndex(keys, tuple(tuple(c) for c in children), tuple(ancestors), tuple(order), involved)


def rule_state(inputs: RuleInputs) -> Tri:
    """Rule này có áp dụng không: F nếu applicability F hoặc không case nào khớp; T nếu cả hai T; còn lại U."""
    if inputs.app == "F" or inputs.law_st == "F":
        return "F"
    return "T" if inputs.app == "T" and inputs.law_st == "T" else "U"


def applies_states(index: ExceptionIndex, states: Sequence[Tri]) -> dict[int, Tri]:
    """Trị "áp dụng" của cả cây: Kleene-OR của chính rule i và các ngoại lệ trực tiếp của nó (đã là cây)."""
    out: dict[int, Tri] = {}
    for i in index.order:
        vals = [states[i], *[out[c] for c in index.children[i]]]
        out[i] = "T" if "T" in vals else ("U" if "U" in vals else "F")
    return out


@dataclass(frozen=True)
class Override:
    key: str
    applies: Tri
    open_facts: tuple[str, ...] = ()


def _dedupe(*parts: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(x for p in parts for x in p))


def finalize(base: RuleResult, overrides: Sequence[Override]) -> RuleResult:
    """Bảng §5.4. Có ngoại lệ T: rule gốc NOT_APPLICABLE. Không T, có U: rule gốc FAIL hạ thành UNKNOWN / needs_facts
    (giữ bất biến "thiếu dữ kiện không thành vi phạm"); trạng thái khác giữ nguyên, chỉ thêm reason."""
    true = [o for o in overrides if o.applies == "T"]
    if true:
        return dataclasses.replace(base, status="NOT_APPLICABLE", finding="ok", legality=None, employee_impact=None, outcome={}, party_impact=None,
                                   law_values={}, missing_facts=(),
                                   reasons=tuple(f"overridden_by:{o.key}" for o in true))
    unknown = [o for o in overrides if o.applies == "U"]
    if not unknown:
        return base
    reasons = (*base.reasons, *[f"exception_unknown:{o.key}" for o in unknown])
    if base.status == "FAIL":
        return dataclasses.replace(base, status="UNKNOWN", finding="needs_facts", legality=None, employee_impact=None, outcome={}, party_impact=None,
                                   missing_facts=_dedupe(base.missing_facts, *[o.open_facts for o in unknown]),
                                   reasons=reasons)
    return dataclasses.replace(base, reasons=reasons)


def exception_open(rule: Rule, facts: Facts, ctx: Context) -> tuple[str, ...]:
    """Dữ kiện đầu vào còn thiếu để biết rule ngoại lệ có áp dụng không (từ applicability và `when` của các case)."""
    names = [*fact_names(rule.applicability), *[n for c in rule.cases for n in fact_names(c.get("when"))]]
    return missing_inputs(names, facts, ctx)


def apply_exceptions(index: ExceptionIndex, bases: Sequence[RuleResult], states: Sequence[Tri],
                     open_of: Callable[[int], tuple[str, ...]], only: Iterable[int] | None = None) -> dict[int, RuleResult]:
    """Kết quả cuối của các rule tham gia quan hệ ngoại lệ (giới hạn ở `only` nếu có), theo vị trí rule.
    `open_of(i)` = dữ kiện còn thiếu của riêng rule ngoại lệ i; hàm gộp cả cây ngoại lệ dưới nó khi trị U."""
    applies = applies_states(index, states)
    want = None if only is None else set(only)

    def tree_open(i: int) -> tuple[str, ...]:
        return _dedupe(open_of(i), *[tree_open(c) for c in index.children[i]])

    out: dict[int, RuleResult] = {}
    for i in index.order:
        if want is not None and i not in want:
            continue
        overrides = [Override(index.keys[c], applies[c], tree_open(c) if applies[c] == "U" else ())
                     for c in index.children[i]]
        out[i] = finalize(bases[i], overrides)
    return out
