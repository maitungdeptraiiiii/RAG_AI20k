"""Kiểu dữ liệu của rule engine: gói luật, ngữ cảnh đánh giá, lỗi nạp (spec §5.5, §7)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal, Mapping

from rag.rules.units import Units

CORE_FINDINGS = frozenset({"ok", "violation", "needs_facts", "conflict", "missing_content"})


class CatalogError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("Danh mục khái niệm lỗi:\n- " + "\n- ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Silence:
    """Kết quả khi hợp đồng không nói tới khái niệm: (status, finding) khi rule áp dụng và khi chưa biết có áp dụng."""
    applicable: tuple[str, str]
    unknown: tuple[str, str]


CORE_SILENCES: dict[str, Silence] = {
    "none": Silence(("PASS", "ok"), ("PASS", "ok")),
    "missing_content": Silence(("FAIL", "missing_content"), ("UNKNOWN", "needs_facts")),
}


@dataclass(frozen=True)
class Definition:
    """Một định nghĩa của dữ kiện suy ra (spec §5.3): lấy `value` hằng hoặc giá trị dữ kiện `from_fact` khi `when` đúng;
    `exception_of` trỏ id định nghĩa mà nó là ngoại lệ."""
    id: str
    when: dict | None
    exception_of: str | None
    from_fact: str | None
    has_value: bool                    # YAML có khóa `value` (False / None cũng là giá trị hợp lệ)
    value: Any
    anchors: tuple[dict, ...] = ()


@dataclass(frozen=True)
class DerivedFact:
    fact: str
    unit: str | None
    definitions: tuple[Definition, ...]


@dataclass(frozen=True)
class Context:
    """Phần của gói mà logic thuần cần: đơn vị, dữ kiện cấp hợp đồng, bảng on_silence, dữ kiện suy ra."""
    units: Units
    document_facts: frozenset[str]
    silences: Mapping[str, Silence]
    derived: Mapping[str, DerivedFact] = field(default_factory=dict)

    @property
    def reported(self) -> frozenset[str]:
        """Finding mang `outcome` (legality...): violation và mọi finding của bảng on_silence, trừ ok / needs_facts."""
        found = {f for s in self.silences.values() for f in (s.applicable[1], s.unknown[1])}
        return frozenset({"violation"} | found) - {"ok", "needs_facts"}


@dataclass(frozen=True)
class PackSpec:
    id: str
    version: str
    extends: tuple[str, ...]
    document_kinds: tuple[str, ...]
    units: Units
    document_facts: Mapping[str, str | None]      # dữ kiện cấp hợp đồng -> đơn vị
    user_facts: frozenset[str]
    findings: frozenset[str]                       # finding thêm ngoài CORE_FINDINGS
    silences: Mapping[str, Silence]                # đã gộp CORE_SILENCES
    derived: Mapping[str, DerivedFact] = field(default_factory=dict)

    def context(self) -> Context:
        return Context(self.units, frozenset(self.document_facts), self.silences, self.derived)


# ── danh mục khái niệm (concepts.yaml) ──
OPS = frozenset({"eq", "lt", "lte", "gt", "gte", "in", "present", "absent"})
MODES = frozenset({"required", "threshold", "prohibited", "default"})
DEROGATIONS = frozenset({"floor", "mandatory", "default"})
SLOT_KINDS = frozenset({"duration", "percent", "money", "bool", "enum"})


@dataclass(frozen=True)
class Slot:
    name: str
    kind: Literal["duration", "percent", "money", "bool", "enum"]
    unit: str | None
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class Rule:
    id: str
    mode: str
    derogation: str
    on_silence: str
    applicability: dict | None
    law: dict
    cases: tuple[dict, ...]
    check: dict | None
    outcome: dict
    # Phép kiểm là một slot có/không "= false" (hợp đồng không có hạn chế): khái niệm có mặt mà slot không được điền
    # thì coi là không có hạn chế. Bộ nạp tự suy từ `check` khi YAML không ghi (spec §5.2).
    unstated_false: bool = False


@dataclass(frozen=True)
class Concept:
    id: str
    label: str
    scope: str
    phase: str
    holder: str
    counterparty: str
    applies_to: tuple[str, ...]
    describe: str
    phrasing: tuple[str, ...]
    slots: dict[str, Slot]
    anchors: tuple[dict, ...]
    value_sources: tuple[dict, ...]
    rules: tuple[Rule, ...]
    not_about: tuple[dict, ...] = ()   # [{text, see}]: điều khoản dễ gán nhầm vào khái niệm này; see = khái niệm đúng


@dataclass(frozen=True)
class Catalog:
    version: str
    law_values_valid_from: date
    roles: dict[str, dict]
    concepts: dict[str, Concept]
    context: Context


def leaves(cond: Any) -> list[dict]:
    """Các lá {fact, op, ...} của một điều kiện all / any / not."""
    if not isinstance(cond, dict):
        return []
    for key in ("all", "any"):
        if key in cond:
            return [x for c in cond[key] for x in leaves(c)]
    if "not" in cond:
        return leaves(cond["not"])
    return [cond]
