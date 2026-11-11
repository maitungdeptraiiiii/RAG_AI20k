"""ParsedDirective + EffectivityInfo -> AmendmentOperation, kèm quy tắc tự xác minh.

AUTO_ACCEPT_RULES — một thao tác được `auto_accepted` khi đủ cả 5 điều kiện:
  1. parse_status == "exact"
  2. có effective_from (và Điều hiệu lực không có flag chưa hỗ trợ)
  3. luật đích phân giải được
  4. đơn vị đích tồn tại (REPLACE_*/DELETE_*/REPLACE_TEXT); với INSERT_*: neo tồn tại và đơn vị mới chưa có
  5. nhãn khớp: new_text bắt đầu bằng đúng nhãn đơn vị ("3. ", "e) ", "Điều 55."); REPLACE_TEXT: cụm từ cũ
     xuất hiện đúng một lần trong đơn vị đích
Không đủ -> `pending` với lý do. UNSUPPORTED / partial / failed luôn `pending`.
Reason dạng `note:*` không ảnh hưởng xác minh (builder chuyển thành notes).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence

from rag.legal.directives import ParsedDirective
from rag.legal.effectivity import EffectivityInfo, effective_date_for
from rag.legal.keys import provision_id
from rag.legal.models import Address, AmendmentOperation, LegalDocument, Provision
from rag.legal.targets import locate, resolve_target_law

AUTO_ACCEPT_RULES = __doc__


def operation_id_for(source_key: str, sequence: int, operation_type: str, target: Address | None) -> str:
    raw = f"{source_key}|{sequence}|{operation_type}|{target!r}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _label_ok(op_type: str, target: Address, new_text: str | None) -> bool:
    if op_type == "REPLACE_ARTICLE_TITLE":
        return bool(new_text and new_text.strip())
    if new_text is None:
        return False
    text = new_text.lstrip()
    if op_type in ("REPLACE_ARTICLE", "INSERT_ARTICLE"):
        return re.match(rf"Điều\s+{re.escape(target.article)}\s*[.:]", text) is not None
    if op_type in ("REPLACE_CLAUSE", "INSERT_CLAUSE", "REPLACE_CLAUSE_LEAD_IN"):
        return text.startswith(f"{target.clause}. ")
    if op_type in ("REPLACE_POINT", "INSERT_POINT"):
        return text.startswith(f"{target.point}) ")
    return True


def _created_by(ops: Sequence[AmendmentOperation]) -> set[str]:
    out = set()
    for o in ops:
        if o.operation_type.startswith("INSERT_") and o.target is not None and o.target_document_key:
            kind = {"INSERT_ARTICLE": "article", "INSERT_CLAUSE": "clause", "INSERT_POINT": "point"}[o.operation_type]
            out.add(provision_id(o.target_document_key, o.target, kind))  # type: ignore[arg-type]
    return out


def _exists(index: Mapping[str, Provision], created: set[str], key: str, address: Address) -> bool:
    if locate(index, key, address) is not None:
        return True
    kind = "point" if address.point else "clause" if address.clause else "article"
    return address.part == "whole" and provision_id(key, address, kind) in created  # type: ignore[arg-type]


def build_operations(source: LegalDocument, directives: Sequence[ParsedDirective], effectivity: EffectivityInfo, *,
                     documents: Sequence[LegalDocument], indexes: Mapping[str, Mapping[str, Provision]],
                     prior_operations: Sequence[AmendmentOperation] = ()) -> list[AmendmentOperation]:
    created = _created_by(prior_operations)
    notes = (f"note:transition:{source.document_key}#d{effectivity.transition_article}",) \
        if effectivity.transition_article else ()
    out = []
    for d in directives:
        reasons = list(d.reasons)
        key, law_reasons = resolve_target_law(d.target_law_name, d.target_law_number, before=source.issued_on,
                                              documents=documents)
        reasons += law_reasons
        effective = effective_date_for(effectivity, d.source_address)
        reasons += effectivity.flags
        if effective is None and not effectivity.flags:
            reasons.append("operation.no_effective_date")
        index = indexes.get(key) if key else None
        if key and index is None:
            reasons.append("operation.target_law_not_loaded")
        if d.parse_status == "exact" and key and index is not None and d.target is not None:
            t = d.target
            if d.operation_type.startswith("INSERT_"):
                if d.anchor is None or not _exists(index, created, key, d.anchor):
                    reasons.append("operation.anchor_missing")
                if _exists(index, created, key, t):
                    reasons.append("operation.target_exists")
            elif d.operation_type == "REPLACE_ARTICLE_TITLE":
                if not _exists(index, created, key, Address(t.article)):
                    reasons.append("operation.target_missing")
            elif d.operation_type == "REPLACE_CLAUSE_LEAD_IN":
                # khoản không có điểm vẫn có "khổ đầu" (đoạn văn đầu tiên)
                if not _exists(index, created, key, Address(t.article, t.clause)):
                    reasons.append("operation.target_missing")
            elif not _exists(index, created, key, t):
                reasons.append("operation.target_missing")
            if d.operation_type == "REPLACE_TEXT":
                unit = locate(index, key, t)
                if unit is not None and unit.text.count(d.old_phrase or "\0") != 1:
                    reasons.append("operation.phrase_not_unique")
            elif not d.operation_type.startswith("DELETE_") and not _label_ok(d.operation_type, t, d.new_text):
                reasons.append("operation.label_mismatch")
        blocking = [r for r in reasons if not r.startswith("note:")]
        accepted = d.parse_status == "exact" and not blocking and effective is not None
        op = AmendmentOperation(
            operation_id=operation_id_for(source.document_key, d.sequence, d.operation_type, d.target),
            source_document_key=source.document_key, source_issued_on=source.issued_on,
            source_locator=d.source_locator, source_address=d.source_address, source_span=d.source_span,
            sequence=d.sequence, target_document_key=key, target_law_name=d.target_law_name,
            operation_type=d.operation_type, target=d.target, anchor=d.anchor, new_text=d.new_text,
            old_phrase=d.old_phrase, effective_from=effective, parse_status=d.parse_status,
            review_status="auto_accepted" if accepted else "pending",
            status_reasons=tuple(dict.fromkeys([*reasons, *notes])))
        out.append(op)
        if accepted:
            created |= _created_by([op])
    return out


def repeal_operations(source: LegalDocument, effectivity: EffectivityInfo, *,
                      documents: Sequence[LegalDocument]) -> list[AmendmentOperation]:
    """Câu "hết hiệu lực" trong Điều hiệu lực -> REPEAL_DOCUMENT (cả văn bản) hoặc DELETE_* (bãi bỏ một phần,
    luôn chờ duyệt). Luật sửa đổi đã biết ("đã được sửa đổi, bổ sung theo Luật số ...") ghi thành note."""
    out = []
    sequence = 100_000
    for rep in effectivity.repeals:
        key, law_reasons = resolve_target_law(rep.target_name, rep.target_number, before=source.issued_on,
                                              documents=documents)
        base = list(law_reasons)
        if rep.effective is None:
            base.append("operation.no_effective_date")
        if rep.has_exception:
            base.append("note:transition_exception")
        targets = [(_DELETE_KIND[_kind(u)], u) for u in rep.units] if rep.units else [("REPEAL_DOCUMENT", None)]
        for op_type, target in targets:
            reasons = list(base)
            if rep.units:
                reasons.append("operation.partial_repeal")       # bãi bỏ một phần: cần người xác nhận phạm vi
            else:
                reasons += [f"note:amended_by:{n}" for n in rep.amended_by]
            blocking = [r for r in reasons if not r.startswith("note:")]
            out.append(AmendmentOperation(
                operation_id=operation_id_for(source.document_key, sequence, op_type, target),
                source_document_key=source.document_key, source_issued_on=source.issued_on,
                source_locator=f"Điều {effectivity.article}", source_address=Address(effectivity.article or "0"),
                source_span=rep.span, sequence=sequence, target_document_key=key, target_law_name=rep.target_name,
                operation_type=op_type, target=target, anchor=None, new_text=None, old_phrase=None,  # type: ignore[arg-type]
                effective_from=rep.effective, parse_status="exact",
                review_status="pending" if blocking else "auto_accepted", status_reasons=tuple(reasons)))
            sequence += 1
    return out


_DELETE_KIND = {"article": "DELETE_ARTICLE", "clause": "DELETE_CLAUSE", "point": "DELETE_POINT"}


def _kind(address: Address) -> str:
    return "point" if address.point else "clause" if address.clause else "article"


__all__ = ["AUTO_ACCEPT_RULES", "build_operations", "operation_id_for", "repeal_operations"]
