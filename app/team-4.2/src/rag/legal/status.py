"""Gắn trạng thái xác minh cho ProvisionVersion (spec 5.6), áp dụng thay thế/hết hiệu lực cả văn bản,
và hạ cấp thao tác của văn bản sửa đổi khi chính chỉ dẫn đó bị sửa.

Thứ tự: hết hiệu lực -> thao tác chờ -> xung đột cùng ngày -> lệch ngày vbpl -> ghi chú -> trạng thái.
`conflicted` thắng `needs_review` thắng `verified`; reason `note:*` chuyển sang `notes`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import date
from itertools import combinations

from rag.legal.models import AmendmentOperation, LegalDocument, ProvisionVersion


def _add(v: ProvisionVersion, reason: str) -> ProvisionVersion:
    return replace(v, status_reasons=v.status_reasons + (reason,))


def _flag(versions: list[ProvisionVersion], match: Callable[[str], bool], start: date | None,
          reason: str) -> list[ProvisionVersion]:
    out = []
    for v in versions:
        if not match(v.provision_id):
            out.append(v)
        elif start is None or v.valid_from >= start:
            out.append(_add(v, reason))
        elif v.valid_to is not None and v.valid_to <= start:
            out.append(v)
        else:
            out.append(replace(v, valid_to=start))
            out.append(_add(replace(v, valid_from=start), reason))
    return out


def apply_repeals(versions: list[ProvisionVersion], operations: Sequence[AmendmentOperation]) -> list[ProvisionVersion]:
    from rag.legal.builder import applicable

    if not versions:
        return versions
    key = versions[0].document_key
    repeals = [o for o in operations if o.operation_type == "REPEAL_DOCUMENT" and o.target_document_key == key
               and applicable(o)]
    if not repeals:
        return versions
    first = min(repeals, key=lambda o: o.effective_from)  # type: ignore[arg-type, return-value]
    day = first.effective_from
    notes = tuple(r for r in first.status_reasons if r.startswith("note:"))
    out = []
    for v in versions:
        if v.valid_from >= day:
            continue
        if v.valid_to is None or v.valid_to > day:
            v = replace(v, valid_to=day)
        if v.valid_to == day:
            v = replace(v, notes=v.notes + notes, source_operations=v.source_operations)
        out.append(v)
    return out


def _finalize(v: ProvisionVersion) -> ProvisionVersion:
    notes = tuple(dict.fromkeys([*v.notes, *(r for r in v.status_reasons if r.startswith("note:"))]))
    reasons = tuple(dict.fromkeys(r for r in v.status_reasons if not r.startswith("note:")))
    status = "conflicted" if any(r.startswith(("operation.conflict", "vbhn.")) for r in reasons) \
        else "needs_review" if reasons else "verified"
    return replace(v, status_reasons=reasons, notes=notes, verification_status=status)


def apply_statuses(versions: list[ProvisionVersion], operations: Sequence[AmendmentOperation], *,
                   default_dates: Mapping[str, date], document: LegalDocument,
                   effectivity_amended: bool) -> list[ProvisionVersion]:
    from rag.legal.builder import applicable, op_base, touches

    key = document.document_key
    ops = [o for o in operations if o.target_document_key == key and o.review_status != "rejected"]
    versions = apply_repeals(list(versions), ops)

    for o in ops:
        if applicable(o):
            continue
        start = o.effective_from or default_dates.get(o.source_document_key)
        failed = any(r.startswith("operation.apply_failed") for r in o.status_reasons)
        reason = f"operation.{'apply_failed' if failed else 'pending'}:{o.operation_id}"
        base = op_base(o)
        if base is not None:
            versions = _flag(versions, lambda pid, b=base: touches(b, pid), start, reason)
        elif o.operation_type == "REPLACE_TEXT" and o.old_phrase:
            phrase = o.old_phrase.casefold()
            hit = {v.provision_id for v in versions if phrase in v.text.casefold()}
            versions = _flag(versions, hit.__contains__, start, reason)
        elif o.parse_status != "unsupported":
            versions = _flag(versions, lambda pid: True, start, reason)

    live = [o for o in ops if applicable(o) and op_base(o) is not None]
    for a, b in combinations(live, 2):
        if a.effective_from != b.effective_from or a.source_document_key == b.source_document_key:
            continue
        ba, bb = op_base(a), op_base(b)
        if not touches(ba, bb):  # type: ignore[arg-type]
            continue
        reason = f"operation.conflict:{a.operation_id},{b.operation_id}"
        versions = [_add(v, reason) if v.valid_from == a.effective_from
                    and (touches(ba, v.provision_id) or touches(bb, v.provision_id)) else v  # type: ignore[arg-type]
                    for v in versions]

    if versions and document.vbpl_effective_from is not None:
        start = min(v.valid_from for v in versions)
        if start != document.vbpl_effective_from:
            reason = "note:vbpl_effective_from_outdated" if effectivity_amended else "effectivity.vbpl_mismatch"
            first = {}
            for v in versions:
                if v.provision_id not in first or v.valid_from < first[v.provision_id]:
                    first[v.provision_id] = v.valid_from
            versions = [_add(v, reason) if first[v.provision_id] == v.valid_from else v for v in versions]

    by_id = {o.operation_id: o for o in operations}
    out = []
    for v in versions:
        extra = tuple(r for oid in v.source_operations if oid in by_id
                      for r in by_id[oid].status_reasons if r.startswith("note:"))
        out.append(_finalize(replace(v, notes=v.notes + extra)))
    return out


def demote_amended_directives(operations: Sequence[AmendmentOperation], *,
                              directive_articles: Mapping[str, set[str]]) -> list[AmendmentOperation]:
    from rag.legal.builder import applicable

    hits: dict[tuple[str, str], str] = {}
    for b in operations:
        if applicable(b) and b.target is not None and b.target_document_key in directive_articles \
                and b.target.article in directive_articles[b.target_document_key]:
            hits.setdefault((b.target_document_key, b.target.article), b.operation_id)
    out = []
    for o in operations:
        hit = hits.get((o.source_document_key, o.source_address.article)) if o.source_address else None
        if hit and o.operation_id != hit and o.review_status != "rejected" and o.reviewer is None:
            o = replace(o, review_status="pending", status_reasons=o.status_reasons + (f"operation.source_amended:{hit}",))
        out.append(o)
    return out


__all__ = ["apply_repeals", "apply_statuses", "demote_amended_directives"]
