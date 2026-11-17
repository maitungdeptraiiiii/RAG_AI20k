"""parse_contract: trang -> ContractDoc (phần, cây đơn vị, giá trị, dẫn chiếu, báo cáo chất lượng)."""
from __future__ import annotations

import statistics

from rag.contracts.doc import (Assembled, ContractDoc, PageText, ParseReport, PartSpec, Unit, Value,
                               assemble, own_texts)
from rag.contracts.models import ContractUnit
from rag.contracts.parts import detect_parts
from rag.contracts.tree import parse_part
from rag.contracts.values import extract_values
from rag.contracts.xrefs import find_xrefs
from rag.quality.pii import _spans as pii_spans

PARSER_VERSION = "2"  # đổi khi đổi quy tắc tách — là đầu vào của bản dựng

_UNSTRUCTURED_LIMIT = 0.3
_THIN_PAGE_RATIO = 0.25
_MIN_NUMBERED_PAGES = 3
_MAX_PAGE_WARNINGS = 3


def _values(units: list[Unit]) -> list[Value]:
    """Giá trị trong văn bản riêng của từng đơn vị (vị trí tính trong văn bản đơn vị); bỏ giá trị chạm vùng PII."""
    own = own_texts(units)
    out: list[Value] = []
    for u in units:
        text = own[u.uid]
        pii = [(s, e) for s, e, _ in pii_spans(text)]
        found = [v for v in extract_values(text)
                 if all(v.end <= s or v.start >= e for s, e in pii)]
        for i, v in enumerate(found, 1):
            out.append(Value(f"{u.uid}#v{i}", u.uid, v.kind, v.raw, v.norm, v.start, v.end))
    return out


def _warn_pages(pages: list[PageText]) -> list[int]:
    numbered = [p for p in pages if p.page is not None and p.kind != "TablePage"]  # bảng không phải trang
    if len(numbered) < _MIN_NUMBERED_PAGES:
        return []
    median = statistics.median(len(p.text) for p in numbered)
    return sorted({p.page for p in numbered
                   if len(p.text) < _THIN_PAGE_RATIO * median or p.kind == "OCRPage"})


def _report(a: Assembled, pages: list[PageText], units: list[Unit], styles: dict[str, str],
            gaps: list[str]) -> ParseReport:
    counts = {"article": 0, "clause": 0, "point": 0}
    for u in units:
        if u.level in counts:
            counts[u.level] += 1
    total = len(a.text)
    loose = sum(len(u.text) for u in units if u.level in ("preamble", "paragraph"))
    ratio = loose / total if total else 0.0
    warn_pages = _warn_pages(pages)
    warnings: list[str] = []
    if ratio > _UNSTRUCTURED_LIMIT:
        warnings.append("Không nhận ra đánh số Điều / khoản cho phần lớn văn bản")
    warnings += [f"Đánh số không liền mạch: {g}" for g in gaps]
    if len(warn_pages) > _MAX_PAGE_WARNINGS:  # nhiều trang: gộp một dòng; danh sách đủ ở warn_pages
        shown = ", ".join(str(n) for n in warn_pages[:_MAX_PAGE_WARNINGS])
        warnings.append(f"Trang {shown}, … có thể chứa nội dung chưa đọc được")
    else:
        warnings += [f"Trang {n} có thể chứa nội dung chưa đọc được" for n in warn_pages]
    return ParseReport(styles, counts, gaps, ratio, warn_pages, warnings)


def parse_contract(pages: list[PageText], parts: list[PartSpec] | None = None) -> ContractDoc:
    """Phân tích các trang hợp đồng thành ContractDoc."""
    a = assemble(pages)
    detected = detect_parts(a.text)
    parts = detected if parts is None else parts
    headings = {(p.start, p.title) for p in detected if p.kind == "appendix"}
    units: list[Unit] = []
    styles: dict[str, str] = {}
    gaps: list[str] = []
    appendix_index = 0
    for i, part in enumerate(parts):
        end = parts[i + 1].start if i + 1 < len(parts) else len(a.text)
        prefix = ""
        if part.kind == "appendix":
            appendix_index += 1
            prefix = f"Phụ lục {part.number or appendix_index} — "
        pu, style, g = parse_part(a, part, end, prefix)
        if part.kind == "appendix" and (part.start, part.title) in headings:  # chỉ bỏ dòng tiêu đề bộ tách nhận ra
            pu = [u for u in pu if not (u.level == "preamble" and u.text.strip() == part.title)]
        units += pu
        styles[part.part_id] = style
        gaps += g
    return ContractDoc(parts, units, _values(units), find_xrefs(units, parts),
                       _report(a, pages, units, styles, gaps))


def to_contract_units(doc: ContractDoc) -> list[ContractUnit]:
    """Đơn vị cấp cao nhất dưới dạng ContractUnit cũ."""
    return [ContractUnit(u.uid, u.label, u.text, page=u.page_start) for u in doc.top_units()]
