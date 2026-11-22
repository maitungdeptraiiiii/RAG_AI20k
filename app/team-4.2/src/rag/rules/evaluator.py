"""Interface của bộ đánh giá rule (spec §7): `Evaluator` -> `Session` -> `results()` / `update()` / `fork()`.

Chữ ký ở đây được công bố cho benchmark và giữ ổn định đến hết giai đoạn 7. `ReferenceEvaluator` tính lại toàn bộ sau
mỗi `update` (chuẩn đúng); `network` (`rag.rules.network`) chỉ tính lại rule bị ảnh hưởng và là mặc định."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, Mapping, Protocol, Sequence

from rag.rules.derived import derive_all
from rag.rules.loader import load_packs
from rag.rules.model import Catalog
from rag.rules.objects import WorkingObject, apply_object_changes
from rag.rules.reference import evaluate_all
from rag.rules.semantics import Fact, Facts, RuleResult

EvaluatorKind = Literal["reference", "network"]


@dataclass(frozen=True)
class RuleChange:
    concept_id: str
    rule_id: str
    before: RuleResult | None
    after: RuleResult | None
    object: str | None = None             # nhóm của rule xuyên đối tượng (spec §5.6)


def slot_changes(before: Sequence[RuleResult], after: Sequence[RuleResult]) -> list[RuleChange]:
    """Thay đổi giữa hai danh sách kết quả của MỘT rule, khóa theo `object`: theo thứ tự kết quả mới, rồi các nhóm biến mất."""
    old = {r.object: r for r in before}
    out = []
    for r in after:
        b = old.pop(r.object, None)
        if b != r:
            out.append(RuleChange(r.concept_id, r.rule_id, b, r, r.object))
    out += [RuleChange(b.concept_id, b.rule_id, b, None, b.object) for b in old.values()]
    return out


def diff_results(before: Sequence[RuleResult], after: Sequence[RuleResult]) -> list[RuleChange]:
    """Thay đổi giữa hai lần đánh giá toàn catalog, theo thứ tự rule rồi theo `slot_changes`."""
    def by_rule(results):
        groups: dict[tuple[str, str], list[RuleResult]] = {}
        for r in results:
            groups.setdefault((r.concept_id, r.rule_id), []).append(r)
        return groups
    b, a = by_rule(before), by_rule(after)
    keys = list(dict.fromkeys([*a, *b]))
    return [c for k in keys for c in slot_changes(b.get(k, ()), a.get(k, ()))]


@dataclass(frozen=True)
class Diff:
    changes: tuple[RuleChange, ...]


class Session(Protocol):
    day: date

    def results(self) -> list[RuleResult]: ...

    def facts(self) -> Facts: ...        # bản sao bảng dữ kiện đã gộp dữ kiện suy ra (cho explain)

    def update(self, changes: Mapping[str, Fact | None], *, present: set[str] | None = None,
               evidence: dict[str, list[dict]] | None = None, objects: Any = None) -> Diff: ...

    def fork(self) -> "Session": ...


class Evaluator(Protocol):
    def session(self, *, day: date, facts: Facts, present: set[str], evidence: dict[str, list[dict]],
                objects: Sequence[Any] = ()) -> Session: ...


def _copy_evidence(evidence: dict[str, list[dict]]) -> dict[str, list[dict]]:
    return {k: list(v) for k, v in evidence.items()}


class ReferenceSession:
    def __init__(self, catalog: Catalog, day: date, facts: Facts, present: set[str], evidence: dict[str, list[dict]],
                 objects: Sequence[WorkingObject] = ()):
        self._catalog, self._day = catalog, day
        self._facts, self._present, self._evidence = dict(facts), set(present), _copy_evidence(evidence)
        self._objects: dict[str, WorkingObject] = {o.id: o for o in objects}
        self._results = self._evaluate()

    @property
    def day(self) -> date:
        return self._day

    def facts(self) -> Facts:
        return derive_all(self._catalog.context, self._facts)

    def _evaluate(self) -> list[RuleResult]:
        return evaluate_all(self._catalog, self._facts, self._present, self._evidence, self._day,
                            list(self._objects.values()))

    def results(self) -> list[RuleResult]:
        return list(self._results)

    def update(self, changes: Mapping[str, Fact | None], *, present: set[str] | None = None,
               evidence: dict[str, list[dict]] | None = None, objects: Any = None) -> Diff:
        """`None` xóa dữ kiện; `present` / `evidence` nếu truyền thì thay hẳn giá trị hiện có; `objects`: ObjectChanges."""
        if objects:
            apply_object_changes(self._objects, objects)
        for name, fact in changes.items():
            if fact is None:
                self._facts.pop(name, None)
            else:
                self._facts[name] = fact
        if present is not None:
            self._present = set(present)
        if evidence is not None:
            self._evidence = _copy_evidence(evidence)
        before, self._results = self._results, self._evaluate()
        return Diff(tuple(diff_results(before, self._results)))

    def fork(self) -> "ReferenceSession":
        return ReferenceSession(self._catalog, self._day, self._facts, self._present, self._evidence,
                                list(self._objects.values()))


class ReferenceEvaluator:
    def __init__(self, catalog: Catalog):
        self._catalog = catalog

    def session(self, *, day: date, facts: Facts, present: set[str], evidence: dict[str, list[dict]],
                objects: Sequence[Any] = ()) -> ReferenceSession:
        return ReferenceSession(self._catalog, day, facts, present, evidence, objects)


def evaluator_for(catalog: Catalog, kind: EvaluatorKind = "reference") -> Evaluator:
    if kind == "network":
        from rag.rules.network.network import NetworkEvaluator   # nạp muộn: network.session import lại Diff / RuleChange ở đây
        return NetworkEvaluator(catalog)
    if kind != "reference":
        raise ValueError(f"evaluator lạ {kind!r}: chọn 'reference' hoặc 'network'")
    return ReferenceEvaluator(catalog)


def default_kind() -> EvaluatorKind:
    """Evaluator mặc định, đổi được bằng biến môi trường RAG_RULE_EVALUATOR (reference | network)."""
    kind = os.environ.get("RAG_RULE_EVALUATOR", "network")
    if kind not in ("reference", "network"):
        raise ValueError(f"RAG_RULE_EVALUATOR={kind!r}: chọn 'reference' hoặc 'network'")
    return kind                                                                 # type: ignore[return-value]


def make_evaluator(packs: Sequence[str], kind: EvaluatorKind | None = None) -> Evaluator:
    """`kind` bỏ trống thì theo `default_kind()` (biến môi trường RAG_RULE_EVALUATOR, mặc định network)."""
    return evaluator_for(load_packs(packs), kind or default_kind())
