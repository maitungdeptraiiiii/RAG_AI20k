"""Áp dụng chất lượng dữ liệu lên kết quả parse, dùng trong ``RAGPipeline.ingest``.

    mask_pages(pages)          Page/TablePage -> bản đã mask PII + SafePIIFinding (một MaskState/tài liệu)
    assess_tables(pages, ...)  validate từng bảng + conflict với fact của tài liệu đã ingest

Gọi ``mask_pages`` NGAY sau loader, trước chunking / contextual LLM / embedding / BM25 / ghi
``chunks.jsonl`` / log, nên không bước nào sau đó thấy PII gốc.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import replace

from rag.ingest.loaders import TablePage
from rag.ingest.tables import mask_table, table_markdown
from rag.quality.issues import QualityIssue
from rag.quality.numeric import CSV_MACHINE, NumericNormalizationConfig
from rag.quality.pii import MaskState, SafePIIFinding, mask_text
from rag.quality.validate import TableFact, detect_conflicts, extract_facts, validate_table
from rag.schema import Page


def mask_pages(pages: Sequence[Page]) -> tuple[list[Page], list[SafePIIFinding]]:
    """Bảng mask trước (biết loại cột từ header), rồi tới văn bản: giá trị PII đã thấy trong bảng
    cũng bị thay trong thân văn bản (DOCX giữ bảng tại chỗ dưới dạng "ô | ô")."""
    state = MaskState()
    out: list[Page | None] = [None] * len(pages)
    findings: list[SafePIIFinding] = []
    for i, page in enumerate(pages):
        if isinstance(page, TablePage) and page.table is not None:
            table, found = mask_table(page.table, state)
            out[i] = replace(page, text=table_markdown(table), table=table)
            findings.extend(found)
    for i, page in enumerate(pages):
        if out[i] is not None:
            continue
        result = mask_text(page.text, state=state, location=f"page:{page.page or i}")
        text, _ = state.mask_known(result.masked_text)
        out[i] = replace(page, text=text)
        findings.extend(result.safe_findings)
    return [p for p in out if p is not None], findings


def assess_tables(
    pages: Iterable[Page],
    existing: Iterable[tuple[str, TableFact]] = (),
    *,
    config: NumericNormalizationConfig = CSV_MACHINE,
) -> tuple[list[QualityIssue], list[TableFact]]:
    """Issue của các bảng trong tài liệu + fact mới (để so conflict với tài liệu sau)."""
    issues: list[QualityIssue] = []
    facts: list[TableFact] = []
    for page in pages:
        if not isinstance(page, TablePage) or page.table is None:
            continue
        issues.extend(validate_table(page.table, config))
        facts.extend(extract_facts(page.table))
    issues.extend(detect_conflicts(facts, existing, config=config))
    return issues, facts


__all__ = ["assess_tables", "mask_pages"]
