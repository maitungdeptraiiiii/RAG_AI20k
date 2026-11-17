"""Phụ lục sửa điều khoản của hợp đồng chính (spec 2026-11-16-contract-graph-agent §5.3): quy tắc, không dùng LLM.

Một đơn vị ngoài hợp đồng chính sửa một đơn vị của hợp đồng chính khi văn bản riêng của nó có động từ sửa đổi trên
cùng dòng với dẫn chiếu nội bộ trỏ vào `p0`. Ngày hiệu lực lấy từ câu "hiệu lực (kể) từ ngày …" trong cùng phần."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

from rag.contracts.doc import ContractDoc, own_texts

AMEND_RE = re.compile(r"điều chỉnh|sửa đổi|thay đổi|thay thế|nâng|bổ sung", re.IGNORECASE)
_EFFECTIVE_RE = re.compile(
    r"hiệu\s+lực\s+(?:kể\s+)?từ\s+ngày\s+(\d{1,2})(?:\s*/\s*|\s+tháng\s+)(\d{1,2})(?:\s*/\s*|\s+năm\s+)(\d{4})",
    re.IGNORECASE)


@dataclass(frozen=True)
class Amendment:
    src_uid: str
    dst_uid: str
    kind: Literal["modify", "supplement"]
    valid_from: date | None
    raw: str


def _effective(text: str) -> date | None:
    for m in _EFFECTIVE_RE.finditer(text):
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
    return None


def _clause(text: str, ref_raw: str) -> str | None:
    """Dòng đầu tiên chứa cả dẫn chiếu và động từ sửa đổi (tiêu đề "Nội dung thay đổi" không tính)."""
    return next((ln.strip() for ln in text.splitlines() if ref_raw in ln and AMEND_RE.search(ln)), None)


def find_amendments(doc: ContractDoc) -> list[Amendment]:
    own = own_texts(doc.units)
    part_of = {u.uid: u.part_id for u in doc.units}
    part_text: dict[str, str] = {}
    for u in doc.units:
        part_text[u.part_id] = part_text.get(u.part_id, "") + "\n" + u.text
    out: list[Amendment] = []
    seen: set[tuple[str, str]] = set()
    for x in doc.xrefs:
        src_part = part_of.get(x.from_uid)
        if x.kind != "internal" or not x.to_uid or not x.to_uid.startswith("p0.") or src_part in (None, "p0"):
            continue
        raw = _clause(own.get(x.from_uid, ""), x.raw)
        if raw is None or (x.from_uid, x.to_uid) in seen:
            continue
        seen.add((x.from_uid, x.to_uid))
        kind = "supplement" if AMEND_RE.search(raw).group(0).casefold() == "bổ sung" else "modify"
        out.append(Amendment(x.from_uid, x.to_uid, kind, _effective(part_text[src_part]), raw))
    return out


__all__ = ["AMEND_RE", "Amendment", "find_amendments"]
