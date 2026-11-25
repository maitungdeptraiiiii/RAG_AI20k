"""Căn cứ luật cho hợp đồng theo mốc (ngày ký): kho có phiên bản (lọc hiệu lực tại mốc) + kho cũ (tham khảo,
chưa xác định phiên bản)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

LegacySearch = Callable[[str, int], list]


@dataclass(frozen=True)
class LawEvidence:
    eid: str
    store: str                  # "versioned" | "legacy"
    source_title: str
    section: str
    text: str
    valid_from: date | None
    valid_to: date | None
    status: str                 # verified | needs_review | conflicted | unversioned
    document_key: str | None
    article_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return {"eid": self.eid, "store": self.store, "source_title": self.source_title, "section": self.section,
                "text": self.text, "valid_from": self.valid_from.isoformat() if self.valid_from else None,
                "valid_to": self.valid_to.isoformat() if self.valid_to else None, "status": self.status,
                "document_key": self.document_key, "article_id": self.article_id}


def _article(section: str | None) -> str:
    """"Chương I > Chương VIII > Mục 3 > Điều 132. ..." -> "Điều 132. ..." (đường dẫn đầy đủ quá dài để hiển thị)."""
    return (section or "").rsplit(" > ", 1)[-1].strip()


def _eid(*parts: str) -> str:
    return "L" + hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:10]


def find_evidence(runtime, legacy_search: LegacySearch | None, query: str, anchor: date, k: int = 4) -> list[LawEvidence]:
    out: list[LawEvidence] = []
    if runtime is not None:
        store = runtime.service.store
        titles: dict[str, str] = {}
        for vc, _score in runtime.index.search(query, anchor, anchor, k):
            if vc.document_key not in titles:
                doc = store.document(vc.document_key)
                titles[vc.document_key] = doc.title if doc else vc.document_key
            out.append(LawEvidence(_eid(vc.chunk_id), "versioned", titles[vc.document_key], _article(vc.section), vc.text,
                                   vc.valid_from, vc.valid_to, vc.verification_status, vc.document_key, vc.article_id))
    if legacy_search is not None:
        for c in legacy_search(query, k)[:k]:
            out.append(LawEvidence(_eid(c.chunk_id), "legacy", c.source, _article(c.section), c.text, None, None,
                                   "unversioned", None, None))
    # một Điều dài bị chia nhiều chunk: giữ một căn cứ cho mỗi (nguồn, Điều)
    seen, unique = set(), []
    for e in out:
        key = (e.store, e.document_key or e.source_title, e.section or e.eid)
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique
