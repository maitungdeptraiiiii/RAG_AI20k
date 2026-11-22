"""Interface của bộ đánh giá rule (spec §7): `Evaluator` -> `Session` -> `results()` / `update()` / `fork()`.

Chữ ký ở đây được công bố cho benchmark và giữ ổn định đến hết giai đoạn 7. Bản hiện tại là stub trả dữ liệu giả
đúng kiểu để dựng khung đo; Task 8 thay bằng ReferenceEvaluator thật."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, Mapping, Protocol, Sequence

from rag.bridge.engine import Fact, Facts, RuleResult   # tạm: Task 8 đổi sang rag.rules.semantics

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


class StubSession:
    def results(self) -> list[RuleResult]:
        return [RuleResult("stub.concept", "r1", "PASS", "ok", None, None, {}, {}, (), (), ()),
                RuleResult("stub.concept", "r2", "FAIL", "violation", "illegal", "unfavorable", {}, {}, (), (), ())]

    def update(self, changes, *, present=None, evidence=None, objects=None) -> Diff:
        return Diff(())

    def fork(self) -> "StubSession":
        return StubSession()


class StubEvaluator:
    def session(self, *, day, facts, present, evidence, objects=()) -> StubSession:
        return StubSession()


def make_evaluator(packs: Sequence[str], kind: EvaluatorKind = "reference") -> Evaluator:
    if kind == "network":
        raise NotImplementedError("network: giai đoạn 2")
    return StubEvaluator()
