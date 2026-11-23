"""Additive, real-data API and static frontend for Contract Studio.

Reuses the existing contract operations. Visualization is a read-only projection
of a build, never a second parser or model-generated graph.
"""
from __future__ import annotations

import json
import secrets
import threading
from dataclasses import asdict
from pathlib import Path

from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles

import contracts_api as api
from rag.contracts import verify
from rag.contracts.graph.build import build_graph, graph_mask_state
from rag.bridge.catalog import load_catalog

DIST = Path(__file__).resolve().parent.parent / "contract-studio" / "dist"
_locks_guard = threading.Lock()
_running: set[str] = set()


def _fact_label_or_blank(catalog, name) -> str:
    label = catalog.fact_label(name) if name else ""
    return "" if label == name else label


def snapshot(cid: str) -> dict:
    c = api.get(cid)
    catalog = api._catalog_or_labor(c)
    build, doc = build_graph(cid, c.page_texts, c.oplog,
                            file_checksum=c.file_checksum or "", built_at=api._now(), catalog=catalog)
    state = graph_mask_state(doc)
    # This API is for the owner viewing their uploaded document. Restore only
    # this contract's placeholders, as the existing graph Q&A UI does.
    def strings(value):
        if isinstance(value, str):
            return state.unmask(value)
        if isinstance(value, dict):
            return {k: strings(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [strings(v) for v in value]
        return value
    return {"card": api.card(c), "document": {
                "pages": [asdict(p) for p in c.page_texts],
                "parts": [asdict(p) for p in doc.parts],
                "units": [asdict(u) for u in doc.units]},
            "graph": {"build_id": build.build_id,
                      "nodes": [{"node_id": n.node_id, "node_type": n.label, **strings(n.props),
                                 "display_label": (catalog.concepts[n.props["concept_id"]].label
                                                   if n.props.get("concept_id") in catalog.concepts else
                                                   _fact_label_or_blank(catalog, n.props.get("name")))} for n in build.nodes],
                      "edges": [strings(asdict(e)) for e in build.edges]},
            "last_check": api.last_concept_check(cid) if c.concept_check else None}


def stream_work(fn, *, cid=None):
    run_id = secrets.token_urlsafe(12)
    def work(emit):
        seq = 0
        lock = threading.Lock()
        def send(event):
            nonlocal seq
            with lock:
                seq += 1
                emit({**event, "run_id": run_id, "sequence": seq, "contract_id": cid})
        if cid:
            with _locks_guard:
                if cid in _running:
                    raise api.GraphBusy()
                _running.add(cid)
        try:
            return {**fn(send), "run_id": run_id}
        finally:
            if cid:
                with _locks_guard:
                    _running.discard(cid)
    return api._sse_queue(api._events(work, f"contract-studio-{run_id}"))


async def upload(request):
    form = await request.form(max_part_size=api.MAX_BYTES)
    file = form.get("file")
    if not file or not getattr(file, "filename", None):
        return JSONResponse({"error": "Hãy chọn file hợp đồng"}, status_code=400)
    data = await file.read(api.MAX_BYTES + 1)
    if len(data) > api.MAX_BYTES:
        return JSONResponse({"error": "File quá lớn: tối đa 50 MB"}, status_code=413)
    persist = str(form.get("persist") or "0") in ("1", "true", "on")
    def run(emit):
        card = api.create(data, file.filename, persist, on_event=emit)
        return snapshot(card["contract_id"])
    return stream_work(run)


async def get_snapshot(request):
    return await api._call(snapshot, request.path_params["cid"])


async def analyze(request):
    cid = request.path_params["cid"]
    body = await api._json(request)
    def run(emit):
        c = api.get(cid)
        verify.check_gate(c, "review")
        emit({"type": "snapshot", **snapshot(cid)})
        result = api.concept_check(cid, body.get("user_facts") or {}, on_event=emit)
        return {**snapshot(cid), "result": result}
    return stream_work(run, cid=cid)


async def index(request):
    if not (DIST / "index.html").is_file():
        return JSONResponse({"error": "Contract Studio chưa build. Chạy npm install và npm run build trong app/team-4.2/contract-studio."}, status_code=503)
    return FileResponse(DIST / "index.html")


_REPORT_SYSTEM = (
    "Bạn là chuyên gia pháp lý lao động Việt Nam. Hãy tổng hợp kết quả kiểm tra hợp đồng "
    "thành một bản báo cáo có cấu trúc rõ ràng, văn phong chuyên nghiệp nhưng dễ hiểu cho người không chuyên. "
    "CHỈ dùng thông tin, điều khoản và căn cứ luật được cung cấp trong dữ liệu đầu vào — tuyệt đối không bịa thêm số liệu hay điều luật.\n\n"
    "Trình bày bằng Markdown sạch với đúng 5 mục:\n"
    "## 1. Tóm tắt tổng quan\n"
    "(Nêu loại hợp đồng, ngày áp luật, đánh giá chung và 1-2 rủi ro lớn nhất nếu có.)\n"
    "## 2. Điểm vi phạm & Thiếu sót cần ưu tiên xử lý\n"
    "(Nếu có mục vi phạm/thiếu/mâu thuẫn: liệt kê từng mục gồm Điều khoản hợp đồng vs Quy định luật áp dụng và Đề xuất sửa cụ thể. Nếu không có, ghi rõ chưa phát hiện vi phạm.)\n"
    "## 3. Quyền lợi & Nội dung cần xác minh thêm\n"
    "(Tóm tắt quyền lợi luật định hợp đồng chưa nhắc tới hoặc các điểm còn thiếu dữ kiện để kết luận.)\n"
    "## 4. Các nội dung đã phù hợp quy định\n"
    "(Liệt kê ngắn gọn theo gạch đầu dòng các hạng mục đạt chuẩn.)\n"
    "## 5. Khuyến nghị hành động tiếp theo\n"
    "(Danh sách 2-4 bước cụ thể nên làm trước khi ký hoặc trong quá trình thực hiện hợp đồng.)"
)


def _fallback_structured_report(c, res: dict, catalog) -> str:
    rep = res.get("report") or {}
    views = res.get("views") or []
    day = rep.get("day") or (c.sign_date.isoformat() if c.sign_date else "chưa rõ")
    issues = [v for v in views if v.get("finding") in ("violation", "missing_content", "conflict")]
    notes = [v for v in views if v.get("finding") in ("hidden_right", "possible_right", "needs_facts")]
    ok_items = [v for v in views if v.get("finding") == "ok"]

    lines = [
        f"# Báo cáo rà soát hợp đồng: {c.filename}",
        "",
        f"> **Ngày áp dụng pháp luật:** {day} · **Tổng quy tắc kiểm tra:** {len(views)}",
        "",
        "## 1. Tóm tắt tổng quan",
        f"Hệ thống đã kiểm tra **{len(views)}** quy tắc đối chiếu giữa điều khoản hợp đồng và Legal Graph tại mốc `{day}`. "
        f"Kết quả ghi nhận **{len(issues)}** điểm cần chỉnh sửa/bổ sung ngay, **{len(notes)}** điểm cần lưu ý/xác minh thêm và **{len(ok_items)}** hạng mục đạt chuẩn.",
        "",
        "## 2. Điểm vi phạm & Thiếu sót cần ưu tiên xử lý",
    ]
    if not issues:
        lines.append("- Chưa phát hiện điểm vi phạm hoặc thiếu nội dung bắt buộc.")
    else:
        for item in issues:
            v = item.get("view") or {}
            title = v.get("title") or item.get("concept_id")
            verdict = catalog.verdict_label(item.get("finding"))
            quotes = "; ".join(
                f"[{ct.get('label') or 'Đoạn'}] “{ct.get('quote')}”"
                for ct in (v.get("contract") or []) if ct.get("quote")
            ) or "Hợp đồng chưa nêu rõ nội dung này."
            laws = "; ".join(
                l.get("citation") or l.get("pid") or ""
                for l in (v.get("law") or []) if l.get("citation") or l.get("pid")
            ) or "Theo danh mục quy tắc kiểm tra"
            lines.append(f"### {title}")
            lines.append(f"- **Đánh giá:** {verdict}")
            lines.append(f"- **Ghi nhận trong hợp đồng:** {quotes}")
            lines.append(f"- **Căn cứ pháp luật:** {laws}")
            if v.get("law_values"):
                lines.append("- **Ngưỡng / yêu cầu luật:** " + "; ".join(lv.get("text", "") for lv in v["law_values"]))
            if v.get("meaning"):
                lines.append(f"- **Gợi ý xử lý:** {v['meaning']}")
            lines.append("")
    lines += ["", "## 3. Quyền lợi & Nội dung cần xác minh thêm"]
    if not notes:
        lines.append("- Không có mục cần bổ sung thêm dữ kiện.")
    else:
        for item in notes:
            v = item.get("view") or {}
            lines.append(f"- **{v.get('title') or item.get('concept_id')}**: {v.get('verdict') or ''}")
    lines += ["", "## 4. Các nội dung đã phù hợp quy định"]
    if not ok_items:
        lines.append("- Chưa ghi nhận hạng mục đạt chuẩn riêng biệt.")
    else:
        for item in ok_items[:12]:
            v = item.get("view") or {}
            lines.append(f"- {v.get('title') or item.get('concept_id')}")
    lines += [
        "",
        "## 5. Khuyến nghị hành động tiếp theo",
        "- Rà soát và cập nhật lại từng điều khoản được đánh dấu ở Mục 2 trước khi ký kết.",
        "- Bổ sung thông tin còn thiếu (nếu có ở Mục 3) để hoàn tất đánh giá các quyền lợi phát sinh.",
    ]
    return "\n".join(lines)


def _compact_report_payload(c, res: dict, mask_state, catalog) -> str:
    rep = res.get("report") or {}
    views = res.get("views") or []
    compact_findings = []
    ok_titles = []
    for item in views:
        v = item.get("view") or {}
        title = v.get("title") or item.get("concept_id")
        finding = item.get("finding")
        if finding == "ok":
            ok_titles.append(title)
            continue
        compact_findings.append({
            "muc": title,
            "ket_luan": catalog.verdict_label(finding),
            "y_nghia": v.get("meaning") or "",
            "hop_dong_ghi": [
                {"dieu_khoan": ct.get("label"), "trich_doan": (ct.get("quote") or "")[:240]}
                for ct in (v.get("contract") or [])[:2]
            ],
            "gia_tri_luat": [lv.get("text") for lv in (v.get("law_values") or []) if lv.get("text")],
            "can_cu_luat": [
                {
                    "ten": l.get("citation") or l.get("pid"),
                    "hieu_luc": l.get("in_force"),
                    "loi_van": (l.get("text") or "")[:300],
                    "ghi_chu": l.get("note") or "",
                }
                for l in (v.get("law") or [])[:2]
            ],
            "du_kien_thieu": v.get("missing") or [],
        })
    raw = json.dumps({
        "ten_hop_dong": c.filename,
        "ngay_ap_luat": rep.get("day"),
        "du_kien_xac_nhan": {
            catalog.fact_label(k): (f"{val.get('value')}" if isinstance(val, dict) else val)
            for k, val in (c.facts or {}).items()
            if k not in ("parties", "error") and val is not None
        },
        "canh_bao_chung": rep.get("warnings") or [],
        "cac_diem_can_chu_y": compact_findings,
        "cac_muc_dat_chuan": ok_titles,
    }, ensure_ascii=False)
    if mask_state is None:
        return raw
    from rag.quality.pii import mask_text
    known_masked, _ = mask_state.mask_known(raw)
    return mask_text(known_masked, state=mask_state).masked_text


async def report_stream(request):
    cid = request.path_params["cid"]
    body = await api._json(request)
    force = bool(body.get("force", False))

    def run(emit):
        c = api.get(cid)
        if not c.concept_check or not isinstance(c.concept_check.get("result"), dict):
            raise api.NeedsConceptCheck()
        res = c.concept_check["result"]
        cached = c.concept_check.get("narrative_report")
        if cached and not force:
            return {"markdown": cached, "cached": True, "llm_used": True}

        catalog = api._catalog_or_labor(c)
        _, doc = build_graph(cid, c.page_texts, c.oplog,
                             file_checksum=c.file_checksum or "", built_at=api._now(), catalog=catalog)
        state = graph_mask_state(doc)
        llm_used = False
        markdown = ""
        try:
            llm = api.CONFIG.llm_factory()
            if llm is not None:
                user_prompt = (
                    "Dưới đây là dữ liệu rà soát hợp đồng đã trích xuất. Hãy viết báo cáo hoàn chỉnh:\n"
                    + _compact_report_payload(c, res, state, catalog)
                )
                if hasattr(llm, "stream"):
                    buf = ""
                    chunks = []
                    for delta in llm.stream(_REPORT_SYSTEM, user_prompt):
                        if not delta:
                            continue
                        chunks.append(delta)
                        buf += delta
                        idx = buf.rfind("[")
                        if idx >= 0 and "]" not in buf[idx:]:
                            safe, buf = buf[:idx], buf[idx:]
                        else:
                            safe, buf = buf, ""
                        if safe:
                            emit({"type": "token", "delta": state.unmask(safe)})
                    if buf:
                        emit({"type": "token", "delta": state.unmask(buf)})
                    markdown = state.unmask("".join(chunks).strip())
                    llm_used = True
                elif hasattr(llm, "complete"):
                    raw = llm.complete(_REPORT_SYSTEM, user_prompt)
                    markdown = state.unmask(raw)
                    emit({"type": "token", "delta": markdown})
                    llm_used = True
        except Exception as exc:  # noqa: BLE001 — rơi về báo cáo cấu trúc chuẩn khi LLM lỗi
            api.log.warning("LLM report generation failed for %s: %s", cid, exc)
            markdown = ""

        if not markdown:
            markdown = state.unmask(_fallback_structured_report(c, res, catalog))
            emit({"type": "token", "delta": markdown})
        else:
            c.concept_check["narrative_report"] = markdown
            api.store().update(c)
        return {"markdown": markdown, "cached": False, "llm_used": llm_used}

    return stream_work(run)


routes = [
    Route("/contract-studio", index),
    Route("/contract-studio/", index),
    Route("/api/contract-studio/upload/stream", upload, methods=["POST"]),
    Route("/api/contracts/{cid}/studio", get_snapshot),
    Route("/api/contracts/{cid}/studio/analyze/stream", analyze, methods=["POST"]),
    Route("/api/contracts/{cid}/studio/report/stream", report_stream, methods=["POST"]),
    Mount("/contract-studio/assets", StaticFiles(directory=str(DIST / "assets"), check_dir=False)),
]
