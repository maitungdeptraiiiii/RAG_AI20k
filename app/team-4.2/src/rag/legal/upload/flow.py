"""Luồng upload 3 bước (spec §4.1–4.3): ① text đúng chưa → ② hệ thống hiểu đúng chưa → ③ vào hàng đợi ghi.

Mọi phương thức kiểm `state` của bản nháp và ném `StepError` khi gọi sai bước; không có đường nào bỏ qua kiểm tra.
`apply_to` chạy bên trong `SnapshotManager.write` (staging): kiểm stale rồi ghi text + văn bản + quan hệ.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

from rag.ingest.loaders import load_source
from rag.ingest.page_report import page_details
from rag.ingest.vbpl import VbplClient
from rag.legal.directives import _target_law, parse_directives
from rag.legal.effectivity import EffectivityInfo, parse_effectivity, parse_vn_date
from rag.legal.keys import document_key, normalize_number
from rag.legal.models import Address, AmendmentOperation, DocumentRelation, LegalDocument
from rag.legal.rawfiles import write_text
from rag.legal.service import LegalService
from rag.legal.snapshots import SnapshotManager
from rag.legal.store import LegalStore, encode
from rag.legal.structure import parse_structure
from rag.legal.targets import resolve_target_law
from rag.legal.text import html_to_legal_text
from rag.legal.upload.diff import diff_articles
from rag.legal.upload.drafts import Draft, DraftStore
from rag.legal.upload.metadata import (FIELDS, FieldValue, header_fields, inherit_fields, is_consolidated,
                                       lookup_vbpl, merge_fields, metadata_conflicts, parse_vbpl_url, type_problem,
                                       vbpl_fields)
from rag.legal.upload.normalize import check_structure, normalize_legal_text
from rag.legal.vbhn import parse_consolidation_header

MISSING_BASE_LAW = "Văn bản này sửa {name} {number}, nhưng kho chưa có luật này. Hãy upload luật gốc."
MISSING_CONSOLIDATED_LAW = "Văn bản hợp nhất {name} {number}, nhưng kho chưa có luật này. Cần upload luật gốc."
STALE_MESSAGE = "Kho đã thay đổi từ lúc bạn so sánh — hãy xem lại bước ①"
REPLACE_NOTE = ("Các chỉ dẫn đã được duyệt tay sẽ giữ nguyên quyết định; chỉ dẫn đã duyệt mà không còn trong bản mới "
                "sẽ mở mục duyệt. Mọi quan hệ trỏ tới / từ văn bản này được giữ nguyên.")
ALL_PENDING = ", nên mọi chỉ dẫn sửa đổi của văn bản này cần duyệt"

# mã lý do (status_reasons / cờ hiệu lực) -> câu tiếng Việt; mã chưa có ở đây hiện nguyên mã
REASONS_VI = {
    "operation.anchor_missing": "Không thấy đơn vị làm mốc để bổ sung",
    "operation.apply_failed": "Không áp dụng được chỉ dẫn vào luật đích",
    "operation.bulk_text_scope": "Thay cụm từ trên phạm vi rộng, cần người xác nhận phạm vi",
    "operation.cannot_split_content": "Không tách được nội dung mới thành từng đơn vị",
    "operation.chapter_replacement": "Chỉ dẫn thay cả Chương/Mục, cần duyệt tay",
    "operation.conflict": "Mâu thuẫn với chỉ dẫn khác cùng nhắm vào đơn vị này",
    "operation.insert_anchor_missing": "Không thấy vị trí bổ sung",
    "operation.insert_before_unsupported": "Bổ sung vào trước một đơn vị chưa được hỗ trợ",
    "operation.label_mismatch": "Nội dung mới không khớp số hiệu đơn vị đích",
    "operation.missing_after_replan": "Chỉ dẫn đã duyệt không còn trong bản mới",
    "operation.missing_amending_law": "Kho thiếu một luật sửa đổi đã biết",
    "operation.missing_new_text": "Không đọc được nội dung mới của chỉ dẫn",
    "operation.no_effective_date": "Chưa xác định được ngày hiệu lực của chỉ dẫn",
    "operation.partial_repeal": "Bãi bỏ một phần luật khác, cần xác nhận phạm vi",
    "operation.phrase_not_unique": "Cụm từ cần thay không xuất hiện đúng một lần",
    "operation.phrase_wording_unparsed": "Không đọc được cụm từ cần thay",
    "operation.source_amended": "Chính chỉ dẫn này đã bị văn bản sau sửa",
    "operation.superseded_by_replan": "Chỉ dẫn được thay khi lập lại",
    "operation.target_exists": "Đơn vị cần bổ sung đã có sẵn trong luật đích",
    "operation.target_law_ambiguous": "Có nhiều luật trong kho khớp luật đích",
    "operation.target_law_mismatch": "Tên và số hiệu luật đích không khớp nhau",
    "operation.target_law_not_found": "Chờ luật gốc: luật đích chưa có trong kho",
    "operation.target_law_not_loaded": "Luật đích chưa được nạp nội dung",
    "operation.target_missing": "Không thấy đơn vị đích trong luật được sửa",
    "operation.target_unresolved": "Chưa xác định được đơn vị đích",
    "operation.text_scope_unknown": "Chưa rõ phạm vi thay cụm từ",
    "operation.unparsed_header": "Không đọc được câu dẫn của chỉ dẫn",
    "operation.unsupported_table_or_appendix": "Chỉ dẫn sửa phụ lục / bảng, chưa hỗ trợ tự động",
    "effectivity.conditional": "Có đơn vị hiệu lực theo sự kiện, không theo ngày",
    "effectivity.conditional_unit": "Đơn vị này có hiệu lực theo sự kiện",
    "effectivity.date_mismatch": "Ngày hiệu lực trong văn bản khác thông tin vbpl",
    "effectivity.invalid_date": "Điều hiệu lực có ngày không hợp lệ",
    "effectivity.multiple_dates": "Điều hiệu lực có nhiều mốc ngày",
    "effectivity.no_default_date": "Điều hiệu lực không ghi ngày hiệu lực chung",
    "effectivity.relative_date": "Ngày hiệu lực tính tương đối (sau N ngày...)",
    "effectivity.transition": "Có quy định chuyển tiếp",
    "effectivity.unit_exception": "Có đơn vị hiệu lực khác ngày chung",
    "effectivity.unit_exception_unresolved": "Điều hiệu lực có ngày chưa gắn được vào điều nào",
    "effectivity.unresolved": "Chưa đọc được ngày hiệu lực",
    "effectivity.unstable": "Ngày hiệu lực chưa ổn định",
    "effectivity.vbpl_mismatch": "Ngày hiệu lực đọc từ văn bản khác vbpl",
    "source.inherited_metadata_conflict": "Thông tin kế thừa mâu thuẫn với text mới",
    "source.no_vbpl_metadata": "Không có thông tin vbpl đối chiếu trong lần upload này",
}

_DATE_FIELDS = ("issued_on", "vbpl_effective_from", "vbpl_effective_to")
_REQUIRED = {"doc_type": "Loại văn bản", "doc_number": "Số hiệu", "title": "Tên văn bản",
             "issuer": "Cơ quan ban hành", "issued_on": "Ngày ban hành"}
_VERBS = {"REPLACE": "Sửa", "INSERT": "Bổ sung", "DELETE": "Bãi bỏ"}
_DATE_RE = re.compile(r"ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4}|\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{4}", re.IGNORECASE)
_SELF_EFFECT = re.compile(r"(?:Bộ\s+luật|Luật|Nghị\s+quyết|Pháp\s+lệnh)\s+này\s+có\s+hiệu\s+lực", re.IGNORECASE)
_EXCERPT = 1500


class StepError(ValueError):
    """Gọi sai bước / thiếu xác nhận; message tiếng Việt hiện thẳng cho người dùng."""


class StaleDraftError(StepError):
    def __init__(self, message: str = STALE_MESSAGE) -> None:
        super().__init__(message)


@dataclass(frozen=True)
class Preview:
    kind: Literal["base", "amending", "consolidated"]
    targets: tuple[dict, ...]           # {"document_key"|None, "name", "number", "in_store", "warning"}
    operations: tuple[dict, ...]        # {"operation_id","source_locator","description","effective_from",...}
    repeals: tuple[dict, ...]
    waiting_for_this: int               # số thao tác của văn bản khác đang chờ văn bản này
    effectivity: dict                   # {"default_from","evidence","exceptions","conditional_units","flags_vi"}
    replace_note: str | None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enc_fields(fields: dict[str, FieldValue]) -> dict[str, dict]:
    return {k: encode(v) for k, v in fields.items()}


def _dec_fields(raw: dict[str, dict]) -> dict[str, FieldValue]:
    out = {}
    for k, v in raw.items():
        value = v.get("value")
        if k in _DATE_FIELDS and isinstance(value, str):
            value = date.fromisoformat(value)
        out[k] = FieldValue(value, v["source"], datetime.fromisoformat(v["at"]), v.get("detail") or "")
    return out


def _value(draft: Draft, name: str) -> Any:
    return (draft.fields.get(name) or {}).get("value")


def _key(draft: Draft) -> str | None:
    t, n = _value(draft, "doc_type"), _value(draft, "doc_number")
    return document_key(t, n) if t and n else None


def _parse_value(name: str, raw: Any) -> Any:
    s = raw.strip() if isinstance(raw, str) else raw
    if s is None or s == "":
        return None
    if name in _DATE_FIELDS:
        try:
            return date.fromisoformat(s)
        except ValueError:
            day = parse_vn_date(s)
            if day is None:
                raise StepError(f"'{s}' không phải ngày hợp lệ (dd/mm/yyyy)") from None
            return day
    return normalize_number(s) if name == "doc_number" else s


def _unit_vi(a: Address) -> str:
    label = f"Điều {a.article}"
    if a.clause is not None:
        label = f"khoản {a.clause} {label}"
    if a.point is not None:
        label = f"điểm {a.point} {label}"
    return {"title": f"tên {label}", "lead_in": f"đoạn đầu {label}"}.get(a.part, label)


def _describe(op: AmendmentOperation) -> str:
    law = f" của {op.target_law_name}" if op.target_law_name else ""
    if op.operation_type == "REPEAL_DOCUMENT":
        return f"Bãi bỏ toàn bộ {op.target_law_name or 'văn bản'}"
    if op.operation_type == "UNSUPPORTED" or op.target is None:
        return f"Chỉ dẫn chưa hỗ trợ tự động{law}"
    unit = _unit_vi(op.target)
    if op.operation_type == "REPLACE_TEXT":
        return f"Thay cụm từ “{op.old_phrase}” trong {unit}{law}"
    if op.operation_type == "AMEND_TEXT":
        return f"Sửa câu chữ trong {unit}{law}"
    return f"{_VERBS.get(op.operation_type.split('_')[0], op.operation_type)} {unit}{law}"


def _reasons_vi(reasons: tuple[str, ...]) -> list[str]:
    out = [REASONS_VI.get(r.split(":", 1)[0].strip(), r) for r in reasons if not r.startswith("note:")]
    return list(dict.fromkeys(out))


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"\n|(?<=[.;])\s+", text) if s.strip()]


def _dates_in(sentence: str) -> list[date]:
    return [d for m in _DATE_RE.finditer(sentence) if (d := parse_vn_date(m.group(0)))]


def _effectivity(provisions, info: EffectivityInfo, has_ops: bool) -> dict:
    article = next((p.text for p in provisions if p.kind == "article" and p.address.article == info.article), "")
    sentences = _sentences(article)
    evidence = next((s for s in sentences if _SELF_EFFECT.search(s)), None)
    groups: dict[date, list[str]] = {}
    for addr, day in info.exceptions:
        groups.setdefault(day, []).append(_unit_vi(addr))
    exceptions = [{"units": units, "date": day.isoformat(),
                   "evidence": next((s for s in sentences if day in _dates_in(s)), None)} for day, units in groups.items()]
    conditional = []
    for a in info.conditional_units:
        needles = [f"điều {a.article}"] + ([f"khoản {a.clause}"] if a.clause else [])
        conditional.append({"unit": _unit_vi(a), "evidence": next(
            (s for s in sentences if all(n in s.casefold() for n in needles) and not _dates_in(s)), None)})
    flags_vi = []
    for flag in info.flags:
        code = flag.split(":", 1)[0].strip()
        msg = REASONS_VI.get(code, flag)
        if code == "effectivity.unit_exception_unresolved":
            known = {info.default_from, *groups}
            loose = sorted({d for s in sentences for d in _dates_in(s)} - known)
            if loose:
                msg = f"Điều hiệu lực có ngày {', '.join(d.strftime('%d/%m/%Y') for d in loose)} chưa gắn được vào điều nào"
        flags_vi.append(msg + (ALL_PENDING if has_ops else ""))
    return {"default_from": info.default_from.isoformat() if info.default_from else None, "evidence": evidence,
            "exceptions": exceptions, "conditional_units": conditional, "flags_vi": flags_vi}


def _amended_laws(store: LegalStore, doc: LegalDocument, provisions) -> list[tuple[str, str | None, str | None, Any]]:
    """(tên, số hiệu, document_key trong kho | None, chỉ dẫn đầu tiên) cho mỗi luật bị văn bản này sửa."""
    documents = [d for d in store.documents() if d.document_key != doc.document_key]
    seen: dict[tuple, tuple] = {}
    for d in parse_directives(provisions, default_target=_target_law(doc.title)):
        ident = (d.target_law_name, d.target_law_number and normalize_number(d.target_law_number))
        if ident in seen or ident == (None, None):
            continue
        key, _ = resolve_target_law(d.target_law_name, d.target_law_number, before=doc.issued_on, documents=documents)
        seen[ident] = (d.target_law_name or "Luật", d.target_law_number, key, d)
    return list(seen.values())


def _resolve(store: LegalStore, name: str | None, number: str | None, before: date | None, self_key: str) -> str | None:
    docs = [d for d in store.documents() if d.document_key != self_key]
    return resolve_target_law(name, number, before=before, documents=docs)[0]


class UploadService:
    def __init__(self, snapshots: SnapshotManager, drafts: DraftStore, *, client_factory: Callable[[], Any] = VbplClient,
                 ocr=None, now: Callable[[], datetime] = _utcnow) -> None:
        self.snapshots, self.drafts = snapshots, drafts
        self.client_factory, self.ocr, self.now = client_factory, ocr, now
        self._lock = threading.RLock()

    # --- bước ① -------------------------------------------------------------------------

    def _new_id(self) -> str:
        return "u" + self.now().strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(3)

    def create_from_file(self, path: Path, source_name: str) -> Draft:
        upload_id = self._new_id()
        ext = Path(path).suffix or Path(source_name).suffix
        original = self.drafts.save_original(upload_id, Path(path), ext)
        try:
            pages = load_source(original, source=source_name, ocr=self.ocr)
        except ValueError as e:                     # UnsupportedSourceError, mã hoá sai...
            self.drafts.discard(upload_id)
            raise StepError(str(e)) from None
        texts = [p.text or "" for p in pages]
        text = normalize_legal_text(texts)
        if not text.strip():
            self.drafts.discard(upload_id)
            raise StepError("Không trích được chữ nào từ file — nếu là bản scan, hãy bật OCR")
        now = self.now()
        # đầu văn bản đọc trên dòng vật lý gốc: chuẩn hoá ghép các dòng ngắn của phần đầu thành một dòng
        fields = header_fields("\n".join(texts), now)
        t, n = fields.get("doc_type"), fields.get("doc_number")
        detail = lookup_vbpl(self.client_factory(), t.value, n.value) if t and n and t.value and n.value else None
        if detail is not None:
            fields = merge_fields(fields, vbpl_fields(detail, now))
        return self._create(upload_id, "file", source_name, text, page_details(pages), fields, detail is not None)

    def create_from_url(self, url: str) -> Draft:
        vid = parse_vbpl_url(url)
        if vid is None:
            raise StepError("Chỉ nhận đường link văn bản vbpl dạng https://vbpl.vn/van-ban/chi-tiet/<id>")
        try:
            detail = self.client_factory().detail(vid)
        except Exception:                           # noqa: BLE001 - mọi lỗi mạng / id không có
            raise StepError(f"Không lấy được văn bản {vid} từ vbpl (id không có hoặc mạng lỗi)") from None
        text = html_to_legal_text((detail.get("documentContent") or {}).get("content") or "")
        if not text:
            raise StepError(f"Văn bản {vid} trên vbpl không có nội dung")
        now = self.now()
        fields = merge_fields(header_fields(text, now), vbpl_fields(detail, now))
        return self._create(self._new_id(), "url", url.strip(), text, [], fields, True)

    def _create(self, upload_id: str, origin: str, source_name: str, text: str, pages: list[dict],
                fields: dict[str, FieldValue], verified: bool) -> Draft:
        d = Draft(upload_id, self.now(), "step1", origin, source_name, text,  # type: ignore[arg-type]
                  hashlib.sha256(text.encode("utf-8")).hexdigest(), pages, {}, _enc_fields(fields), verified, "", None)
        d.structure = encode(check_structure(text, _key(d) or "upload"))
        self._check_duplicate(d)
        self.drafts.save(d)
        return d

    def _check_duplicate(self, d: Draft) -> None:
        """So với snapshot đang công bố; ghi `base_snapshot_id` + checksum bản trong kho đã so sánh."""
        snap = self.snapshots.current()
        d.base_snapshot_id = snap.snapshot_id
        key = _key(d)
        existing = self.snapshots.store(snap.snapshot_id).document(key) if key else None
        d.duplicate = None
        if existing is None:
            return
        dup = {"document_key": key, "checksum": existing.raw_checksum, "text_source": existing.text_source,
               "fetched_at": existing.fetched_at.isoformat(), "discovered_via": existing.discovered_via,
               "diff": None, "replace_allowed": False}
        if existing.raw_checksum == d.checksum:
            d.state = "duplicate"
        else:
            try:
                old = Path(existing.raw_text_path).read_text(encoding="utf-8")
            except OSError:
                old = ""
            dup["diff"] = encode(diff_articles(old, d.text, key))
            dup["replace_allowed"] = not (existing.text_source == "vbpl" and d.origin == "file")
            d.state = "step1"
        d.duplicate = dup

    def _load(self, upload_id: str, *states: str) -> Draft:
        d = self.drafts.load(upload_id)
        if d.state not in states:
            if d.state == "duplicate":
                raise StepError("Văn bản này đã có trong kho, không có gì thay đổi")
            raise StepError(f"Bản nháp đang ở trạng thái '{d.state}', không làm được thao tác này")
        return d

    def _confirmation(self, by: str, note: str = "") -> dict:
        if not (by or "").strip():
            raise StepError("Cần tên người thực hiện")
        return {"by": by.strip(), "at": self.now().isoformat(), "note": note}

    def _save(self, d: Draft) -> Draft:
        self.drafts.save(d)
        return d

    def confirm_text(self, upload_id: str, by: str) -> Draft:
        with self._lock:
            d = self._load(upload_id, "step1")
            if d.duplicate is not None:
                raise StepError("Văn bản cùng số hiệu đã có trong kho với nội dung khác — chọn 'Thay bản trong kho' "
                                "hoặc 'Hủy'")
            d.confirmations["step1"] = self._confirmation(by)
            d.state = "step2"
            return self._save(d)

    def choose_replace(self, upload_id: str, by: str) -> Draft:
        with self._lock:
            d = self._load(upload_id, "step1")
            if d.duplicate is None:
                raise StepError("Kho chưa có văn bản cùng số hiệu, không có gì để thay")
            if not d.duplicate["replace_allowed"]:
                raise StepError("Bản trong kho lấy từ vbpl (bản vbpl là text gốc) — không thay bằng file tải lên được")
            d.confirmations["step1"] = self._confirmation(by)
            existing = self.snapshots.store().document(d.duplicate["document_key"])
            if existing is not None:
                d.fields = _enc_fields(inherit_fields(_dec_fields(d.fields), existing, self.now()))
            d.replace, d.state, d.preview = True, "step2", None
            return self._save(d)

    # --- bước ② -------------------------------------------------------------------------

    def update_fields(self, upload_id: str, values: dict[str, str], by: str) -> Draft:
        with self._lock:
            d = self._load(upload_id, "step2")
            who = self._confirmation(by)["by"]
            fields, now, before = _dec_fields(d.fields), self.now(), _key(d)
            for name, raw in values.items():
                if name not in FIELDS:
                    raise StepError(f"Trường không hợp lệ: {name}")
                fields[name] = FieldValue(_parse_value(name, raw), "user", now, who)
            d.fields, d.preview = _enc_fields(fields), None
            self._recheck_if_rekeyed(d, before)
            return self._save(d)

    def _recheck_if_rekeyed(self, d: Draft, before: str | None) -> None:
        """Số hiệu / loại đổi: kiểm trùng lại; trùng thì quay về bước ① (so sánh), bỏ các xác nhận."""
        if _key(d) == before:
            return
        d.replace = False
        self._check_duplicate(d)
        if d.duplicate is not None:
            d.confirmations = {}

    def relookup_vbpl(self, upload_id: str) -> Draft:
        with self._lock:
            d = self._load(upload_id, "step1", "step2")
            fields, now, before = _dec_fields(d.fields), self.now(), _key(d)
            client = self.client_factory()
            if d.origin == "url":
                try:
                    detail = client.detail(str(_value(d, "vbpl_id") or parse_vbpl_url(d.source_name)))
                except Exception:                   # noqa: BLE001
                    detail = None
            else:
                t, n = _value(d, "doc_type"), _value(d, "doc_number")
                detail = lookup_vbpl(client, t, n) if t and n else None
            if detail is not None:
                user = {k: v for k, v in fields.items() if v.source == "user"}
                d.fields = _enc_fields(merge_fields(fields, vbpl_fields(detail, now), user))
                d.source_verified, d.preview = True, None
                self._recheck_if_rekeyed(d, before)
            return self._save(d)

    def preview(self, upload_id: str) -> Draft:
        with self._lock:
            d = self._load(upload_id, "step2")
            key = _key(d)
            if key is None:
                raise StepError("Cần loại văn bản và số hiệu trước khi xem hệ thống hiểu văn bản")
            with self.snapshots.scratch() as svc:
                doc = self._document(d, key, svc.store.path.parent / "raw", None)
                waiting_ids = {o.operation_id: o.source_document_key for o in svc.store.operations()
                               if o.source_document_key != key and o.target_document_key is None
                               and "operation.target_law_not_found" in o.status_reasons}
                svc.store.upsert_document(doc)
                ops = svc.plan_operations(key)
                waiting = sum(1 for src in sorted(set(waiting_ids.values())) for o in svc.plan_operations(src)
                              if o.target_document_key == key and o.operation_id in waiting_ids)
                d.preview = encode(self._preview(svc, d, doc, ops, waiting))
            return self._save(d)

    def _preview(self, svc: LegalService, d: Draft, doc: LegalDocument, ops: list[AmendmentOperation],
                 waiting: int) -> Preview:
        provisions = parse_structure(d.text, doc.document_key)
        info = parse_effectivity(provisions)
        targets = []
        if doc.is_consolidated:
            kind = "consolidated"
            h = parse_consolidation_header(d.text)
            if h.target_name or h.target_number:
                k = _resolve(svc.store, h.target_name, h.target_number, None, doc.document_key)
                targets.append({"document_key": k, "name": h.target_name, "number": h.target_number,
                                "in_store": k is not None, "warning": None if k else MISSING_CONSOLIDATED_LAW.format(
                                    name=h.target_name or "Luật", number=h.target_number or "")})
        else:
            kind = "amending" if re.search(r"sửa\s+đổi", doc.title, re.IGNORECASE) else "base"
            for name, number, k, _ in _amended_laws(svc.store, doc, provisions):
                targets.append({"document_key": k, "name": name, "number": number, "in_store": k is not None,
                                "warning": None if k else MISSING_BASE_LAW.format(name=name, number=number or "")})
        operations = [{"operation_id": o.operation_id, "source_locator": o.source_locator, "description": _describe(o),
                       "effective_from": o.effective_from.isoformat() if o.effective_from else None,
                       "review_status": o.review_status, "reasons_vi": _reasons_vi(o.status_reasons),
                       "target_document_key": o.target_document_key,
                       "excerpt": d.text[o.source_span[0]:o.source_span[1]][:_EXCERPT]}
                      for o in ops if o.operation_type != "REPEAL_DOCUMENT"]
        repeals = []
        article = next((p.text for p in provisions if p.kind == "article" and p.address.article == info.article), "")
        for r in info.repeals:
            sentence = next((s for s in _sentences(article) if r.target_number and r.target_number in s), None)
            k = _resolve(svc.store, r.target_name, r.target_number, doc.issued_on, doc.document_key)
            repeals.append({"name": r.target_name, "number": r.target_number, "document_key": k, "in_store": k is not None,
                            "effective_from": r.effective.isoformat() if r.effective else None,
                            "units": [_unit_vi(u) for u in r.units],
                            "evidence": sentence or d.text[r.span[0]:r.span[1]]})
        directive_ops = any(o.sequence < 100_000 for o in ops)
        return Preview(kind, tuple(targets), tuple(operations), tuple(repeals), waiting,
                       _effectivity(provisions, info, directive_ops), REPLACE_NOTE if d.replace else None)

    def confirm_understanding(self, upload_id: str, by: str) -> Draft:
        with self._lock:
            d = self._load(upload_id, "step2")
            confirmation = self._confirmation(by)
            t, n = _value(d, "doc_type"), _value(d, "doc_number")
            if t and (problem := type_problem(t, n)):
                raise StepError(problem)
            missing = [label for name, label in _REQUIRED.items() if _value(d, name) in (None, "")]
            if missing:
                raise StepError("Còn trường bắt buộc trống: " + ", ".join(missing))
            if is_consolidated(t, n):
                if not parse_consolidation_header(d.text).target_number:
                    raise StepError("Không xác định được luật được hợp nhất từ phần đầu văn bản hợp nhất")
            elif parse_effectivity(parse_structure(d.text, _key(d))).default_from is None \
                    and not _value(d, "vbpl_effective_from"):
                raise StepError("Chưa đọc được ngày hiệu lực chung từ văn bản — hãy nhập ngày hiệu lực")
            if d.preview is None:
                d = self.preview(upload_id)
            d.confirmations["step2"] = confirmation
            d.state = "step3"
            return self._save(d)

    # --- bước ③ -------------------------------------------------------------------------

    def submit(self, upload_id: str, by: str, note: str = "") -> Draft:
        with self._lock:
            d = self._load(upload_id, "step3")
            d.confirmations["step3"] = self._confirmation(by, note)
            d.state = "queued"
            return self._save(d)

    def cancel(self, upload_id: str) -> Draft:
        with self._lock:
            d = self._load(upload_id, "step1", "step2", "step3", "queued", "duplicate", "stale", "failed")
            d.state = "cancelled"
            return self._save(d)

    # --- ghi vào kho (trong SnapshotManager.write) ----------------------------------------

    def _document(self, d: Draft, key: str, raw_dir: Path, existing: LegalDocument | None) -> LegalDocument:
        fields = _dec_fields(d.fields)
        if existing is not None and d.replace:
            fields = inherit_fields(fields, existing, self.now())
        path, checksum = write_text(raw_dir, key, d.text)

        def v(name: str) -> Any:
            return fields[name].value if name in fields else None

        step1 = d.confirmations.get("step1")
        checked = max((f.at for f in fields.values() if f.source == "vbpl"), default=None) if d.source_verified else None
        number = normalize_number(v("doc_number"))
        title, doc_type = v("title") or number, v("doc_type")
        if doc_type and not title.casefold().startswith(doc_type.casefold()):
            title = f"{doc_type} {title}"       # đầu văn bản: "LUẬT" / "NHÀ Ở" -> "Luật NHÀ Ở" (khớp tên luật đích)
        return LegalDocument(
            document_key=key, vbpl_id=str(v("vbpl_id") or ""), title=title, doc_type=doc_type,
            doc_number=number, issuer=v("issuer"), issued_on=v("issued_on"),
            vbpl_effective_from=v("vbpl_effective_from"), vbpl_effective_to=v("vbpl_effective_to"),
            eff_status=v("eff_status"), is_consolidated=is_consolidated(v("doc_type"), number),
            raw_text_path=str(path), raw_checksum=checksum, fetched_at=self.now(),
            discovered_via=f"upload:{d.upload_id}", text_source="vbpl" if d.origin == "url" else "file",
            content_verified={"by": step1["by"], "at": step1["at"]} if d.origin == "file" and step1 else None,
            source_verified=d.source_verified, source_checked_at=checked,
            field_sources={k: {"source": f.source, "at": f.at.isoformat(), "detail": f.detail} for k, f in fields.items()},
            metadata_conflicts=metadata_conflicts(fields, d.text, key))

    def apply_to(self, svc: LegalService, upload_id: str) -> None:
        d = self._load(upload_id, "queued", "building")
        key = _key(d)
        if key is None:
            raise StepError("Bản nháp thiếu loại văn bản / số hiệu")
        existing = svc.store.document(key)
        expected = d.duplicate["checksum"] if d.duplicate else None
        if (existing.raw_checksum if existing else None) != expected:
            raise StaleDraftError()
        if existing is not None and not d.replace:
            raise StepError("Văn bản đã có trong kho mà bản nháp không ở chế độ thay thế")
        if existing is not None and existing.text_source == "vbpl" and d.origin == "file":
            raise StepError("Bản trong kho lấy từ vbpl (bản vbpl là text gốc) — không thay bằng file tải lên được")
        doc = self._document(d, key, self.snapshots.legal_dir / "raw", existing)
        svc.store.upsert_document(doc)
        # thay thế giữ mọi quan hệ: không bao giờ ghi đè trạng thái / bằng chứng của quan hệ đã có (kể cả `rejected`)
        known = {(r.source_key, r.target_key, r.relation) for r in svc.store.relations(key)}
        for rel in self._relations(svc.store, doc, d.text):
            if (rel.source_key, rel.target_key, rel.relation) not in known:
                svc.store.add_relation(rel)

    def _relations(self, store: LegalStore, doc: LegalDocument, text: str) -> list[DocumentRelation]:
        """Quan hệ `confirmed` kèm bằng chứng câu chữ (như `discovery._confirm`); quan hệ cũ không bị xoá."""
        key = doc.document_key
        if doc.is_consolidated:
            h = parse_consolidation_header(text)
            k = _resolve(store, h.target_name, h.target_number, None, key) if h.target_number else None
            return [DocumentRelation(key, k, "HOP_NHAT", f"hợp nhất {h.target_name} số {h.target_number}",
                                     "confirmed")] if k else []
        provisions = parse_structure(text, key)
        out = [DocumentRelation(key, k, "SUA_DOI_BO_SUNG", f"{dv.source_locator}: {dv.operation_type}", "confirmed")
               for _, _, k, dv in _amended_laws(store, doc, provisions) if k]
        for r in parse_effectivity(provisions).repeals:
            k = _resolve(store, r.target_name, r.target_number, doc.issued_on, key) if not r.units else None
            if k:
                out.append(DocumentRelation(key, k, "THAY_THE", f"hết hiệu lực: {r.target_name} số {r.target_number}",
                                            "confirmed"))
        return out


__all__ = ["MISSING_BASE_LAW", "Preview", "REASONS_VI", "STALE_MESSAGE", "StaleDraftError", "StepError",
           "UploadService"]
