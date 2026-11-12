"""HTTP cho phần 4 — đính kèm hợp đồng trong chat (spec 2026-11-11-contract-review-design.md).

    POST   /api/contracts                      multipart file + persist=0|1 -> thẻ hợp đồng
    GET    /api/contracts?ids=a,b              các hợp đồng đã lưu mà trình duyệt đang giữ id
    GET    /api/contracts/{id}                 thẻ hợp đồng
    POST   /api/contracts/{id}/party           {"party": "neutral" | vai trò}
    POST   /api/contracts/{id}/sign-date       {"date": "YYYY-MM-DD", "by"?} (nguồn: người dùng nhập)
    POST   /api/contracts/{id}/layout          {"parts": [{"start", "kind": "appendix", "title"}], "by"?} -> thẻ
    POST   /api/contracts/{id}/save            chuyển sang "Lưu lại"
    DELETE /api/contracts/{id}                 gỡ / xoá hẳn
    POST   /api/contracts/{id}/run             {"op": summary|review|partial|law_changes|redline, unit_ids?, topics?}
    GET    /api/contracts/{id}/reports/{rid}.docx|.pdf

Hợp đồng không bao giờ đi /api/ingest hay vào kho tra cứu. Mỗi thao tác giữ một LegalRuntime (lease) suốt request.
Mọi thay đổi (tạo, bên, ngày ký, bố cục, chuyển đổi bản Phần 4) ghi vào nhật ký thao tác rồi dựng lại đồ thị trong
khóa ghi của hợp đồng; đồ thị lỗi chỉ báo trong thẻ (card["graph"]), không thành lỗi 5xx.
"""

from __future__ import annotations

import asyncio
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
from types import SimpleNamespace
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from rag.contracts import review as rv
from rag.contracts.doc import PageText, PartSpec, assemble
from rag.contracts.export import report_docx, report_pdf
from rag.contracts.facts import extract_facts
from rag.contracts.graph.oplog import OperationLog, human_op, machine_op
from rag.contracts.graph.service import ContractGraphService, GraphBusy
from rag.contracts.llm_json import ContractAIError
from rag.contracts.models import Contract
from rag.contracts.parse import DEMO_MAX_UNITS
from rag.contracts.parts import detect_parts
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
            "coverage": {"reviewed": min(len(c.units), DEMO_MAX_UNITS), "total": max(len(c.units), c.total_units)},
            "pages": c.pages,
            "reports": [{"rid": r["rid"], "op": r["op"], "created_at": r["created_at"]} for r in c.reports.values()],
            "parts": [{"part_id": p.part_id, "kind": p.kind, "title": p.title} for p in c.doc.parts] if c.doc else [],
            "parse_report": {"counts": dict(rep.counts) if rep else {}, "gaps": list(rep.gaps) if rep else [],
                             "warnings": list(rep.warnings) if rep else []},
            "graph": {"enabled": bool(g.get("enabled")), "published": bool(g.get("published")),
                      "build_id": g.get("build_id"), "error": g.get("error"),
                      "problems": list(g.get("problems") or [])}}


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
    texts = [PageText(p.page, p.text or "", type(p).__name__) for p in pages]
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


def _rebuild(c: Contract, now: datetime) -> None:
    """Gọi trong writing(cid): tách lại + dựng / công bố đồ thị; đơn vị = đơn vị cấp cao nhất (không cắt)."""
    doc, status = _graph().rebuild(c.contract_id, c.page_texts, c.oplog, file_checksum=c.file_checksum or "",
                                   now=now)
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

def create(data: bytes, filename: str, persist: bool) -> dict[str, Any]:
    pages, texts = _load_pages(data, filename)
    now = _now()
    c = Contract(secrets.token_urlsafe(18), Path(filename).name, persist, now, "", [], 0)
    _set_pages(c, data, pages, texts)
    c.oplog.add(_layout_op(c, now))
    c.units = to_contract_units(parse_contract(c.page_texts, [PartSpec(**p) for p in c.oplog.layout()]))
    try:
        extract_facts(CONFIG.llm_factory(), c)
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


def _layout_parts(text: str, raw) -> list[PartSpec]:
    """p0 luôn giữ; các phần người gửi thành phụ lục p1, p2… theo vị trí bắt đầu."""
    try:
        given = sorted(((int(p["start"]), str(p.get("title") or "")) for p in raw or []), key=lambda x: x[0])
    except (AttributeError, KeyError, TypeError, ValueError):
        raise ValueError(BAD_LAYOUT) from None
    starts = [s for s, _ in given]
    if any(not 0 < s < len(text) for s in starts) or len(set(starts)) != len(starts):
        raise ValueError(BAD_LAYOUT)
    return [PartSpec("p0", "main", "", 0, None)] + [PartSpec(f"p{i}", "appendix", title, start, None)
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
    Route("/api/contracts/{cid}/run", handle_run, methods=["POST"]),
    Route("/api/contracts/{cid}/reports/{rid}.{fmt}", handle_download, methods=["GET"]),
]
