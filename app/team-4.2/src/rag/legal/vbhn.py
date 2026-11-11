"""Đối chiếu bản dựng với Văn bản hợp nhất (VBHN). VBHN chỉ dùng để kiểm tra, không làm nguồn dựng.

Phần đầu VBHN nêu luật được hợp nhất và các văn bản sửa đổi kèm ngày hiệu lực; thời điểm hợp nhất (cutoff)
= ngày hiệu lực muộn nhất trong số đó. Bản dựng tại cutoff được so từng Điều sau chuẩn hoá.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from rag.legal.effectivity import parse_vn_date
from rag.legal.models import ProvisionVersion
from rag.legal.structure import ARTICLE_RE, parse_structure

_NUMBER = r"(\d+/\d{4}/[A-Z0-9Đ]+)"
_TARGET = re.compile(r"((?:Bộ\s+luật|Luật)\s+(?!số\b)[^,\n]+?)\s+số\s+" + _NUMBER)
_INCLUDED = re.compile(r"(?:Bộ\s+luật|Luật|Nghị\s+quyết)\s+số\s+" + _NUMBER)
_EFFECTIVE = re.compile(r"có\s+hiệu\s+lực(?:\s+thi\s+hành)?(?:\s+kể)?\s+từ\s+(?:ngày\s+)?"
                        r"(ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4}|\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{4})", re.IGNORECASE)
_EXCERPT = 200


@dataclass(frozen=True)
class ConsolidationInfo:
    target_name: str | None
    target_number: str | None
    included: tuple[tuple[str, date | None], ...]
    cutoff: date | None


@dataclass(frozen=True)
class VbhnMismatch:
    article: str
    reason: str
    built_excerpt: str
    vbhn_excerpt: str


def _split_header(text: str) -> tuple[str, str]:
    lines = text.split("\n")
    idx = next((i for i, l in enumerate(lines) if ARTICLE_RE.match(l.strip())), len(lines))
    return "\n".join(lines[:idx]), "\n".join(lines[idx:])


def parse_consolidation_header(text: str) -> ConsolidationInfo:
    header, _ = _split_header(unicodedata.normalize("NFC", text))
    m = _TARGET.search(header)
    name, number = (re.sub(r"\s+", " ", m.group(1)).strip(), m.group(2)) if m else (None, None)
    hits = [h for h in _INCLUDED.finditer(header) if h.group(1) != number]
    included = []
    for i, h in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(header)
        e = _EFFECTIVE.search(header, h.end(), end)
        included.append((h.group(1), parse_vn_date(e.group(1)) if e else None))
    dates = [d for _, d in included if d is not None]
    return ConsolidationInfo(name, number, tuple(included), max(dates) if dates else None)


def normalize_for_compare(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    lines = [l for l in text.split("\n") if not re.match(r"^\s*\[\d+\]", l)]
    text = re.sub(r"\[\d+\]", "", "\n".join(lines))
    text = text.replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().casefold()


def _excerpt(a: str, b: str) -> tuple[str, str]:
    i = next((k for k, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    lo = max(0, i - _EXCERPT // 2)
    return a[lo:lo + _EXCERPT], b[lo:lo + _EXCERPT]


def compare_with_vbhn(built_as_of: Sequence[ProvisionVersion], vbhn_text: str) -> list[VbhnMismatch]:
    _, body = _split_header(unicodedata.normalize("NFC", vbhn_text))
    vbhn = {p.address.article: normalize_for_compare(p.text)
            for p in parse_structure(body, "vbhn:compare") if p.kind == "article"}
    built = {v.provision_id.partition("#d")[2]: normalize_for_compare(v.text)
             for v in built_as_of if v.kind == "article"}
    out = []
    for art in sorted(set(vbhn) | set(built), key=lambda a: (int(re.match(r"\d+", a).group()), a)):
        if art not in built:
            out.append(VbhnMismatch(art, "vbhn.missing_in_build", "", vbhn[art][:_EXCERPT]))
        elif art not in vbhn:
            out.append(VbhnMismatch(art, "vbhn.missing_in_vbhn", built[art][:_EXCERPT], ""))
        elif built[art] != vbhn[art]:
            a, b = _excerpt(built[art], vbhn[art])
            out.append(VbhnMismatch(art, "vbhn.text_differs", a, b))
    return out


__all__ = ["ConsolidationInfo", "VbhnMismatch", "compare_with_vbhn", "normalize_for_compare",
           "parse_consolidation_header"]
