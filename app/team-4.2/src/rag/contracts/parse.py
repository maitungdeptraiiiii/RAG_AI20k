"""Tách hợp đồng thành đơn vị theo đánh số của chính hợp đồng: Điều > Mục (1., 2. / I, II) > đoạn văn."""

from __future__ import annotations

import re
import unicodedata

from rag.contracts.models import ContractUnit

DEMO_MAX_UNITS = 30

_DIEU = re.compile(r"^\s*Điều\s+(\d+[a-zđ]?)\s*[.:]", re.IGNORECASE)
_MUC = re.compile(r"^\s*(?:Mục\s+)?([IVXLC]+|\d+)\s*[.)]\s+\S", re.IGNORECASE)


def _split(lines: list[str], pattern: re.Pattern, label: str) -> list[tuple[str, list[str]]] | None:
    blocks: list[tuple[str, list[str]]] = [("Phần mở đầu", [])]
    found = False
    for line in lines:
        m = pattern.match(line)
        if m:
            found = True
            blocks.append((f"{label} {m.group(1)}", [line]))
        else:
            blocks[-1][1].append(line)
    if not found:
        return None
    return [(lab, body) for lab, body in blocks if "".join(body).strip()]


def split_units(text: str) -> list[ContractUnit]:
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n")
    lines = text.split("\n")
    blocks = _split(lines, _DIEU, "Điều") or _split(lines, _MUC, "Mục")
    if blocks is None:
        paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
        blocks = [(f"Đoạn {i}", [p]) for i, p in enumerate(paragraphs, 1)]
    return [ContractUnit(f"u{i}", label, "\n".join(body).strip())
            for i, (label, body) in enumerate(blocks, 1)]


def limit_units(units: list[ContractUnit], n: int = DEMO_MAX_UNITS) -> tuple[list[ContractUnit], int]:
    return units[:n], len(units)
