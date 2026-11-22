"""Phiên của mạng: giữ trị node, kết quả từng rule; `update` chỉ tính lại rule bị ảnh hưởng (spec §6.3).

Rule xuyên đối tượng (§5.6, §6.1 phần 2) theo kiểu TREAT: phiên giữ bộ nhớ đối tượng theo kiểu (`ObjectMemory`: đối
tượng + bảng dữ kiện riêng của từng đối tượng) và trị ứng viên của từng đối tượng cho từng rule. Khi đối tượng đổi, chỉ
ứng viên của đối tượng đó được tính lại; số đếm theo nhóm cộng lại từ trị ứng viên đã nhớ, không lưu kết quả nối."""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Sequence

from rag.rules.derived import derive_all, eval_derived
from rag.rules.evaluator import Diff, slot_changes
from rag.rules.exceptions import apply_exceptions, exception_open, rule_state
from rag.rules.network.network import Network
from rag.rules.network.nodes import CondState
from rag.rules.objects import (WorkingObject, aggregate, apply_object_changes, candidate, check_object, object_facts,
                               object_results)
from rag.rules.semantics import (Fact, Facts, RuleInputs, RuleResult, Tri, check_cond, decide_rule, resolve_law_with)


def _same(old: object, new: object) -> bool:
    """`Fact.__eq__` coi 1 == True == 1.0; ở đây khác kiểu giá trị là dữ kiện đã đổi (kết quả mang theo giá trị).
    Mốc CONFLICT / UNKNOWN không có `.value`: so như thường."""
    return old == new and type(getattr(old, "value", None)) is type(getattr(new, "value", None))


def _copy_evidence(evidence: dict[str, list[dict]]) -> dict[str, list[dict]]:
    return {k: list(v) for k, v in evidence.items()}


class ObjectMemory:
    """Bộ nhớ đối tượng của phiên (bộ nhớ alpha kiểu TREAT): đối tượng theo id, bảng dữ kiện của từng đối tượng
    (thuộc tính + dữ kiện suy ra theo kiểu), và trị ứng viên `cands[slot][id] = (tri, khóa nhóm)`."""

    def __init__(self, objects: Sequence[WorkingObject] = ()):
        self.objects: dict[str, WorkingObject] = {check_object(o).id: o for o in objects}
        self.tables: dict[str, Facts] = {}
        self.cands: dict[int, dict[str, tuple[Tri, tuple | None]]] = {}

    def copy(self) -> "ObjectMemory":
        clone = ObjectMemory()
        clone.objects, clone.tables = dict(self.objects), dict(self.tables)
        clone.cands = {i: dict(c) for i, c in self.cands.items()}
        return clone


class NetworkSession:
    def __init__(self, network: Network, day: date, facts: Facts, present: set[str], evidence: dict[str, list[dict]],
                 objects: Sequence[WorkingObject] = ()):
        self._net, self._day = network, day
        ctx = network.catalog.context
        self._facts = derive_all(ctx, facts)                  # bảng đã gộp dữ kiện suy ra (khóa trùng tên bị bỏ)
        self._present, self._evidence = set(present), _copy_evidence(evidence)
        self._cond = CondState(network.graph, self._facts, ctx)
        self._mem = ObjectMemory(objects)
        recomputed = 0
        for oid, o in self._mem.objects.items():
            self._mem.tables[oid] = object_facts(o, ctx, day)
        for typ, slots in network.object_slots_by_type.items():
            for i in slots:
                self._mem.cands[i] = {}
                for oid, o in self._mem.objects.items():
                    if o.type == typ:
                        self._mem.cands[i][oid] = candidate(network.rules[i].rule, o, self._mem.tables[oid], day, ctx)
                        recomputed += 1
        computed = [self._compute(i) for i in range(len(network.rules))]
        self._base: list = [r for r, _ in computed]          # kết quả trước ngoại lệ; rule xuyên đối tượng: danh sách
        self._state: list[Tri] = [s for _, s in computed]     # rule có áp dụng không (rule_state)
        self._results: list[list[RuleResult]] = self._finalize(None)
        self.stats = {"nodes_recomputed": len(network.graph.kinds), "rules_recomputed": len(network.rules),
                      "objects_recomputed": recomputed}

    # ── tính ──
    def _inputs(self, i: int) -> RuleInputs:
        slot, ctx, facts = self._net.rules[i], self._net.catalog.context, self._facts
        values = self._cond.values
        app = "T" if slot.app_node is None else values[slot.app_node]
        whens = ["T" if n is None else values[n] for n in slot.when_nodes]
        law, law_st, law_reasons = resolve_law_with(slot.rule, whens, facts, self._day)
        check_st = None if slot.rule.check is None or slot.rule.over is not None else \
            check_cond(slot.rule.check, facts, law or {}, ctx)
        return RuleInputs(app, law, law_st, law_reasons, check_st)

    def _compute(self, i: int) -> tuple[Any, Tri]:
        slot, ctx = self._net.rules[i], self._net.catalog.context
        inputs = self._inputs(i)
        evidence = self._evidence.get(slot.concept_id, ())
        if slot.rule.over is not None:
            groups = aggregate(self._mem.cands[i].values())
            return object_results(slot.concept_id, slot.rule, self._facts, evidence, inputs, groups, ctx), "F"
        return (decide_rule(slot.concept_id, slot.rule, self._facts, slot.concept_id in self._present, evidence,
                            inputs, ctx), rule_state(inputs))

    def _finalize(self, only: set[int] | None) -> list[list[RuleResult]]:
        """Kết quả cuối (danh sách theo slot) của mọi slot, hoặc chỉ `only` theo thứ tự tăng dần."""
        net, ctx = self._net, self._net.catalog.context
        idx = net.exceptions
        which = range(len(self._base)) if only is None else sorted(only)
        final = {}
        if idx is not None and idx.involved and (only is None or only & idx.involved):
            final = apply_exceptions(idx, self._base, self._state,
                                     lambda i: exception_open(net.rules[i].rule, self._facts, ctx), only=only)
        return [self._base[i] if isinstance(self._base[i], list) else [final.get(i, self._base[i])] for i in which]

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

    def _apply_objects(self, changes) -> tuple[set[int], int]:
        """Ghi thay đổi đối tượng; tính lại bảng dữ kiện và trị ứng viên CHỈ của đối tượng đổi. Trả (slot bẩn, số ứng viên)."""
        net, ctx, mem = self._net, self._net.catalog.context, self._mem
        before = dict(mem.objects)
        changed = apply_object_changes(mem.objects, changes)
        dirty, recomputed = set(), 0
        for oid in changed:
            old, new = before.get(oid), mem.objects.get(oid)
            if new is None:
                mem.tables.pop(oid, None)
            else:
                mem.tables[oid] = object_facts(new, ctx, self._day)
            for typ in {o.type for o in (old, new) if o is not None}:
                for i in net.object_slots_by_type.get(typ, ()):
                    cands = mem.cands[i]
                    if new is not None and new.type == typ:
                        cands[oid] = candidate(net.rules[i].rule, new, mem.tables[oid], self._day, ctx)
                        recomputed += 1
                    else:
                        cands.pop(oid, None)
                    dirty.add(i)
        return dirty, recomputed

    # ── API phiên ──
    @property
    def day(self) -> date:
        return self._day

    def facts(self) -> Facts:
        return dict(self._facts)

    def results(self) -> list[RuleResult]:
        return [r for slot in self._results for r in slot]

    def update(self, changes: Mapping[str, Fact | None], *, present: set[str] | None = None,
               evidence: dict[str, list[dict]] | None = None, objects: Any = None) -> Diff:
        """`None` xóa dữ kiện; `present` / `evidence` nếu truyền thì thay hẳn giá trị hiện có; `objects`: ObjectChanges."""
        net, dirty = self._net, set()
        changed_names = set()
        ctx = net.catalog.context
        objects_recomputed = 0
        if objects:
            dirty, objects_recomputed = self._apply_objects(objects)
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
        if changed_names and net.derived_order:
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
            out += slot_changes(before, after)
        self.stats = {"nodes_recomputed": self._cond.last_recomputed, "rules_recomputed": len(dirty),
                      "objects_recomputed": objects_recomputed}
        return Diff(tuple(out))

    def fork(self) -> "NetworkSession":
        clone = NetworkSession.__new__(NetworkSession)
        clone._net, clone._day = self._net, self._day
        clone._facts, clone._present, clone._evidence = dict(self._facts), set(self._present), _copy_evidence(self._evidence)
        clone._cond = self._cond.copy()
        clone._mem = self._mem.copy()
        clone._base, clone._state = list(self._base), list(self._state)
        clone._results = [list(r) for r in self._results]
        clone.stats = dict(self.stats)
        return clone
