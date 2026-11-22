"""Interface của bộ đánh giá rule (spec §7): `Evaluator` -> `Session` -> `results()` / `update()` / `fork()`.

Chữ ký ở đây được công bố cho benchmark và giữ ổn định đến hết giai đoạn 7. `ReferenceEvaluator` tính lại toàn bộ sau
mỗi `update` (chuẩn đúng); `network` (giai đoạn 2) chưa có."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, Mapping, Protocol, Sequence

from rag.rules.loader import load_packs
from rag.rules.model import Catalog
from rag.rules.reference import evaluate_all
from rag.rules.semantics import Fact, Facts, RuleResult

EvaluatorKind = Literal["reference", "network"]


@dataclass(frozen=True)
class RuleChange:
    concept_id: str
    rule_id: str
    before: RuleResult | None
    after: RuleResult | None


@dataclass(frozen=True)
class Diff:
    changes: tuple[RuleChange, ...]


class Session(Protocol):
    def results(self) -> list[RuleResult]: ...

    def update(self, changes: Mapping[str, Fact | None], *, present: set[str] | None = None,
               evidence: dict[str, list[dict]] | None = None, objects: Any = None) -> Diff: ...

    def fork(self) -> "Session": ...


class Evaluator(Protocol):
    def session(self, *, day: date, facts: Facts, present: set[str], evidence: dict[str, list[dict]],
                objects: Sequence[Any] = ()) -> Session: ...


def _copy_evidence(evidence: dict[str, list[dict]]) -> dict[str, list[dict]]:
    return {k: list(v) for k, v in evidence.items()}


class ReferenceSession:
    def __init__(self, catalog: Catalog, day: date, facts: Facts, present: set[str], evidence: dict[str, list[dict]]):
        self._catalog, self._day = catalog, day
        self._facts, self._present, self._evidence = dict(facts), set(present), _copy_evidence(evidence)
        self._results = self._evaluate()

    def _evaluate(self) -> list[RuleResult]:
        return evaluate_all(self._catalog, self._facts, self._present, self._evidence, self._day)

    def results(self) -> list[RuleResult]:
        return list(self._results)

    def update(self, changes: Mapping[str, Fact | None], *, present: set[str] | None = None,
               evidence: dict[str, list[dict]] | None = None, objects: Any = None) -> Diff:
        """`None` xóa dữ kiện; `present` / `evidence` nếu truyền thì thay hẳn giá trị hiện có."""
        if objects:
            raise NotImplementedError("objects: giai đoạn 7")
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
        return Diff(tuple(RuleChange(b.concept_id, b.rule_id, b, a) for b, a in zip(before, self._results) if b != a))

    def fork(self) -> "ReferenceSession":
        return ReferenceSession(self._catalog, self._day, self._facts, self._present, self._evidence)


class ReferenceEvaluator:
    def __init__(self, catalog: Catalog):
        self._catalog = catalog

    def session(self, *, day: date, facts: Facts, present: set[str], evidence: dict[str, list[dict]],
                objects: Sequence[Any] = ()) -> ReferenceSession:
        if objects:
            raise NotImplementedError("objects: giai đoạn 7")
        return ReferenceSession(self._catalog, day, facts, present, evidence)


def evaluator_for(catalog: Catalog, kind: EvaluatorKind = "reference") -> Evaluator:
    if kind == "network":
        from rag.rules.network.network import NetworkEvaluator   # nạp muộn: network.session import lại Diff / RuleChange ở đây
        return NetworkEvaluator(catalog)
    if kind != "reference":
        raise ValueError(f"evaluator lạ {kind!r}: chọn 'reference' hoặc 'network'")
    return ReferenceEvaluator(catalog)


def default_kind() -> EvaluatorKind:
    """Evaluator mặc định, đổi được bằng biến môi trường RAG_RULE_EVALUATOR (reference | network)."""
    kind = os.environ.get("RAG_RULE_EVALUATOR", "reference")
    if kind not in ("reference", "network"):
        raise ValueError(f"RAG_RULE_EVALUATOR={kind!r}: chọn 'reference' hoặc 'network'")
    return kind                                                                 # type: ignore[return-value]


def make_evaluator(packs: Sequence[str], kind: EvaluatorKind = "reference") -> Evaluator:
    return evaluator_for(load_packs(packs), kind)
