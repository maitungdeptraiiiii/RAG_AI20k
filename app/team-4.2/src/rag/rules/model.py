"""Kiểu dữ liệu của rule engine: gói luật, ngữ cảnh đánh giá, lỗi nạp (spec §5.5, §7)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

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
class Context:
    """Phần của gói mà logic thuần cần: đơn vị, dữ kiện cấp hợp đồng, bảng on_silence."""
    units: Units
    document_facts: frozenset[str]
    silences: Mapping[str, Silence]

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

    def context(self) -> Context:
        return Context(self.units, frozenset(self.document_facts), self.silences)
