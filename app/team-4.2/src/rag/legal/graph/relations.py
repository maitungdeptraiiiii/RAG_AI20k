"""Quan hệ giữa văn bản suy từ câu chữ: GUIDES (tiêu đề "quy định chi tiết / hướng dẫn thi hành … của <luật>")
và BASED_ON (dòng "Căn cứ <văn bản>" ở phần mở đầu)."""
from __future__ import annotations

import re
import unicodedata

from rag.legal.graph.refs import DocIndex, find_doc_mentions
from rag.legal.models import LegalDocument
from rag.legal.structure import ARTICLE_RE

_GUIDE_CUE = re.compile(r"quy\s+định\s+chi\s+tiết|hướng\s+dẫn", re.IGNORECASE)
_SUBORDINATE = ("nghị định", "thông tư", "quyết định")


def _targets(text: str, doc: LegalDocument, index: DocIndex) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for kind, tail in find_doc_mentions(text):
        if re.match(r"này\b", tail.strip(), re.IGNORECASE):
            continue
        key, _ = index.resolve(kind, tail, doc.issued_on, by_issue=True)
        if key and key != doc.document_key and key not in [k for k, _ in out]:
            out.append((key, re.sub(r"\s+", " ", f"{kind} {tail}")[:160].strip()))
    return out


def doc_relations(doc: LegalDocument, text: str, index: DocIndex) -> list[tuple[str, str, str]]:
    """[(loại quan hệ, document_key đích, bằng chứng câu chữ)] cho một văn bản dưới luật."""
    if unicodedata.normalize("NFC", doc.doc_type).casefold() not in _SUBORDINATE:
        return []
    out: list[tuple[str, str, str]] = []
    title = re.split(r"\s+số\s+\S+\s+", doc.title, maxsplit=1)[-1]      # bỏ "Nghị định số N" ở đầu tiêu đề
    cue = _GUIDE_CUE.search(title)
    if cue:
        out += [("GUIDES", key, f"tiêu đề: {ev}") for key, ev in _targets(title[cue.start():], doc, index)]
    guided = {key for _, key, _ in out}
    for raw in unicodedata.normalize("NFC", text).split("\n"):
        line = raw.strip()
        if ARTICLE_RE.match(line):
            break                                     # hết phần mở đầu
        if re.match(r"Căn\s+cứ\s", line, re.IGNORECASE):
            for key, ev in _targets(line, doc, index):
                if key not in guided and ("BASED_ON", key) not in [(t, k) for t, k, _ in out]:
                    out.append(("BASED_ON", key, f"Căn cứ: {ev}"))
    return out


__all__ = ["doc_relations"]
