"""HTTP cho phần 4 — đính kèm hợp đồng trong chat (spec 2026-11-11-contract-review-design.md).

    POST   /api/contracts                      multipart file + persist=0|1 -> thẻ hợp đồng
    GET    /api/contracts?ids=a,b              các hợp đồng đã lưu mà trình duyệt đang giữ id
    GET    /api/contracts/{id}                 thẻ hợp đồng
    POST   /api/contracts/{id}/party           {"party": "neutral" | vai trò}
    POST   /api/contracts/{id}/sign-date       {"date": "YYYY-MM-DD"} (nguồn: người dùng nhập)
    POST   /api/contracts/{id}/save            chuyển sang "Lưu lại"
    DELETE /api/contracts/{id}                 gỡ / xoá hẳn
    POST   /api/contracts/{id}/run             {"op": summary|review|partial|law_changes|redline, unit_ids?, topics?}
    GET    /api/contracts/{id}/reports/{rid}.docx|.pdf

Hợp đồng không bao giờ đi /api/ingest hay vào kho tra cứu. Mỗi thao tác giữ một LegalRuntime (lease) suốt request.
"""

from __future__ import annotations

import asyncio
import logging
import re
import secrets
import unicodedata
from urllib.parse import quote as _urlquote
import tempfile
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from rag.contracts import review as rv
from rag.contracts.export import report_docx, report_pdf
from rag.contracts.facts import extract_facts
from rag.contracts.llm_json import ContractAIError
from rag.contracts.models import Contract
from rag.contracts.parse import limit_units, split_units
from rag.contracts.store import ContractStore

log = logging.getLogger("rag.ui.contracts")

MAX_BYTES = 50 * 1024 * 1024
ALLOWED = {".pdf", ".docx", ".txt", ".md", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}
GONE = "Hợp đồng này đã hết phiên — hãy đính kèm lại"
OPS = ("summary", "review", "partial", "law_changes", "redline")


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
)
_store: ContractStore | None = None


def reset() -> None:
    global _store
    _store = None


def store() -> ContractStore:
    global _store
    if _store is None:
        root = CONFIG.root() if callable(CONFIG.root) else CONFIG.root
        _store = ContractStore(Path(root))
    return _store


def _ctx(runtime) -> rv.ReviewContext:
    return rv.ReviewContext(CONFIG.llm_factory(), runtime, CONFIG.legacy_search, CONFIG.today())


def card(c: Contract) -> dict[str, Any]:
    return {"contract_id": c.contract_id, "filename": c.filename, "persist": c.persist,
            "created_at": c.created_at.isoformat(), "facts": c.facts, "party": c.party,
            "sign_date": c.sign_date.isoformat() if c.sign_date else None, "sign_date_source": c.sign_date_source,
            "units": [{"uid": u.uid, "label": u.label} for u in c.units],
            "coverage": {"reviewed": len(c.units), "total": c.total_units}, "pages": c.pages,
            "reports": [{"rid": r["rid"], "op": r["op"], "created_at": r["created_at"]} for r in c.reports.values()]}


# --- đồng bộ (chạy ngoài event loop) -------------------------------------------------------------

def create(data: bytes, filename: str, persist: bool) -> dict[str, Any]:
    from rag.ingest.loaders import load_source

    suffix = Path(filename).suffix.lower()
    with tempfile.TemporaryDirectory() as tmp:          # file tạm xoá ngay sau khi đọc
        path = Path(tmp) / f"upload{suffix}"
        path.write_bytes(data)
        pages = load_source(path, source=filename, ocr=CONFIG.ocr_factory())
    text = "\n\n".join(p.text for p in pages if p.text and p.text.strip())
    if not text.strip():
        raise ValueError("Không đọc được nội dung hợp đồng (file trống hoặc ảnh không OCR được)")
    units, total = limit_units(split_units(text))
    c = Contract(secrets.token_urlsafe(18), Path(filename).name, persist, datetime.now(timezone.utc), text, units,
                 total, pages=[{"page": p.page, "chars": len(p.text or ""), "kind": type(p).__name__}
                               for p in pages])
    try:
        extract_facts(CONFIG.llm_factory(), c)
    except ContractAIError as e:
        c.facts = {"type": "chưa rõ", "parties": [], "error": str(e)}
    store().add(c, original=data, suffix=suffix)
    return card(c)


def get(cid: str) -> Contract:
    return store().get(cid)


def set_party(cid: str, party: str) -> dict[str, Any]:
    c = get(cid)
    roles = {p.get("role") for p in c.facts.get("parties") or []}
    if party != "neutral" and party not in roles:
        raise ValueError("Bên không có trong hợp đồng")
    c.party = party
    store().update(c)
    return card(c)


def set_sign_date(cid: str, value: str) -> dict[str, Any]:
    try:
        day = date.fromisoformat(str(value))
    except ValueError:
        raise ValueError("Ngày ký phải dạng YYYY-MM-DD") from None
    c = get(cid)
    c.sign_date, c.sign_date_source = day, "user"
    store().update(c)
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
    except ContractAIError as e:
        return _error(str(e), 502)
    except ValueError as e:
        return _error(str(e), 400)
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
        for cid in ids:
            try:
                out.append(card(get(cid)))
            except KeyError:
                continue
        return {"contracts": out}
    return await _call(listed)


async def handle_get(request: Request) -> Response:
    return await _call(lambda: card(get(request.path_params["cid"])))


async def handle_party(request: Request) -> Response:
    body = await _json(request)
    return await _call(set_party, request.path_params["cid"], str(body.get("party") or ""))


async def handle_sign_date(request: Request) -> Response:
    body = await _json(request)
    return await _call(set_sign_date, request.path_params["cid"], str(body.get("date") or ""))


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
    Route("/api/contracts/{cid}/run", handle_run, methods=["POST"]),
    Route("/api/contracts/{cid}/reports/{rid}.{fmt}", handle_download, methods=["GET"]),
]
