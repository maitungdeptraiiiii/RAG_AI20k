"""Conservative guard against treating amendment fragments as complete articles.

This recognizes textual warning signs; absence of a match is NOT proof of legal
completeness. Findings contain fixed reasons, never excerpts of raw source text.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence

from rag.models.content import Block
from rag.models.document import UnitAssignment
from rag.models.results import ParseResult

_ACTION = r"(?:sửa\s+đổi(?:\s*,?\s*bổ\s+sung)?|bổ\s+sung|bãi\s+bỏ|thay\s+thế|thay\s+(?:cụm\s+từ|từ\s+ngữ|từ|số)|đình\s+chỉ)"
_SUBUNIT = r"(?:khoản\s+\d+[a-zđ]?|điểm\s+[a-zđ](?=\s|[.,:;\)]|$))"
_DIRECTIVES = (
    re.compile(_ACTION + r".{0,240}?\b" + _SUBUNIT),
    re.compile(_SUBUNIT + r"[^.!?;]{0,120}?(?:được\s+|nay\s+|:\s*)?" + _ACTION),
)
_ARTICLE = re.compile(r"(?m)^\s*[\"“”‘’']?\s*điều\s+(\d+[a-zđ]?)\s*[.:]")
_CLAUSE = re.compile(r"(?m)^\s*[\"“”‘’']?\s*(\d+)\s*[.)]\s+")
_POINT = re.compile(r"^\s*[\"“”‘’']?\s*([a-zđ])\s*[.)]\s+")
_BARE_SUBUNIT = re.compile(r"^\s*[\"“”‘’']?\s*(?:khoản\s+\d+|điểm\s+[a-zđ]\b|\d+\s*[.)]\s+|[a-zđ]\)\s+)")


def source_text(blocks: Sequence[Block]) -> str:
    """Normalized source text for conservative guards, including table content."""
    parts = []
    for block in sorted(blocks, key=lambda b: b.order):
        parts.append(block.text)
        if block.table is not None:
            parts.extend(" ".join(row) for row in (*block.table.headers, *block.table.rows))
            parts.extend((block.table.caption or "", *block.table.notes))
    return unicodedata.normalize("NFC", "\n".join(parts)).casefold()


def _points(text: str) -> set[tuple[str | None, str]]:
    """Keep point labels scoped to their clause, not a global a/b/c set."""
    result, clause = set(), None
    for line in text.splitlines():
        numbered = _CLAUSE.match(line)
        if numbered:
            clause = numbered.group(1)
        point = _POINT.match(line)
        if point:
            result.add((clause, point.group(1)))
    return result


def amendment_fragment_reasons(
    parsed: ParseResult, *, assignments: Sequence[UnitAssignment] = (),
    previous_blocks: Mapping[str, Sequence[Block]] | None = None,
) -> tuple[str, ...]:
    """Review suspicious directives, missing article headings and missing clauses.

    previous_blocks is populated only for confirmed replacement targets. Clause
    reduction is routed to review even when it might be a legitimate rewrite.
    Only explicit article:N keys are checked against article headings.
    """
    text = source_text(parsed.blocks)
    flat = re.sub(r"\s+", " ", text)
    reasons = []
    if any(pattern.search(flat) for pattern in _DIRECTIVES):
        reasons.append("amendment.fragment: source contains clause/point amendment instructions; complete revised article text is required")
    if not _ARTICLE.search(text) and _BARE_SUBUNIT.match(text):
        reasons.append("amendment.fragment: source starts with a clause/point rather than a complete article")
    by_id = {b.block_id: b for b in parsed.blocks}
    for assignment in assignments:
        key = re.fullmatch(r"article:(\d+[a-zđ]?)", assignment.unit_key.casefold())
        if key is None:
            continue
        if any(bid not in by_id for bid in assignment.block_ids):
            continue  # the planner/repository validates block ownership separately
        incoming = source_text(tuple(by_id[bid] for bid in assignment.block_ids))
        headings = _ARTICLE.findall(incoming)
        if headings != [key.group(1)]:
            reasons.append("amendment.fragment: article assignment must contain exactly its own article heading")
        old = (previous_blocks or {}).get(assignment.unit_key)
        if old:
            old_clauses, new_clauses = set(_CLAUSE.findall(source_text(old))), set(_CLAUSE.findall(incoming))
            if old_clauses - new_clauses:
                reasons.append("amendment.missing_clauses: replacement omits numbered clauses from the previous article; manual consolidation is required")
            if _points(source_text(old)) - _points(incoming):
                reasons.append("amendment.missing_points: replacement omits lettered points from the previous article; manual consolidation is required")
    return tuple(dict.fromkeys(reasons))
