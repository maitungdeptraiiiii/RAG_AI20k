"""FastAPI / Starlette Web Server cho UI RAG Team 4.2.

Chạy server tại gốc repo:
    python app/team-4.2/ui/server.py
Hoặc:
    uvicorn app.team-4.2.ui.server:app --host 0.0.0.0 --port 8501 --reload

Endpoints:
    GET  /           -> Giao diện web Perplexity UI (index.html)
    GET  /api/info   -> Danh sách bộ luật đã index, số chunk, thông tin mô hình
    POST /api/chat   -> Truy vấn RAG, trả lời + căn cứ pháp lý + thống kê ranking
    POST /api/ingest -> Tải lên file mới hoặc nạp URL luật vào kho
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
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
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response, PlainTextResponse
from starlette.routing import Route

from rag.config import Settings
from rag.pipeline import AskTrace, RAGPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("rag.ui.server")

# Thư mục gốc UI
UI_DIR = Path(__file__).resolve().parent
HTML_PATH = UI_DIR / "index.html"

_pipeline: RAGPipeline | None = None
_settings: Settings | None = None
_executor = ThreadPoolExecutor(max_workers=2)


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


def _sync_ask(query: str, pipeline: RAGPipeline) -> dict[str, Any]:
    trace: AskTrace = pipeline.ask_debug(query)
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

    pipeline, _ = get_pipeline()
    loop = asyncio.get_running_loop()
    try:
        data = await loop.run_in_executor(_executor, _sync_ask, query, pipeline)
        return JSONResponse(data)
    except Exception as e:
        log.exception("Lỗi khi xử lý chat: %s", e)
        return JSONResponse({"error": f"Lỗi hệ thống: {e}"}, status_code=500)


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

    def _do_ingest(target: str | Path, source_name: str | None):
        return pipeline.ingest(target, source=source_name)

    loop = asyncio.get_running_loop()

    for f in files:
        if hasattr(f, "filename") and f.filename:
            content = await f.read()
            target_path = raw_dir / Path(f.filename).name
            target_path.write_bytes(content)
            try:
                r = await loop.run_in_executor(_executor, _do_ingest, target_path, f.filename)
                results.append({
                    "source": r.source,
                    "pages": r.n_pages,
                    "chunks": r.n_chunks,
                    "skipped": r.skipped,
                    "empty_pages": r.empty_pages,
                })
            except Exception as e:
                results.append({"source": f.filename, "error": str(e)})

    if url and str(url).strip():
        u = str(url).strip()
        try:
            r = await loop.run_in_executor(_executor, _do_ingest, u, None)
            results.append({
                "source": r.source,
                "pages": r.n_pages,
                "chunks": r.n_chunks,
                "skipped": r.skipped,
                "empty_pages": r.empty_pages,
            })
        except Exception as e:
            results.append({"source": u, "error": str(e)})

    return JSONResponse({"status": "ok", "results": results})


VBPL_OFFICIAL_DOCS = {
    "bo_luat_dan_su_2015.txt": {
        "url": "https://vbpl.vn/van-ban/chi-tiet/95942",
        "doc_number": "91/2015/QH13",
        "title": "Bộ luật Dân sự 2015",
        "authority": "Quốc hội khóa XIII",
    },
    "bo_luat_hinh_su_2015.txt": {
        "url": "https://vbpl.vn/van-ban/chi-tiet/96122",
        "doc_number": "100/2015/QH13",
        "title": "Bộ luật Hình sự 2015",
        "authority": "Quốc hội khóa XIII",
    },
    "bo_luat_to_tung_dan_su_2015.txt": {
        "url": "https://vbpl.vn/van-ban/chi-tiet/96115",
        "doc_number": "92/2015/QH13",
        "title": "Bộ luật Tố tụng dân sự 2015",
        "authority": "Quốc hội khóa XIII",
    },
    "bo_luat_to_tung_hinh_su_2015.txt": {
        "url": "https://vbpl.vn/van-ban/chi-tiet/96172",
        "doc_number": "101/2015/QH13",
        "title": "Bộ luật Tố tụng hình sự 2015",
        "authority": "Quốc hội khóa XIII",
    },
    "bo_luat_lao_dong_2019.txt": {
        "url": "https://vbpl.vn/van-ban/chi-tiet/139264",
        "doc_number": "45/2019/QH14",
        "title": "Bộ luật Lao động 2019",
        "authority": "Quốc hội khóa XIV",
    },
    "bo_luat_hang_hai_2015.txt": {
        "url": "https://vbpl.vn/van-ban/chi-tiet/96117",
        "doc_number": "95/2015/QH13",
        "title": "Bộ luật Hàng hải Việt Nam 2015",
        "authority": "Quốc hội khóa XIII",
    },
}


def _render_doc_html(title: str, filename: str, content: str, vbpl_meta: dict | None = None) -> HTMLResponse:
    escaped_title = html.escape(title)
    escaped_filename = html.escape(filename)
    escaped_content = html.escape(content)
    is_markdown = filename.lower().endswith(".md")

    vbpl_button = ""
    vbpl_badge = ""
    if vbpl_meta:
        doc_num = html.escape(vbpl_meta.get("doc_number", ""))
        vbpl_url = html.escape(vbpl_meta.get("url", "#"))
        authority = html.escape(vbpl_meta.get("authority", "Quốc hội"))
        vbpl_badge = f"""
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-[11px] font-semibold text-emerald-800 bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full uppercase tracking-wider">Căn cứ quy phạm pháp luật</span>
            <span class="text-[11px] font-medium text-neutral-600 bg-neutral-100 px-2 py-0.5 rounded-md">Số: {doc_num}</span>
            <span class="text-[11px] text-neutral-500">Ban hành: {authority}</span>
          </div>
        """
        vbpl_button = f"""
          <a href="{vbpl_url}" target="_blank" rel="noopener noreferrer" class="px-3.5 py-2 text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg shadow-sm flex items-center space-x-1.5 transition-colors">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
            <span>Mở văn bản gốc trên vbpl.vn ↗</span>
          </a>
        """
    else:
        vbpl_badge = """
          <div class="flex items-center space-x-2">
            <span class="text-[11px] font-semibold text-blue-700 bg-blue-50 border border-blue-200 px-2.5 py-0.5 rounded-full uppercase tracking-wider">Tài liệu nạp người dùng</span>
          </div>
        """

    content_render = f"""
      <div id="markdown-container" class="prose max-w-none text-[15px] leading-relaxed text-neutral-800"></div>
      <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
      <script>
        document.getElementById('markdown-container').innerHTML = marked.parse({json.dumps(content)});
      </script>
    """ if is_markdown else f"""
      <pre class="text-[14.5px] leading-relaxed text-neutral-800 whitespace-pre-wrap select-text font-sans">{escaped_content}</pre>
    """

    doc_page = f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escaped_title} — VinAI Legal</title>
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
  </style>
</head>
<body class="py-8 px-4 sm:px-6">
  <div class="max-w-4xl mx-auto bg-white rounded-2xl border border-neutral-200 shadow-sm overflow-hidden">
    <!-- Header -->
    <header class="p-6 sm:p-8 border-b border-neutral-100 bg-white sticky top-0 z-10 backdrop-blur-sm bg-white/95 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div>
        {vbpl_badge}
        <h1 class="text-xl sm:text-2xl font-bold text-neutral-900 mt-1">{escaped_title}</h1>
        <p class="text-xs text-neutral-500 mt-0.5">Tệp lưu trữ: {escaped_filename}</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        {vbpl_button}
        <a href="/doc/{escaped_filename}?download=1" download="{escaped_filename}" class="px-3 py-2 text-xs font-medium border border-neutral-200 rounded-lg text-neutral-700 hover:bg-neutral-50 hover:text-black transition-colors flex items-center space-x-1.5">
          <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          <span>Tải file gốc</span>
        </a>
        <button onclick="window.print()" class="px-3 py-2 text-xs font-medium border border-neutral-200 rounded-lg text-neutral-700 hover:bg-neutral-50 hover:text-black transition-colors flex items-center space-x-1.5">
          <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
          </svg>
          <span>In</span>
        </button>
      </div>
    </header>

    <!-- Content -->
    <main class="p-6 sm:p-10 text-[14.5px] leading-relaxed text-neutral-800 select-text">
      {content_render}
    </main>
  </div>
</body>
</html>"""
    return HTMLResponse(doc_page)


async def handle_view_doc(request: Request) -> Response:
    filename = request.path_params.get("filename", "").strip()
    if not filename:
        return HTMLResponse("<h1>Tên tài liệu không hợp lệ</h1>", status_code=400)

    # Check if download requested
    download = request.query_params.get("download") == "1"

    pipeline, settings = get_pipeline()
    candidates = [
        settings.data_dir / "raw" / filename,
        Path("data/team-4.2/raw") / filename,
        settings.data_dir / filename,
        Path("data/team-4.2") / filename,
    ]
    target: Path | None = None
    for c in candidates:
        if c.exists() and c.is_file():
            target = c
            break

    if not target:
        for f in Path("data/team-4.2").rglob(filename):
            if f.is_file():
                target = f
                break

    clean_title = filename.replace(".txt", "").replace(".md", "").replace(".pdf", "").replace(".docx", "")
    clean_title = clean_title.replace("bo_luat_", "Bộ luật ").replace("luat_", "Luật ").replace("_", " ").title()
    vbpl_meta = VBPL_OFFICIAL_DOCS.get(filename)
    if vbpl_meta:
        clean_title = vbpl_meta["title"]

    if not target:
        matching_chunks = [c for c in pipeline.store.all() if c.source == filename]
        if not matching_chunks:
            return HTMLResponse(f"<h1>Không tìm thấy tài liệu: {html.escape(filename)}</h1>", status_code=404)
        full_text = "\n\n".join(c.text for c in matching_chunks)
        if download:
            return Response(
                content=full_text.encode("utf-8"),
                media_type="text/plain; charset=utf-8",
                headers={"Content-Disposition": f"attachment; filename=\"{filename}\""}
            )
        return _render_doc_html(clean_title, filename, full_text, vbpl_meta=vbpl_meta)

    suffix = target.suffix.lower()
    if suffix == ".pdf":
        disposition = "attachment" if download else "inline"
        return Response(
            content=target.read_bytes(),
            media_type="application/pdf",
            headers={"Content-Disposition": f"{disposition}; filename=\"{filename}\""}
        )

    if download:
        return Response(
            content=target.read_bytes(),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename=\"{filename}\""}
        )

    content = target.read_text(encoding="utf-8", errors="replace")
    return _render_doc_html(clean_title, filename, content, vbpl_meta=vbpl_meta)


routes = [
    Route("/", handle_index, methods=["GET"]),
    Route("/api/info", handle_info, methods=["GET"]),
    Route("/api/chat", handle_chat, methods=["POST"]),
    Route("/api/ingest", handle_ingest, methods=["POST"]),
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
