"""Dẫn chiếu trong lời văn luật: tìm ("điểm a khoản 1 Điều 35 của Bộ luật Lao động") và giải ra nút đích.

Lời văn luật viết dẫn chiếu theo thể thức cố định nên dùng mẫu, không dùng LLM. Dẫn chiếu không giải được không
tạo cạnh: trả về lý do (`doc_not_in_store`, `provision_not_found`, `ambiguous_law`).
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from rag.legal.keys import normalize_number, provision_id
from rag.legal.models import Address, LegalDocument
from rag.legal.targets import law_name

_NUM = r"\d+[a-zđ]?(?![\d/]|\.\d)"
_NOT_UNIT = r"(?![ \t]*(?:ngày|tháng|năm|giờ|lần|tuổi|người|triệu|tỷ|đồng|phần|%))"
_PT = r"[a-zđ]\d?"
_PTS = rf"{_PT}(?:[ \t]*(?:,|và|hoặc)[ \t]*(?:điểm[ \t]+)?{_PT}(?=[ \t]*(?:,|và|hoặc|khoản)))*"
_CLS = rf"{_NUM}(?:[ \t]*(?:,|và|hoặc)[ \t]*(?:khoản[ \t]+)?{_NUM}{_NOT_UNIT})*"
_ARTS = rf"{_NUM}(?:[ \t]*(?:,|và|hoặc)[ \t]*(?:Điều[ \t]+)?{_NUM}{_NOT_UNIT})*"
_KINDS = r"Bộ[ \t]+luật|Luật|Nghị[ \t]+định|Thông[ \t]+tư|Nghị[ \t]+quyết|Pháp[ \t]+lệnh"
_DOC_NUMBER = r"\d+/\d{4}/[A-ZĐ0-9]+(?:-[A-ZĐ0-9]+)*"

_ADDRESS = re.compile(
    rf"(?<![\w])(?:(?:các[ \t]+)?điểm[ \t]+(?P<pts>{_PTS})[ \t]+)?"
    rf"(?:(?:các[ \t]+)?khoản[ \t]+(?P<cls>{_CLS})[ \t]+)?"
    rf"(?:(?:các[ \t]+)?Điều[ \t]+(?P<arts>{_ARTS})|(?P<this_art>Điều[ \t]+này)|(?P<this_cl>khoản[ \t]+này))",
    re.IGNORECASE)
_DOC_AFTER = re.compile(rf"[ \t]*,?[ \t]*(?:(?:của|tại|theo)[ \t]+)?(?P<kind>{_KINDS})[ \t]+(?P<tail>[^\n]{{0,160}})")
_DOC_MENTION = re.compile(rf"(?<![\w])(?P<kind>{_KINDS})[ \t]+")
_TAIL_NUMBER = re.compile(rf"^(?:[^\n,.;()]{{0,90}}?\s+)?số\s+(?P<number>{_DOC_NUMBER})")
_APPENDIX = re.compile(r"(?<![\w])Phụ\s+lục(?:\s+(?:số\s+)?(?P<number>[IVXLC]+|\d+))?(?=[^\n]{0,60}?kèm\s+theo\s+"
                       rf"(?:{_KINDS})\s+này)", re.IGNORECASE)
_SPLIT = re.compile(r"\s*(?:,|và|hoặc)\s*(?:điểm\s+|khoản\s+|Điều\s+)?", re.IGNORECASE)
_DETAIL_CUE = re.compile(r"quy\s+định\s+chi\s+tiết|hướng\s+dẫn", re.IGNORECASE)


@dataclass(frozen=True)
class Ref:
    raw: str
    offset: int
    addresses: tuple[Address, ...]          # rỗng: dẫn chiếu cả văn bản hoặc phụ lục
    relative: str | None = None             # "article" / "clause": "Điều này" / "khoản này"
    doc_kind: str | None = None             # loại văn bản đích nêu sau địa chỉ
    doc_tail: str = ""                      # phần chữ sau loại văn bản (tên luật / "này" / "số N ...")
    appendix: str | None = None             # số phụ lục ("" nếu không ghi số)


@dataclass(frozen=True)
class Resolved:
    target: str | None                      # node_id đích
    reason: str | None                      # lý do không giải được
    doc_key: str | None = None


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def _labels(group: str | None) -> list[str]:
    return [x.lower() for x in _SPLIT.split(group.strip()) if x] if group else []


def _addresses(m: re.Match) -> tuple[Address, ...]:
    pts, cls, arts = _labels(m.group("pts")), _labels(m.group("cls")), _labels(m.group("arts"))
    if m.group("this_art") or m.group("this_cl"):
        arts = [""]                                   # điền từ địa chỉ nguồn khi giải
    out: list[Address] = []
    first = arts[0]
    if cls:
        if pts:
            out += [Address(first, cls[0], p) for p in pts]
            out += [Address(first, c) for c in cls[1:]]
        else:
            out += [Address(first, c) for c in cls]
        out += [Address(a) for a in arts[1:]]
    elif pts:                                         # "điểm b khoản này"
        out += [Address(first, "", p) for p in pts]
    else:
        out += [Address(a) for a in arts]
    return tuple(out)


def find_refs(text: str) -> list[Ref]:
    """Mọi dẫn chiếu trong `text`, theo thứ tự xuất hiện. Dòng tiêu đề "Điều N. …" không phải dẫn chiếu."""
    text = unicodedata.normalize("NFC", text)
    out: list[Ref] = []
    taken: list[tuple[int, int]] = []
    for m in _ADDRESS.finditer(text):
        bare = not m.group("pts") and not m.group("cls")
        if bare and (m.group("this_art") or m.group("this_cl")):
            continue                                  # "Điều này" đứng riêng: không trỏ đi đâu
        line_start = m.start() == 0 or text[m.start() - 1] == "\n"
        if bare and line_start and text[m.end():m.end() + 1] in (".", ":"):
            continue                                  # tiêu đề Điều
        relative = "article" if m.group("this_art") else "clause" if m.group("this_cl") else None
        kind, tail, end = None, "", m.end()
        if relative is None:
            d = _DOC_AFTER.match(text, m.end())
            if d:
                kind, tail, end = _norm(d.group("kind")), d.group("tail"), d.start("tail")
        out.append(Ref(text[m.start():m.end()], m.start(), _addresses(m), relative, kind, tail))
        taken.append((m.start(), end))
    for kind, tail, start, tail_at in _mentions(text):  # "Nghị định số 122/2020/NĐ-CP" đứng riêng
        number = _TAIL_NUMBER.match(tail)
        if number is None or any(a <= start < b + 1 for a, b in taken):
            continue
        out.append(Ref(text[start:tail_at + number.end()], start, (), None, kind, tail))
    for m in _APPENDIX.finditer(text):
        out.append(Ref(text[m.start():m.end()], m.start(), (), None, None, "", (m.group("number") or "").upper()))
    return sorted(out, key=lambda r: r.offset)


class DocIndex:
    """Tra văn bản theo số hiệu hoặc theo tên luật (họ luật nhiều đời, chọn theo ngày)."""

    def __init__(self, documents: Iterable[LegalDocument]):
        self.docs = [d for d in documents if not d.is_consolidated]
        self.by_number: dict[str, list[LegalDocument]] = {}
        self.families: dict[str, list[LegalDocument]] = {}
        for d in self.docs:
            self.by_number.setdefault(normalize_number(d.doc_number), []).append(d)
            if d.doc_type.casefold() in ("luật", "bộ luật"):
                self.families.setdefault(law_name(d.title), []).append(d)
        self._names = sorted(self.families, key=len, reverse=True)

    @staticmethod
    def _start(d: LegalDocument) -> date:
        return d.vbpl_effective_from or d.issued_on or date.min

    def resolve(self, kind: str, tail: str, day: date | None, *, by_issue: bool = False) -> tuple[str | None, str | None]:
        """(document_key, lý do không giải được). `tail` là phần chữ ngay sau loại văn bản. Tên luật không kèm số
        hiệu: chọn đời luật hiệu lực tại `day`; `by_issue` thì chọn đời ban hành gần nhất tính tới `day` (nghị định
        hướng dẫn được ban hành trước ngày luật có hiệu lực)."""
        number = _TAIL_NUMBER.match(tail)
        if number:
            hits = self.by_number.get(normalize_number(number.group("number")), [])
            typed = [d for d in hits if _norm(d.doc_type).casefold() == kind.casefold()] or hits
            return (typed[0].document_key, None) if len(typed) == 1 else \
                (None, "ambiguous_law" if typed else "doc_not_in_store")
        full = _norm(f"{kind} {tail}").casefold()
        for name in self._names:
            if full.startswith(name) and not full[len(name):len(name) + 1].isalnum():
                family = sorted(self.families[name], key=self._start)
                if day is None:
                    return family[-1].document_key, None
                if by_issue:
                    issued = [d for d in family if (d.issued_on or self._start(d)) <= day]
                    return (max(issued, key=lambda d: d.issued_on or self._start(d)) if issued else family[0]).document_key, None
                started = [d for d in family if self._start(d) <= day]
                live = [d for d in started if d.vbpl_effective_to is None or d.vbpl_effective_to > day]
                if len(live) > 1:
                    live = live[-1:] if len({self._start(d) for d in live}) == len(live) else live
                if len(live) > 1:
                    return None, "ambiguous_law"
                chosen = live[0] if live else (started[-1] if started else family[0])
                return chosen.document_key, None
        return None, "doc_not_in_store"


def resolve(ref: Ref, *, source_key: str, source_address: Address, valid_from: date | None, index: DocIndex,
            provision_ids: set[str] | frozenset[str], appendices: dict[str, dict[str, str]] | None = None,
            guided_key: str | None = None, in_scope_article: bool = False) -> list[Resolved]:
    """Nút đích của từng địa chỉ trong `ref` theo năm quy tắc ở spec §5.2."""
    if ref.appendix is not None:
        mine = (appendices or {}).get(source_key, {})
        target = mine.get(ref.appendix) or (next(iter(mine.values())) if not ref.appendix and len(mine) == 1 else None)
        return [Resolved(target, None if target else "provision_not_found", source_key)]
    if ref.doc_kind and re.match(r"này\b", ref.doc_tail.strip(), re.IGNORECASE):
        key, reason = source_key, None
    elif ref.doc_kind:
        key, reason = index.resolve(ref.doc_kind, ref.doc_tail, valid_from)
    elif ref.relative is None and in_scope_article and guided_key:
        key, reason = guided_key, None
    else:
        key, reason = source_key, None
    if key is None:
        return [Resolved(None, reason)]
    if not ref.addresses:
        return [Resolved(key, None, key)]
    out = []
    for a in ref.addresses:
        article = a.article or source_address.article
        clause = source_address.clause if a.clause == "" else a.clause
        if a.clause == "" and clause is None:
            out.append(Resolved(None, "provision_not_found", key))
            continue
        addr = Address(article, clause, a.point)
        pid = provision_id(key, addr, "point" if a.point else "clause" if clause else "article")
        out.append(Resolved(pid, None, key) if pid in provision_ids else Resolved(None, "provision_not_found", key))
    return out


def ref_kind(ref: Ref, target_doc: str | None, text: str, *, guided_keys: Sequence[str], in_scope_article: bool) -> str:
    """`details`: điều khoản nguồn quy định chi tiết đích (văn bản được hướng dẫn); còn lại `cite`."""
    if target_doc is None or target_doc not in guided_keys:
        return "cite"
    if in_scope_article or _DETAIL_CUE.search(text[max(0, ref.offset - 80):ref.offset]):
        return "details"
    return "cite"


def find_doc_mentions(text: str) -> list[tuple[str, str]]:
    """(loại văn bản, phần chữ theo sau) cho mọi chỗ nhắc tới một văn bản trong `text` (tiêu đề, dòng "Căn cứ")."""
    return [(kind, tail) for kind, tail, _, _ in _mentions(unicodedata.normalize("NFC", text))]


def _mentions(text: str) -> list[tuple[str, str, int, int]]:
    """(loại, phần chữ theo sau tới hết dòng, vị trí bắt đầu, vị trí bắt đầu phần chữ theo sau)."""
    out = []
    for m in _DOC_MENTION.finditer(text):
        tail = text[m.end():m.end() + 200].split(chr(10), 1)[0]
        out.append((_norm(m.group("kind")), tail, m.start(), m.end()))
    return out


__all__ = ["DocIndex", "Ref", "Resolved", "find_doc_mentions", "find_refs", "ref_kind", "resolve"]
