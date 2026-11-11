"""Trạng thái cấp văn bản cho căn cứ (verified / partially_verified / unversioned / outdated / unknown), bảng định danh
kho luật cũ, loại trùng giữa hai kho, và nhận diện văn bản "chỉ để sửa đổi" (không đưa vào truy xuất)."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from rag.legal.directives import _ACTION_START, _PASSIVE
from rag.legal.keys import normalize_number
from rag.legal.models import Provision, ProvisionVersion
from rag.legal.store import LegalStore

DocumentStatus = Literal["verified", "partially_verified", "unversioned", "outdated", "unknown"]


@dataclass(frozen=True)
class LegacyLaw:
    source: str
    doc_type: str
    doc_number: str
    issuer: str


def load_legacy_map(path: Path) -> dict[str, LegacyLaw]:
    import yaml

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return {x["source"]: LegacyLaw(x["source"], x["type"], normalize_number(x["number"]), x["issuer"])
            for x in data.get("laws", [])}


def _identity(doc_type: str, number: str, issuer: str | None) -> tuple[str, str, str]:
    return doc_type.strip().casefold(), normalize_number(number), (issuer or "").strip().casefold()


DOCUMENT_LABEL = "Tài liệu (không phải văn bản pháp luật)"
"""Nhãn nguồn của kho cũ sau khi đồng bộ: kho cũ chỉ còn tài liệu thường, văn bản pháp luật ở kho có phiên bản."""


def legacy_documents(docs, legacy: Mapping[str, LegacyLaw]) -> list:
    """Tài liệu thường của kho cũ: bỏ các bộ luật trong legacy_map (đã chuyển sang kho có phiên bản)."""
    return [d for d in docs if d.source not in legacy]


def document_search(retriever, legacy: Mapping[str, LegacyLaw]):
    """Tìm trong kho cũ nhưng chỉ trả tài liệu thường (bỏ chunk của các bộ luật trong legacy_map).
    `retriever` có .retrieve(query, k) -> kết quả có .hits và .chunks (id -> Chunk)."""

    def search(query: str, k: int) -> list:
        if k < 1:
            return []
        result = retriever.retrieve(query, k * 3)
        chunks = retriever.chunks
        out = [chunks[h.chunk_id] for h in result.hits if h.chunk_id in chunks]
        return [c for c in out if c.source not in legacy][:k]

    return search


def legacy_duplicates(store: LegalStore, legacy: Mapping[str, LegacyLaw]) -> set[str]:
    known = {_identity(d.doc_type, d.doc_number, d.issuer) for d in store.documents() if not d.is_consolidated}
    return {src for src, law in legacy.items() if _identity(law.doc_type, law.doc_number, law.issuer) in known}


def legacy_status(store: LegalStore, law: LegacyLaw | None, *, start: date, end: date) -> DocumentStatus:
    if law is None:
        return "unknown"
    number = normalize_number(law.doc_number)
    same = [d for d in store.documents() if not d.is_consolidated and normalize_number(d.doc_number) == number
            and d.doc_type.casefold() == law.doc_type.casefold()]
    for d in same:
        versions = store.versions(d.document_key)
        if versions and not any(v.valid_from <= end and (v.valid_to is None or v.valid_to > start) for v in versions):
            return "outdated"
    for o in store.operations():
        if (o.operation_type == "REPEAL_DOCUMENT" and o.review_status in ("auto_accepted", "approved")
                and o.effective_from and o.effective_from <= start
                and any(o.target_document_key == d.document_key for d in same)):
            return "outdated"
    return "unversioned"


def versioned_status(versions_at: Sequence[ProvisionVersion]) -> DocumentStatus:
    if not versions_at:
        return "outdated"
    if all("effectivity.unresolved" in v.status_reasons for v in versions_at):
        return "unknown"
    if all(v.verification_status == "verified" for v in versions_at):
        return "verified"
    return "partially_verified"


_EFFECT_TITLE = re.compile(r"hiệu\s+lực|thi\s+hành|chuyển\s+tiếp", re.IGNORECASE)


def is_amendment_only(provisions: Sequence[Provision]) -> bool:
    """Mọi Điều đều là chỉ dẫn sửa đổi (tiêu đề hành động/bị động) hoặc Điều hiệu lực / thi hành / chuyển tiếp."""
    titles = [p.text for p in provisions if p.kind == "article_title"]
    if not titles:
        return False
    directive = [t for t in titles if _ACTION_START.match(t) or _PASSIVE.match(t)]
    return bool(directive) and all(t in directive or _EFFECT_TITLE.search(t) for t in titles)


__all__ = ["DOCUMENT_LABEL", "DocumentStatus", "LegacyLaw", "document_search", "legacy_documents", "is_amendment_only", "legacy_duplicates", "legacy_status",
           "load_legacy_map", "versioned_status"]
