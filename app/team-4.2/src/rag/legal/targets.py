"""Phân giải tên luật đích -> document_key, và định vị đơn vị đích trong cây Provision."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import date

from rag.legal.keys import normalize_number, provision_id
from rag.legal.models import Address, LegalDocument, Provision


def law_name(title: str) -> str:
    """"Luật Doanh nghiệp số 59/2020/QH14" -> "luật doanh nghiệp"."""
    name = unicodedata.normalize("NFC", title).casefold()
    name = re.split(r"\s+số\s+", name, maxsplit=1)[0]
    name = re.sub(r"\s+(?:năm\s+)?\d{4}\s*$", "", name)
    return re.sub(r"\s+", " ", name).strip()


def resolve_target_law(name: str | None, number: str | None, *, before: date | None,
                       documents: Sequence[LegalDocument]) -> tuple[str | None, tuple[str, ...]]:
    laws = [d for d in documents if not d.is_consolidated]
    wanted = law_name(name) if name else None
    if number:
        num = normalize_number(number)
        hits = [d for d in laws if normalize_number(d.doc_number) == num]
        if len(hits) > 1:
            hits = [d for d in hits if d.doc_type.casefold() in ("luật", "bộ luật")] or hits
        if wanted:
            named = [d for d in hits if law_name(d.title) == wanted]
            if hits and not named:
                return None, ("operation.target_law_mismatch",)
            hits = named
        if len(hits) == 1:
            return hits[0].document_key, ()
        if not hits:
            return None, ("operation.target_law_not_found",)
        return None, ("operation.target_law_ambiguous",)
    if not wanted:
        return None, ("operation.target_law_not_found",)
    candidates = [d for d in laws if law_name(d.title) == wanted and d.issued_on is not None
                  and (before is None or d.issued_on < before)]
    if not candidates:
        return None, ("operation.target_law_not_found",)
    best = max(candidates, key=lambda d: d.issued_on)
    return best.document_key, ()


def locate(index: Mapping[str, Provision], document_key: str, address: Address) -> Provision | None:
    if address.part == "title":
        kind = "article_title"
    elif address.part == "lead_in":
        kind = "clause_lead_in"
    elif address.point is not None:
        kind = "point"
    elif address.clause is not None:
        kind = "clause"
    else:
        kind = "article"
    return index.get(provision_id(document_key, address, kind))  # type: ignore[arg-type]


__all__ = ["law_name", "locate", "resolve_target_law"]
