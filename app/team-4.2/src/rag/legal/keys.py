"""Khoá văn bản, id điều khoản và thứ tự đơn vị (5 < 5a < 6; a < đ < g < g1)."""

from __future__ import annotations

import re
import unicodedata

from rag.legal.models import Address, ProvisionKind

_TYPE_PREFIX = {"luật": "luat", "bộ luật": "bo-luat", "nghị quyết": "nghi-quyet",
                "văn bản hợp nhất": "vbhn", "nghị định": "nghi-dinh", "thông tư": "thong-tu",
                "pháp lệnh": "phap-lenh", "hiến pháp": "hien-phap"}
_POINT_ORDER = "a b c d đ e g h i k l m n o p q r s t u v x y".split()


def _ascii_slug(value: str) -> str:
    value = unicodedata.normalize("NFD", value.replace("đ", "d").replace("Đ", "D"))
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def normalize_number(doc_number: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", doc_number)).upper()


def document_key(doc_type: str, doc_number: str) -> str:
    number = normalize_number(doc_number)
    kind = unicodedata.normalize("NFC", doc_type).strip().casefold()
    prefix = "vbhn" if "VBHN" in number else _TYPE_PREFIX.get(kind) or _ascii_slug(kind)
    return f"{prefix}:{number}"


def provision_id(document_key: str, address: Address, kind: ProvisionKind) -> str:
    parts = [f"d{address.article}"]
    if address.clause is not None:
        parts.append(f"k{address.clause}")
    if address.point is not None:
        parts.append(address.point)
    if kind == "article_title":
        parts.append("title")
    elif kind == "clause_lead_in":
        parts.append("lead")
    return f"{document_key}#{'.'.join(parts)}"


def parse_provision_id(pid: str) -> tuple[str, Address, ProvisionKind]:
    key, _, path = pid.partition("#")
    parts = path.split(".")
    article = parts[0][1:]
    if parts[-1] == "title":
        return key, Address(article, part="title"), "article_title"
    if parts[-1] == "lead":
        return key, Address(article, parts[1][1:], part="lead_in"), "clause_lead_in"
    if len(parts) == 1:
        return key, Address(article), "article"
    if len(parts) == 2:
        return key, Address(article, parts[1][1:]), "clause"
    return key, Address(article, parts[1][1:], parts[2]), "point"


def unit_sort_key(label: str) -> tuple:
    """Khoá sắp xếp cho nhãn Điều/khoản (số + hậu tố chữ) và điểm (chữ + hậu tố số)."""
    m = re.fullmatch(r"(\d+)([a-zđ]*)", label)
    if m:
        suffix = m.group(2)
        return (0, int(m.group(1)), _POINT_ORDER.index(suffix) + 1 if suffix in _POINT_ORDER else len(suffix))
    m = re.fullmatch(r"([a-zđ])(\d*)", label)
    if m:
        letter = m.group(1)
        return (1, _POINT_ORDER.index(letter) if letter in _POINT_ORDER else 99, int(m.group(2) or 0))
    return (2, 0, 0, label)


__all__ = ["document_key", "normalize_number", "parse_provision_id", "provision_id", "unit_sort_key"]
