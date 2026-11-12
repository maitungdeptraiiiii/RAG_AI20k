"""Dẫn chiếu nội bộ của hợp đồng: Điều/khoản/điểm, Phụ lục, văn bản luật bên ngoài."""
from __future__ import annotations

import re

from rag.contracts.doc import CrossRef, PartSpec, Unit, own_texts

_REF_RE = re.compile(
    r"(?=(?i:điểm|khoản)|Điều)(?i:"
    r"(?:điểm\s+(?P<pt>[a-zđ])(?![\wÀ-ỹ])\s*)?"
    r"(?:khoản\s+(?P<kh>\d+[a-z]?)(?![\wÀ-ỹ])\s*)?)"
    r"(?P<dieu>Điều\s+(?:(?P<dn>\d+[a-z]?)(?![\wÀ-ỹ])|(?P<this>này)(?![\wÀ-ỹ])))?"
    r"|(?P<pl>(?i:Phụ lục)\s+(?:(?i:số)\s+)?(?P<pln>\d+)(?!\d))",
)
_EXTERNAL_RE = re.compile(
    r"\s*(?:(?:của|theo|tại)\s+)?(?:Bộ luật|Luật|Nghị định|Thông tư)[^,;.:)\n]*")
_LIST_TAIL_RE = re.compile(
    r"(?P<list>(?:\s*(?:,|và|hoặc|đến|-)\s*(?:(?i:khoản)\s+)?\d+[a-z]?(?![\wÀ-ỹ]))+)"
    r"\s+(?P<dieu>Điều\s+(?:(?P<dn>\d+[a-z]?)(?![\wÀ-ỹ])|(?P<this>này)(?![\wÀ-ỹ])))")
_BARE_NUM_RE = re.compile(r"(?<![\wÀ-ỹ])(?<!khoản )(?<!Khoản )(\d+[a-z]?)(?![\wÀ-ỹ])")
_DIEU_LIST_LAW_RE = re.compile(
    r"(?P<items>Điều\s+\d+[a-z]?(?:\s*(?:,|và|hoặc)\s*Điều\s+\d+[a-z]?)+)"
    r"(?=\s*(?:(?:của|theo|tại)\s+)?(?:Bộ luật|Luật|Nghị định|Thông tư))")
_BASE_CONTRACT_RE = re.compile(r"\s*(?:của\s+Hợp đồng|Hợp đồng\s+(?:gốc|số))")
_LAW_START_RE = re.compile(r"\s*(?:(?:của|theo|tại)\s+)?(?:Bộ luật|Luật|Nghị định|Thông tư)")


def _code(letter: str) -> str:
    return letter.replace("đ", "dd")


def _art_code(num: str) -> str:
    m = re.fullmatch(r"(\d+)([a-z]?)", num)
    return f"{int(m.group(1))}{m.group(2)}" if m else num


def find_xrefs(units: list[Unit], parts: list[PartSpec]) -> list[CrossRef]:
    """Tìm dẫn chiếu trong văn bản riêng của mỗi đơn vị (lá, hoặc đoạn dẫn của đơn vị có con) và phân giải."""
    by_uid = {u.uid: u for u in units}
    own = own_texts(units)
    refs: list[CrossRef] = []
    seen: set[tuple[str, str | None, str]] = set()

    def ancestors(u: Unit) -> list[Unit]:
        chain, cur = [u], u
        while cur.parent_uid and cur.parent_uid in by_uid:
            cur = by_uid[cur.parent_uid]
            chain.append(cur)
        return chain

    def appendix_target(n: int) -> str | None:
        for p in parts:
            if p.number == n:
                top = next((u for u in units if u.part_id == p.part_id
                            and u.level in ("preamble", "article", "paragraph")), None)
                return top.uid if top else None
        return None

    def add(u: Unit, to_uid: str | None, raw: str, kind: str, drop_self: bool = True) -> None:
        if drop_self and to_uid and to_uid in {a.uid for a in ancestors(u)}:
            return
        key = (u.uid, to_uid, raw)
        if key in seen:
            return
        seen.add(key)
        refs.append(CrossRef(u.uid, to_uid, raw, kind))  # type: ignore[arg-type]

    for u in units:
        chain = ancestors(u)
        cur_art = next((a.uid for a in chain if a.level == "article"), None)
        cur_clause = next((a.uid for a in chain if a.level == "clause"), None)
        # đơn vị có con: chỉ quét đoạn dẫn trước con đầu tiên (phần còn lại thuộc các con)
        text = own[u.uid]
        if not text:
            continue
        def emit(pt, kh, dn, this, d_end, raw, own_dieu):
            """Phân giải một mục; d_end là vị trí sau 'Điều N' (nếu có) để xét văn bản luật/Hợp đồng."""
            has_dieu = bool(dn or this)
            if dn and (ext := _EXTERNAL_RE.match(text, d_end)) and _LAW_START_RE.match(text, d_end):
                add(u, None, text[own_dieu:ext.end()].rstrip() if own_dieu is not None else raw,
                    "external_law", drop_self=False)
                return
            if has_dieu and not this:
                pid = "p0" if u.part_id != "p0" and _BASE_CONTRACT_RE.match(text, d_end) else u.part_id
                art = f"{pid}.d{_art_code(dn.lower())}"
            else:
                art = cur_art
            target: str | None = art
            if target is not None and kh:
                target = f"{target}.k{_art_code(kh.lower())}"
            elif pt and not kh and not has_dieu:
                target = cur_clause
            if target is not None and pt:
                target = f"{target}.{_code(pt.lower())}"
            if target is not None and target not in by_uid:
                target = None
            add(u, target, raw, "internal" if target else "missing")

        law_lists = [d for lm in _DIEU_LIST_LAW_RE.finditer(text)
                     for d in list(re.finditer(r"Điều\s+\d+[a-z]?(?![\wÀ-ỹ])", lm.group("items")))[:-1]
                     for d in [(lm.start("items") + d.start(), d.group(0))]]
        skip = {pos for pos, _ in law_lists}
        for pos, raw_d in law_lists:  # "Điều 3, Điều 4 Luật X": Điều đứng trước là văn bản ngoài
            add(u, None, raw_d, "external_law", drop_self=False)
        for m in _REF_RE.finditer(text):
            if m.start("dieu") in skip:
                continue
            if m.group("pl"):
                add(u, appendix_target(int(m.group("pln"))), m.group(0), "appendix")
                continue
            pt, kh, dieu = m.group("pt"), m.group("kh"), m.group("dieu")
            if not (pt or kh or dieu):
                continue
            raw = m.group(0).rstrip()
            if dieu:
                emit(pt, kh, m.group("dn"), m.group("this"), m.end(), raw,
                     m.start("dieu"))
                continue
            tail = _LIST_TAIL_RE.match(text, m.end())
            if kh and tail:  # danh sách "khoản 1, 2 Điều 5": Điều đứng cuối áp dụng cho mọi mục
                dn, this = tail.group("dn"), tail.group("this")
                emit(pt, kh, dn, this, tail.end(), raw, tail.start("dieu"))
                for n in _BARE_NUM_RE.finditer(tail.group("list")):
                    emit(None, n.group(1), dn, this, tail.end(), n.group(1), tail.start("dieu"))
                continue
            emit(pt, kh, None, None, m.end(), raw, None)
    return refs
