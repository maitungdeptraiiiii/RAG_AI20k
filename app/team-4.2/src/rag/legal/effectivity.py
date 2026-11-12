"""Đọc Điều hiệu lực thi hành của một văn bản: ngày chung, ngoại lệ theo đơn vị, câu "hết hiệu lực",
Điều chuyển tiếp. Không tự tính ngày tương đối/có điều kiện: các trường hợp đó thành `flags`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from rag.legal.directives import _address, _ctx, _groups, _tokens
from rag.legal.models import Address, Provision
from rag.versioning.effectivity_guard import effectivity_reasons_for_text

_DATE_TEXT = r"(?:ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4}|\d{1,2}\s*[/.-]\s*\d{1,2}\s*[/.-]\s*\d{4}|\d{4}-\d{1,2}-\d{1,2})"
_KIND = r"(?:Bộ\s+luật|Luật|Nghị\s+quyết|Pháp\s+lệnh|Nghị\s+định|Thông\s+tư)"   # loại văn bản tự xưng
_DEFAULT = re.compile(
    _KIND + r"\s+này\s+có\s+hiệu\s+lực(?:\s+thi\s+hành)?(?:\s+kể)?\s+từ\s+(?:ngày\s+)?"
    r"(" + _DATE_TEXT + r")", re.IGNORECASE)
_NUMBER = r"\d+/\d{4}/[A-Z0-9Đ]+(?:-[A-Z0-9Đ]+)*"
_IS_SELF = re.compile(_KIND + r"\s+này\s*$", re.IGNORECASE)
_SINCE_THIS_LEAD = re.compile(r"^\s*(?:\d+\.\s*)?kể\s+từ\s+ngày\s+" + _KIND + r"\s+này\s+có\s+hiệu\s+lực(?:\s+thi\s+hành)?\s*,?\s*",
                              re.IGNORECASE)


def _strip_self(subject: str) -> str:
    return re.sub(r"của\s+" + _KIND + r"\s+này\s*$", "", subject.strip(), flags=re.IGNORECASE).strip()


_EVENT_EFFECT = re.compile(r"(?:có\s+hiệu\s+lực(?:\s+thi\s+hành)?|(?:được\s+)?áp\s+dụng)(?:\s+kể)?\s+từ\s+(?:ngày|khi|thời\s+điểm)\s+(?!\d|ngày\s+\d)",
                           re.IGNORECASE)
_UNIT_EFFECT = re.compile(r"(?:có\s+hiệu\s+lực(?:\s+thi\s+hành)?|(?:được\s+)?áp\s+dụng)(?:\s+kể)?\s+từ\s+(?:ngày\s+)?(" + _DATE_TEXT + r")", re.IGNORECASE)
_REPEAL_SENTENCE = re.compile(r"[^.;\n]*?hết\s+hiệu\s+lực[^.;\n]*", re.IGNORECASE)
_REPEAL_TARGET = re.compile(r"(Bộ\s+luật|Luật|Nghị\s+định|Thông\s+tư)(?:\s+([^,;]+?))?\s+số\s+(" + _NUMBER + r")")
_SINCE_THIS = re.compile(r"kể\s+từ\s+ngày\s+" + _KIND + r"\s+này\s+có\s+hiệu\s+lực", re.IGNORECASE)
_SINCE_DATE = re.compile(r"kể\s+từ\s+(?:ngày\s+)?(" + _DATE_TEXT + r")", re.IGNORECASE)
_REPEAL_EXCEPTION = re.compile(r"\b(?:trừ|ngoại\s+trừ)\b|trường\s+hợp\s+quy\s+định\s+tại", re.IGNORECASE)
_LAW_REF = r"(?:Bộ\s+luật|Luật|Nghị\s+quyết|Nghị\s+định|Thông\s+tư)\s+số\s+" + _NUMBER
_AMENDED_BY = re.compile(r"(?:đã\s+)?được\s+sửa\s+đổi(?:\s*,\s*bổ\s+sung)?(?:\s+một\s+số\s+điều)?\s+(?:theo|bởi|tại)\s+"
                         + _LAW_REF + r"(?:\s*(?:,|và)\s*" + _LAW_REF + r")*", re.IGNORECASE)
_LIST_LEAD = re.compile(r"sau\s+đây\s+hết\s+hiệu\s+lực(?:\s+thi\s+hành)?\s*:\s*$", re.IGNORECASE)
_LIST_ITEM = re.compile(r"^[a-zđ]\)\s+")
_PARENTHETICAL = re.compile(r"\(sau\s+đây[^)]*\)", re.IGNORECASE)
_PARTIAL = re.compile(r"(?:điều|khoản|điểm|chương|mục|phần)\s+\S+(?:\s+\S+){0,8}\s+của\s*$", re.IGNORECASE)
_HANDLED = ("effectivity.transition", "effectivity.unit_exception", "effectivity.multiple_dates",
            "effectivity.date_mismatch")


@dataclass(frozen=True)
class RepealStatement:
    target_name: str
    target_number: str | None
    effective: date | None
    has_exception: bool
    span: tuple[int, int]
    units: tuple[Address, ...] = ()          # khác rỗng: chỉ các đơn vị này hết hiệu lực (bãi bỏ một phần)
    amended_by: tuple[str, ...] = ()         # "đã được sửa đổi, bổ sung theo Luật số ..." (luật sửa đổi đã biết)


@dataclass(frozen=True)
class EffectivityInfo:
    article: str | None
    default_from: date | None
    exceptions: tuple[tuple[Address, date], ...]
    repeals: tuple[RepealStatement, ...]
    transition_article: str | None
    flags: tuple[str, ...]
    conditional_units: tuple[Address, ...] = ()     # đơn vị có hiệu lực theo sự kiện, không theo ngày


def parse_vn_date(s: str) -> date | None:
    nums = [int(n) for n in re.findall(r"\d+", s)]
    try:
        if re.fullmatch(r"\s*\d{4}-\d{1,2}-\d{1,2}\s*", s):
            return date(nums[0], nums[1], nums[2])
        if len(nums) == 3:
            return date(nums[2], nums[1], nums[0])
    except ValueError:
        return None
    return None


def _article(provisions: Sequence[Provision], pattern: str) -> Provision | None:
    titles = {p.address.article: p.text for p in provisions if p.kind == "article_title"}
    for p in provisions:
        if p.kind == "article" and re.search(pattern, titles.get(p.address.article, ""), re.IGNORECASE):
            return p
    return None


_EFF_TITLE = r"^\s*(?:hiệu\s+lực(?:\s+thi\s+hành)?|điều\s+khoản\s+thi\s+hành|hiệu\s+lực\s+thi\s+hành\b.*)\s*$"
_SELF_EFFECT = re.compile(_KIND + r"\s+này\s+có\s+hiệu\s+lực", re.IGNORECASE)


def _effectivity_article(provisions: Sequence[Provision]) -> Provision | None:
    """Điều hiệu lực của chính văn bản: Điều có câu "(Bộ) luật này có hiệu lực" (ưu tiên tiêu đề kiểu "Hiệu lực
    thi hành" / "Điều khoản thi hành"); không có câu đó thì theo tiêu đề. Tránh Điều cùng chữ như "Hiệu lực
    nghị quyết của Hội đồng thành viên"."""
    titles = {p.address.article: p.text for p in provisions if p.kind == "article_title"}
    articles = [p for p in provisions if p.kind == "article"]
    titled = [p for p in articles if re.search(_EFF_TITLE, titles.get(p.address.article, ""), re.IGNORECASE)]
    stating = [p for p in articles if _SELF_EFFECT.search(p.text)]
    preferred = [p for p in stating if p in titled]
    if preferred:
        return preferred[-1]
    if stating:
        return stating[-1]
    return titled[-1] if titled else None


def parse_effectivity(provisions: Sequence[Provision]) -> EffectivityInfo:
    eff = _effectivity_article(provisions)
    trans = _article(provisions, r"chuyển\s+tiếp")
    if eff is None:
        return EffectivityInfo(None, None, (), (), trans.address.article if trans else None, ())
    text = eff.text
    m = _DEFAULT.search(text)
    default_from = parse_vn_date(m.group(1)) if m else None

    exceptions = []
    conditional: list[Address] = []
    unresolved = False

    def units_of(subject: str) -> list[Address]:
        out = []
        for targets, quals in _groups(_tokens(subject)):
            ctx = _ctx(quals)
            out += [a for t in targets if (a := _address(t, ctx)) is not None]
        return out

    for sentence in re.split(r"[;\n]|\.(?=\s|$)", text):
        if re.search(r"hết\s+hiệu\s+lực", sentence, re.IGNORECASE) and not _EVENT_EFFECT.search(sentence):
            continue                                   # câu bãi bỏ, xử lý ở dưới
        m = _UNIT_EFFECT.search(sentence)
        if not m:
            ev = _EVENT_EFFECT.search(sentence)
            subject = _strip_self(sentence[:ev.start()]) if ev else ""
            if ev and subject and not _IS_SELF.search(subject):
                conditional += [a for a in units_of(subject) if a not in conditional]
            continue
        day = parse_vn_date(m.group(1))
        subject = _strip_self(sentence[:m.start()])
        if day is None or day == default_from:
            continue
        found = [] if _IS_SELF.search(subject) else units_of(subject)
        if not found:
            unresolved = True                          # có ngày riêng nhưng không xác định được đơn vị nào
        for addr in found:
            if (addr, day) not in exceptions:
                exceptions.append((addr, day))

    repeals = []

    def emit(head: str, where: str, base: int, effective: date | None, has_exc: bool) -> None:
        """Các văn bản đích nêu trong `head` (phần chủ ngữ của câu "hết hiệu lực"); `where` là đoạn chứa chúng,
        bắt đầu tại vị trí `base` trong Điều hiệu lực."""
        amended_by = tuple(n for a in _AMENDED_BY.finditer(head) for n in re.findall(_NUMBER, a.group(0)))
        # bỏ phần bối cảnh: "đã được sửa đổi, bổ sung ... theo Luật số A, Luật số B" và "(sau đây gọi là ...)"
        subject = _PARENTHETICAL.sub(" ", _AMENDED_BY.sub(" ", head))
        prev_end = 0
        for t in _REPEAL_TARGET.finditer(subject):
            name = f"{t.group(1)} {t.group(2)}".strip() if t.group(2) else t.group(1)
            if name.casefold().split()[-1:] == ["này"] or " này " in f" {name.casefold()} ":
                continue
            offset = where.find(t.group(0))
            start = eff.span[0] + base + max(offset, 0)
            units: tuple[Address, ...] = ()
            if _PARTIAL.search(subject[:t.start()]):
                units = tuple(units_of(subject[prev_end:t.start()]))   # "khoản 3 Điều 248 của Luật X": bãi bỏ một phần
                if not units:
                    continue
            repeals.append(RepealStatement(re.sub(r"\s+", " ", name), t.group(3), effective, has_exc,
                                           (start, start + len(t.group(0))), units, () if units else amended_by))
            prev_end = t.end()

    def effective_of(sentence: str) -> date | None:
        if _SINCE_THIS.search(sentence):
            return default_from
        d = _SINCE_DATE.search(sentence)
        return parse_vn_date(d.group(1)) if d else None

    for s in _REPEAL_SENTENCE.finditer(text):
        sentence = s.group(0)
        head = sentence[: re.search(r"hết\s+hiệu\s+lực", sentence, re.IGNORECASE).start()]
        if _LIST_LEAD.search(sentence):
            # "… các Nghị định và các điều khoản sau đây hết hiệu lực thi hành:" + các điểm a), b) … liệt kê văn bản
            pos = s.end()
            for line in text[pos:].split(chr(10)):
                if line.strip() and not _LIST_ITEM.match(line.strip()):
                    break
                if line.strip():
                    item = _LIST_ITEM.sub("", line.strip()).rstrip(".;")
                    emit(item, line, pos, effective_of(sentence), bool(_REPEAL_EXCEPTION.search(line)))
                pos += len(line) + 1
            continue
        head = _SINCE_THIS_LEAD.sub("", head)          # "Kể từ ngày Luật này có hiệu lực thi hành, Luật X ..."
        if _IS_SELF.search(head.strip()) or re.search(r"có\s+hiệu\s+lực", head, re.IGNORECASE):
            continue                                   # chủ ngữ là chính văn bản, hoặc câu hiệu lực theo sự kiện
        emit(head, sentence, s.start(), effective_of(sentence), bool(_REPEAL_EXCEPTION.search(sentence)))

    raw_flags = effectivity_reasons_for_text(text, effective_from=None)
    flags = [f for f in raw_flags if not f.startswith(_HANDLED)]
    if unresolved:
        flags.append("effectivity.unit_exception_unresolved: a date differs from the default but its units are unknown")
    if default_from is None and not flags:
        flags.append("effectivity.no_default_date: effectivity article has no explicit date for this document")
    if conditional and not any(f.startswith("effectivity.conditional") for f in flags):
        flags.append("effectivity.conditional: some units take effect on an event, not a date")
    return EffectivityInfo(eff.address.article, default_from, tuple(exceptions), tuple(repeals),
                           trans.address.article if trans else None, tuple(flags), tuple(conditional))


def effective_date_for(info: EffectivityInfo, address: Address | None) -> date | None:
    if address is not None:
        best, score = None, -1
        for ex, day in info.exceptions:
            if ex.article != address.article:
                continue
            if ex.clause is not None and ex.clause != address.clause:
                continue
            if ex.point is not None and ex.point != address.point:
                continue
            s = (ex.clause is not None) + (ex.point is not None)
            if s > score:
                best, score = day, s
        if best is not None:
            return best
    return info.default_from


__all__ = ["EffectivityInfo", "RepealStatement", "effective_date_for", "parse_effectivity", "parse_vn_date"]
