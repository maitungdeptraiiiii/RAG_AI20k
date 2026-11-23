"""HTTP cho phần 4 — đính kèm hợp đồng trong chat (spec 2026-11-11-contract-review-design.md).

    POST   /api/contracts                      multipart file + persist=0|1 -> thẻ hợp đồng
    GET    /api/contracts?ids=a,b              các hợp đồng đã lưu mà trình duyệt đang giữ id
    GET    /api/contracts/{id}                 thẻ hợp đồng
    POST   /api/contracts/{id}/party           {"party": "neutral" | vai trò}
    POST   /api/contracts/{id}/sign-date       {"date": "YYYY-MM-DD", "by"?} (nguồn: người dùng nhập)
    POST   /api/contracts/{id}/layout          {"parts": [{"start", "kind": "appendix", "title"}], "by"?} -> thẻ
    POST   /api/contracts/{id}/facts           {"answers": {key | "q:<qid>": {"action": confirm|set|unknown, "value"?}},
                                               "by"?} -> thẻ (bảng xác minh, spec 2026-11-13)
    POST   /api/contracts/{id}/save            chuyển sang "Lưu lại"
    DELETE /api/contracts/{id}                 gỡ / xoá hẳn
    POST   /api/contracts/{id}/run             {"op": summary|review|partial|law_changes|redline, unit_ids?, topics?}
                                               soát khi còn dữ kiện bắt buộc chưa xác minh -> 409 {"error", "pending"}
    GET    /api/contracts/{id}/reports/{rid}.docx|.pdf

Hợp đồng không bao giờ đi /api/ingest hay vào kho tra cứu. Mỗi thao tác giữ một LegalRuntime (lease) suốt request.
Mọi thay đổi (tạo, bên, ngày ký, bố cục, chuyển đổi bản Phần 4) ghi vào nhật ký thao tác rồi dựng lại đồ thị trong
khóa ghi của hợp đồng; đồ thị lỗi chỉ báo trong thẻ (card["graph"]), không thành lỗi 5xx.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import copy
import hashlib
import logging
import re
import secrets
import unicodedata
from urllib.parse import quote as _urlquote
import tempfile
from contextlib import contextmanager
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from functools import lru_cache
from types import SimpleNamespace
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from rag.bridge.basis import AnchorLawBasis
from rag.bridge.catalog import load_catalog
from rag.bridge.check import check_contract, report_json, report_markdown
from rag.bridge.view import result_views
from rag.contracts.classify import AUTO_KIND, UNKNOWN, classify_contract
from rag.contracts import review as rv
from rag.contracts.doc import PageText, PartSpec, assemble
from rag.contracts.export import report_docx, report_pdf
from rag.contracts.facts import extract_facts
from rag.contracts.graph.oplog import OperationLog, human_op, machine_op
from rag.contracts.graph.service import ContractGraphService, GraphBusy
from rag.contracts.llm_json import ContractAIError
from rag.contracts.models import Contract
from rag.rules.loader import load_packs, packs_for_kind
from rag.contracts import verify
from rag.contracts.parts import detect_parts, heading_number
from rag.contracts.store import ContractStore
from rag.contracts.structure import parse_contract, to_contract_units

log = logging.getLogger("rag.ui.contracts")

MAX_BYTES = 50 * 1024 * 1024
ALLOWED = {".pdf", ".docx", ".txt", ".md", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}
GONE = "Hợp đồng này đã hết phiên — hãy đính kèm lại"
OPS = ("summary", "review", "partial", "law_changes", "redline")
MAX_PAGES = 150
TOO_LONG = "Hợp đồng dài hơn 150 trang — chưa hỗ trợ"
BAD_LAYOUT = "Vị trí phần không hợp lệ"
USER = "người dùng"            # người sửa mặc định khi request không ghi "by"
CONVERTED = "chuyển đổi"       # người sửa của thao tác chuyển từ bản Phần 4
FAILED = "Không cập nhật được hợp đồng — hãy thử lại"


@contextmanager
def _no_lease():
    yield None


CONFIG = SimpleNamespace(
    root=None,                 # Path: DATA_DIR/contracts (server đặt)
    llm_factory=None,          # () -> llm có .complete(system, user)
    lease=_no_lease,           # () -> context manager trả LegalRuntime | None
    legacy_search=None,        # (query, k) -> list[Chunk] | None
    ocr_factory=lambda: None,
    today=lambda: date.today(),
    agent_baseline=None,       # () -> RAGPipeline kho cũ (llm, condenser, context_config, top_k, retriever)
    agent_config=None,         # () -> AgentConfig
    document_source=None,      # () -> (chunk_id -> Chunk, tìm(q, k) -> [Hit]) tài liệu thường cho agent
    graph=None,                # () -> ContractGraphService; None -> chỉ tách, không ghi Neo4j
    tag_llm=None,              # (model, temp) -> LLM gán khái niệm | None (dùng LLM của app); None -> _default_tag_llm
    legal_graph=None,          # () -> LegalGraph | None; None -> _default_legal_graph
)
_store: ContractStore | None = None
_no_graph = ContractGraphService(None)
_unconvertible: set[str] = set()       # bản Phần 4 đọc lại file gốc thất bại: không thử lại mỗi lần mở


def reset() -> None:
    global _store
    _store = None
    _unconvertible.clear()


def store() -> ContractStore:
    global _store
    if _store is None:
        root = CONFIG.root() if callable(CONFIG.root) else CONFIG.root
        _store = ContractStore(Path(root))
    return _store


def _graph() -> ContractGraphService:
    return CONFIG.graph() if CONFIG.graph is not None else _no_graph


def _ctx(runtime) -> rv.ReviewContext:
    return rv.ReviewContext(CONFIG.llm_factory(), runtime, CONFIG.legacy_search, CONFIG.today())


def card(c: Contract) -> dict[str, Any]:
    rep = c.doc.report if c.doc is not None else None
    g = c.graph or {}
    return {"contract_id": c.contract_id, "filename": c.filename, "persist": c.persist,
            "created_at": c.created_at.isoformat(), "facts": c.facts, "party": c.party,
            "sign_date": c.sign_date.isoformat() if c.sign_date else None, "sign_date_source": c.sign_date_source,
            "units": [{"uid": u.uid, "label": u.label} for u in c.units],
            "coverage": {"reviewed": len(c.units), "total": max(len(c.units), c.total_units)},
            "pages": c.pages,
            "reports": [{"rid": r["rid"], "op": r["op"], "created_at": r["created_at"]} for r in c.reports.values()],
            "parts": [{"part_id": p.part_id, "kind": p.kind, "title": p.title} for p in c.doc.parts] if c.doc else [],
            "parse_report": {"counts": dict(rep.counts) if rep else {}, "gaps": list(rep.gaps) if rep else [],
                             "warnings": list(rep.warnings) if rep else []},
            "graph": {"enabled": bool(g.get("enabled")), "published": bool(g.get("published")),
                      "build_id": g.get("build_id"), "error": g.get("error"),
                      "problems": list(g.get("problems") or [])},
            "verification": verify.summary(c),
            "last_check": ({"checked_at": c.concept_check["checked_at"],
                            "stale": c.concept_check.get("facts_sig") != _facts_sig(c)} if c.concept_check else None),
            "concepts": len({(o.content or {}).get("concept_id") for o in c.oplog.active()
                             if (o.content or {}).get("kind") == "concept"})}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_pages(data: bytes, filename: str) -> tuple[list, list[PageText]]:
    """Đọc file bằng loader chung (file tạm xoá ngay); quá 150 trang -> ValueError, không nạp một phần."""
    from rag.ingest.loaders import load_source

    suffix = Path(filename).suffix.lower()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"upload{suffix}"
        path.write_bytes(data)
        pages = load_source(path, source=filename, ocr=CONFIG.ocr_factory())
    if (len({p.page for p in pages if p.page is not None}) or 1) > MAX_PAGES:
        raise ValueError(TOO_LONG)
    # DOCX giữ bảng ngay trong thân văn bản: bỏ bản sao TablePage. PDF/OCR: bảng OCR đã bị tách khỏi text
    # trang (split_ocr_markdown) nên TablePage là bản duy nhất -> giữ.
    docx = suffix == ".docx"
    texts = [PageText(p.page, p.text or "", type(p).__name__) for p in pages
             if not (docx and type(p).__name__ == "TablePage")]
    if not any(t.text.strip() for t in texts):
        raise ValueError("Không đọc được nội dung hợp đồng (file trống hoặc ảnh không OCR được)")
    return pages, texts


def _set_pages(c: Contract, data: bytes, pages: list, texts: list[PageText]) -> None:
    c.page_texts, c.file_checksum = texts, hashlib.sha256(data).hexdigest()
    c.text = assemble(texts).text                    # cùng văn bản mà bộ tách và vị trí bố cục dùng
    c.pages = [{"page": p.page, "chars": len(p.text or ""), "kind": type(p).__name__} for p in pages]


def _layout_op(c: Contract, now: datetime):
    """Bố cục phần do bộ tách đề xuất."""
    parts = [asdict(p) for p in detect_parts(c.text)]
    return machine_op(c.contract_id, "SET_LAYOUT", None, {"parts": parts}, "rule", "auto_accepted", at=now)


def _active(c: Contract, op_type: str, target: str | None):
    """Thao tác đang hiệu lực mới nhất cùng loại / đích."""
    return next((o for o in reversed(c.oplog.active()) if o.op_type == op_type and o.target == target), None)


def _human(c: Contract, op_type: str, target: str | None, content: dict, by: str, now: datetime) -> None:
    """Thao tác của người thay thế thao tác đang hiệu lực cùng đích (nếu có)."""
    new = human_op(c.contract_id, op_type, target, content, by, at=now)
    old = _active(c, op_type, target)
    if old is None:
        c.oplog.add(new)
    else:
        c.oplog.supersede(old.op_id, new, by, "", now)


def catalog_for(c: Contract):
    """Danh mục của gói ứng với loại hợp đồng đã nhận diện (`facts["document_kind"]`). Chưa có loại: labor như trước (hợp đồng
    đã lưu từ bản cũ). Loại không có gói: ValueError, không rơi về labor."""
    kind = (c.facts or {}).get("document_kind")
    return _catalog_of_kind(kind) if kind else load_catalog()


def _catalog_of_kind(kind: str):
    packs = packs_for_kind(kind)
    if not packs:
        raise ValueError(f"Loại hợp đồng {kind!r} không có gói luật")
    return _packs_catalog(tuple(packs))


@lru_cache(maxsize=16)
def _packs_catalog(packs: tuple[str, ...]):
    return load_packs(list(packs))


def _resolve_kind(c: Contract, llm, document_kind: str | None) -> tuple[str | None, dict | None]:
    """(loại hợp đồng để soát, kết quả nhận diện nếu vừa nhận diện). Thứ tự: loại người dùng chỉ định (phải có gói; được lưu, sửa
    được loại nhận diện sai) > loại đã lưu có gói > nhận diện bằng LLM. `unknown` cũng được lưu (hỏi đáp báo rõ thay vì rơi về
    labor) nhưng không coi là đã nhận diện: lần soát sau nhận diện lại. `document_kind=None` = chế độ cũ (gói labor)."""
    if document_kind is None:
        return None, None
    if document_kind != AUTO_KIND:
        if not packs_for_kind(document_kind):
            raise ValueError(f"Loại hợp đồng {document_kind!r} không có gói luật")
        c.facts = {**(c.facts or {}), "document_kind": document_kind}
        return document_kind, None
    stored = (c.facts or {}).get("document_kind")
    if stored and stored != UNKNOWN:
        return stored, None
    found = classify_contract(llm, c)
    c.facts = {**(c.facts or {}), "document_kind": found["kind"]}
    return found["kind"], found


def _rebuild(c: Contract, now: datetime) -> None:
    """Gọi trong writing(cid): tách lại + dựng / công bố đồ thị; đơn vị = đơn vị cấp cao nhất (không cắt)."""
    doc, status = _graph().rebuild(c.contract_id, c.page_texts, c.oplog, file_checksum=c.file_checksum or "",
                                   now=now, catalog=_catalog_or_labor(c))
    c.doc, c.units = doc, to_contract_units(doc)
    c.total_units, c.graph = len(c.units), status
    c.builds.append(status["record"])


_SNAP = ("party", "sign_date", "sign_date_source", "page_texts", "file_checksum", "text", "pages", "units",
         "total_units", "doc", "graph", "builds")
_MISSING = object()


def _snapshot(c: Contract) -> dict[str, Any]:
    snap = {n: copy.copy(getattr(c, n)) for n in _SNAP}
    snap["oplog"] = c.oplog.to_json()
    snap["pre_graph"] = {rid: r.get("pre_graph", _MISSING) for rid, r in c.reports.items()}
    return snap


def _restore(c: Contract, snap: dict[str, Any]) -> None:
    for n in _SNAP:
        setattr(c, n, snap[n])
    c.oplog = OperationLog.from_json(c.contract_id, snap["oplog"])
    for rid, v in snap["pre_graph"].items():
        if rid in c.reports:
            if v is _MISSING:
                c.reports[rid].pop("pre_graph", None)
            else:
                c.reports[rid]["pre_graph"] = v


def _change(c: Contract, apply) -> None:
    """Ghi thao tác + dựng lại + lưu (nếu "Lưu lại") trong khóa ghi của hợp đồng (GraphBusy -> 409).
    Trọn gói: lỗi ở bất kỳ bước nào -> hợp đồng trở lại đúng như trước rồi ném lỗi.
    Hợp đồng Phần 4 không còn file gốc chỉ ghi thao tác, không dựng."""
    now = _now()
    with _graph().writing(c.contract_id):
        snap = _snapshot(c)
        try:
            apply(now)
            if c.page_texts:
                _rebuild(c, now)
            store().update(c)
        except BaseException:
            _restore(c, snap)
            raise


# --- đồng bộ (chạy ngoài event loop) -------------------------------------------------------------

def create(data: bytes, filename: str, persist: bool, *, on_event=None) -> dict[str, Any]:
    emit = on_event or (lambda event: None)
    emit({"type": "stage", "stage": "read", "status": "start"})
    pages, texts = _load_pages(data, filename)
    emit({"type": "document", "pages": [{"page": t.page, "text": t.text} for t in texts]})
    now = _now()
    c = Contract(secrets.token_urlsafe(18), Path(filename).name, persist, now, "", [], 0)
    _set_pages(c, data, pages, texts)
    c.oplog.add(_layout_op(c, now))
    c.units = to_contract_units(parse_contract(c.page_texts, [PartSpec(**p) for p in c.oplog.layout()]))
    emit({"type": "structure", "units": [{"uid": u.uid, "label": u.label, "text": u.text, "page": u.page} for u in c.units]})
    if on_event:
        from rag.contracts.graph.build import build_graph
        built, _ = build_graph(c.contract_id, c.page_texts, c.oplog,
                               file_checksum=c.file_checksum or "", built_at=now)
        emit({"type": "graph", "phase": "read", "build_id": built.build_id,
              "nodes": [{"node_id": n.node_id, "node_type": n.label, **n.props} for n in built.nodes],
              "edges": [asdict(e) for e in built.edges]})
    try:
        emit({"type": "stage", "stage": "facts", "status": "start"})
        extract_facts(CONFIG.llm_factory(), c, **({"on_event": emit} if on_event else {}))
        emit({"type": "stage", "stage": "facts", "status": "done"})
    except ContractAIError as e:
        c.facts = {"type": "chưa rõ", "parties": [], "error": str(e)}
    kind = c.facts.get("type")
    fields = {"type": kind if kind and kind != "chưa rõ" else None,
              "sign_date": c.sign_date.isoformat() if c.sign_date else None}
    for target, value in fields.items():
        if value is not None:
            c.oplog.add(machine_op(c.contract_id, "SET_FIELD", target, {"value": value}, "llm", "auto_accepted",
                                   at=now))
    with _graph().writing(c.contract_id):
        _rebuild(c, now)
    store().add(c, original=data, suffix=Path(filename).suffix.lower())
    emit({"type": "stage", "stage": "read", "status": "done"})
    return card(c)


def _convert_part4(c: Contract) -> None:
    """Hợp đồng Phần 4 có file gốc: nạp lại trang (không gọi LLM), chuyển lựa chọn của người thành thao tác,
    đánh dấu báo cáo cũ pre_graph, dựng đồ thị. Không đọc được file -> vẫn mở như Phần 4."""
    orig = None if c.contract_id in _unconvertible else store().original(c.contract_id)
    if orig is None:
        return
    try:
        pages, texts = _load_pages(orig[0], f"original{orig[1]}")
    except Exception as e:  # noqa: BLE001 — file hỏng / quá dài: giữ nguyên bản Phần 4
        log.warning("Không chuyển được hợp đồng %s sang đồ thị: %s", c.contract_id, e)
        _unconvertible.add(c.contract_id)
        return

    def apply(now):
        _set_pages(c, orig[0], pages, texts)
        c.oplog.add(_layout_op(c, now))
        if c.party:
            _human(c, "SET_FIELD", "party", {"value": c.party}, CONVERTED, now)
        if c.sign_date and c.sign_date_source == "user":
            _human(c, "SET_FIELD", "sign_date", {"value": c.sign_date.isoformat()}, CONVERTED, now)
        for r in c.reports.values():
            r["pre_graph"] = True
    try:
        _change(c, apply)
    except GraphBusy:
        log.info("Hợp đồng %s đang được chuyển đổi ở request khác", c.contract_id)
    except Exception:  # noqa: BLE001 — giữ nguyên bản Phần 4, lần mở sau thử lại
        log.exception("Chuyển hợp đồng %s sang đồ thị thất bại", c.contract_id)


def get(cid: str) -> Contract:
    c = store().get(cid)
    if c.doc is None and not c.page_texts:
        _convert_part4(c)
    return c


def set_party(cid: str, party: str, by: str = USER) -> dict[str, Any]:
    c = get(cid)
    roles = {p.get("role") for p in c.facts.get("parties") or []}
    if party != "neutral" and party not in roles:
        raise ValueError("Bên không có trong hợp đồng")

    def apply(now):
        c.party = party
        _human(c, "SET_FIELD", "party", {"value": party}, by, now)
    _change(c, apply)
    return card(c)


def set_sign_date(cid: str, value: str, by: str = USER) -> dict[str, Any]:
    try:
        day = date.fromisoformat(str(value))
    except ValueError:
        raise ValueError("Ngày ký phải dạng YYYY-MM-DD") from None
    c = get(cid)

    def apply(now):
        c.sign_date, c.sign_date_source = day, "user"
        _human(c, "SET_FIELD", "sign_date", {"value": day.isoformat()}, by, now)
    _change(c, apply)
    return card(c)


def set_facts(cid: str, answers, by: str = USER) -> dict[str, Any]:
    """Xác nhận / sửa / "không biết" cho dữ kiện và câu hỏi; mỗi câu trả lời là một thao tác của người."""
    c = get(cid)
    _change(c, lambda now: verify.apply_answers(c, answers, by, now))
    return card(c)


def _layout_parts(text: str, raw) -> list[PartSpec]:
    """p0 luôn giữ; các phần người gửi thành phụ lục p1, p2… theo vị trí bắt đầu."""
    try:
        given = sorted(((int(p["start"]), str(p.get("title") or "")) for p in raw or []), key=lambda x: x[0])
    except (AttributeError, KeyError, TypeError, ValueError):
        raise ValueError(BAD_LAYOUT) from None
    starts = [s for s, _ in given]
    if any(not 0 < s < len(text) for s in starts) or len(set(starts)) != len(starts):
        raise ValueError(BAD_LAYOUT)
    # số phụ lục: theo tiêu đề như bộ tách, không có thì theo thứ tự (để "Phụ lục N" vẫn phân giải được)
    return [PartSpec("p0", "main", "", 0, None)] + [
        PartSpec(f"p{i}", "appendix", title, start, heading_number(title) or i)
        for i, (start, title) in enumerate(given, 1)]


def set_layout(cid: str, parts, by: str = USER) -> dict[str, Any]:
    c = get(cid)
    if not c.page_texts:
        raise ValueError("Hợp đồng này chưa có cấu trúc để sửa bố cục — hãy đính kèm lại")
    specs = _layout_parts(c.text, parts)
    _change(c, lambda now: _human(c, "SET_LAYOUT", None, {"parts": [asdict(p) for p in specs]}, by, now))
    return card(c)


def run(cid: str, op: str, unit_ids=None, topics=None) -> dict[str, Any]:
    if op not in OPS:
        raise ValueError(f"Thao tác không hợp lệ: {op}")
    c = get(cid)
    verify.check_gate(c, op)
    with CONFIG.lease() as runtime:
        ctx = _ctx(runtime)
        if op == "summary":
            rep = rv.summarize(ctx, c)
        elif op in ("review", "partial"):
            if op == "partial" and not (unit_ids or topics):
                raise ValueError("Hãy chọn điều khoản hoặc chủ đề cần soát")
            rep = rv.review(ctx, c, unit_ids=unit_ids, topics=topics)
        elif op == "law_changes":
            rep = rv.law_changes_report(ctx, c)
        else:
            rep = rv.redline(ctx, c)
    store().update(c)
    return rep


def _default_legal_graph():
    try:
        from rag.legal.graph.query import LegalGraph
        from rag.legal.graph.service import open_store
        store_ = open_store()                # None khi LEGAL_GRAPH != "1"
        return LegalGraph(store_) if store_ is not None else None
    except Exception as exc:  # noqa: BLE001 — không có đồ thị luật vẫn chạy được
        log.warning("Không mở được đồ thị luật: %s", exc)
        return None


def _default_tag_llm(model: str | None, temp: float | None):
    """Không model: CONCEPT_TAG_MODEL (có cache). "app": LLM của app. Id khác: model đó qua OpenRouter, không cache."""
    from rag.bridge.llm import OPENROUTER_URL, concept_tag_llm
    from rag.config import Settings
    from rag.generate.llm import LLMCache, OpenAIChatLLM
    s = Settings.load()
    if not model:
        return concept_tag_llm(s, cache=LLMCache(s.cache_dir / "concept_tag_llm.sqlite"))
    if model == "app":
        return None
    if not s.openrouter_api_key:
        raise ValueError("Thiếu OPENROUTER_API_KEY")
    return OpenAIChatLLM(model, temperature=temp, base_url=OPENROUTER_URL, api_key=s.openrouter_api_key, cache=None)


def _catalog_or_labor(c: Contract, kind: str | None = None):
    """Danh mục cho chỗ chỉ tra vai trò / nhãn mà kết quả có thể rỗng (loại không có gói): không ném lỗi, rơi về labor.
    `kind` cho trước (kể cả chưa lưu) thắng loại trong facts; kind None + facts không loại = labor."""
    try:
        return _catalog_of_kind(kind) if kind else catalog_for(c)
    except ValueError:
        return load_catalog()


def concept_check(cid: str, user_facts: dict | None = None, *, tag_model: str | None = None,
                  tag_temp: float | None = None, on_event=None, document_kind: str | None = AUTO_KIND) -> dict[str, Any]:
    """Soát hợp đồng theo danh mục khái niệm; dựng lại đồ thị để có Party / ConceptInstance vừa gán.
    on_event nhận sự kiện tiến trình của check_contract; sự kiện `partial` được thêm `views` để trang vẽ."""
    c = get(cid)
    llm = CONFIG.llm_factory()
    now = _now()
    kind, found = _resolve_kind(c, llm, document_kind)      # chọn gói trước: nền luật (basis) phải dựng trên danh mục của gói đó
    catalog = _catalog_or_labor(c, kind)
    tag_llm = (CONFIG.tag_llm or _default_tag_llm)(tag_model, tag_temp)
    legal_graph = (CONFIG.legal_graph or _default_legal_graph)()

    def relay(event: dict) -> None:
        if on_event is None:
            return
        if event.get("type") == "partial":
            event = {**event, "views": result_views(event["results"], catalog, c, {})}
        on_event(event)

    which = {"catalog": catalog} if kind is None else {"document_kind": kind}
    report = check_contract(llm, c, **which, basis=AnchorLawBasis(catalog, legal_graph, on_event=relay if on_event else None), at=now,
                            model=getattr(llm, "model_id", None), tag_llm=tag_llm,
                            tag_model=getattr(tag_llm, "model_id", None), user_facts=user_facts, graph=_graph(),
                            on_event=relay)
    if found is not None and found["kind"] == UNKNOWN:      # lý do nhận diện thất bại (check_contract chỉ thấy "unknown")
        report.warnings.append(f"Không nhận diện được loại hợp đồng ({found.get('reason')}): chọn loại thủ công để soát")
    with _graph().writing(c.contract_id):
        _rebuild(c, now)
    g = c.graph or {}
    labels = {x.concept_id: catalog.concepts[x.concept_id].label for x in report.results}
    js = report_json(report)
    out = {"report": js, "markdown": report_markdown(report, catalog), "labels": labels,
           "graph": {k: g.get(k) for k in ("enabled", "published", "error")},
           "views": result_views(js["results"], catalog, c, report.basis)}
    # Lưu để xem lại không phải chạy lại (tốn LLM); facts_sig cho biết dữ kiện đã đổi sau lần kiểm tra này chưa.
    c.concept_check = {"checked_at": now.isoformat(), "facts_sig": _facts_sig(c), "result": out}
    store().update(c)
    return out


def _facts_sig(c: Contract) -> str:
    import hashlib
    return hashlib.sha256(json.dumps(c.facts, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]


def last_concept_check(cid: str) -> dict[str, Any]:
    """Kết quả Kiểm tra concept gần nhất đã lưu; ValueError khi hợp đồng chưa được kiểm tra."""
    c = get(cid)
    saved = c.concept_check
    if not saved:
        raise ValueError("Hợp đồng này chưa có kết quả Kiểm tra concept")
    return {**saved["result"], "checked_at": saved["checked_at"], "stale": saved.get("facts_sig") != _facts_sig(c)}


NEEDS_CHECK = "Hãy chạy Kiểm tra concept trước khi hỏi"


class NeedsConceptCheck(Exception):
    """Đồ thị chưa có khái niệm đã gán: agent không có điểm bắt đầu."""


def _open_agent(c: Contract, catalog, legal, user_facts: dict | None):
    """Mở đồ thị đã dựng (Neo4j nếu có, không thì bộ nhớ) và tạo GraphAgent -> (agent, ngày soát, cảnh báo).
    Không soát lại: dùng khái niệm Kiểm tra concept đã gán vào oplog."""
    from rag.bridge.check import contract_view, user_fact_set
    from rag.contracts.graph.agent import GraphAgent, agent_context
    from rag.contracts.graph.build import graph_mask_state
    from rag.contracts.graph.tools import make_tools
    facts = user_fact_set(user_facts)
    view, _, warnings, doc = contract_view(c, _graph(), _now(), catalog)
    if not view.find("ConceptInstance"):
        raise NeedsConceptCheck()
    day = c.sign_date or catalog.law_values_valid_from
    tools = make_tools(view, catalog=catalog, day=day, sign_date=c.sign_date, legal=legal, user_facts=facts)
    agent = GraphAgent(CONFIG.llm_factory(), tools, view, mask=graph_mask_state(doc),
                       context=agent_context(view, catalog, sign_date=c.sign_date))
    return agent, day, warnings


def contract_ask(cid: str, question: str, history: list | None = None, user_facts: dict | None = None, *,
                 on_event=None) -> dict[str, Any]:
    """Hỏi về hợp đồng bằng agent trên đồ thị (spec 2026-11-17-contract-page-graph-qa); on_event nhận từng bước."""
    from rag.bridge.view import law_entry
    question = str(question or "").strip()
    if not question:
        raise ValueError("Câu hỏi không được rỗng")
    c = get(cid)
    catalog = catalog_for(c)
    legal = (CONFIG.legal_graph or _default_legal_graph)()
    agent, day, warnings = _open_agent(c, catalog, legal, user_facts)
    a = agent.ask(question, history=history if isinstance(history, list) else None, on_step=on_event)
    pids = list(dict.fromkeys(a.law))
    for t in a.trace:              # kết luận qua check_concept -> căn cứ là neo luật của khái niệm đó trong danh mục
        concept = catalog.concepts.get((t.get("args") or {}).get("concept_id"))
        if t.get("tool") == "check_concept" and concept and not str(t.get("result", "")).startswith('{"error"'):
            pids += [x["pid"] for x in concept.anchors if x.get("pid") and x["pid"] not in pids]
    law = []
    for pid in pids:
        p = None
        if legal is not None:
            try:
                p = legal.text_at(pid, day)
            except Exception:  # noqa: BLE001 — pid không có / đồ thị luật lỗi: vẫn hiện pid
                p = None
        law.append(law_entry(pid, p))
    return {"answer": a.answer, "confidence": a.confidence, "path": _path_view(a, catalog, legal, day), "law": law,
            "seen_unused": [_label_concept(n, catalog) for n in a.seen_unused],
            "warnings": warnings + a.warnings, "trace": a.trace, "stats": a.stats}


def _label_concept(node: dict, catalog) -> dict:
    """ConceptInstance: thêm nhãn tiếng Việt của khái niệm (thay vì mã như content.wage_terms)."""
    concept = catalog.concepts.get(node.get("concept_id") or "")
    return {**node, "concept_label": concept.label} if concept else node


def _path_view(a, catalog, legal, day) -> list[dict]:
    """Đường đi của agent, mỗi nút Khái niệm nối sang graph luật qua neo của khái niệm trong danh mục.
    `law_links[].read_by_agent`: agent có thật sự gọi công cụ luật / check_concept cho neo này trong lượt hay không."""
    from rag.bridge.view import law_entry
    read_pids = {str((t.get("args") or {}).get("pid")) for t in a.trace
                 if str(t.get("tool", "")).startswith("law_") and not t.get("error")}
    checked = {str((t.get("args") or {}).get("concept_id")) for t in a.trace
               if t.get("tool") in ("check_concept", "concept_basis") and not t.get("error")}
    out = []
    for node in a.path:
        node = _label_concept(node, catalog)
        concept = catalog.concepts.get(node.get("concept_id") or "")
        if concept is not None:
            links = []
            for anchor in concept.anchors:
                p = None
                if legal is not None:
                    try:
                        p = legal.text_at(anchor["pid"], day)
                    except Exception:  # noqa: BLE001 — đồ thị luật lỗi: vẫn hiện pid
                        p = None
                links.append({**law_entry(anchor["pid"], p), "role": anchor.get("role"),
                              "read_by_agent": anchor["pid"] in read_pids or concept.id in checked})
            node = {**node, "law_links": links}
        out.append(node)
    return out


def _error_status(exc: Exception) -> tuple[str, int]:
    """Cùng cách ánh xạ lỗi như _call, cho luồng stream."""
    if isinstance(exc, KeyError):
        return GONE, 404
    if isinstance(exc, LookupError):            # hồ sơ mẫu không có (rag.rules.scenario.UnknownDossier)
        return str(exc), 404
    if isinstance(exc, NeedsConceptCheck):
        return NEEDS_CHECK, 409
    if isinstance(exc, GraphBusy):
        return str(exc), 409
    if isinstance(exc, ContractAIError):
        return str(exc), 502
    if isinstance(exc, verify.NeedsVerification):
        return str(exc), 409
    if isinstance(exc, ValueError):
        return str(exc), 400
    log.error("Kiểm tra concept thất bại", exc_info=exc)
    return FAILED, 500


_END = object()


def _events(fn, name: str) -> "queue.Queue":
    """Chạy fn(on_event) trong luồng nền; trả hàng đợi sự kiện, kết thúc bằng `done` / `error` rồi _END.
    Hàng đợi không giới hạn: client đóng giữa chừng thì luồng vẫn chạy hết, không bị chặn."""
    q: queue.Queue = queue.Queue()

    def work():
        try:
            q.put({"type": "done", **fn(q.put)})
        except Exception as exc:  # noqa: BLE001 — mọi lỗi thành sự kiện error cho trang
            msg, status = _error_status(exc)
            q.put({"type": "error", "error": msg, "status": status})
        finally:
            q.put(_END)
    threading.Thread(target=work, daemon=True, name=name).start()
    return q


def concept_check_events(cid: str, user_facts: dict | None = None, document_kind: str | None = AUTO_KIND) -> "queue.Queue":
    return _events(lambda emit: concept_check(cid, user_facts, on_event=emit, document_kind=document_kind),
                   f"concept-check-{cid}")


def contract_ask_events(cid: str, question: str, history: list | None = None,
                        user_facts: dict | None = None) -> "queue.Queue":
    return _events(lambda emit: contract_ask(cid, question, history, user_facts, on_event=emit), f"ask-{cid}")


def chat_answer(cid: str, question: str, history: list[dict]) -> dict[str, Any]:
    """Hỏi với hợp đồng (không Think) — dạng trả về giống /api/chat để UI hiển thị chung."""
    c = get(cid)
    with CONFIG.lease() as runtime:
        out = rv.answer(_ctx(runtime), c, question, history)
    sources = [{"n": i, "chunk_id": e["eid"], "source": e["source_title"], "title": e["source_title"],
                "section": e["section"], "page": None, "score": 0.0, "text": e["text"], "store": e["store"],
                "valid_from": e["valid_from"], "valid_to": e["valid_to"], "provision_status": e["status"]}
               for i, e in enumerate(out["evidence"], 1)]
    return {"query": question, "answer": out["answer"], "refused": False, "citations": sources, "sources": sources,
            "contract_id": cid, "contract_units": out["units"], "legal_status": out["legal_status"],
            "contract_warnings": out.get("warnings", []),
            "anchor": out["anchor"], "trace": {"context_mode": "contract", "n_context_blocks": len(sources),
                                               "errors": {}, "arms": {}, "final_hits": []}}


CONTRACT_AGENT_ROUNDS = 2
CONTRACT_AGENT_DEADLINE_S = 300.0


def _contract_agent_config(base):
    """Think với hợp đồng: mỗi lượt có thêm nguồn hợp đồng + luật có phiên bản nên bước kiểm chứng cuối hay chạm hạn
    180 s của cấu hình chung -> tối đa 2 vòng tìm, hạn 300 s. Think tự do giữ cấu hình chung."""
    import dataclasses

    from rag.agent import AgentConfig

    base = base or AgentConfig()
    return dataclasses.replace(base, max_rounds=min(base.max_rounds, CONTRACT_AGENT_ROUNDS),
                               deadline_s=max(base.deadline_s, CONTRACT_AGENT_DEADLINE_S))


def chat_think(cid: str, question: str, history: list[dict], stream: bool = False):
    """Hỏi với hợp đồng + Think: agent multi-hop trên hợp đồng + luật có phiên bản tại ngày ký + kho cũ.
    stream=True -> iterator sự kiện (progress ... done); lease giữ tới khi iterator chạy xong."""
    from rag.contracts.agent_view import run_contract_agent

    c = get(cid)
    baseline = CONFIG.agent_baseline()
    if CONFIG.document_source is not None:
        doc_chunks, legacy_hits = CONFIG.document_source()
    else:
        doc_chunks = baseline.retriever.chunks

        def legacy_hits(query: str, k: int):
            return baseline.retriever.retrieve(query, k).hits

    config = _contract_agent_config(CONFIG.agent_config() if CONFIG.agent_config else None)
    if not stream:
        with CONFIG.lease() as runtime:
            return run_contract_agent(c, baseline, config, runtime, doc_chunks, legacy_hits, question, history)

    def events():
        with CONFIG.lease() as runtime:
            yield from run_contract_agent(c, baseline, config, runtime, doc_chunks, legacy_hits, question,
                                          history, stream=True)
    return events()


def _disposition(stem: str, op: str, fmt: str) -> str:
    """Header phải là latin-1: tên ASCII (bỏ dấu, đ -> d) + filename* UTF-8 cho trình duyệt hiển thị đúng tên."""
    ascii_stem = unicodedata.normalize("NFKD", stem.replace("đ", "d").replace("Đ", "D"))
    ascii_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_stem.encode("ascii", "ignore").decode()).strip("_")[:60]
    ascii_name = f"{ascii_stem or 'hop_dong'}_{op}.{fmt}"
    utf8_name = f"{stem[:60] or 'hop_dong'}_{op}.{fmt}"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{_urlquote(utf8_name)}"


def download(cid: str, rid: str, fmt: str) -> Response:
    c = get(cid)
    rep = c.reports.get(rid)
    if rep is None:
        raise KeyError(rid)
    if fmt == "docx":
        data, mime = report_docx(c, rep), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        data, mime = report_pdf(c, rep), "application/pdf"
    return Response(data, media_type=mime,
                    headers={"Content-Disposition": _disposition(Path(c.filename).stem, rep["op"], fmt)})


# --- HTTP ----------------------------------------------------------------------------------------

def _error(msg: str, status: int) -> JSONResponse:
    return JSONResponse({"error": msg}, status_code=status)


async def _call(fn, *args) -> Response:
    try:
        result = await asyncio.get_running_loop().run_in_executor(None, fn, *args)
    except KeyError:
        return _error(GONE, 404)
    except GraphBusy as e:
        return _error(str(e), 409)
    except ContractAIError as e:
        return _error(str(e), 502)
    except verify.NeedsVerification as e:
        return JSONResponse({"error": str(e), "pending": e.pending}, status_code=409)
    except ValueError as e:
        return _error(str(e), 400)
    except Exception:  # noqa: BLE001 — lỗi ngoài dự kiến: JSON cho UI, chi tiết ở log
        log.exception("Thao tác hợp đồng thất bại")
        return _error(FAILED, 500)
    return result if isinstance(result, Response) else JSONResponse(result)


async def _json(request: Request) -> dict:
    try:
        data = await request.json()
    except Exception:  # noqa: BLE001
        return {}
    return data if isinstance(data, dict) else {}


async def handle_create(request: Request) -> Response:
    try:
        if int(request.headers.get("content-length") or 0) > MAX_BYTES:
            return _error("File quá lớn: tối đa 50 MB", 413)
    except ValueError:
        pass
    form = await request.form()
    upload = form.get("file")
    if upload is None or not getattr(upload, "filename", ""):
        return _error("Cần chọn file hợp đồng", 400)
    if Path(upload.filename).suffix.lower() not in ALLOWED:
        return _error("Định dạng chưa hỗ trợ: dùng PDF, DOCX, TXT hoặc ảnh scan", 400)
    data = await upload.read()
    if len(data) > MAX_BYTES:
        return _error("File quá lớn: tối đa 50 MB", 413)
    persist = str(form.get("persist") or "0") in ("1", "true", "on")
    return await _call(create, data, upload.filename, persist)


async def handle_list(request: Request) -> Response:
    ids = [i for i in str(request.query_params.get("ids") or "").split(",") if i][:50]

    def listed():
        out = []
        for cid in ids:                 # chỉ đọc thẻ: không chuyển bản Phần 4 (chuyển khi mở từng hợp đồng)
            try:
                out.append(card(store().get(cid)))
            except KeyError:
                continue
            except Exception:  # noqa: BLE001 — một file hỏng không làm hỏng cả danh sách
                log.warning("Bỏ qua hợp đồng không đọc được: %s", cid)
        return {"contracts": out}
    return await _call(listed)


async def handle_get(request: Request) -> Response:
    return await _call(lambda: card(get(request.path_params["cid"])))


def _by(body: dict) -> str:
    return str(body.get("by") or "").strip() or USER


async def handle_party(request: Request) -> Response:
    body = await _json(request)
    return await _call(set_party, request.path_params["cid"], str(body.get("party") or ""), _by(body))


async def handle_sign_date(request: Request) -> Response:
    body = await _json(request)
    return await _call(set_sign_date, request.path_params["cid"], str(body.get("date") or ""), _by(body))


async def handle_layout(request: Request) -> Response:
    body = await _json(request)
    return await _call(set_layout, request.path_params["cid"], body.get("parts"), _by(body))


async def handle_facts(request: Request) -> Response:
    body = await _json(request)
    return await _call(set_facts, request.path_params["cid"], body.get("answers"), _by(body))


async def handle_save(request: Request) -> Response:
    return await _call(lambda: card(store().save(request.path_params["cid"])))


async def handle_delete(request: Request) -> Response:
    def drop():
        store().delete(request.path_params["cid"])
        return {"status": "ok"}
    return await _call(drop)


async def handle_run(request: Request) -> Response:
    body = await _json(request)
    unit_ids = [str(x) for x in body.get("unit_ids") or []] or None
    topics = [str(x) for x in body.get("topics") or []] or None
    return await _call(run, request.path_params["cid"], str(body.get("op") or ""), unit_ids, topics)


async def handle_concept_check(request: Request) -> Response:
    body = await _json(request)
    facts = body.get("user_facts")
    return await _call(lambda cid, f, kind: concept_check(cid, f, document_kind=kind), request.path_params["cid"],
                       facts if isinstance(facts, dict) else {}, str(body.get("document_kind") or AUTO_KIND))


async def handle_concept_check_last(request: Request) -> Response:
    return await _call(last_concept_check, request.path_params["cid"])


async def handle_concept_check_stream(request: Request) -> Response:
    body = await _json(request)
    facts = body.get("user_facts")
    return _sse_queue(concept_check_events(request.path_params["cid"], facts if isinstance(facts, dict) else {},
                                           str(body.get("document_kind") or AUTO_KIND)))


async def handle_ask_stream(request: Request) -> Response:
    body = await _json(request)
    facts = body.get("user_facts")
    return _sse_queue(contract_ask_events(request.path_params["cid"], str(body.get("question") or ""),
                                          body.get("history"), facts if isinstance(facts, dict) else {}))


def scenario_events(dossier_id: str, evaluator: str = "network", answers: dict | None = None) -> "queue.Queue":
    """E3: chạy kịch bản của một hồ sơ mẫu, mỗi sự kiện (step / evaluation / evaluation_diff / explain / expect / questions) một dòng SSE."""
    from rag.rules.scenario import run_scenario

    def run(emit) -> dict:
        for event in run_scenario(dossier_id, evaluator=evaluator, answers=answers):
            emit(event)
        return {}
    return _events(run, f"scenario-{dossier_id}")


async def handle_dossiers(request: Request) -> Response:
    from rag.rules.scenario import list_dossiers
    return JSONResponse({"dossiers": list_dossiers()})


async def handle_scenario_stream(request: Request) -> Response:
    body = await _json(request)
    answers = body.get("answers")
    return _sse_queue(scenario_events(request.path_params["did"], str(body.get("evaluator") or "network"),
                                      answers if isinstance(answers, dict) else None))


def _sse_queue(q: "queue.Queue") -> Response:
    loop = asyncio.get_running_loop()

    async def events():
        while True:
            event = await loop.run_in_executor(None, q.get)
            if event is _END:
                return
            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def handle_download(request: Request) -> Response:
    fmt = request.path_params["fmt"]
    if fmt not in ("docx", "pdf"):
        return _error("Định dạng tải về: docx hoặc pdf", 400)
    return await _call(download, request.path_params["cid"], request.path_params["rid"], fmt)


routes = [
    Route("/api/contracts", handle_create, methods=["POST"]),
    Route("/api/contracts", handle_list, methods=["GET"]),
    Route("/api/contracts/{cid}", handle_get, methods=["GET"]),
    Route("/api/contracts/{cid}", handle_delete, methods=["DELETE"]),
    Route("/api/contracts/{cid}/party", handle_party, methods=["POST"]),
    Route("/api/contracts/{cid}/sign-date", handle_sign_date, methods=["POST"]),
    Route("/api/contracts/{cid}/save", handle_save, methods=["POST"]),
    Route("/api/contracts/{cid}/layout", handle_layout, methods=["POST"]),
    Route("/api/contracts/{cid}/facts", handle_facts, methods=["POST"]),
    Route("/api/contracts/{cid}/run", handle_run, methods=["POST"]),
    Route("/api/contracts/{cid}/concept-check", handle_concept_check, methods=["POST"]),
    Route("/api/contracts/{cid}/concept-check/last", handle_concept_check_last, methods=["GET"]),
    Route("/api/contracts/{cid}/concept-check/stream", handle_concept_check_stream, methods=["POST"]),
    Route("/api/contracts/{cid}/ask/stream", handle_ask_stream, methods=["POST"]),
    Route("/api/rules/dossiers", handle_dossiers, methods=["GET"]),
    Route("/api/rules/dossiers/{did}/scenario/stream", handle_scenario_stream, methods=["POST"]),
    Route("/api/contracts/{cid}/reports/{rid}.{fmt}", handle_download, methods=["GET"]),
]
