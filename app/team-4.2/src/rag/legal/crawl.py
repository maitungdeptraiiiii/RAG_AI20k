"""Tải một văn bản từ vbpl.vn (API công khai) thành LegalDocument + text thô đã lưu đĩa."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from rag.ingest.vbpl import metadata_from_detail, pick_detail
from rag.legal.keys import document_key, normalize_number
from rag.legal.models import LegalDocument
from rag.legal.text import html_to_legal_text


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _day(value: str | None) -> date | None:
    return date.fromisoformat(value[:10]) if value else None


def _type_name(value: Any) -> str:
    return (value.get("name") if isinstance(value, dict) else value) or ""


def raw_path_for(raw_dir: Path, key: str) -> Path:
    return Path(raw_dir) / (re.sub(r"[^A-Za-z0-9_-]+", "_", key) + ".txt")


def document_from_detail(detail: dict, raw_path: Path, text: str, *, now: Callable[[], datetime] = _now,
                         discovered_via: str | None = None) -> LegalDocument:
    meta = metadata_from_detail(detail)
    doc_type = meta["doc_type"] or "Văn bản"
    number = meta["doc_number"] or str(detail.get("id"))
    return LegalDocument(
        document_key=document_key(doc_type, number), vbpl_id=meta["vbpl_id"], title=meta["title"] or number,
        doc_type=doc_type, doc_number=normalize_number(number), issuer=meta["agency"],
        issued_on=_day(meta["issue_date"]), vbpl_effective_from=_day(meta["effective_from"]),
        vbpl_effective_to=_day(meta["effective_to"]), eff_status=meta["effective_status"],
        is_consolidated=bool(meta["is_consolidated"]) or "VBHN" in normalize_number(number),
        raw_text_path=str(raw_path), raw_checksum=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        fetched_at=now(), discovered_via=discovered_via)


def save_detail(detail: dict, raw_dir: Path, *, now: Callable[[], datetime] = _now,
                discovered_via: str | None = None) -> tuple[LegalDocument, str] | None:
    text = html_to_legal_text((detail.get("documentContent") or {}).get("content") or "")
    if not text:
        return None
    meta = metadata_from_detail(detail)
    key = document_key(meta["doc_type"] or "Văn bản", meta["doc_number"] or str(detail.get("id")))
    path = raw_path_for(raw_dir, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")
    return document_from_detail(detail, path, text, now=now, discovered_via=discovered_via), text


def fetch_document(client: Any, doc_type: str, doc_number: str, raw_dir: Path, *,
                   now: Callable[[], datetime] = _now, discovered_via: str | None = None) -> tuple[LegalDocument, str] | None:
    """Số hiệu trùng giữa các loại văn bản (Bộ luật 91/2015/QH13 vs Nghị quyết 91/2015/QH13) -> lọc theo loại."""
    items = [i for i in client.search_by_number(doc_number)
             if _type_name(i.get("docType")).casefold() == doc_type.casefold()]
    detail = pick_detail(client, items) if items else None
    if detail is None:
        return None
    return save_detail(detail, raw_dir, now=now, discovered_via=discovered_via)


__all__ = ["document_from_detail", "fetch_document", "raw_path_for", "save_detail"]
