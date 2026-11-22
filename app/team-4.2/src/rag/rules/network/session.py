"""Phiên của mạng: giữ trị node, kết quả từng rule; `update` chỉ tính lại rule bị ảnh hưởng (spec §6.3)."""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from rag.rules.derived import derive_all, eval_derived
from rag.rules.evaluator import Diff, RuleChange
from rag.rules.exceptions import apply_exceptions, exception_open, rule_state
from rag.rules.network.network import Network
from rag.rules.network.nodes import CondState
from rag.rules.semantics import (Fact, Facts, RuleInputs, RuleResult, Tri, check_cond, decide_rule, resolve_law_with)


def _same(old: object, new: object) -> bool:
    """`Fact.__eq__` coi 1 == True == 1.0; ở đây khác kiểu giá trị là dữ kiện đã đổi (kết quả mang theo giá trị).
    Mốc CONFLICT / UNKNOWN không có `.value`: so như thường."""
    return old == new and type(getattr(old, "value", None)) is type(getattr(new, "value", None))


def _copy_evidence(evidence: dict[str, list[dict]]) -> dict[str, list[dict]]:
    return {k: list(v) for k, v in evidence.items()}


class NetworkSession:
    def __init__(self, network: Network, day: date, facts: Facts, present: set[str], evidence: dict[str, list[dict]]):
        self._net, self._day = network, day
        ctx = network.catalog.context
        self._facts = derive_all(ctx, facts)                  # bảng đã gộp dữ kiện suy ra (khóa trùng tên bị bỏ)
        self._present, self._evidence = set(present), _copy_evidence(evidence)
        self._cond = CondState(network.graph, self._facts, ctx)
        computed = [self._compute(i) for i in range(len(network.rules))]
        self._base: list[RuleResult] = [r for r, _ in computed]       # kết quả trước khi áp dụng ngoại lệ giữa rule
        self._state: list[Tri] = [s for _, s in computed]             # rule có áp dụng không (rule_state)
        self._results: list[RuleResult] = self._finalize()
        self.stats = {"nodes_recomputed": len(network.graph.kinds), "rules_recomputed": len(network.rules)}

    def _finalize(self, only: set[int] | None = None) -> list[RuleResult]:
        """Kết quả cuối của mọi rule (hoặc chỉ `only` khi đã có `_results`): `_base` cộng ngoại lệ giữa rule."""
        net, ctx = self._net, self._net.catalog.context
        idx = net.exceptions
        if idx is None or not idx.involved or (only is not None and not only & idx.involved):
            return list(self._base) if only is None else [self._base[i] for i in sorted(only)]
        final = apply_exceptions(idx, self._base, self._state,
                                 lambda i: exception_open(net.rules[i].rule, self._facts, ctx), only=only)
        which = range(len(self._base)) if only is None else sorted(only)
        return [final.get(i, self._base[i]) for i in which]

    def _recompute_derived(self, changed: set[str]) -> set[str]:
        """Tính lại dữ kiện suy ra có đầu vào trong `changed` theo thứ tự topo; trả tên dữ kiện suy ra có giá trị đổi."""
        net, ctx = self._net, self._net.catalog.context
        touched, out = set(changed), set()
        for name in net.derived_order:
            if not touched & net.derived_deps[name]:
                continue
            new, old = eval_derived(ctx.derived[name], self._facts, ctx), self._facts.get(name)
            if new is None:
                if old is None:
                    continue
                del self._facts[name]
            elif old is not None and _same(old, new):
                continue
            else:
                self._facts[name] = new
            out.add(name)
            touched.add(name)
        return out

    def _compute(self, i: int) -> tuple[RuleResult, Tri]:
        slot, ctx, facts = self._net.rules[i], self._net.catalog.context, self._facts
        values = self._cond.values
        app = "T" if slot.app_node is None else values[slot.app_node]
        whens = ["T" if n is None else values[n] for n in slot.when_nodes]
        law, law_st, law_reasons = resolve_law_with(slot.rule, whens, facts, self._day)
        check_st = None if slot.rule.check is None else check_cond(slot.rule.check, facts, law or {}, ctx)
        inputs = RuleInputs(app, law, law_st, law_reasons, check_st)
        return (decide_rule(slot.concept_id, slot.rule, facts, slot.concept_id in self._present,
                            self._evidence.get(slot.concept_id, ()), inputs, ctx), rule_state(inputs))

    def results(self) -> list[RuleResult]:
        return list(self._results)

    def update(self, changes: Mapping[str, Fact | None], *, present: set[str] | None = None,
               evidence: dict[str, list[dict]] | None = None, objects: Any = None) -> Diff:
        """`None` xóa dữ kiện; `present` / `evidence` nếu truyền thì thay hẳn giá trị hiện có."""
        if objects:
            raise NotImplementedError("objects: giai đoạn 7")
        net, dirty = self._net, set()
        changed_names = set()
        ctx = net.catalog.context
        for name, fact in changes.items():
            if name in ctx.derived:                      # dữ kiện suy ra do định nghĩa quyết định, không nhận từ ngoài
                continue
            if fact is None:
                if name in self._facts:
                    del self._facts[name]
                    changed_names.add(name)
            elif not _same(self._facts.get(name), fact):
                self._facts[name] = fact
                changed_names.add(name)
        if changed_names and ctx.derived:
            changed_names |= self._recompute_derived(changed_names)
        for name in changed_names:
            dirty.update(net.rules_by_fact.get(name, ()))
        for node in self._cond.update(changed_names, self._facts, net.catalog.context):
            dirty.update(net.rules_by_node.get(node, ()))
        if present is not None:
            for cid in self._present ^ set(present):
                dirty.update(net.rules_by_concept.get(cid, ()))
            self._present = set(present)
        if evidence is not None:
            new = _copy_evidence(evidence)
            for cid in set(self._evidence) | set(new):
                if self._evidence.get(cid, []) != new.get(cid, []):
                    dirty.update(net.rules_by_concept.get(cid, ()))
            self._evidence = new
        for i in sorted(dirty):
            self._base[i], self._state[i] = self._compute(i)
        region = set(dirty)                              # kết quả cuối đổi theo rule bẩn và theo mọi rule mà nó là ngoại lệ
        if net.exceptions is not None:
            for i in dirty:
                region.update(net.exceptions.ancestors[i])
        out = []
        for i, after in zip(sorted(region), self._finalize(region)):
            before = self._results[i]
            self._results[i] = after                     # luôn ghi: `==` coi True và 1.0 là một, nhưng kết quả phải giữ kiểu mới
            if before != after:
                out.append(RuleChange(after.concept_id, after.rule_id, before, after))
        self.stats = {"nodes_recomputed": self._cond.last_recomputed, "rules_recomputed": len(dirty)}
        return Diff(tuple(out))

    def fork(self) -> "NetworkSession":
        clone = NetworkSession.__new__(NetworkSession)
        clone._net, clone._day = self._net, self._day
        clone._facts, clone._present, clone._evidence = dict(self._facts), set(self._present), _copy_evidence(self._evidence)
        clone._cond = self._cond.copy()
        clone._base, clone._state, clone._results = list(self._base), list(self._state), list(self._results)
        clone.stats = dict(self.stats)
        return clone
