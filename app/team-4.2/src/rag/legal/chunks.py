"""Xuất chunk có phiên bản cho retrieval (phần 2): một nhóm chunk cho mỗi phiên bản của một Điều.

Mỗi chunk mang khoảng hiệu lực và trạng thái xác minh của phiên bản Điều; Điều dài tách theo ranh giới dòng,
dòng "Điều N. ..." lặp ở đầu mỗi mảnh.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from rag.legal.keys import parse_provision_id, unit_sort_key
from rag.legal.models import VerificationStatus
from rag.legal.store import LegalStore
from rag.legal.structure import parse_structure


@dataclass(frozen=True)
class VersionedChunk:
    chunk_id: str
    document_key: str
    article_id: str
    section: str
    text: str
    valid_from: date
    valid_to: date | None
    verification_status: VerificationStatus
    status_reasons: tuple[str, ...]
    notes: tuple[str, ...]
    source_operations: tuple[str, ...]
    build_id: str


def _pieces(lines: list[str], limit: int) -> list[list[str]]:
    groups: list[list[str]] = [[]]
    count = 0
    for line in lines:
        words = line.split()
        while len(words) > limit:                       # một dòng quá dài: cắt theo từ
            if groups[-1]:
                groups.append([])
            groups[-1].append(" ".join(words[:limit]))
            groups.append([])
            words, count = words[limit:], 0
        if count + len(words) > limit and groups[-1]:
            groups.append([])
            count = 0
        groups[-1].append(" ".join(words) if words else line)
        count += len(words)
    return [g for g in groups if g] or [[]]


def _headings(store: LegalStore, key: str) -> dict[str, tuple[str, ...]]:
    doc = store.document(key)
    if doc is None or not Path(doc.raw_text_path).exists():
        return {}
    return {p.address.article: p.heading_path
            for p in parse_structure(Path(doc.raw_text_path).read_text(encoding="utf-8"), key) if p.kind == "article"}


def export_chunks(store: LegalStore, document_key: str, *, build_id: str | None = None,
                  max_syllables: int = 300) -> list[VersionedChunk]:
    headings = _headings(store, document_key)
    known = sorted(headings, key=unit_sort_key)
    out: list[VersionedChunk] = []
    for v in store.versions(document_key, build_id=build_id):
        if v.kind != "article":
            continue
        _, address, _ = parse_provision_id(v.provision_id)
        path = headings.get(address.article)
        if path is None:                                 # Điều được bổ sung: lấy heading của Điều đứng trước
            before = [a for a in known if unit_sort_key(a) < unit_sort_key(address.article)]
            path = headings[before[-1]] if before else ()
        lines = v.text.split("\n")
        heading, body = lines[0], lines[1:]
        section = " > ".join((*path, heading))
        for i, group in enumerate(_pieces(body, max_syllables)):
            out.append(VersionedChunk(
                chunk_id=f"{v.build_id}:{v.provision_id}:{v.valid_from.isoformat()}:{i}", document_key=document_key,
                article_id=v.provision_id, section=section, text="\n".join([heading, *group]).strip(),
                valid_from=v.valid_from, valid_to=v.valid_to, verification_status=v.verification_status,
                status_reasons=v.status_reasons, notes=v.notes, source_operations=v.source_operations,
                build_id=v.build_id))
    return out


__all__ = ["VersionedChunk", "export_chunks"]
