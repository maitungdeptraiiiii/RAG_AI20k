"""Thông tin văn bản tải lên: mỗi trường mang nguồn (vbpl / text / user / inherited)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from rag.ingest.vbpl import metadata_from_detail, pick_detail
from rag.legal.crawl import _type_name
from rag.legal.effectivity import parse_effectivity, parse_vn_date
from rag.legal.models import LegalDocument
from rag.legal.structure import ARTICLE_RE, parse_structure

Source = Literal["vbpl", "text", "user", "inherited"]


@dataclass(frozen=True)
class FieldValue:
    value: Any                   # str | date | None
    source: Source
    at: datetime
    detail: str = ""             # bằng chứng: câu chữ, vbpl_id, tên người nhập, nguồn của bản trước


FIELDS = ("doc_type", "doc_number", "title", "issuer", "issued_on",
          "vbpl_id", "vbpl_effective_from", "vbpl_effective_to", "eff_status")

INHERITABLE = ("vbpl_id", "eff_status", "vbpl_effective_from", "vbpl_effective_to", "issuer")

ACCEPTED_TYPES = ("Luật", "Bộ luật", "Nghị quyết")
REJECT_TYPE_MESSAGE = "Kho luật chỉ nhận Luật / Bộ luật / Nghị quyết / VBHN của VPQH; hãy dùng 'Tài liệu thường'"

_URL = re.compile(r"^https://vbpl\.vn/van-ban/chi-tiet/([^/?#\s]+)(?:[?#].*)?$")
_TYPE_LINE = re.compile(r"^(LUẬT|BỘ\s+LUẬT|NGHỊ\s+QUYẾT|VĂN\s+BẢN\s+HỢP\s+NHẤT)$")
_NUMBER_LINE = re.compile(r"^(?:(?:Bộ\s+luật|Luật|Nghị\s+quyết)\s+)?Số\s*:?\s*(\d+(?:/\d{4})?/[A-Z0-9Đ\-]+(?:/[A-Z0-9Đ\-]+)*)", re.IGNORECASE)
_DATE_LINE = re.compile(r"ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4}", re.IGNORECASE)
_TITLE_END = re.compile(r"^(Căn\s+cứ|Quốc\s+hội\s+ban\s+hành|Theo\s+đề\s+nghị)", re.IGNORECASE)
_ISSUERS = {"QUỐC HỘI": "Quốc hội", "ỦY BAN THƯỜNG VỤ QUỐC HỘI": "Ủy ban Thường vụ Quốc hội",
            "VĂN PHÒNG QUỐC HỘI": "Văn phòng Quốc hội"}


def parse_vbpl_url(url: str) -> str | None:
    m = _URL.match((url or "").strip())
    return m.group(1) if m else None


def _canon_type(raw: str) -> str:
    s = re.sub(r"\s+", " ", raw).strip().casefold()
    return s[:1].upper() + s[1:]


def header_fields(text: str, now: datetime) -> dict[str, FieldValue]:
    lines = [l.strip() for l in unicodedata.normalize("NFC", text).split("\n")]
    idx = next((i for i, l in enumerate(lines) if ARTICLE_RE.match(l)), len(lines))
    head = [l for l in lines[:idx] if l]
    out: dict[str, FieldValue] = {}

    def put(name, value, detail):
        out[name] = FieldValue(value, "text", now, detail)

    for l in head:
        if l.upper() in _ISSUERS:
            put("issuer", _ISSUERS[l.upper()], l)
            break
    for l in head:
        m = _NUMBER_LINE.match(l)
        if m:
            put("doc_number", m.group(1).upper(), l)
            break
    for l in head:
        m = _DATE_LINE.search(l)
        if m and (d := parse_vn_date(m.group(0))):
            put("issued_on", d, l)
            break
    ti = next((i for i, l in enumerate(head) if _TYPE_LINE.match(l.upper())), None)
    if ti is not None:
        put("doc_type", _canon_type(head[ti]), head[ti])
        title = []
        for l in head[ti + 1:]:
            if _TITLE_END.match(l):
                break
            title.append(l)
        if title:
            put("title", " ".join(title), " ".join(title))
    return out


def vbpl_fields(detail: dict, now: datetime) -> dict[str, FieldValue]:
    meta = metadata_from_detail(detail)
    vid = str(detail.get("id")) if detail.get("id") is not None else None

    def d(v):
        return date.fromisoformat(v) if v else None

    raw = {"doc_type": meta["doc_type"], "doc_number": meta["doc_number"], "title": meta["title"],
           "issuer": meta["agency"], "issued_on": d(meta["issue_date"]), "vbpl_id": vid,
           "vbpl_effective_from": d(meta["effective_from"]), "vbpl_effective_to": d(meta["effective_to"]),
           "eff_status": meta["effective_status"]}
    return {k: FieldValue(v, "vbpl", now, f"vbpl_id={vid}") for k, v in raw.items() if v is not None}


def lookup_vbpl(client, doc_type: str, doc_number: str) -> dict | None:
    try:
        items = [i for i in client.search_by_number(doc_number)
                 if _type_name(i.get("docType")).casefold() == doc_type.casefold()]
        return pick_detail(client, items) if items else None
    except Exception:  # mọi lỗi từ client (VbplError, requests.*) -> không tra được
        return None


def merge_fields(*layers: dict[str, FieldValue]) -> dict[str, FieldValue]:
    out: dict[str, FieldValue] = {}
    for layer in layers:
        for k, v in layer.items():
            if v.value is not None or k not in out:
                out[k] = v
    return out


def inherit_fields(new: dict[str, FieldValue], old_doc: LegalDocument, now: datetime) -> dict[str, FieldValue]:
    out = dict(new)
    for name in INHERITABLE:
        if name in out and out[name].value is not None:
            continue
        value = getattr(old_doc, name, None)
        if value is None or value == "":
            continue
        prev = old_doc.field_sources.get(name) or {}
        out[name] = FieldValue(value, "inherited", now,
                               f"bản trước: {prev.get('source', 'vbpl')} {prev.get('at') or old_doc.fetched_at.isoformat()}")
    return out


def _fmt(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def metadata_conflicts(fields: dict[str, FieldValue], text: str, key: str) -> tuple[str, ...]:
    out = []
    eff = fields.get("vbpl_effective_from")
    if eff and eff.source == "inherited" and eff.value is not None:
        read = parse_effectivity(parse_structure(text, key)).default_from
        if read is not None and read != eff.value:
            out.append(f"Ngày hiệu lực kế thừa {_fmt(eff.value)} khác ngày đọc từ điều hiệu lực {_fmt(read)}")
    return tuple(out)


def is_consolidated(doc_type: str | None, doc_number: str | None) -> bool:
    return "VBHN" in (doc_number or "").upper() or "hợp nhất" in (doc_type or "").casefold()


def type_problem(doc_type: str | None, doc_number: str | None) -> str | None:
    t = unicodedata.normalize("NFC", doc_type or "").strip().casefold()
    if t in {a.casefold() for a in ACCEPTED_TYPES}:
        return None
    if is_consolidated(doc_type, doc_number) and "VBHN-VPQH" in (doc_number or "").upper():
        return None
    return REJECT_TYPE_MESSAGE


__all__ = ["ACCEPTED_TYPES", "FIELDS", "FieldValue", "REJECT_TYPE_MESSAGE", "Source", "header_fields",
           "inherit_fields", "is_consolidated", "lookup_vbpl", "merge_fields", "metadata_conflicts",
           "parse_vbpl_url", "type_problem", "vbpl_fields"]
