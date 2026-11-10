"""API kho luật có phiên bản cho server (spec §4.3–4.4): upload 3 bước, quyết định duyệt, hàng đợi ghi, chỉ mục chat.

Quy tắc: chat không bao giờ trả lời từ kho nửa cũ nửa mới. Mọi lần ghi (upload, quyết định duyệt, dựng lại chỉ mục)
đi qua `WriteWorker` -> `SnapshotManager.write` (staging -> kiểm tra -> công bố) -> dựng chỉ mục -> đổi cặp chat.
Đọc (`/review`, so sánh trùng, xem trước) dùng snapshot đang công bố.

`LegalBackend` có hai phần:
- nhẹ (dựng ngay): `SnapshotManager`, `DraftStore`, `UploadService` — không cần RAG pipeline;
- nặng (lần đầu cần, luôn ngoài event loop): `RuntimeHolder` + `WriteWorker`, dựng runtime đầu bằng
  `CONFIG.make_runtime_for(snapshots)` (server.py cấu hình: BM25 + Dense dùng chung + TemporalQA).
"""

from __future__ import annotations

import asyncio
import logging
import re
import tempfile
import threading
import time
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from legal_runtime import Job, RuntimeHolder, WriteWorker
from rag.legal.keys import document_key, normalize_number
from rag.legal.snapshots import SnapshotManager
from rag.legal.store import LegalStore, encode
from rag.legal.targets import law_name
from rag.legal.upload.drafts import Draft, DraftStore
from rag.legal.upload.flow import STALE_MESSAGE, StaleDraftError, StepError, UploadService

log = logging.getLogger("rag.ui.legal_api")

TERMINAL = ("done", "failed", "index_failed")
RETRY_S = 300.0                 # kho mới lỗi khởi tạo / chưa có chỉ mục: chờ bấy lâu mới thử lại (chat dùng pipeline cũ)
FINALIZE_WAIT_S = 5.0           # việc upload đã xong: chờ bản nháp được cập nhật trước khi báo trạng thái cuối
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
               ".tif": "image/tiff", ".tiff": "image/tiff"}
_NUMBER_RE = re.compile(r"\d+\s*/\s*\d{4}\s*/\s*[A-ZĐ0-9-]+", re.IGNORECASE)


def _default_legal_dir() -> Path:
    from rag.config import Settings

    return Settings.load().data_dir / "legal"


def _default_client_factory() -> Any:
    from rag.ingest.vbpl import VbplClient

    return VbplClient()


# server.py gán `make_runtime_for` (và `ocr_factory`); test thay `client_factory` bằng client giả.
CONFIG = SimpleNamespace(
    legal_dir=_default_legal_dir,
    make_runtime_for=None,          # Callable[[SnapshotManager], Callable[[str], LegalRuntime]]
    client_factory=_default_client_factory,
    ocr_factory=None,               # Callable[[], OCR engine | None]
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_dict(job: Job) -> dict[str, Any]:
    return {"job_id": job.job_id, "kind": job.kind, "ref": job.ref, "actor": job.actor, "state": job.state,
            "progress": job.progress, "snapshot_id": job.snapshot_id, "error": job.error}


def _version_sets(store: LegalStore, key: str) -> dict[str, set]:
    out: dict[str, set] = {}
    for v in store.versions(key):
        out.setdefault(v.provision_id, set()).add((v.valid_from, v.valid_to, v.text))
    return out


def _draft_key(d: Draft) -> str | None:
    t = (d.fields.get("doc_type") or {}).get("value")
    n = (d.fields.get("doc_number") or {}).get("value")
    return document_key(t, n) if t and n else None


class LegalBackend:
    def __init__(self, legal_dir: Path) -> None:
        self.snapshots = SnapshotManager(legal_dir)
        self.drafts = DraftStore(Path(legal_dir) / "uploads")
        # tiến trình trước chết giữa chừng: staging -> failed, bản nháp queued/building -> failed (có nút "Thử lại")
        for what, mark in (("snapshot", self.snapshots.mark_interrupted), ("bản nháp", self.drafts.mark_interrupted)):
            ids = mark()
            if ids:
                log.warning("%s bị dừng giữa chừng -> failed: %s", what, ids)
        ocr = None
        if CONFIG.ocr_factory is not None:
            try:
                ocr = CONFIG.ocr_factory()
            except Exception:                   # noqa: BLE001 - không có OCR thì file scan báo lỗi ở bước ①
                log.exception("Không khởi tạo được OCR cho upload văn bản pháp luật")
        self.upload = UploadService(self.snapshots, self.drafts, client_factory=CONFIG.client_factory, ocr=ocr)
        self.holder: RuntimeHolder | None = None
        self.worker: WriteWorker | None = None
        self._rt_lock = threading.Lock()
        self._index_retry_at = 0.0
        self._lock = threading.Lock()
        self._finished: dict[str, threading.Event] = {}
        self._stale: set[str] = set()

    # --- runtime + hàng đợi ghi ------------------------------------------------------------

    def runtime(self) -> tuple[RuntimeHolder, WriteWorker]:
        """Dựng holder (runtime đầu, đồng bộ) + worker lần đầu cần. Gọi ngoài event loop."""
        with self._rt_lock:
            if self.worker is None:
                if CONFIG.make_runtime_for is None:
                    raise RuntimeError("legal_api.CONFIG.make_runtime_for chưa được cấu hình")
                make_runtime = CONFIG.make_runtime_for(self.snapshots)
                holder = RuntimeHolder(self.snapshots, make_runtime)
                self.worker = WriteWorker(self.snapshots, holder, make_runtime=make_runtime,
                                          on_upload_done=self._on_upload_done)
                self.holder = holder
                self._index_retry_at = time.monotonic() + RETRY_S
            assert self.holder is not None
            return self.holder, self.worker

    def maybe_retry_index(self) -> None:
        """Chưa có cặp (snapshot, chỉ mục) nào dùng được: đưa "dựng lại chỉ mục" vào hàng đợi, tối đa 1 lần / RETRY_S."""
        holder, worker = self.holder, self.worker
        if holder is None or worker is None or holder.get() is not None:
            return
        with self._lock:
            if time.monotonic() < self._index_retry_at:
                return
            self._index_retry_at = time.monotonic() + RETRY_S
        log.info("Chat chưa có chỉ mục kho luật: đưa việc dựng lại chỉ mục vào hàng đợi")
        worker.reindex()

    def served(self, snapshot_id: str | None) -> bool:
        """Chat đang dùng snapshot này, hoặc một snapshot công bố sau nó (đã chứa thay đổi của nó)."""
        rt = self.holder.get() if self.holder is not None else None
        if rt is None or not snapshot_id:
            return False
        if rt.snapshot_id == snapshot_id:
            return True
        try:
            cur, snap = self.snapshots.get(rt.snapshot_id), self.snapshots.get(snapshot_id)
        except KeyError:
            return False
        return bool(cur.published_at and snap.published_at and cur.published_at > snap.published_at)

    def _event(self, job_id: str) -> threading.Event:
        with self._lock:
            return self._finished.setdefault(job_id, threading.Event())

    def job_view(self, job_id: str) -> dict[str, Any]:
        if self.worker is None:
            raise KeyError(job_id)
        job = self.worker.job(job_id)
        if job.kind == "upload" and job.state in TERMINAL:
            # callback chạy SAU khi việc ở trạng thái cuối: đợi bản nháp được cập nhật để UI đọc thấy nhất quán
            self._event(job_id).wait(FINALIZE_WAIT_S)
        return _job_dict(job)

    # --- upload ----------------------------------------------------------------------------

    def _apply_fn(self, upload_id: str) -> Callable[[Any], None]:
        def apply(svc: Any) -> None:
            try:
                self.upload.apply_to(svc, upload_id)
            except StaleDraftError:
                with self._lock:
                    self._stale.add(upload_id)
                raise
        return apply

    def _enqueue(self, d: Draft, worker: WriteWorker) -> None:
        """Gọi bên trong `upload.mutate` (giữ khoá bản nháp): việc ghi không chạm tới bản nháp trước khi `job_id` được
        ghi lại, nên callback luôn khớp đúng việc."""
        job = worker.submit("upload", d.upload_id, d.confirmations["step3"]["by"], self._apply_fn(d.upload_id))
        d.job_id, d.progress = job.job_id, None

    def submit_upload(self, upload_id: str, by: str, note: str) -> str:
        _, worker = self.runtime()
        self.upload.submit(upload_id, by, note)
        return self.upload.mutate(upload_id, lambda d: self._enqueue(d, worker)).job_id or ""

    def retry_upload(self, upload_id: str, by: str) -> str:
        _, worker = self.runtime()

        def retry(d: Draft) -> None:
            if d.state == "failed":
                if not (by or "").strip():
                    raise StepError("Cần tên người thực hiện")
                note = (d.confirmations.get("step3") or {}).get("note", "")
                d.confirmations["step3"] = {"by": by.strip(), "at": _now_iso(), "note": note}
                d.state, d.error = "queued", None
                self._enqueue(d, worker)
            elif d.state == "published" and d.index_error and not self.served(d.snapshot_id):
                d.job_id = worker.reindex().job_id          # kho đã công bố: chỉ cần dựng lại chỉ mục
            else:
                raise StepError("Chỉ thử lại được bản nháp bị lỗi (dựng kho lỗi hoặc dựng chỉ mục lỗi)")

        return self.upload.mutate(upload_id, retry).job_id or ""

    def _on_upload_done(self, job: Job) -> None:
        """Trên luồng ghi, khi việc upload đã ở trạng thái cuối: cập nhật bản nháp theo kết quả."""
        try:
            with self._lock:
                stale = job.ref in self._stale
                self._stale.discard(job.ref)

            def finish(d: Draft) -> None:
                if d.job_id != job.job_id:
                    return
                d.progress = None
                if job.state in ("done", "index_failed"):
                    d.state, d.snapshot_id, d.error = "published", job.snapshot_id, None
                    d.index_error = job.error if job.state == "index_failed" else None
                    try:
                        d.result = self.result(job.snapshot_id or "", d)
                    except Exception:           # noqa: BLE001 - kho đã công bố; thiếu bảng kết quả không làm hỏng nó
                        log.exception("Không tính được kết quả upload %s", d.upload_id)
                elif d.state == "cancelled":
                    pass
                elif stale:
                    d.state, d.error = "stale", STALE_MESSAGE
                else:
                    d.state, d.error = "failed", job.error

            self.upload.mutate(job.ref, finish)
        finally:
            self._event(job.job_id).set()

    def result(self, snapshot_id: str, d: Draft) -> dict[str, Any]:
        """Với từng luật có thay đổi so với snapshot cha: số `provision_id` có tập (valid_from, valid_to, text) khác,
        số mục duyệt `open` mới (có trong snapshot mới, không có trong snapshot cha)."""
        snap = self.snapshots.get(snapshot_id)
        new = self.snapshots.store(snapshot_id)
        old = self.snapshots.store(snap.parent_id) if snap.parent_id else None
        old_open = {i.review_id for i in old.review_items("open")} if old is not None else set()
        new_items = Counter(i.document_key for i in new.review_items("open") if i.review_id not in old_open)
        uploaded = _draft_key(d)
        laws = []
        for doc in new.documents():
            key = doc.document_key
            changed = 0
            if not doc.is_consolidated:
                after = _version_sets(new, key)
                before = _version_sets(old, key) if old is not None else {}
                changed = sum(1 for pid in after.keys() | before.keys() if after.get(pid) != before.get(pid))
            if changed or new_items.get(key) or key == uploaded:
                laws.append({"document_key": key, "title": doc.title, "changed_provisions": changed,
                             "new_review_items": new_items.get(key, 0), "review_url": f"/review?document={key}"})
        laws.sort(key=lambda law: (law["document_key"] != uploaded, law["document_key"]))
        return {"laws": laws}

    def draft_view(self, d: Draft, *, text: bool = True) -> dict[str, Any]:
        data = encode(d)
        if not text:
            data.pop("text", None)
        job = None
        if d.job_id and self.worker is not None:
            try:
                job = _job_dict(self.worker.job(d.job_id))
            except KeyError:                    # việc của tiến trình server trước
                job = None
        data["job"] = job
        data["index_failed"] = bool(d.index_error) and not self.served(d.snapshot_id)
        return data

    # --- đọc snapshot đang công bố ------------------------------------------------------------

    def pending_base_laws(self) -> list[dict[str, Any]]:
        from rag.legal.directives import _target_law, parse_directives

        svc = self.snapshots.service()
        pending = [op for op in svc.store.operations()
                   if op.target_document_key is None and "operation.target_law_not_found" in op.status_reasons]
        # số hiệu luật đích không lưu trên thao tác: đọc lại từ chỉ dẫn của văn bản nguồn (khớp theo `sequence`)
        numbers: dict[tuple[str, int], str | None] = {}
        for src in sorted({op.source_document_key for op in pending}):
            doc = svc.store.document(src)
            try:
                directives = parse_directives(svc.provisions_for(src), default_target=_target_law(doc.title))
            except Exception:                   # noqa: BLE001 - thiếu file text: nhóm theo tên
                log.exception("Không đọc lại được chỉ dẫn của %s", src)
                continue
            numbers.update({(src, d.sequence): d.target_law_number for d in directives})
        groups: dict[tuple, dict[str, Any]] = {}
        for op in pending:
            raw = op.target_law_name or ""
            m = _NUMBER_RE.search(raw)
            number = numbers.get((op.source_document_key, op.sequence)) or (m.group(0) if m else None)
            number = normalize_number(number) if number else None
            name = law_name(raw) if raw else ""
            g = groups.setdefault((name, number), {"target_law_name": raw.split(" số ")[0].strip() or None,
                                                   "target_law_number": number, "operations": []})
            g["operations"].append({"operation_id": op.operation_id, "source_document_key": op.source_document_key,
                                    "source_locator": op.source_locator, "operation_type": op.operation_type})
        out = [dict(g, count=len(g["operations"])) for g in groups.values()]
        out.sort(key=lambda g: (-g["count"], g["target_law_name"] or "", g["target_law_number"] or ""))
        return out


_backend: LegalBackend | None = None
_backend_lock = threading.Lock()
_chat_failed_at: float | None = None


def get_backend() -> LegalBackend:
    global _backend
    if _backend is None:
        with _backend_lock:
            if _backend is None:
                _backend = LegalBackend(Path(CONFIG.legal_dir()))
    return _backend


def reset() -> None:
    """Bỏ backend hiện tại (test / đổi DATA_DIR). Đợi hàng đợi ghi của nó rảnh trước."""
    global _backend, _chat_failed_at
    with _backend_lock:
        old, _backend = _backend, None
        _chat_failed_at = None
    if old is not None and old.worker is not None:
        old.worker.wait_idle(120)


def chat_holder() -> RuntimeHolder | None:
    """Holder cho chat; None -> chat dùng pipeline cũ. Khởi tạo lỗi: không thử lại trong RETRY_S giây."""
    global _chat_failed_at
    if _chat_failed_at is not None and time.monotonic() - _chat_failed_at < RETRY_S:
        return None
    try:
        backend = get_backend()
        holder, _ = backend.runtime()
    except Exception:                           # noqa: BLE001 - kho mới lỗi không được làm hỏng chat
        log.exception("Không khởi tạo được kho luật có phiên bản cho chat; dùng pipeline cũ")
        _chat_failed_at = time.monotonic()
        return None
    _chat_failed_at = None
    backend.maybe_retry_index()
    return holder


# --- HTTP ----------------------------------------------------------------------------------------


def _error(msg: str, status: int) -> JSONResponse:
    return JSONResponse({"error": msg}, status_code=status)


async def _call(fn: Callable[[], Any], status: int = 200) -> Response:
    """Chạy `fn` ngoài event loop. StepError -> 409, KeyError (không có bản nháp / việc / mục) -> 404."""
    try:
        result = await asyncio.get_running_loop().run_in_executor(None, fn)
    except StepError as e:
        return _error(str(e), 409)
    except KeyError:
        return _error("Không tìm thấy", 404)
    if isinstance(result, Response):
        return result
    return JSONResponse(result, status_code=status)


async def _body(request: Request) -> dict[str, Any] | None:
    try:
        raw = await request.body()
        if not raw.strip():
            return {}
        data = await request.json()
    except Exception:                           # noqa: BLE001
        return None
    return data if isinstance(data, dict) else None


def _by(body: dict[str, Any]) -> str:
    return str(body.get("by") or "")


async def handle_create(request: Request) -> Response:
    form = await request.form()
    upload = form.get("file")
    url = str(form.get("url") or "").strip()
    if upload is not None and getattr(upload, "filename", None):
        name = Path(str(upload.filename)).name or "upload"
        content = await upload.read()

        def create_file() -> dict[str, Any]:
            backend = get_backend()
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / f"upload{Path(name).suffix.lower()}"
                path.write_bytes(content)
                return backend.draft_view(backend.upload.create_from_file(path, name))
        return await _call(create_file, 201)
    if url:
        return await _call(lambda: get_backend().draft_view(get_backend().upload.create_from_url(url)), 201)
    return _error("Cần file hoặc đường link vbpl", 400)


async def handle_list(request: Request) -> Response:
    def run() -> dict[str, Any]:
        backend = get_backend()
        return {"uploads": [backend.draft_view(d, text=False) for d in backend.drafts.list()]}
    return await _call(run)


async def handle_get(request: Request) -> Response:
    uid = request.path_params["upload_id"]
    return await _call(lambda: get_backend().draft_view(get_backend().drafts.load(uid)))


def _step(method: str, *, with_preview: bool = False, needs_by: bool = True):
    async def handler(request: Request) -> Response:
        uid = request.path_params["upload_id"]
        body = await _body(request)
        if body is None:
            return _error("Body JSON không hợp lệ", 400)

        def run() -> dict[str, Any]:
            backend = get_backend()
            up = backend.upload
            if method == "fields":
                values = body.get("values")
                if not isinstance(values, dict):
                    raise StepError("'values' phải là object {trường: giá trị}")
                d = up.update_fields(uid, values, _by(body))
            elif needs_by:
                d = getattr(up, method)(uid, _by(body))
            else:
                d = getattr(up, method)(uid)
            if with_preview and d.state == "step2":       # đổi số hiệu có thể quay về bước ① (so sánh trùng)
                d = up.preview(uid)
            return backend.draft_view(d)
        return await _call(run)
    return handler


async def handle_submit(request: Request) -> Response:
    uid = request.path_params["upload_id"]
    body = await _body(request)
    if body is None:
        return _error("Body JSON không hợp lệ", 400)
    note = str(body.get("note") or "")
    return await _call(lambda: {"job_id": get_backend().submit_upload(uid, _by(body), note)}, 202)


async def handle_retry(request: Request) -> Response:
    uid = request.path_params["upload_id"]
    body = await _body(request)
    if body is None:
        return _error("Body JSON không hợp lệ", 400)
    return await _call(lambda: {"job_id": get_backend().retry_upload(uid, _by(body))}, 202)


async def handle_job(request: Request) -> Response:
    job_id = request.path_params["job_id"]
    return await _call(lambda: get_backend().job_view(job_id))


async def handle_reindex(request: Request) -> Response:
    return await _call(lambda: {"job_id": get_backend().runtime()[1].reindex().job_id}, 202)


async def handle_pending_base_laws(request: Request) -> Response:
    return await _call(lambda: {"laws": get_backend().pending_base_laws()})


async def page_image_response(src_file: Path | None, page_no: int) -> Response:
    """Ảnh trang gốc (PDF render 1.5x, hoặc chính file ảnh)."""
    if src_file is None or page_no < 1:
        return Response(status_code=404)
    suffix = src_file.suffix.lower()
    headers = {"Cache-Control": "private, max-age=3600"}
    if suffix in IMAGE_TYPES:
        return Response(src_file.read_bytes(), media_type=IMAGE_TYPES[suffix], headers=headers)
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


async def handle_page_image(request: Request) -> Response:
    try:
        page_no = int(request.path_params.get("page", "0"))
    except ValueError:
        return Response(status_code=400)
    uid = request.path_params["upload_id"]
    try:
        src = await asyncio.get_running_loop().run_in_executor(None, lambda: get_backend().drafts.original(uid))
    except KeyError:
        return Response(status_code=404)
    return await page_image_response(src, page_no)


async def handle_review_decision(request: Request) -> Response:
    """Kiểm đồng bộ (body; mục có và đang `open` trên snapshot đang công bố) rồi đưa quyết định vào hàng đợi ghi.
    Lỗi nghiệp vụ của `decide` (vd. bản sửa không hợp lệ) hiện ở việc ghi (`failed`, `error`)."""
    from rag.legal.models import ReviewDecision

    body = await _body(request)
    if body is None:
        return _error("Body JSON không hợp lệ", 400)
    reviewer, note = str(body.get("reviewer") or "").strip(), str(body.get("note") or "").strip()
    if not reviewer or not note:
        return _error("Cần tên người duyệt và ghi chú", 400)
    corrected = body.get("corrected_fields") or {}
    if not isinstance(corrected, dict):
        return _error("'corrected_fields' phải là object", 400)
    review_id = request.path_params["review_id"]
    decision = ReviewDecision(review_id, body.get("action"), reviewer, note, corrected, datetime.now(timezone.utc))

    def run() -> Response:
        backend = get_backend()
        item = backend.snapshots.store().review_item(review_id)
        if item is None:
            return _error("Không có mục duyệt này", 404)
        if item.status != "open":
            return _error("Mục duyệt đã đóng", 409)
        _, worker = backend.runtime()
        job = worker.submit("review", review_id, reviewer, lambda svc: svc.decide(decision))
        return JSONResponse({"job_id": job.job_id}, status_code=202)
    return await _call(run)


_U = "/api/legal/uploads/{upload_id}"
routes = [
    Route("/api/legal/uploads", handle_create, methods=["POST"]),
    Route("/api/legal/uploads", handle_list, methods=["GET"]),
    Route(_U, handle_get, methods=["GET"]),
    Route(_U + "/confirm-text", _step("confirm_text"), methods=["POST"]),
    Route(_U + "/replace", _step("choose_replace"), methods=["POST"]),
    Route(_U + "/fields", _step("fields", with_preview=True), methods=["POST"]),
    Route(_U + "/relookup", _step("relookup_vbpl", with_preview=True, needs_by=False), methods=["POST"]),
    Route(_U + "/confirm-understanding", _step("confirm_understanding"), methods=["POST"]),
    Route(_U + "/submit", handle_submit, methods=["POST"]),
    Route(_U + "/retry", handle_retry, methods=["POST"]),
    Route(_U + "/cancel", _step("cancel", needs_by=False), methods=["POST"]),
    Route(_U + "/page_image/{page}", handle_page_image, methods=["GET"]),
    Route("/api/legal/jobs/{job_id}", handle_job, methods=["GET"]),
    Route("/api/legal/reindex", handle_reindex, methods=["POST"]),
    Route("/api/legal/pending-base-laws", handle_pending_base_laws, methods=["GET"]),
]

__all__ = ["CONFIG", "IMAGE_TYPES", "LegalBackend", "chat_holder", "get_backend", "handle_review_decision",
           "page_image_response", "reset", "routes"]
