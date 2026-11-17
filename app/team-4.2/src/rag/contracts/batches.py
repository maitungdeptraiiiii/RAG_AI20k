"""Chia hợp đồng dài thành lô cho LLM (spec 2026-11-12 §9.1, 2026-11-13 §4).

Mỗi lô: các đơn vị cấp cao nhất liền nhau trong ngân sách ký tự, kèm ngữ cảnh chung (phần mở đầu, Điều định nghĩa)
và nguyên văn các đơn vị lô dẫn chiếu tới — cả hai đánh dấu "chỉ để tham khảo".
"""
from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from rag.contracts.llm_json import ContractAIError
from rag.contracts.models import Contract, ContractUnit

BUDGET = 12_000          # ký tự đơn vị trong một lô
HARD_MAX = 24_000        # một đơn vị dài hơn: cắt thành nhiều mảnh cùng uid
CONTEXT_MAX = 3_000      # mỗi đơn vị ngữ cảnh / tham khảo
REFS_MAX = 3_000         # tổng đơn vị tham khảo của một lô
_DEFINITION = re.compile(r"giải\s+thích\s+từ\s+ngữ|định\s+nghĩa|các\s+thuật\s+ngữ", re.IGNORECASE)


@dataclass(frozen=True)
class Batch:
    index: int
    units: tuple[ContractUnit, ...]                 # đơn vị cần đọc (có thể là mảnh của một đơn vị dài)
    context: tuple[dict, ...] = ()                  # ngữ cảnh chung, chỉ để tham khảo
    references: tuple[dict, ...] = ()               # đơn vị được dẫn chiếu, chỉ để tham khảo

    @property
    def uids(self) -> list[str]:
        return list(dict.fromkeys(u.uid for u in self.units))

    def payload_units(self) -> list[dict]:
        return [{"uid": u.uid, "label": u.label, "text": u.text} for u in self.units]

    def span_label(self) -> str:
        labels = [u.label for u in self.units]
        return labels[0] if len(set(labels)) == 1 else f"{labels[0]} – {labels[-1]}"


@dataclass
class BatchRun:
    """Kết quả chạy một hàm trên mọi lô: dữ liệu của lô thành công, lô lỗi."""
    results: list[tuple[Batch, Any]] = field(default_factory=list)
    failed: list[Batch] = field(default_factory=list)

    @property
    def read_uids(self) -> list[str]:
        return list(dict.fromkeys(uid for b, _ in self.results for uid in b.uids))

    def warnings(self) -> list[str]:
        return [f"Chưa đọc được {b.span_label()} (AI lỗi hai lần)" for b in self.failed]


def _pieces(u: ContractUnit) -> list[ContractUnit]:
    if len(u.text) <= HARD_MAX:
        return [u]
    n = -(-len(u.text) // HARD_MAX)
    size = -(-len(u.text) // n)
    return [ContractUnit(u.uid, f"{u.label} (phần {i + 1}/{n})", u.text[i * size:(i + 1) * size], u.page)
            for i in range(n)]


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + " …"


def _top_of(uid: str, tops: Sequence[str]) -> str | None:
    return next((t for t in tops if uid == t or uid.startswith(t + ".")), None)


def make_batches(contract: Contract, units: Sequence[ContractUnit] | None = None, *,
                 budget: int = BUDGET) -> list[Batch]:
    """Lô trên `units` (mặc định mọi đơn vị cấp cao nhất), theo thứ tự trong hợp đồng."""
    units = list(contract.units if units is None else units)
    groups: list[list[ContractUnit]] = []
    size = 0
    for u in units:
        for piece in _pieces(u):
            if groups and size + len(piece.text) <= budget and len(piece.text) <= budget:
                groups[-1].append(piece)
                size += len(piece.text)
            else:
                groups.append([piece])
                size = len(piece.text)

    tops = [u.uid for u in contract.units]
    context: list[dict] = []
    first = contract.units[0] if contract.units else None
    if first is not None and not first.label.startswith("Điều"):
        context.append({"uid": first.uid, "label": first.label, "text": _cut(first.text, CONTEXT_MAX)})
    for u in contract.units:
        head = u.text.split("\n", 1)[0]
        if u.label.startswith("Điều") and _DEFINITION.search(head) and len(context) < 3:
            context.append({"uid": u.uid, "label": u.label, "text": _cut(u.text, CONTEXT_MAX)})

    xrefs = contract.doc.xrefs if contract.doc is not None else []
    by_uid = {u.uid: u for u in contract.units}
    out = []
    for i, group in enumerate(groups):
        inside = {u.uid for u in group} | {c["uid"] for c in context}
        targets: list[str] = []
        for x in xrefs:
            src, dst = _top_of(x.from_uid, tops), _top_of(x.to_uid or "", tops)
            if src in inside and dst and dst not in inside and dst not in targets:
                targets.append(dst)
        refs, used = [], 0
        for t in targets:
            text = _cut(by_uid[t].text, CONTEXT_MAX)
            if used + len(text) > REFS_MAX:
                break
            refs.append({"uid": t, "label": by_uid[t].label, "text": text})
            used += len(text)
        ctx = tuple(c for c in context if c["uid"] not in {u.uid for u in group})
        out.append(Batch(i, tuple(group), ctx, tuple(refs)))
    return out


def run_batches(batches: Sequence[Batch], fn: Callable[[Batch], Any], *, retries: int = 1) -> BatchRun:
    """Gọi `fn(batch)` cho từng lô; ContractAIError -> thử lại `retries` lần rồi ghi lô lỗi."""
    run = BatchRun()
    for b in batches:
        for attempt in range(retries + 1):
            try:
                run.results.append((b, fn(b)))
                break
            except ContractAIError:
                if attempt == retries:
                    run.failed.append(b)
    return run


def unit_text(batch: Batch, uid: str) -> str:
    """Toàn văn của `uid` trong lô (gộp các mảnh)."""
    return "\n".join(u.text for u in batch.units if u.uid == uid)


__all__ = ["BUDGET", "Batch", "BatchRun", "make_batches", "run_batches", "unit_text"]
