"""Căn cứ luật cho hợp đồng theo mốc (ngày ký): kho có phiên bản (lọc hiệu lực tại mốc) + kho cũ (tham khảo,
chưa xác định phiên bản); và so phiên bản tại ngày ký với hiện hành."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from rag.temporal.transitions import _transition_articles

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

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "LawEvidence":
        return cls(d["eid"], d["store"], d["source_title"], d["section"], d["text"],
                   date.fromisoformat(d["valid_from"]) if d.get("valid_from") else None,
                   date.fromisoformat(d["valid_to"]) if d.get("valid_to") else None,
                   d["status"], d.get("document_key"), d.get("article_id"))


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
            out.append(LawEvidence(_eid(vc.chunk_id), "versioned", titles[vc.document_key], vc.section, vc.text,
                                   vc.valid_from, vc.valid_to, vc.verification_status, vc.document_key, vc.article_id))
    if legacy_search is not None:
        for c in legacy_search(query, k)[:k]:
            out.append(LawEvidence(_eid(c.chunk_id), "legacy", c.source, c.section or "", c.text, None, None,
                                   "unversioned", None, None))
    seen, unique = set(), []
    for e in out:
        if e.eid not in seen:
            seen.add(e.eid)
            unique.append(e)
    return unique


def _current(history, day: date):
    return next((v for v in history if v.valid_from <= day and (v.valid_to is None or v.valid_to > day)), None)


def law_changes(runtime, evidence: list[LawEvidence], today: date) -> list[dict[str, Any]]:
    """Mỗi căn cứ: unchanged | changed | repealed (+ luật thay thế, ngày, Điều chuyển tiếp) | untracked (kho cũ)."""
    rows: list[dict[str, Any]] = []
    for e in evidence:
        row: dict[str, Any] = {"eid": e.eid, "source_title": e.source_title, "section": e.section,
                               "at_signing": e.text, "store": e.store}
        if e.store != "versioned" or runtime is None:
            rows.append({**row, "status": "untracked"})
            continue
        store = runtime.service.store
        in_force = {d.document_key for d in store.laws_in_force(today)}
        if e.document_key not in in_force:
            repeal = next((o for o in store.operations(target_key=e.document_key)
                           if o.operation_type == "REPEAL_DOCUMENT" and o.review_status != "rejected"), None)
            replaced = None
            if repeal is not None:
                doc = store.document(repeal.source_document_key)
                replaced = {"document_key": repeal.source_document_key,
                            "title": doc.title if doc else repeal.source_document_key}
            transitions = []
            if replaced:
                try:
                    transitions = [{"article": a, "text": t} for a, t in
                                   _transition_articles(runtime.service, replaced["document_key"])]
                except Exception:  # noqa: BLE001 — thiếu text luật mới: chỉ không liệt kê Điều chuyển tiếp
                    transitions = []
            since = None
            if repeal is not None:
                # "hết hiệu lực kể từ ngày Luật này có hiệu lực": theo Điều hiệu lực ĐÃ SỬA của luật mới (phần 1)
                since = runtime.service.current_effective_from(repeal.source_document_key) or repeal.effective_from
            rows.append({**row, "status": "repealed", "replaced_by": replaced,
                         "replaced_from": since.isoformat() if since else None,
                         "transition_articles": transitions})
            continue
        current = _current(store.provision_history(e.article_id), today) if e.article_id else None
        if current is None or " ".join(current.text.split()) == " ".join(e.text.split()):
            rows.append({**row, "status": "unchanged"})
        else:
            rows.append({**row, "status": "changed", "current": current.text,
                         "current_from": current.valid_from.isoformat()})
    return rows
