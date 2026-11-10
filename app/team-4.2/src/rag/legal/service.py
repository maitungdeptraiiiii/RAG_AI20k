"""Điều phối kho luật: lập thao tác cho văn bản nguồn, dựng phiên bản từng luật, đối chiếu VBHN, xử lý quyết
định duyệt (approve / reject / correct) rồi dựng lại.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, get_args

from rag.legal.builder import build_versions
from rag.legal.directives import _target_law, parse_directives
from rag.legal.effectivity import parse_effectivity
from rag.legal.models import (Address, AmendmentOperation, BuildRun, LegalDocument, OperationType, Provision,
                              ReviewDecision, ReviewItem)
from rag.legal.operations import _label_ok, build_operations, repeal_operations
from rag.legal.status import _finalize, _flag, demote_amended_directives
from rag.legal.store import LegalStore, encode
from rag.legal.structure import index_provisions, parse_structure
from rag.legal.vbhn import compare_with_vbhn, parse_consolidation_header

CORRECTABLE = {"operation_type", "target", "anchor", "new_text", "old_phrase", "effective_from", "target_document_key"}
_EXCERPT = 1500


def _not_actionable(op: AmendmentOperation) -> str | None:
    """Thao tác được duyệt phải áp dụng được, nếu không phiên bản sẽ `verified` mà thiếu nội dung."""
    if op.operation_type == "UNSUPPORTED":
        return "thao tác chưa hỗ trợ (phụ lục/bảng)"
    if op.target is None and op.operation_type != "REPEAL_DOCUMENT":
        return "chưa xác định đơn vị đích"
    if op.effective_from is None:
        return "chưa có ngày hiệu lực"
    if not op.target_document_key:
        return "chưa xác định luật đích"
    return None


class ReviewClosedError(ValueError):
    """Mục duyệt đã đóng."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sha1(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def _address(value: Any) -> Address | None:
    if value is None or isinstance(value, Address):
        return value
    return Address(str(value["article"]), value.get("clause"), value.get("point"), value.get("part", "whole"))


class LegalService:
    def __init__(self, store: LegalStore, *, now: Callable[[], datetime] = _now, code_version: str = "legal-v1") -> None:
        self.store = store
        self.now = now
        self.code_version = code_version
        self._cache: dict[tuple[str, str], list[Provision]] = {}

    # --- dữ liệu nguồn --------------------------------------------------------------------

    def text_for(self, key: str) -> str:
        doc = self.store.document(key)
        if doc is None:
            raise KeyError(key)
        return Path(doc.raw_text_path).read_text(encoding="utf-8")

    def provisions_for(self, key: str) -> list[Provision]:
        doc = self.store.document(key)
        if doc is None:
            raise KeyError(key)
        cache_key = (key, doc.raw_checksum)
        if cache_key not in self._cache:
            self._cache[cache_key] = parse_structure(self.text_for(key), key)
        return self._cache[cache_key]

    # --- lập thao tác ---------------------------------------------------------------------

    def plan_operations(self, source_key: str) -> list[AmendmentOperation]:
        doc = self.store.document(source_key)
        if doc is None or doc.is_consolidated:
            return []
        provisions = self.provisions_for(source_key)
        effectivity = parse_effectivity(provisions)
        directives = parse_directives(provisions, default_target=_target_law(doc.title))
        documents = self.store.documents()
        indexes = {d.document_key: index_provisions(self.provisions_for(d.document_key))
                   for d in documents if not d.is_consolidated}
        prior = [o for o in self.store.operations() if o.source_document_key != source_key
                 and (o.source_issued_on or date.min) < (doc.issued_on or date.max)]
        ops = build_operations(doc, directives, effectivity, documents=documents, indexes=indexes,
                               prior_operations=prior) + repeal_operations(doc, effectivity, documents=documents)
        retired, human_missing = self.store.refresh_machine_operations(ops, source_key=source_key, now=self.now())
        for op_id in retired:                      # thao tác máy bị loại khi lập lại: mục duyệt của nó cũng đóng
            old_item = self.store.review_item(f"op:{op_id}")
            if old_item is not None and old_item.status == "open":
                self.store.resolve_review(ReviewDecision(old_item.review_id, "approve", "system",
                                                         "thao tác bị thay khi lập lại", {}, self.now()))
        text = self.text_for(source_key)
        for op_id in human_missing:
            stored = self.store.operation(op_id)
            payload = encode(stored)
            payload["source_excerpt"] = text[stored.source_span[0]:stored.source_span[1]][:_EXCERPT]
            self.store.add_review_item(ReviewItem(
                f"op:{op_id}", "operation", stored.target_document_key or source_key, op_id, None,
                ("operation.missing_after_replan",), "open", self.now(), payload), reopen=True)
        for op in ops:
            stored = self.store.operation(op.operation_id)
            if stored is None:
                continue
            item = self.store.review_item(f"op:{stored.operation_id}")
            if stored.review_status != "pending":
                if item is not None and item.status == "open" and stored.reviewer is None:
                    self.store.resolve_review(ReviewDecision(item.review_id, "approve", "system",
                                                             f"đánh giá lại: {stored.review_status}", {}, self.now()))
                continue
            if stored.target_document_key is None and "operation.target_law_not_found" in stored.status_reasons:
                # luật đích ngoài kho: không ảnh hưởng phiên bản nào; mục cũ do hệ thống đóng (mở lại khi luật được thêm)
                if item is not None and item.status == "open":
                    self.store.resolve_review(ReviewDecision(item.review_id, "approve", "system",
                                                             "luật đích ngoài phạm vi kho", {}, self.now()))
                continue
            payload = encode(stored)
            payload["source_excerpt"] = text[stored.source_span[0]:stored.source_span[1]][:_EXCERPT]
            self.store.add_review_item(ReviewItem(
                f"op:{stored.operation_id}", "operation", stored.target_document_key or source_key,
                stored.operation_id, None, tuple(r for r in stored.status_reasons if not r.startswith("note:")),
                "open", self.now(), payload))
        return ops

    # --- dựng ------------------------------------------------------------------------------

    def _ops_for_build(self, key: str) -> tuple[LegalDocument, list[AmendmentOperation]]:
        doc = self.store.document(key)
        if doc is None:
            raise KeyError(key)
        all_ops = self.store.operations()
        directive_articles: dict[str, set[str]] = {}
        for o in all_ops:
            if o.operation_type != "REPEAL_DOCUMENT" and o.source_address is not None:
                directive_articles.setdefault(o.source_document_key, set()).add(o.source_address.article)
        all_ops = demote_amended_directives(all_ops, directive_articles=directive_articles)
        return doc, [self._repeal_on_current_date(o) for o in all_ops if o.target_document_key == key]

    @staticmethod
    def _inputs(doc: LegalDocument, ops: list[AmendmentOperation]) -> str:
        extra = []
        if not doc.source_verified:
            extra.append("src:unverified")
        if doc.metadata_conflicts:
            extra.append("conflicts:" + "|".join(sorted(doc.metadata_conflicts)))
        return _sha1(doc.raw_checksum, *sorted(f"{o.operation_id}:{o.review_status}:{o.effective_from}" for o in ops),
                     *extra)

    def build_inputs(self, key: str) -> str:
        """`inputs_checksum` mà `build_law(key)` sẽ ghi nếu dựng lại ngay bây giờ (không ghi gì vào kho)."""
        return self._inputs(*self._ops_for_build(key))

    def build_law(self, key: str) -> BuildRun:
        doc, ops = self._ops_for_build(key)
        provisions = self.provisions_for(key)
        effectivity = parse_effectivity(provisions)
        for o in ops:
            amended = [r for r in o.status_reasons if r.startswith("operation.source_amended")]
            if amended and o.reviewer is None:
                self.store.add_review_item(ReviewItem(
                    f"op:{o.operation_id}", "operation", key, o.operation_id, None, tuple(amended), "open",
                    self.now(), encode(o)))
        default_dates = {}
        for src in {o.source_document_key for o in ops}:
            if self.store.document(src) is not None:
                day = parse_effectivity(self.provisions_for(src)).default_from
                if day is not None:
                    default_dates[src] = day
        inputs = self._inputs(doc, ops)
        build_id = _sha1(key, inputs)[:16]
        versions = build_versions(doc, provisions, effectivity, ops, build_id=build_id, default_dates=default_dates)
        versions = self._flag_known_gaps(doc, ops, versions)
        if not doc.source_verified:
            versions = _flag(versions, lambda pid: True, None, "source.no_vbpl_metadata")
        if doc.metadata_conflicts:
            versions = _flag(versions, lambda pid: True, None, "source.inherited_metadata_conflict")
        versions = self._check_vbhn(key, versions)
        run = BuildRun(build_id, key, tuple(o.operation_id for o in ops), inputs, self.now(), self.code_version)
        self.store.save_build(run, versions)
        return run

    def _flag_known_gaps(self, doc, ops: list[AmendmentOperation], versions: list) -> list:
        """Gắn cờ khi biết chắc kho đang thiếu dữ liệu, thay vì để phiên bản `verified` sai:
        - luật sửa đổi đã biết (câu "đã được sửa đổi, bổ sung theo Luật số ...") chưa có trong kho hoặc chưa có
          thao tác nào vào luật này -> từ năm ban hành của luật sửa đổi đó;
        - vbpl ghi "hết hiệu lực một phần" mà không có thao tác sửa đổi nào nhắm vào luật này;
        - vbpl ghi hết hiệu lực (effTo / "toàn bộ") mà không có REPEAL áp dụng được."""
        live = [o for o in ops if o.review_status != "rejected"]
        known = {r.split(":", 2)[2] for o in live if o.operation_type == "REPEAL_DOCUMENT"
                 for r in o.status_reasons if r.startswith("note:amended_by:")}
        numbers = {d.doc_number: d.document_key for d in self.store.documents() if not d.is_consolidated}
        for number in sorted(known):
            source = numbers.get(number)
            if source and any(o.source_document_key == source for o in self.store.operations(target_key=doc.document_key)):
                continue
            parts = number.split("/")
            year = int(parts[1]) if len(parts) >= 3 and parts[1].isdigit() else None
            versions = _flag(versions, lambda pid: True, date(year, 1, 1) if year else None,
                             f"operation.missing_amending_law:{number}")
        status = (doc.eff_status or "").casefold()
        if "một phần" in status and not [o for o in live if o.operation_type != "REPEAL_DOCUMENT"]:
            versions = _flag(versions, lambda pid: True, None, "effectivity.vbpl_partial_without_amendments")
        repealed = any(o.operation_type == "REPEAL_DOCUMENT" and o.review_status in ("auto_accepted", "approved")
                       and o.effective_from for o in live)
        if (doc.vbpl_effective_to or "toàn bộ" in status) and not repealed:
            versions = _flag(versions, lambda pid: True, doc.vbpl_effective_to,
                             "effectivity.vbpl_effective_to_without_repeal")
        return versions

    def current_effective_from(self, key: str) -> date | None:
        """Ngày hiệu lực chung của văn bản theo Điều hiệu lực ở bản dựng mới nhất (đã áp sửa đổi), nếu có."""
        effectivity = parse_effectivity(self.provisions_for(key))
        if effectivity.article and self.store.latest_build(key):
            history = self.store.provision_history(f"{key}#d{effectivity.article}")
            if history:
                current = parse_effectivity(parse_structure(history[-1].text, key)).default_from
                if current is not None:
                    return current
        return effectivity.default_from

    def _repeal_on_current_date(self, op: AmendmentOperation) -> AmendmentOperation:
        """"<luật cũ> hết hiệu lực kể từ ngày Luật này có hiệu lực": ngày đó theo Điều hiệu lực đã sửa của luật mới."""
        if op.operation_type != "REPEAL_DOCUMENT" or self.store.document(op.source_document_key) is None:
            return op
        current = self.current_effective_from(op.source_document_key)
        if current is None or current == op.effective_from:
            return op
        return replace(op, effective_from=current,
                       status_reasons=op.status_reasons + ("note:repeal_date_from_amended_effectivity",))

    def _check_vbhn(self, key: str, versions: list) -> list:
        for rel in self.store.relations(key):
            if rel.relation != "HOP_NHAT" or rel.target_key != key or rel.status != "confirmed":
                continue
            text = self.text_for(rel.source_key)
            cutoff = parse_consolidation_header(text).cutoff
            if cutoff is None:
                versions = [replace(v, notes=v.notes + ("note:vbhn_cutoff_unknown",)) for v in versions]
                continue
            as_of = [v for v in versions if v.valid_from <= cutoff and (v.valid_to is None or v.valid_to > cutoff)]
            for m in compare_with_vbhn(as_of, text):
                article = f"{key}#d{m.article}"
                review_id = f"vbhn:{rel.source_key}:{m.article}"
                if self._vbhn_accepted(review_id, m):
                    versions = [replace(v, notes=v.notes + (f"note:vbhn_mismatch_accepted:{review_id}",))
                                if v.provision_id == article else v for v in versions]
                    continue
                versions = _flag(versions, lambda pid, a=article: pid == a or pid.startswith(a + "."), cutoff, m.reason)
                self.store.add_review_item(ReviewItem(
                    review_id, "vbhn_mismatch", key, None, article, (m.reason,), "open",
                    self.now(), {"built_excerpt": m.built_excerpt, "vbhn_excerpt": m.vbhn_excerpt,
                                 "vbhn_key": rel.source_key, "cutoff": cutoff.isoformat()}))
        return [_finalize(v) for v in versions]

    def _vbhn_accepted(self, review_id: str, mismatch) -> bool:
        item = self.store.review_item(review_id)
        if item is None or item.status != "resolved":
            return False
        decisions = [d for d in self.store.decisions(review_id) if d.reviewer != "system"]
        return (bool(decisions) and decisions[-1].action == "approve"
                and item.payload.get("built_excerpt") == mismatch.built_excerpt
                and item.payload.get("vbhn_excerpt") == mismatch.vbhn_excerpt)

    def build_all(self, progress: Callable[[str, int, int], None] | None = None) -> list[BuildRun]:
        docs = sorted((d for d in self.store.documents() if not d.is_consolidated),
                      key=lambda d: (d.issued_on or date.min, d.document_key))
        n = len(docs)
        for i, d in enumerate(docs, 1):
            self.plan_operations(d.document_key)
            if progress:
                progress("plan", i, n)
        # mới trước, cũ sau: ngày "hết hiệu lực" của luật cũ đọc từ bản dựng của luật mới (Điều hiệu lực đã sửa)
        runs = []
        for i, d in enumerate(reversed(docs), 1):
            runs.append(self.build_law(d.document_key))
            if progress:
                progress("build", i, n)
        return runs

    # --- duyệt ----------------------------------------------------------------------------

    def decide(self, decision: ReviewDecision) -> BuildRun | None:
        if not decision.note.strip():
            raise ValueError("Ghi chú quyết định là bắt buộc")
        if not decision.reviewer.strip():
            raise ValueError("Cần tên người duyệt")
        item = self.store.review_item(decision.review_id)
        if item is None:
            raise KeyError(decision.review_id)
        if item.status != "open":
            raise ReviewClosedError("Mục duyệt đã đóng")
        op = self.store.operation(item.operation_id) if item.operation_id else None
        target = item.document_key
        if op is not None:
            target = op.target_document_key or target
            if decision.action == "approve":
                problem = _not_actionable(op)
                if problem:
                    raise ValueError(f"Không thể chấp nhận nguyên trạng: {problem}. Hãy dùng 'Sửa lại' để bổ sung.")
                self.store.set_review(op.operation_id, "approved", decision.reviewer, decision.note, decision.decided_at)
            elif decision.action == "reject":
                self.store.set_review(op.operation_id, "rejected", decision.reviewer, decision.note, decision.decided_at)
            elif decision.action == "correct":
                unknown = set(decision.corrected_fields) - CORRECTABLE
                if unknown or not decision.corrected_fields:
                    raise ValueError(f"Trường không được sửa: {sorted(unknown) or 'không có trường nào'}")
                fields = self._validated_correction(op, decision.corrected_fields)
                new = replace(op, **fields, operation_id=_sha1(op.operation_id, decision.decided_at.isoformat())[:16],
                              review_status="approved", parse_status="exact", status_reasons=(),
                              reviewer=decision.reviewer, review_note=decision.note, reviewed_at=decision.decided_at)
                problem = _not_actionable(new)
                if problem:
                    raise ValueError(f"Bản sửa chưa áp dụng được: {problem}")
                self.store.supersede_operation(op.operation_id, new, decision.reviewer, decision.note, decision.decided_at)
                target = new.target_document_key or target
            else:
                raise ValueError(f"Hành động không hợp lệ: {decision.action}")
        self.store.resolve_review(decision)
        return self.build_law(target) if target and self.store.document(target) else None

    def _validated_correction(self, op: AmendmentOperation, raw: dict[str, Any]) -> dict[str, Any]:
        """Kiểm tra đầy đủ trước khi ghi: một bản sửa hỏng không được làm hỏng kho."""
        fields = dict(raw)
        for name in ("target", "anchor"):
            if name in fields and fields[name] is not None:
                value = fields[name]
                if isinstance(value, dict) and not str(value.get("article") or "").strip():
                    raise ValueError(f"'{name}' phải có số Điều")
                if not isinstance(value, (dict, Address)):
                    raise ValueError(f"'{name}' không hợp lệ")
                fields[name] = _address(value)
        if "effective_from" in fields:
            try:
                fields["effective_from"] = date.fromisoformat(str(fields["effective_from"]))
            except ValueError:
                raise ValueError("'effective_from' phải là ngày dạng YYYY-MM-DD") from None
        if "operation_type" in fields and fields["operation_type"] not in get_args(OperationType):
            raise ValueError(f"Loại thao tác không hợp lệ: {fields['operation_type']}")
        if "target_document_key" in fields and self.store.document(str(fields["target_document_key"] or "")) is None:
            raise ValueError("Luật đích không có trong kho")
        merged = replace(op, **fields)
        if merged.operation_type == "REPLACE_TEXT" and not (merged.old_phrase or "").strip():
            raise ValueError("Thay cụm từ cần 'old_phrase'")
        needs_label = merged.operation_type.startswith(("REPLACE_", "INSERT_")) and merged.operation_type != "REPLACE_TEXT"
        if merged.target is not None and needs_label and not _label_ok(merged.operation_type, merged.target, merged.new_text):
            raise ValueError("Nội dung mới không khớp nhãn đơn vị đích")
        return fields

    def report(self) -> dict[str, Any]:
        ops = Counter((o.parse_status, o.review_status) for o in self.store.operations(include_rejected=True))
        versions = {}
        for d in self.store.documents():
            if not d.is_consolidated and self.store.latest_build(d.document_key):
                versions[d.document_key] = dict(Counter(v.verification_status for v in self.store.versions(d.document_key)))
        return {"operations": dict(ops), "versions": versions, "open_reviews": len(self.store.review_items("open"))}


__all__ = ["CORRECTABLE", "LegalService", "ReviewClosedError"]
