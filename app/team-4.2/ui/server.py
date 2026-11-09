"""FastAPI / Starlette Web Server cho UI RAG Team 4.2.

Chạy server tại gốc repo:
    python app/team-4.2/ui/server.py
Hoặc:
    uvicorn app.team-4.2.ui.server:app --host 0.0.0.0 --port 8501 --reload

Endpoints:
    GET  /           -> Giao diện web Perplexity UI (index.html)
    GET  /upload     -> Trang nạp tài liệu + báo cáo chi tiết sau OCR (upload.html)
    GET  /api/ingest_reports            -> Danh sách báo cáo ingest đã lưu (tóm tắt)
    GET  /api/ingest_reports/{doc_id}   -> Báo cáo chi tiết: từng trang, độ tin cậy OCR, độ đầy đủ
    GET  /review     -> Trang duyệt kho luật có phiên bản (review.html)
    GET  /api/legal/reviews?status=open|resolved|all     -> Danh sách mục cần duyệt
    GET  /api/legal/reviews/{review_id}                  -> Chi tiết: chỉ dẫn gốc, thao tác, trước/sau
    POST /api/legal/reviews/{review_id}/decision         -> approve / reject / correct rồi dựng lại luật
    GET  /api/info   -> Danh sách bộ luật đã index, số chunk, thông tin mô hình
    POST /api/chat   -> Truy vấn RAG, trả lời + căn cứ pháp lý + thống kê ranking
    POST /api/ingest -> Tải lên file mới hoặc nạp URL luật vào kho
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
import logging
import threading
from pathlib import Path
import sys
from typing import Any

# Đảm bảo import được package rag khi chạy trực tiếp từ bất kỳ thư mục nào
_HERE = Path(__file__).resolve().parent
_TEAM_DIR = _HERE.parent
_SRC_DIR = _TEAM_DIR / "src"
_REPO_ROOT = _TEAM_DIR.parent.parent
for _p in (_SRC_DIR, _REPO_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import html
import json
import re
import time
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response, PlainTextResponse, RedirectResponse
from starlette.routing import Route

from rag.config import Settings
from rag.pipeline import AskTrace, IngestReport, RAGPipeline
from rag.quality.pii import MaskState

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("rag.ui.server")

# Thư mục gốc UI
UI_DIR = Path(__file__).resolve().parent
HTML_PATH = UI_DIR / "index.html"
UPLOAD_HTML_PATH = UI_DIR / "upload.html"
REVIEW_HTML_PATH = UI_DIR / "review.html"

_pipeline: RAGPipeline | None = None
_settings: Settings | None = None
_executor = ThreadPoolExecutor(max_workers=2)
_legal_service = None

# Bảng tra PII (placeholder <-> giá trị gốc) theo phiên chat, chỉ nằm trong RAM của server.
# Cùng một session_id -> cùng một khách hàng luôn là cùng placeholder qua các lượt hỏi.
_MAX_PII_SESSIONS = 500
_pii_states: OrderedDict[str, MaskState] = OrderedDict()
_pii_lock = threading.Lock()


def get_mask_state(session_id: str | None) -> MaskState:
    if not session_id:
        return RAGPipeline.new_query_mask_state()
    with _pii_lock:
        state = _pii_states.pop(session_id, None) or RAGPipeline.new_query_mask_state()
        _pii_states[session_id] = state          # đưa lên cuối = dùng gần nhất
        while len(_pii_states) > _MAX_PII_SESSIONS:
            _pii_states.popitem(last=False)
        return state


def get_pipeline() -> tuple[RAGPipeline, Settings]:
    global _pipeline, _settings
    if _pipeline is None:
        log.info("Khởi tạo RAGPipeline...")
        _settings = Settings.load()
        _pipeline = RAGPipeline.from_settings(_settings)
        log.info(
            "RAGPipeline sẵn sàng: %d chunks, %d docs",
            len(_pipeline.store),
            len(_pipeline.store.docs()),
        )
    return _pipeline, _settings


async def handle_index(request: Request) -> HTMLResponse:
    """Trả về file index.html."""
    if not HTML_PATH.exists():
        return HTMLResponse("<h1>index.html chưa được tạo</h1>", status_code=404)
    content = HTML_PATH.read_text(encoding="utf-8")
    return HTMLResponse(content)


async def handle_info(request: Request) -> JSONResponse:
    """Trả về thông tin kho tài liệu và cấu hình đang chạy."""
    pipeline, settings = get_pipeline()
    docs = pipeline.store.docs()
    adv_parts = []
    if settings.decomp_enabled:
        adv_parts.append("Decomposition")
    if settings.listwise_enabled:
        adv_parts.append("Gated Listwise")
    if settings.advanced:
        adv_parts.append(settings.advanced.upper())
    advanced_str = " + ".join(adv_parts) if adv_parts else "None"

    return JSONResponse({
        "status": "ready",
        "total_chunks": len(pipeline.store),
        "docs": [
            {
                "doc_id": d.doc_id,
                "source": d.source,
                "n_chunks": d.n_chunks,
            }
            for d in docs
        ],
        "settings": {
            "llm_model": settings.llm_model,
            "embed_model": settings.embed_model,
            "embed_dim": settings.embed_dim,
            "rerank_backend": settings.rerank_backend,
            "advanced": advanced_str,
            "decomp_enabled": settings.decomp_enabled,
            "listwise_enabled": settings.listwise_enabled,
            "context_min_p": settings.context_min_p,
            "top_k": settings.top_k,
            "ocr": settings.ocr_model if settings.ocr_engine.lower() == "gemini" else None,
        },
    })


def _format_hits(hits: list, chunks_map: dict, limit: int = 5) -> list[dict[str, Any]]:
    rows = []
    for h in hits[:limit]:
        c = chunks_map.get(h.chunk_id)
        rows.append({
            "rank": h.rank,
            "score": round(float(h.score), 4),
            "source": c.source if c else "",
            "section": c.section if c else "",
            "page": c.page_start if c else None,
            "text": " ".join(c.text.split())[:180] if c else "",
        })
    return rows


def _sync_ask(query: str, pipeline: RAGPipeline, mask_state: MaskState) -> dict[str, Any]:
    trace: AskTrace = pipeline.ask_debug(query, mask_state=mask_state)
    chunks = pipeline.retriever.chunks

    # Danh sách các khối context thực tế đưa vào LLM
    scores_map = {h.chunk_id: round(float(h.score), 4) for h in trace.retrieval.ranked}
    sources = []
    for b in trace.context.blocks:
        c = b.chunk
        score = scores_map.get(c.chunk_id, 0.0)
        sources.append({
            "n": b.n,
            "chunk_id": c.chunk_id,
            "source": c.source,
            "section": c.section or "Không có tiêu đề",
            "page": c.page_start,
            "score": score,
            "text": c.text,
        })

    # Citations thực tế trong câu trả lời
    citations = []
    for c in trace.answer.citations:
        chunk_obj = chunks.get(c.chunk_id)
        citations.append({
            "n": c.n,
            "chunk_id": c.chunk_id,
            "source": c.source,
            "section": chunk_obj.section if chunk_obj else "Căn cứ pháp lý",
            "page": c.page,
            "quote": c.quote,
            "score": scores_map.get(c.chunk_id, 0.0),
            "text": chunk_obj.text if chunk_obj else "",
        })

    # Chi tiết từng arm retrieval để minh bạch quá trình tra cứu
    res = trace.retrieval
    arms_data = {}
    for arm_name, arm_hits in res.arms.items():
        arms_data[arm_name] = _format_hits(arm_hits, chunks, limit=5)
    final_hits = _format_hits(res.hits, chunks, limit=5)

    return {
        "query": query,
        "answer": trace.answer.text,
        "refused": trace.answer.refused,
        "query_pii": trace.query_pii,          # số PII đã che trong câu hỏi trước khi gửi đi, theo loại
        "citations": citations,
        "sources": sources,
        "trace": {
            "context_mode": trace.context.mode,
            "n_context_blocks": len(trace.context.blocks),
            "reranked": res.reranked,
            "errors": res.errors,
            "arms": arms_data,
            "final_hits": final_hits,
        },
    }


async def handle_chat(request: Request) -> JSONResponse:
    """Xử lý câu hỏi, gọi ask_debug trong thread pool để không block event loop."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Body JSON không hợp lệ"}, status_code=400)

    query = (body.get("query") or "").strip()
    if not query:
        return JSONResponse({"error": "Câu hỏi không được rỗng"}, status_code=400)

    session_id = str(body.get("session_id") or "").strip()[:128] or None
    pipeline, _ = get_pipeline()
    loop = asyncio.get_running_loop()
    try:
        data = await loop.run_in_executor(
            _executor, _sync_ask, query, pipeline, get_mask_state(session_id)
        )
        return JSONResponse(data)
    except Exception as e:
        log.exception("Lỗi khi xử lý chat: %s", e)
        return JSONResponse({"error": f"Lỗi hệ thống: {e}"}, status_code=500)


# --- báo cáo ingest: lưu JSON theo doc_id để xem lại sau (text trong đó đã mask PII) ------------

_SAFE_ID = re.compile(r"[^A-Za-z0-9_.-]")


def _reports_dir(settings: Settings) -> Path:
    return settings.data_dir / "ingest_reports"


def _report_path(settings: Settings, doc_id: str) -> Path:
    return _reports_dir(settings) / f"{_SAFE_ID.sub('_', doc_id)[:120]}.json"


def _load_report(settings: Settings, doc_id: str) -> dict[str, Any] | None:
    path = _report_path(settings, doc_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("Không đọc được báo cáo ingest %s", path)
        return None


def _save_report(settings: Settings, row: dict[str, Any]) -> None:
    path = _report_path(settings, row["doc_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")


def _ingest_row(r: IngestReport, settings: Settings, origin: str | None = None) -> dict[str, Any]:
    """Kết quả ingest cho UI. Tài liệu đã có (skipped) thì trả báo cáo đã lưu của lần nạp trước.

    ``origin``: đường dẫn file đã upload / URL — để bước "Embedding" chạy lại ``prepare`` nếu server đã
    khởi động lại và mất bản đã trích xuất trong RAM (OCR lấy từ cache nên không tốn thêm)."""
    if r.skipped:
        stored = _load_report(settings, r.doc_id)
        if stored:
            return {**stored, "skipped": True, "indexed": True}
    row = {
        **r.to_dict(),
        # tên trường cũ mà index.html đang dùng
        "pages": r.n_pages, "chunks": r.n_chunks, "tables": r.n_tables,
        "ingested_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "origin": origin,
    }
    if r.indexed:
        row["indexed_at"] = row["ingested_at"]
    if not r.skipped:
        _save_report(settings, row)
    return row


def _report_overview(row: dict[str, Any]) -> dict[str, Any]:
    summary = row.get("summary") or {}
    return {
        "doc_id": row.get("doc_id"),
        "source": row.get("source"),
        "ingested_at": row.get("ingested_at"),
        "status": summary.get("status"),
        "completeness_pct": summary.get("completeness_pct"),
        "mean_confidence": summary.get("mean_confidence"),
        "pages_total": summary.get("pages_total", row.get("n_pages")),
        "ocr_pages": summary.get("ocr_pages", 0),
        "n_chunks": row.get("n_chunks"),
        "n_issues": len(row.get("quality_issues") or []),
        "indexed": row.get("indexed", True),      # báo cáo cũ (trước khi tách 2 bước) đều đã index
    }


async def handle_upload_page(request: Request) -> HTMLResponse:
    if not UPLOAD_HTML_PATH.exists():
        return HTMLResponse("<h1>upload.html chưa được tạo</h1>", status_code=404)
    return HTMLResponse(UPLOAD_HTML_PATH.read_text(encoding="utf-8"))


async def handle_list_reports(request: Request) -> JSONResponse:
    _, settings = get_pipeline()
    rows = []
    for path in _reports_dir(settings).glob("*.json"):
        try:
            rows.append(_report_overview(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError):
            continue
    rows.sort(key=lambda r: r.get("ingested_at") or "", reverse=True)
    return JSONResponse({"reports": rows})


async def handle_get_report(request: Request) -> JSONResponse:
    _, settings = get_pipeline()
    row = _load_report(settings, request.path_params["doc_id"])
    if row is None:
        return JSONResponse({"error": "Chưa có báo cáo cho tài liệu này"}, status_code=404)
    return JSONResponse(row)


async def handle_ingest(request: Request) -> JSONResponse:
    """Nạp file hoặc URL vào kho tài liệu."""
    pipeline, settings = get_pipeline()
    form = await request.form()
    url = form.get("url")
    files = form.getlist("files")

    if not url and not files:
        return JSONResponse({"error": "Cần cung cấp file hoặc URL để ingest"}, status_code=400)

    raw_dir = settings.data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    results = []

    # mode=prepare (trang upload): chỉ trích xuất / OCR + báo cáo; người dùng bấm "Embedding" sau.
    # mode=index (mặc định, ô upload trong trang chat): làm hết như trước.
    prepare_only = str(form.get("mode") or "index") == "prepare"

    def _do_ingest(target: str | Path, source_name: str | None):
        if not prepare_only:
            return pipeline.ingest(target, source=source_name)
        prepared = pipeline.prepare(target, source=source_name)
        if not prepared.report.skipped:
            _remember_prepared(prepared)
        return prepared.report

    loop = asyncio.get_running_loop()

    for f in files:
        if hasattr(f, "filename") and f.filename:
            content = await f.read()
            target_path = raw_dir / Path(f.filename).name
            target_path.write_bytes(content)
            try:
                r = await loop.run_in_executor(_executor, _do_ingest, target_path, f.filename)
                results.append(_ingest_row(r, settings, origin=str(target_path)))
            except Exception as e:
                results.append({"source": f.filename, "error": str(e)})

    if url and str(url).strip():
        u = str(url).strip()
        try:
            r = await loop.run_in_executor(_executor, _do_ingest, u, None)
            results.append(_ingest_row(r, settings, origin=u))
        except Exception as e:
            results.append({"source": u, "error": str(e)})

    return JSONResponse({"status": "ok", "results": results})


def _render_doc_html(title: str, filename: str, content: str, chunks_count: int | None = None) -> HTMLResponse:
    escaped_title = html.escape(title)
    escaped_filename = html.escape(filename)
    escaped_content = html.escape(content)
    badge = f"<span class='text-xs bg-neutral-100 text-neutral-600 px-2 py-0.5 rounded-full font-normal'>{chunks_count} chunks</span>" if chunks_count else ""

    doc_page = f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escaped_title} — Just-ice</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body {{
      font-family: 'Inter', -apple-system, sans-serif;
      background-color: #f7f7f8;
      color: #171717;
      line-height: 1.7;
    }}
    pre {{
      font-family: 'Inter', -apple-system, sans-serif;
      white-space: pre-wrap;
      word-break: break-word;
    }}
  </style>
</head>
<body class="py-8 px-4 sm:px-6">
  <div class="max-w-4xl mx-auto bg-white rounded-2xl border border-neutral-200 shadow-sm overflow-hidden">
    <!-- Header -->
    <header class="p-6 sm:p-8 border-b border-neutral-100 bg-white sticky top-0 z-10 backdrop-blur-sm bg-white/95 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div>
        <div class="flex items-center space-x-2">
          <span class="text-[11px] font-semibold text-teal-700 tracking-wider uppercase">Căn cứ quy phạm pháp luật</span>
          {badge}
        </div>
        <h1 class="text-xl sm:text-2xl font-bold text-neutral-900 mt-1">{escaped_title}</h1>
        <p class="text-xs text-neutral-500 mt-0.5">Tệp lưu trữ: {escaped_filename}</p>
      </div>
      <div class="flex items-center space-x-2">
        <button onclick="window.print()" class="px-3.5 py-1.5 text-xs font-medium border border-neutral-200 rounded-lg text-neutral-700 hover:bg-neutral-50 hover:text-black transition-colors flex items-center space-x-1.5">
          <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
          </svg>
          <span>In / Lưu PDF</span>
        </button>
      </div>
    </header>

    <!-- Content -->
    <main class="p-6 sm:p-10 text-[14.5px] leading-relaxed text-neutral-800 select-text">
      <pre>{escaped_content}</pre>
    </main>
  </div>
</body>
</html>"""
    return HTMLResponse(doc_page)


_GLOB_CHARS = set("*?[]")
_DOC_SUFFIXES = {".pdf", ".txt", ".md", ".docx", ".csv", ".tsv", ".xlsx", ".png", ".jpg", ".jpeg",
                 ".tif", ".tiff", ".webp", ".html"}
# cache/ chứa text OCR gốc CHƯA mask PII; indexes/ ingest_reports/ là dữ liệu nội bộ
_PRIVATE_DIRS = {"cache", "indexes", "ingest_reports", "ocr_bench", "_envs", "processed"}


def _find_doc_file(settings: Settings, filename: str) -> Path | None:
    """Tìm file nguồn theo TÊN FILE (không phải đường dẫn) trong thư mục dữ liệu.

    Chặn path traversal (``../../app/team-4.2/.env``, ``..\\``) và ký tự glob (``*.json``) vì route
    dùng ``{filename:path}`` và tên lấy thẳng từ URL. File tìm được phải nằm trong thư mục dữ liệu.
    """
    if (not filename or filename != Path(filename).name or "/" in filename or "\\" in filename
            or filename in {".", ".."} or _GLOB_CHARS & set(filename)):
        return None
    if Path(filename).suffix.lower() not in _DOC_SUFFIXES:     # không phục vụ cache/index/config
        return None
    roots = [settings.data_dir, Path("data/team-4.2")]
    candidates = [settings.data_dir / "raw" / filename, Path("data/team-4.2/raw") / filename,
                  settings.data_dir / filename, Path("data/team-4.2") / filename]
    candidates += [f for f in Path("data/team-4.2").rglob(filename) if not _PRIVATE_DIRS & set(f.parts)]
    for c in candidates:
        if c.is_file() and any(c.resolve().is_relative_to(r.resolve()) for r in roots) \
                and not _PRIVATE_DIRS & set(c.parts):
            return c
    return None


def _content_disposition(filename: str, kind: str = "inline") -> str:
    """Header chỉ nhận Latin-1: tên ASCII dự phòng + ``filename*`` UTF-8 theo RFC 5987/6266."""
    from urllib.parse import quote
    import unicodedata

    ascii_name = unicodedata.normalize("NFKD", filename.replace("đ", "d").replace("Đ", "D"))
    ascii_name = "".join(c for c in ascii_name if ord(c) < 128 and c not in '"\\') or "document"
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"


async def handle_view_doc(request: Request) -> Response:
    filename = request.path_params.get("filename", "").strip()
    if not filename:
        return HTMLResponse("<h1>Tên tài liệu không hợp lệ</h1>", status_code=400)

    # Nếu tài liệu là đường link (URL) -> mở ra đường link luôn
    if filename.startswith("http://") or filename.startswith("https://"):
        return RedirectResponse(filename, status_code=302)

    pipeline, settings = get_pipeline()
    target = _find_doc_file(settings, filename)

    clean_title = filename.replace(".txt", "").replace(".md", "").replace(".pdf", "").replace(".docx", "")
    clean_title = clean_title.replace("bo_luat_", "Bộ luật ").replace("luat_", "Luật ").replace("_", " ").title()

    if not target:
        matching_chunks = [c for c in pipeline.store.all() if c.source == filename]
        if not matching_chunks:
            return HTMLResponse(f"<h1>Không tìm thấy tài liệu: {html.escape(filename)}</h1>", status_code=404)
        full_text = "\n\n".join(c.text for c in matching_chunks)
        return _render_doc_html(clean_title, filename, full_text, len(matching_chunks))

    suffix = target.suffix.lower()
    if suffix == ".pdf":
        return Response(
            content=target.read_bytes(),
            media_type="application/pdf",
            headers={"Content-Disposition": _content_disposition(filename)}
        )

    content = target.read_text(encoding="utf-8", errors="replace")
    chunks_count = len([c for c in pipeline.store.all() if c.source == filename])
    return _render_doc_html(clean_title, filename, content, chunks_count=chunks_count or None)


async def handle_doc_content(request: Request) -> JSONResponse:
    """Trả về nội dung văn bản dưới dạng JSON để Canvas frontend highlight trích dẫn."""
    filename = request.path_params.get("filename", "").strip()
    if not filename:
        return JSONResponse({"error": "Tên tài liệu không hợp lệ"}, status_code=400)

    is_link = filename.startswith("http://") or filename.startswith("https://")
    pipeline, settings = get_pipeline()

    clean_title = filename.replace(".txt", "").replace(".md", "").replace(".pdf", "").replace(".docx", "")
    clean_title = clean_title.replace("bo_luat_", "Bộ luật ").replace("luat_", "Luật ").replace("_", " ").title()

    matching_chunks = [c for c in pipeline.store.all() if c.source == filename]

    content = ""
    if not is_link:
        target = _find_doc_file(settings, filename)
        if target and target.suffix.lower() != ".pdf":
            try:
                content = target.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass

    if not content and matching_chunks:
        content = "\n\n".join(c.text for c in matching_chunks)

    return JSONResponse({
        "source": filename,
        "title": clean_title,
        "content": content,
        "is_url": is_link,
        "n_chunks": len(matching_chunks),
    })


_IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
                 ".tif": "image/tiff", ".tiff": "image/tiff"}


def _load_extracted(pipeline: RAGPipeline, settings: Settings, doc_id: str) -> tuple[dict[str, Any] | None, bool]:
    """Toàn văn đã index theo trang. Tài liệu nạp trước khi có tính năng này: dựng lại từ chunk
    (gộp theo trang, có thể lặp đoạn do overlap) -> trả cờ ``rebuilt=True`` để UI ghi chú."""
    from rag.pipeline import extracted_path

    path = extracted_path(settings.data_dir / "extracted", doc_id)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8")), False
    chunks = pipeline.store.by_doc(doc_id) if hasattr(pipeline.store, "by_doc") else []
    if not chunks:
        return None, False
    by_page: dict[Any, list[str]] = OrderedDict()
    for c in chunks:
        by_page.setdefault(c.page_start, []).append(c.text)
    pages = [{"index": i, "page": page, "kind": "text", "text": "\n\n".join(texts)}
             for i, (page, texts) in enumerate(by_page.items())]
    return {"doc_id": doc_id, "source": chunks[0].source, "pages": pages}, True


async def handle_view_extracted(request: Request) -> HTMLResponse:
    """Toàn văn SAU OCR / trích xuất (đúng thứ đã index, đã che PII), đặt cạnh ảnh trang gốc."""
    doc_id = request.path_params.get("doc_id", "")
    pipeline, settings = get_pipeline()
    data, rebuilt = _load_extracted(pipeline, settings, doc_id)
    if data is None:
        return HTMLResponse(f"<h1>Chưa có bản trích xuất cho {html.escape(doc_id)}</h1>", status_code=404)
    report = _load_report(settings, doc_id) or {}
    details = {d.get("index"): d for d in report.get("pages_detail") or []}
    source = data.get("source") or report.get("source") or doc_id
    src_file = _find_doc_file(settings, source)
    has_image = src_file is not None and (src_file.suffix.lower() == ".pdf" or src_file.suffix.lower() in _IMAGE_TYPES)
    kind_label = {"text": "Text layer", "ocr": "OCR", "flagged": "Nghi vỡ dấu", "table": "Bảng", "empty": "Trống"}
    reason_label = {"empty": "trang scan", "bad_chars": "font cũ vỡ dấu", "image": "file ảnh"}

    cards = []
    n_review = 0
    for p in data["pages"]:
        d = details.get(p["index"], {})
        kind = d.get("kind", p.get("kind", "text"))
        issues = d.get("issues") or []
        review = bool(issues) or kind in ("flagged", "empty")
        n_review += review
        label = f"Trang {p['page']}" if p.get("page") else ("Bảng" if kind == "table" else "Văn bản")
        badges = [f"<span class='b'>{html.escape(kind_label.get(kind, kind))}</span>"]
        if kind == "ocr":
            conf = d.get("confidence")
            badges.append(f"<span class='b {'warn' if d.get('confidence_status') == 'low' else ''}'>"
                          f"Tin cậy {f'{conf:.1f}' if isinstance(conf, (int, float)) else 'không đo được'}</span>")
            if d.get("ocr_reason"):
                badges.append(f"<span class='b'>OCR vì {html.escape(reason_label.get(d['ocr_reason'], d['ocr_reason']))}</span>")
            if d.get("ocr_model"):
                badges.append(f"<span class='b'>{html.escape(d['ocr_model'])}</span>")
        badges += [f"<span class='b warn'>{html.escape(i.get('detail', i.get('code', '')))}</span>" for i in issues]
        image = ""
        if has_image and p.get("page") and kind != "table":
            img_url = f"/api/page_image/{quote(doc_id, safe='')}/{int(p['page'])}"
            image = (f"<a href='{img_url}' target='_blank'><img loading='lazy' src='{img_url}' "
                     f"alt='Ảnh {html.escape(label)}'></a>")
        text = p.get("text") or ""
        cards.append(f"""
<section id="p{p['index']}" class="card {'review' if review else ''}" data-review="{int(review)}">
  <header><h2>{html.escape(label)}</h2><div class="badges">{''.join(badges)}</div>
    <span class="count">{len(text.split())} từ</span></header>
  <div class="cols{'' if image else ' one'}">
    {f'<div class="img">{image}</div>' if image else ''}
    <pre>{html.escape(text) if text.strip() else '<i>Không có chữ</i>'}</pre>
  </div>
</section>""")

    note = ("<p class='note'>Tài liệu này nạp trước khi có bản trích xuất theo trang: nội dung được dựng lại từ "
            "các chunk đã index (có thể lặp đoạn do overlap). Nạp lại tài liệu để có bản chính xác.</p>"
            if rebuilt else "")
    page = f"""<!DOCTYPE html>
<html lang="vi"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bản trích xuất — {html.escape(source)}</title>
<style>
  :root {{ --bg:#fafafa; --card:#fff; --line:#e5e5e5; --text:#171717; --muted:#737373; --warn:#b45309; --warnbg:#fffbeb; }}
  * {{ box-sizing:border-box }} body {{ margin:0; font:14px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif; background:var(--bg); color:var(--text) }}
  .top {{ position:sticky; top:0; z-index:5; background:var(--card); border-bottom:1px solid var(--line); padding:12px 24px;
         display:flex; flex-wrap:wrap; gap:12px; align-items:center; justify-content:space-between }}
  .top h1 {{ font-size:16px; margin:0 }} .top .sub {{ color:var(--muted); font-size:12.5px }}
  .top a, .top button {{ font:inherit; font-size:12.5px; border:1px solid var(--line); background:var(--card); border-radius:8px;
         padding:5px 10px; color:var(--text); text-decoration:none; cursor:pointer }}
  .top button.on {{ background:var(--text); color:#fff; border-color:var(--text) }}
  main {{ max-width:1400px; margin:0 auto; padding:20px 24px 60px; display:flex; flex-direction:column; gap:16px }}
  .note {{ background:var(--warnbg); color:var(--warn); border:1px solid #fde68a; border-radius:10px; padding:10px 14px; margin:0 }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; overflow:hidden; scroll-margin-top:80px }}
  .card.review {{ border-color:#f59e0b }}
  .card header {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; padding:10px 16px; border-bottom:1px solid var(--line) }}
  .card h2 {{ font-size:14px; margin:0 8px 0 0 }} .badges {{ display:flex; flex-wrap:wrap; gap:6px; flex:1 }}
  .b {{ font-size:11.5px; background:#f5f5f5; border-radius:999px; padding:1px 8px; color:#404040 }}
  .b.warn {{ background:var(--warnbg); color:var(--warn) }} .count {{ color:var(--muted); font-size:12px }}
  .cols {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr) }} .cols.one {{ grid-template-columns:1fr }}
  .img {{ border-right:1px solid var(--line); background:#f5f5f5; padding:12px; max-height:80vh; overflow:auto }}
  .img img {{ width:100%; height:auto; display:block; background:#fff; box-shadow:0 1px 3px rgba(0,0,0,.12) }}
  pre {{ margin:0; padding:16px; white-space:pre-wrap; word-break:break-word; font:13.5px/1.7 ui-sans-serif,system-ui,"Segoe UI",sans-serif;
         max-height:80vh; overflow:auto }}
  body.only-review .card:not(.review) {{ display:none }}
  @media (max-width: 900px) {{ .cols {{ grid-template-columns:1fr }} .img {{ border-right:0; border-bottom:1px solid var(--line) }} }}
</style></head>
<body>
<div class="top">
  <div><h1>{html.escape(source)}</h1>
    <div class="sub">Bản trích xuất (sau OCR, bỏ header/footer, đã che PII) — đúng nội dung được embedding · {'đã trong kho tra cứu' if report.get('indexed', True) else 'CHƯA vào kho tra cứu'} · {len(data['pages'])} trang/phần · {n_review} cần xem</div></div>
  <div style="display:flex;gap:8px">
    <button id="flt" type="button">Chỉ trang cần xem ({n_review})</button>
    {f'<a href="/doc/{quote(source, safe="")}" target="_blank" rel="noopener">Mở file gốc</a>' if src_file else ''}
  </div>
</div>
<main>{note}{''.join(cards)}</main>
<script>
  const b = document.getElementById('flt');
  b.onclick = () => {{ document.body.classList.toggle('only-review'); b.classList.toggle('on'); }};
</script>
</body></html>"""
    return HTMLResponse(page)


async def handle_page_image(request: Request) -> Response:
    """Ảnh trang gốc (PDF render 1.5x, hoặc file ảnh) để đặt cạnh text trích xuất."""
    doc_id = request.path_params.get("doc_id", "")
    try:
        page_no = int(request.path_params.get("page", "0"))
    except ValueError:
        return Response(status_code=400)
    pipeline, settings = get_pipeline()
    data, _ = _load_extracted(pipeline, settings, doc_id)
    report = _load_report(settings, doc_id) or {}
    source = (data or {}).get("source") or report.get("source")
    src_file = _find_doc_file(settings, source) if source else None
    if src_file is None or page_no < 1:
        return Response(status_code=404)
    suffix = src_file.suffix.lower()
    headers = {"Cache-Control": "private, max-age=3600"}
    if suffix in _IMAGE_TYPES:
        return Response(src_file.read_bytes(), media_type=_IMAGE_TYPES[suffix], headers=headers)
    if suffix != ".pdf":
        return Response(status_code=404)
    import fitz

    def render() -> bytes | None:
        with fitz.open(src_file) as doc:
            if page_no > doc.page_count:
                return None
            return doc[page_no - 1].get_pixmap(matrix=fitz.Matrix(1.5, 1.5)).tobytes("png")

    png = await asyncio.get_running_loop().run_in_executor(None, render)
    return Response(png, media_type="image/png", headers=headers) if png else Response(status_code=404)


# --- bước 2 sau khi trích xuất: embedding / tải bản OCR / bỏ ------------------------------------

_PREPARED: OrderedDict[str, Any] = OrderedDict()      # doc_id -> PreparedDoc (RAM, tối đa 20)
_PREPARED_LOCK = threading.Lock()


def _remember_prepared(prepared: Any) -> None:
    with _PREPARED_LOCK:
        _PREPARED[prepared.report.doc_id] = prepared
        _PREPARED.move_to_end(prepared.report.doc_id)
        while len(_PREPARED) > 20:
            _PREPARED.popitem(last=False)


def _raw_upload(settings: Settings, origin: str | None) -> Path | None:
    """File upload nằm trong DATA_DIR/raw (không xoá / không đọc file ở chỗ khác)."""
    if not origin or origin.startswith(("http://", "https://")):
        return None
    path = Path(origin)
    raw = (settings.data_dir / "raw").resolve()
    return path if path.is_file() and path.resolve().is_relative_to(raw) else None


async def handle_index_doc(request: Request) -> JSONResponse:
    """Embedding + đưa tài liệu đã trích xuất vào kho tra cứu."""
    doc_id = request.path_params["doc_id"]
    pipeline, settings = get_pipeline()
    row = _load_report(settings, doc_id)
    if row is None:
        return JSONResponse({"error": "Chưa có báo cáo trích xuất cho tài liệu này"}, status_code=404)
    if row.get("indexed", True):
        return JSONResponse({**row, "indexed": True})
    with _PREPARED_LOCK:
        prepared = _PREPARED.pop(doc_id, None)

    def run():
        p = prepared
        if p is None:                                   # server đã khởi động lại: trích xuất lại (OCR cache)
            origin = row.get("origin") or ""
            target = origin if origin.startswith(("http://", "https://")) else _raw_upload(settings, origin)
            if target is None:
                raise FileNotFoundError("Không còn file đã upload để embedding; hãy upload lại")
            p = pipeline.prepare(target, source=row.get("source"))
        if p.report.doc_id != doc_id:
            raise ValueError("File đã thay đổi so với lần trích xuất; hãy upload lại")
        return pipeline.commit(p)

    try:
        report = await asyncio.get_running_loop().run_in_executor(_executor, run)
    except Exception as e:  # noqa: BLE001 — trả lỗi cho UI
        return JSONResponse({"error": str(e)}, status_code=400)
    row.update(indexed=True, n_chunks=report.n_chunks, chunks=report.n_chunks,
               indexed_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    _save_report(settings, row)
    return JSONResponse(row)


async def handle_download_extracted(request: Request) -> Response:
    """Tải bản đã OCR / trích xuất (đã che PII): ?format=md (mặc định) | txt | json."""
    doc_id = request.path_params["doc_id"]
    fmt = request.query_params.get("format", "md")
    pipeline, settings = get_pipeline()
    data, _ = _load_extracted(pipeline, settings, doc_id)
    if data is None or fmt not in {"md", "txt", "json"}:
        return Response(status_code=404)
    stem = Path(data.get("source") or doc_id).stem or doc_id
    if fmt == "json":
        body, media = json.dumps(data, ensure_ascii=False, indent=1), "application/json"
    else:
        nl = "\n"
        parts = [f"# {data.get('source')}{nl}" if fmt == "md" else f"{data.get('source')}{nl}"]
        for p in data["pages"]:
            label = f"Trang {p['page']}" if p.get("page") else ("Bảng" if p.get("kind") == "table" else "Nội dung")
            text = p.get("text", "")
            parts.append(f"{nl}## {label}{nl}{nl}{text}{nl}" if fmt == "md" else f"{nl}===== {label} ====={nl}{text}{nl}")
        body, media = "".join(parts), "text/markdown" if fmt == "md" else "text/plain"
    return Response(body.encode("utf-8"), media_type=f"{media}; charset=utf-8",
                    headers={"Content-Disposition": _content_disposition(f"{stem}_ocr.{fmt}", "attachment")})


async def handle_discard_doc(request: Request) -> JSONResponse:
    """Bỏ tài liệu CHƯA index: xoá báo cáo, bản trích xuất và file đã upload. Không đụng kho tra cứu."""
    from rag.pipeline import extracted_path

    doc_id = request.path_params["doc_id"]
    _, settings = get_pipeline()
    row = _load_report(settings, doc_id)
    if row is None:
        return JSONResponse({"error": "Không có tài liệu này"}, status_code=404)
    if row.get("indexed", True):
        return JSONResponse({"error": "Tài liệu đã ở trong kho tra cứu, không bỏ ở đây được"}, status_code=409)
    with _PREPARED_LOCK:
        _PREPARED.pop(doc_id, None)
    for path in (_report_path(settings, doc_id), extracted_path(settings.data_dir / "extracted", doc_id),
                 _raw_upload(settings, row.get("origin"))):
        if path is not None and path.is_file():
            path.unlink()
    return JSONResponse({"status": "discarded", "doc_id": doc_id})


# --- kho luật có phiên bản: duyệt -------------------------------------------------------------

def get_legal_service():
    """LegalService trên DATA_DIR/legal/catalog.sqlite (không cần khởi tạo RAG pipeline)."""
    global _legal_service
    if _legal_service is None:
        from rag.legal.service import LegalService
        from rag.legal.store import LegalStore

        _legal_service = LegalService(LegalStore(Settings.load().data_dir / "legal" / "catalog.sqlite"))
    return _legal_service


def _review_title(item, op) -> str:
    if op is not None:
        target = op.target
        where = ""
        if target is not None:
            where = f" → Điều {target.article}" + (f" khoản {target.clause}" if target.clause else "")                 + (f" điểm {target.point}" if target.point else "")
        return f"{op.source_locator} · {op.operation_type}{where}"
    return f"{item.kind} · {item.provision_id or item.document_key}"


def _sync_list_reviews(status: str | None) -> dict[str, Any]:
    from rag.legal.store import encode

    svc = get_legal_service()
    out = []
    for item in svc.store.review_items(status):
        op = svc.store.operation(item.operation_id) if item.operation_id else None
        row = encode(item)
        row.pop("payload", None)
        row["title"] = _review_title(item, op)
        row["target_law_name"] = op.target_law_name if op else None
        out.append(row)
    return {"items": out}


async def handle_list_reviews(request: Request) -> JSONResponse:
    status = request.query_params.get("status", "open")
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(_executor, _sync_list_reviews, None if status == "all" else status)
    return JSONResponse(data)


def _sync_review_detail(review_id: str) -> dict[str, Any] | None:
    from datetime import timedelta

    from rag.legal.keys import provision_id
    from rag.legal.store import encode

    svc = get_legal_service()
    item = svc.store.review_item(review_id)
    if item is None:
        return None
    op = svc.store.operation(item.operation_id) if item.operation_id else None
    data = encode(item)
    data["operation"] = encode(op) if op else None
    data["source_excerpt"] = item.payload.get("source_excerpt")
    data["target_before"] = data["target_after"] = None
    if op is not None:
        data["target_after"] = op.new_text
        if op.target is not None and op.target_document_key and op.effective_from:
            kind = ("article_title" if op.target.part == "title" else "clause_lead_in" if op.target.part == "lead_in"
                    else "point" if op.target.point else "clause" if op.target.clause else "article")
            pid = provision_id(op.target_document_key, op.target, kind)
            before = [v for v in svc.store.provisions_as_of(op.target_document_key, op.effective_from - timedelta(days=1))
                      if v.provision_id == pid]
            data["target_before"] = before[0].text if before else None
    if item.kind == "vbhn_mismatch":
        data["vbhn"] = item.payload
    return data


async def handle_review_detail(request: Request) -> JSONResponse:
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(_executor, _sync_review_detail, request.path_params["review_id"])
    if data is None:
        return JSONResponse({"error": "Không có mục duyệt này"}, status_code=404)
    return JSONResponse(data)


async def handle_review_decision(request: Request) -> JSONResponse:
    from datetime import datetime, timezone

    from rag.legal.models import ReviewDecision
    from rag.legal.service import ReviewClosedError

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Body JSON không hợp lệ"}, status_code=400)
    reviewer, note = str(body.get("reviewer") or "").strip(), str(body.get("note") or "").strip()
    if not reviewer or not note:
        return JSONResponse({"error": "Cần tên người duyệt và ghi chú"}, status_code=400)
    decision = ReviewDecision(request.path_params["review_id"], body.get("action"), reviewer, note,
                              body.get("corrected_fields") or {}, datetime.now(timezone.utc))
    loop = asyncio.get_running_loop()
    try:
        run = await loop.run_in_executor(_executor, get_legal_service().decide, decision)
    except ReviewClosedError as e:
        return JSONResponse({"error": str(e)}, status_code=409)
    except KeyError:
        return JSONResponse({"error": "Không có mục duyệt này"}, status_code=404)
    except (ValueError, TypeError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"status": "ok", "build_id": run.build_id if run else None})


async def handle_review_page(request: Request) -> HTMLResponse:
    if not REVIEW_HTML_PATH.exists():
        return HTMLResponse("<h1>review.html chưa được tạo</h1>", status_code=404)
    return HTMLResponse(REVIEW_HTML_PATH.read_text(encoding="utf-8"))


routes = [
    Route("/api/index/{doc_id}", handle_index_doc, methods=["POST"]),
    Route("/api/discard/{doc_id}", handle_discard_doc, methods=["POST"]),
    Route("/api/extracted/{doc_id}/download", handle_download_extracted, methods=["GET"]),
    Route("/extracted/{doc_id}", handle_view_extracted, methods=["GET"]),
    Route("/api/page_image/{doc_id}/{page}", handle_page_image, methods=["GET"]),
    Route("/", handle_index, methods=["GET"]),
    Route("/upload", handle_upload_page, methods=["GET"]),
    Route("/review", handle_review_page, methods=["GET"]),
    Route("/api/legal/reviews", handle_list_reviews, methods=["GET"]),
    Route("/api/legal/reviews/{review_id:path}/decision", handle_review_decision, methods=["POST"]),
    Route("/api/legal/reviews/{review_id:path}", handle_review_detail, methods=["GET"]),
    Route("/api/ingest_reports", handle_list_reports, methods=["GET"]),
    Route("/api/ingest_reports/{doc_id:path}", handle_get_report, methods=["GET"]),
    Route("/api/info", handle_info, methods=["GET"]),
    Route("/api/chat", handle_chat, methods=["POST"]),
    Route("/api/ingest", handle_ingest, methods=["POST"]),
    Route("/api/doc_content/{filename:path}", handle_doc_content, methods=["GET"]),
    Route("/doc/{filename:path}", handle_view_doc, methods=["GET"]),
]

middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
]

app = Starlette(debug=True, routes=routes, middleware=middleware)

if __name__ == "__main__":
    import uvicorn

    log.info("Chạy server tại http://127.0.0.1:8501 ...")
    uvicorn.run(app, host="127.0.0.1", port=8501, log_level="info")
