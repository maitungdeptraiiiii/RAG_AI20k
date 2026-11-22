"""Bảng đơn vị và quy đổi do gói luật khai báo (spec §5.1). Lõi không biết đơn vị nào cả."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class Units:
    names: frozenset[str]
    factors: Mapping[str, tuple[str, float]]     # đơn vị -> (đơn vị gốc, hệ số quy về gốc)

    def convert(self, value: float, unit: str | None, to: str | None) -> float | None:
        """Cùng đơn vị -> giữ nguyên; cả hai có hệ số và cùng gốc -> quy đổi; còn lại None (không quy đổi được)."""
        if unit == to:
            return value
        a, b = self.factors.get(unit), self.factors.get(to)
        if a is None or b is None or a[0] != b[0]:
            return None
        return value * a[1] / b[1]
