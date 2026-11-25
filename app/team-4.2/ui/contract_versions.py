"""Contract Studio: bổ sung văn bản vào hợp đồng đã phân tích (spec 2026-11-26-contract-versions-design).

Ba bước: `additions` (đọc file, đoán loại) -> `prepare` (tạo bản NHÁP của phiên bản mới: phụ lục -> chỉ trích phần
mới; hợp đồng khác -> phân tích thường) -> người dùng xác minh -> `analyze` (soát, đối chiếu, phiên bản thành `ready`).
Bản cha không bao giờ bị sửa; lỗi giữa chừng không tạo phiên bản. Nháp tải lên và nháp phiên bản chỉ ở bộ nhớ.
"""
from __future__ import annotations

import copy
import dataclasses
import secrets
import threading
from datetime import date
from pathlib import Path

from starlette.responses import JSONResponse
from starlette.routing import Route

import contracts_api as api
from contract_studio import snapshot, stream_work
from rag.bridge.check import check_contract, report_json
from rag.bridge.view import result_views
from rag.contracts import verify
from rag.contracts.classify import UNKNOWN, classify_contract, document_kinds
from rag.contracts.doc import PageText
from rag.contracts.dossier import AMENDMENT
from rag.contracts.facts import extract_part_facts
from rag.contracts.llm_json import ContractAIError
from rag.contracts.models import Contract, family_id, version_of
from rag.contracts.structure import parse_contract, to_contract_units
from rag.contracts.version_cross import cross_check
from rag.contracts.versions import (append_appendix, compare_results, copy_for_version, effective_date,
                                    reopen_changed_fields)

AMENDMENT_LABEL = "Phụ lục hợp đồng (sửa đổi, bổ sung một hợp đồng đã ký)"
KINDS = ("appendix", "contract")
NOT_LATEST = "Chỉ bổ sung được vào phiên bản mới nhất đã phân tích"
UNREAD = "AI lỗi hai lần"          # chữ trong cảnh báo lô không đọc được (batches.BatchRun.warnings)

_uploads: dict[str, dict] = {}
_guard = threading.Lock()


def _latest(cid: str) -> Contract:
    """Hợp đồng `cid` nếu được bổ sung vào: bản mới nhất của họ và đã phân tích; không thì NotAllowed."""
    c = api.get(cid)
    family = api.store().family(family_id(c))
    if not family or family[-1].contract_id != cid or not c.concept_check:
        raise NotAllowed(NOT_LATEST)
    return c


class NotAllowed(ValueError):
    pass


def _contract_of(name: str, texts: list[PageText]) -> Contract:
    doc = parse_contract(texts)
    units = to_contract_units(doc)
    return Contract(secrets.token_urlsafe(8), name, False, api._now(), "\n\n".join(t.text for t in texts), units,
                    len(units), doc=doc)


def create_upload(cid: str, data: bytes, filename: str) -> dict:
    _latest(cid)
    _, texts = api._load_pages(data, filename)
    name = Path(filename).name
    kinds = {**document_kinds(), AMENDMENT: AMENDMENT_LABEL}
    found = classify_contract(api.CONFIG.llm_factory(), _contract_of(name, texts), kinds=kinds)["kind"]
    aid = secrets.token_urlsafe(12)
    with _guard:
        _uploads[aid] = {"cid": cid, "data": data, "filename": name, "texts": texts}
    return {"addition_id": aid, "filename": name,
            "suggested_kind": None if found == UNKNOWN else ("appendix" if found == AMENDMENT else "contract"),
            "excerpt": "\n".join(t.text for t in texts)[:600], "today": api.CONFIG.today().isoformat()}


def _upload_of(cid: str, aid: str) -> dict:
    with _guard:
        u = _uploads.get(aid)
    if u is None or u["cid"] != cid:
        raise LookupError("Văn bản bổ sung đã hết phiên — hãy tải lại")
    return u


def _unread(warnings) -> list[str]:
    return [w for w in warnings or [] if UNREAD in str(w)]


def prepare(cid: str, aid: str, kind: str, *, on_event=None) -> dict:
    if kind not in KINDS:
        raise ValueError("Hãy chọn loại văn bản bổ sung: phụ lục hoặc hợp đồng khác")
    parent = _latest(cid)
    up = _upload_of(cid, aid)
    now = api._now()
    draft = copy_for_version(parent, secrets.token_urlsafe(18), now)
    other_id = None
    try:
        if kind == "appendix":
            title = next((ln.strip() for t in up["texts"] for ln in t.text.splitlines() if ln.strip()), up["filename"])
            part = append_appendix(draft, up["texts"], up["data"], title, now)
            before = len(draft.facts.get("warnings") or [])
            catalog = api._catalog_or_labor(draft)
            changed = extract_part_facts(api.CONFIG.llm_factory(), draft, part,
                                         extra_fields=catalog.context.extract_fields, on_event=on_event)
            if _unread((draft.facts.get("warnings") or [])[before:]):
                raise ContractAIError("AI chưa đọc hết phụ lục — hãy thử lại")
            reopen_changed_fields(draft, changed)
            addition = {"kind": kind, "filename": up["filename"], "part_id": part}
            eff = effective_date(draft, part)
            day = eff.isoformat() if eff else None
        else:
            other_id = api.create(up["data"], up["filename"], False, on_event=on_event)["contract_id"]
            other = api.get(other_id)
            other.lineage = {"family_id": family_id(parent), "status": "member"}
            if other.facts.get("error") or _unread(other.facts.get("warnings")):
                raise ContractAIError("AI chưa đọc được hợp đồng bổ sung — hãy thử lại")
            draft.lineage["linked"].append(other_id)
            addition = {"kind": kind, "filename": up["filename"], "other_contract_id": other_id}
            day = api.CONFIG.today().isoformat()
        previous = (parent.lineage.get("addition") or {}).get("review_date")
        if day and previous:
            day = max(day, previous)              # không mặc định sớm hơn ngày của lần bổ sung trước (dạng ISO)
        draft.lineage["addition"] = addition
        with api._graph().writing(draft.contract_id):
            api._rebuild(draft, now)
        original = api.store().original(parent.contract_id) or (up["data"], Path(up["filename"]).suffix.lower())
        api.store().add(draft, original=original[0], suffix=original[1])
    except BaseException:
        if other_id:
            api.store().delete(other_id)
        raise
    return {"draft": snapshot(draft.contract_id), "other": snapshot(other_id) if other_id else None,
            "review_date": day}


def _review_date(body: dict, kind: str) -> date:
    raw = body.get("review_date")
    if not raw:
        if kind == "appendix":
            raise ValueError("Hãy nhập ngày đánh giá (phụ lục không ghi ngày hiệu lực)")
        return api.CONFIG.today()
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        raise ValueError("Ngày đánh giá phải dạng YYYY-MM-DD") from None


def _with_views(diff: dict, contract: Contract) -> dict:
    """Thêm phần hiển thị (tên mục, kết luận, trích đoạn) cho từng kết quả của bảng đối chiếu."""
    catalog = api._catalog_or_labor(contract)

    def view(r):
        return result_views([r], catalog, contract, {})[0]
    return {"changed": [{**x, "before": view(x["before"]), "after": view(x["after"])} for x in diff["changed"]],
            "added": [view(r) for r in diff["added"]], "removed": [view(r) for r in diff["removed"]],
            "unchanged": diff["unchanged"]}


def _checked(c: Contract, user: dict, emit, **kw) -> dict:
    out = api.concept_check(c.contract_id, user, on_event=emit, **kw)
    if _unread(out["report"]["warnings"][len(c.facts.get("warnings") or []):]):
        raise ContractAIError("AI chưa đọc hết văn bản bổ sung — hãy thử lại")
    return out


def analyze(draft_id: str, body: dict, *, on_event=None) -> dict:
    draft = api.get(draft_id)
    if draft.lineage.get("status") != "draft":
        raise ValueError("Văn bản bổ sung này đã được phân tích")
    parent = _latest(draft.lineage["parent_id"])
    addition = draft.lineage["addition"]
    kind = addition["kind"]
    day = _review_date(body, kind)
    other = api.get(addition["other_contract_id"]) if kind == "contract" else None
    if other is not None:
        if body.get("same_party") is not True:
            raise ValueError("Chỉ bổ sung hợp đồng cùng bên (cùng người lao động) với hợp đồng đang xem")
        verify.check_gate(other, "review")
    verify.check_gate(draft, "review")
    saved = parent.concept_check["result"]["report"]
    user = {**(parent.concept_check.get("user_facts") or {}),
            **{k: v for k, v in (body.get("user_facts") or {}).items() if v is not None}}
    continuous = body.get("continuous_employment")
    if "continuous_employment" not in body:       # không gửi: theo lần trước; gửi null = người dùng chọn "Không rõ"
        continuous = (parent.lineage.get("addition") or {}).get("continuous_employment")
    elif not isinstance(continuous, bool):
        continuous = None
    contract_diff, differs, check_day = None, False, day
    if kind == "appendix":
        part = addition["part_id"]
        new_units = [u.uid for u in draft.units if u.uid.startswith(f"{part}.")]
        document_kind = (parent.facts or {}).get("document_kind")
        before = report_json(check_contract(
            None, copy.deepcopy(parent), at=api._now(), rules_only=True, day=day, user_facts=user,
            document_kind=document_kind))["results"]
        result = _checked(draft, user, on_event, only_units=new_units, day=day)
        contract_diff = _with_views(compare_results(before, result["report"]["results"]), draft)
        d = compare_results(saved["results"], before)
        differs = bool(d["changed"] or d["added"] or d["removed"])
    else:
        _checked(other, user, on_event)
        # Hợp đồng đang xem không đổi nội dung: chỉ chạy lại luật ở đúng ngày bản cha đã đánh giá.
        check_day = date.fromisoformat(saved["day"])
        result = _checked(draft, user, on_event, rules_only=True, day=check_day)

    fid = family_id(parent)

    def docs(base: Contract, linked: list[str]) -> list[Contract]:
        # mã văn bản chính ổn định giữa hai phiên bản: mạng luật chỉ tính lại phần thật sự thêm
        return [dataclasses.replace(base, contract_id=fid), *(api.get(i) for i in linked)]

    cross = None
    if draft.lineage["linked"]:
        cross = cross_check(docs(parent, parent.lineage.get("linked") or []), docs(draft, draft.lineage["linked"]),
                            day=day, continuous_employment=continuous, user_facts=user)
        if cross["supported"]:
            cross["compare"] = _with_views(cross["compare"], draft)
    compare = {"day": day.isoformat(), "against": parent.contract_id, "contract": contract_diff,
               "before_differs_from_saved": differs, "cross": cross,
               "catalog_changed": saved["catalog_version"] != result["report"]["catalog_version"]}
    _latest(parent.contract_id)                       # vẫn là bản mới nhất khi sắp công bố phiên bản
    draft.lineage.update(status="ready", compare=compare, addition={
        **addition, "review_date": day.isoformat(), "check_day": check_day.isoformat(),
        "continuous_employment": continuous})
    draft.persist = parent.persist
    if parent.persist:
        if other is not None:
            api.store().save(other.contract_id)
        api.store().save(draft.contract_id)
    return {**snapshot(draft.contract_id), "result": result, "compare": compare}


def versions(cid: str) -> dict:
    family = api.store().family(family_id(api.get(cid)))
    return {"versions": [{"contract_id": c.contract_id, "version": version_of(c), "filename": c.filename,
                          "addition": c.lineage.get("addition"), "latest": c is family[-1]} for c in family]}


def comparison(cid: str) -> dict:
    found = api.get(cid).lineage.get("compare")
    if not found:
        raise LookupError("Phiên bản này không có bản trước để so")
    return found


# ── HTTP ──
async def upload(request):
    cid = request.path_params["cid"]
    form = await request.form(max_part_size=api.MAX_BYTES)
    file = form.get("file")
    if not file or not getattr(file, "filename", None):
        return JSONResponse({"error": "Hãy chọn văn bản bổ sung"}, status_code=400)
    if Path(file.filename).suffix.lower() not in api.ALLOWED:
        return JSONResponse({"error": "Định dạng chưa hỗ trợ: dùng PDF, DOCX, TXT hoặc ảnh scan"}, status_code=400)
    data = await file.read(api.MAX_BYTES + 1)
    if len(data) > api.MAX_BYTES:
        return JSONResponse({"error": "File quá lớn: tối đa 50 MB"}, status_code=413)
    try:
        _latest(cid)
    except KeyError:
        return JSONResponse({"error": api.GONE}, status_code=404)
    except NotAllowed as e:
        return JSONResponse({"error": str(e)}, status_code=409)
    return await api._call(create_upload, cid, data, file.filename)


async def prepare_stream(request):
    cid, aid = request.path_params["cid"], request.path_params["aid"]
    body = await api._json(request)
    return stream_work(lambda emit: prepare(cid, aid, str(body.get("kind") or ""), on_event=emit), cid=cid)


async def analyze_stream(request):
    draft_id = request.path_params["cid"]
    body = await api._json(request)
    try:
        parent = api.get(draft_id).lineage.get("parent_id") or draft_id
    except KeyError:
        return JSONResponse({"error": api.GONE}, status_code=404)
    return stream_work(lambda emit: analyze(draft_id, body, on_event=emit), cid=parent)


async def get_versions(request):
    return await api._call(versions, request.path_params["cid"])


async def get_compare(request):
    try:
        return JSONResponse(comparison(request.path_params["cid"]))
    except KeyError:
        return JSONResponse({"error": api.GONE}, status_code=404)
    except LookupError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


routes = [
    Route("/api/contracts/{cid}/additions", upload, methods=["POST"]),
    Route("/api/contracts/{cid}/additions/{aid}/prepare/stream", prepare_stream, methods=["POST"]),
    Route("/api/contracts/{cid}/additions/analyze/stream", analyze_stream, methods=["POST"]),
    Route("/api/contracts/{cid}/versions", get_versions, methods=["GET"]),
    Route("/api/contracts/{cid}/studio/compare", get_compare, methods=["GET"]),
]
