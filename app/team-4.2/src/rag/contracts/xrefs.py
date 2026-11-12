"""Dẫn chiếu nội bộ của hợp đồng: Điều/khoản/điểm, Phụ lục, văn bản luật bên ngoài."""
from __future__ import annotations

import re

from rag.contracts.doc import CrossRef, PartSpec, Unit

_REF_RE = re.compile(
    r"(?=điểm|khoản|Điều)(?i:"
    r"(?:điểm\s+(?P<pt>[a-zđ])(?![\wÀ-ỹ])\s*)?"
    r"(?:khoản\s+(?P<kh>\d+[a-z]?)(?![\wÀ-ỹ])\s*)?)"
    r"(?P<dieu>Điều\s+(?:(?P<dn>\d+[a-z]?)(?![\wÀ-ỹ])|(?P<this>này)(?![\wÀ-ỹ])))?"
    r"|(?P<pl>(?i:Phụ lục)\s+(?:(?i:số)\s+)?(?P<pln>\d+)(?!\d))",
)
_EXTERNAL_RE = re.compile(
    r"\s*(?:(?:của|theo|tại)\s+)?(?:Bộ luật|Luật|Nghị định|Thông tư)[^,;.:)\n]*")
_BASE_CONTRACT_RE = re.compile(r"\s*(?:của\s+Hợp đồng|Hợp đồng\s+(?:gốc|số))")
_LAW_START_RE = re.compile(r"\s*(?:(?:của|theo|tại)\s+)?(?:Bộ luật|Luật|Nghị định|Thông tư)")


def _code(letter: str) -> str:
    return letter.replace("đ", "dd")


def _art_code(num: str) -> str:
    m = re.fullmatch(r"(\d+)([a-z]?)", num)
    return f"{int(m.group(1))}{m.group(2)}" if m else num


def find_xrefs(units: list[Unit], parts: list[PartSpec]) -> list[CrossRef]:
    """Tìm dẫn chiếu trong các đơn vị lá và phân giải về mã đơn vị đích."""
    by_uid = {u.uid: u for u in units}
    has_child = {u.parent_uid for u in units if u.parent_uid}
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
        if u.uid in has_child:
            continue
        chain = ancestors(u)
        cur_art = next((a.uid for a in chain if a.level == "article"), None)
        cur_clause = next((a.uid for a in chain if a.level == "clause"), None)
        text = u.text
        for m in _REF_RE.finditer(text):
            if m.group("pl"):
                add(u, appendix_target(int(m.group("pln"))), m.group(0), "appendix")
                continue
            pt, kh, dieu = m.group("pt"), m.group("kh"), m.group("dieu")
            if not (pt or kh or dieu):
                continue
            end = m.end()
            if dieu and m.group("dn") and _EXTERNAL_RE.match(text, end) and _LAW_START_RE.match(text, end):
                ext = _EXTERNAL_RE.match(text, end)
                raw = text[m.start("dieu"):ext.end()].rstrip()
                add(u, None, raw, "external_law", drop_self=False)
                continue
            raw = m.group(0).rstrip()
            if dieu:
                if m.group("this"):
                    art = cur_art
                else:
                    pid = u.part_id
                    if u.part_id != "p0" and _BASE_CONTRACT_RE.match(text, end):
                        pid = "p0"
                    art = f"{pid}.d{_art_code(m.group('dn').lower())}"
            else:
                art = cur_art
            target: str | None = art
            if target is not None and kh:
                target = f"{target}.k{_art_code(kh.lower())}"
            elif pt and not kh and not dieu:
                target = cur_clause
            if target is not None and pt:
                target = f"{target}.{_code(pt.lower())}"
            if target is not None and target not in by_uid:
                target = None
            add(u, target, raw, "internal" if target else "missing")
    return refs
