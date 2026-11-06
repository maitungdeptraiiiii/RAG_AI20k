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

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
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
            "advanced": settings.advanced,
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
    citations = [
        {
            "n": c.n,
            "chunk_id": c.chunk_id,
            "source": c.source,
            "page": c.page,
            "quote": c.quote,
        }
        for c in trace.answer.citations
    ]

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


routes = [
    Route("/", handle_index, methods=["GET"]),
    Route("/api/info", handle_info, methods=["GET"]),
    Route("/api/chat", handle_chat, methods=["POST"]),
    Route("/api/ingest", handle_ingest, methods=["POST"]),
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
