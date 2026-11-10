"""Tự tìm và tự thêm văn bản liên quan tới các luật gốc (seed): văn bản sửa đổi, luật bị thay thế / luật
thay thế, VBHN. API công khai không có lược đồ quan hệ, nên: tìm ứng viên theo tiêu đề -> tải -> **xác nhận
bằng nội dung** -> mới thêm. Ứng viên không xác nhận được chỉ ghi vào báo cáo.
"""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from rag.legal.crawl import _type_name, fetch_document, save_detail
from rag.legal.directives import _target_law, parse_directives
from rag.legal.effectivity import parse_effectivity
from rag.legal.keys import document_key, normalize_number
from rag.legal.models import DocumentRelation, LegalDocument
from rag.legal.store import LegalStore
from rag.legal.structure import parse_structure
from rag.legal.targets import law_name
from rag.legal.vbhn import parse_consolidation_header


_LAW_MAKERS = ("luật", "bộ luật", "nghị quyết")
_LAW_TYPES = ("Luật", "Bộ luật", "Nghị quyết")


@dataclass(frozen=True)
class Seed:
    doc_type: str
    doc_number: str


@dataclass
class DiscoveryReport:
    added: list[tuple[str, str, str]] = field(default_factory=list)      # (document_key, relation, evidence)
    rejected: list[tuple[str, str]] = field(default_factory=list)        # (tiêu đề ứng viên, lý do)
    suspicious: list[str] = field(default_factory=list)


def load_seeds(path: Path) -> list[Seed]:
    import yaml

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return [Seed(str(x["type"]), str(x["number"])) for x in data.get("laws", [])]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _display_name(title: str) -> str:
    return re.split(r"\s+số\s+", title, maxsplit=1)[0].strip()


def _day(value: Any) -> date | None:
    return date.fromisoformat(str(value)[:10]) if value else None


def _classify(item: dict, base: LegalDocument) -> str | None:
    number = normalize_number(item.get("docNum") or "")
    title = item.get("title") or ""
    if "VBHN" in number or "hợp nhất" in _type_name(item.get("docType")).casefold():
        return "HOP_NHAT"
    if "sửa đổi" in title.casefold():
        return "SUA_DOI_BO_SUNG"
    if law_name(title) == law_name(base.title) and _type_name(item.get("docType")).casefold() in ("luật", "bộ luật"):
        return "THAY_THE"
    return None


def _confirm(relation: str, text: str, key: str, title: str, base: LegalDocument) -> str | None:
    """Bằng chứng câu chữ nếu nội dung xác nhận quan hệ, None nếu không."""
    provisions = parse_structure(text, key)
    if relation == "SUA_DOI_BO_SUNG":
        default = _target_law(title)
        for d in parse_directives(provisions, default_target=default):
            by_number = d.target_law_number and normalize_number(d.target_law_number) == base.doc_number
            by_name = d.target_law_name and law_name(d.target_law_name) == law_name(base.title) \
                and (d.target_law_number is None or by_number)
            if by_number or by_name:
                return f"{d.source_locator}: {d.operation_type}"
        return None
    if relation == "THAY_THE":
        for rep in parse_effectivity(provisions).repeals:
            if rep.target_number and normalize_number(rep.target_number) == base.doc_number:
                return f"hết hiệu lực: {rep.target_name} số {rep.target_number}"
        return None
    if relation == "HOP_NHAT":
        info = parse_consolidation_header(text)
        if info.target_number and normalize_number(info.target_number) == base.doc_number:
            return f"hợp nhất {info.target_name} số {info.target_number}"
    return None


def discover(client: Any, store: LegalStore, seeds: Sequence[Seed], raw_dir: Path, *, max_depth: int = 2,
             max_pages: int = 3, page_size: int = 50, now: Callable[[], datetime] = _now) -> DiscoveryReport:
    report = DiscoveryReport()
    queue: deque[tuple[str, int]] = deque()
    texts: dict[str, str] = {}

    def remember(doc: LegalDocument, text: str) -> None:
        store.upsert_document(doc)
        texts[doc.document_key] = text

    def text_of(doc: LegalDocument) -> str:
        if doc.document_key not in texts:
            texts[doc.document_key] = Path(doc.raw_text_path).read_text(encoding="utf-8")
        return texts[doc.document_key]

    for seed in seeds:
        key = document_key(seed.doc_type, seed.doc_number)
        existing = store.document(key)
        if existing is None:
            got = fetch_document(client, seed.doc_type, seed.doc_number, raw_dir, now=now, discovered_via="seed")
            if got is None:
                report.rejected.append((f"{seed.doc_type} {seed.doc_number}", "discovery.seed_not_found"))
                continue
            remember(*got)
        queue.append((key, 0))

    def fetch_amender(number: str, target: LegalDocument, *, via: str) -> None:
        """Số hiệu có thể trùng giữa Luật và Nghị quyết (Luật Sĩ quan vs Nghị quyết 19/2008/QH12): thử từng loại tới
        khi nội dung xác nhận có chỉ dẫn nhắm vào luật đích."""
        seen_titles = []
        for kind in _LAW_TYPES:
            doc = store.document(document_key(kind, number))
            fetched = False
            if doc is None:
                got = fetch_document(client, kind, number, raw_dir, now=now,
                                     discovered_via=f"{via} | đã được sửa đổi theo | {target.document_key}")
                if got is None:
                    continue
                (doc, text), fetched = got, True
            else:
                text = text_of(doc)
            evidence = _confirm("SUA_DOI_BO_SUNG", text, doc.document_key, doc.title, target)
            if evidence is None:
                if fetched:
                    Path(doc.raw_text_path).unlink(missing_ok=True)
                seen_titles.append(doc.title)
                continue
            if fetched:
                remember(replace(doc, discovered_via=f"{via} | đã được sửa đổi theo | {evidence}"), text)
            store.add_relation(DocumentRelation(doc.document_key, target.document_key, "SUA_DOI_BO_SUNG", evidence,
                                                "confirmed"))
            report.added.append((doc.document_key, "SUA_DOI_BO_SUNG", evidence))
            return
        if seen_titles:
            report.rejected += [(t, "discovery.amender_without_directives") for t in seen_titles]
        else:
            report.rejected.append((f"Văn bản số {number}", "discovery.not_found"))

    seen: set[str] = set()
    while queue:
        key, depth = queue.popleft()
        if key in seen:
            continue
        seen.add(key)
        base = store.document(key)
        if base is None or base.is_consolidated:
            continue

        # luật cũ bị chính văn bản này thay thế (đọc Điều hiệu lực)
        if depth < max_depth:
            for rep in parse_effectivity(parse_structure(text_of(base), key)).repeals:
                if not rep.target_number:
                    continue
                kind = "Bộ luật" if rep.target_name.casefold().startswith("bộ luật") else "Luật"
                old_key = document_key(kind, rep.target_number)
                if store.document(old_key) is None:
                    got = fetch_document(client, kind, rep.target_number, raw_dir, now=now,
                                         discovered_via=f"{key} | Điều hiệu lực | hết hiệu lực")
                    if got is None:
                        report.rejected.append((f"{rep.target_name} số {rep.target_number}", "discovery.not_found"))
                        continue
                    remember(*got)
                relation = "BAI_BO" if rep.units else "THAY_THE"     # bãi bỏ một phần ≠ thay thế cả luật
                evidence = f"hết hiệu lực: {rep.target_name} số {rep.target_number}"
                store.add_relation(DocumentRelation(key, old_key, relation, evidence, "confirmed"))
                report.added.append((old_key, relation, evidence))
                queue.append((old_key, depth + 1))
                # "Luật X đã được sửa đổi, bổ sung theo Luật số A, B ...": tải A, B — kể cả khi sửa đổi nằm trong
                # một luật khác (vd. Luật Đầu tư 2020 sửa Luật Nhà ở ở các Điều cuối) mà tìm theo tiêu đề không ra
                old_doc = store.document(old_key)
                for number in rep.amended_by:
                    fetch_amender(number, old_doc, via=key)

        # ứng viên theo tiêu đề: tìm theo tên và theo số hiệu
        candidates: dict[str, dict] = {}
        for keyword in dict.fromkeys([_display_name(base.title), base.doc_number]):
            for page in range(1, max_pages + 1):
                items = client.list_page(page, page_size, keyword=keyword).get("items") or []
                for item in items:
                    candidates.setdefault(str(item.get("id")), item)
                if len(items) < page_size:
                    break
        for item in candidates.values():
            number = normalize_number(item.get("docNum") or "")
            title = item.get("title") or ""
            issued = _day(item.get("issueDate"))
            if number == base.doc_number or (issued and base.issued_on and issued <= base.issued_on):
                continue
            if law_name(base.title) not in title.casefold() and base.doc_number not in normalize_number(title):
                continue
            relation = _classify(item, base)
            if relation is None:
                continue
            doc_type = _type_name(item.get("docType")).casefold()
            if relation == "HOP_NHAT" and "VBHN-VPQH" not in number:
                continue                     # VBHN của luật do Văn phòng Quốc hội ban hành; VBHN-Bộ là văn bản dưới luật
            if relation != "HOP_NHAT" and doc_type not in _LAW_MAKERS:
                report.rejected.append((title, "discovery.subordinate_document"))
                continue                     # chỉ Luật/Bộ luật/Nghị quyết của Quốc hội sửa đổi, thay thế được luật
            cand_key = document_key(_type_name(item.get("docType")) or "Văn bản", number)
            if store.document(cand_key) is not None:
                cand = store.document(cand_key)
                evidence = _confirm(relation, text_of(cand), cand_key, cand.title, base)
                if evidence and not any(r.source_key == cand_key and r.target_key == key for r in store.relations(key)):
                    store.add_relation(DocumentRelation(cand_key, key, relation, evidence, "confirmed"))
                continue
            got = save_detail(client.detail(str(item.get("id"))), raw_dir, now=now,
                              discovered_via=f"{key} | keyword | {relation}")
            if got is None:
                report.rejected.append((title, "discovery.no_content"))
                continue
            doc, text = got
            evidence = _confirm(relation, text, doc.document_key, doc.title, base)
            if evidence is None:
                Path(doc.raw_text_path).unlink(missing_ok=True)
                report.rejected.append((title, "discovery.not_confirmed_by_content"))
                continue
            doc = replace(doc, discovered_via=f"{key} | {relation} | {evidence}")
            remember(doc, text)
            store.add_relation(DocumentRelation(doc.document_key, key, relation, evidence, "confirmed"))
            report.added.append((doc.document_key, relation, evidence))
            if relation == "SUA_DOI_BO_SUNG" and depth + 1 < max_depth:
                queue.append((doc.document_key, depth + 1))
            elif relation == "THAY_THE":
                queue.append((doc.document_key, depth))

    for doc in store.documents():
        if doc.eff_status and "một phần" in doc.eff_status.casefold() and not doc.is_consolidated:
            if not any(r.relation == "SUA_DOI_BO_SUNG" and r.target_key == doc.document_key
                       for r in store.relations(doc.document_key)):
                report.suspicious.append(doc.document_key)
    return report


__all__ = ["DiscoveryReport", "Seed", "discover", "load_seeds"]
