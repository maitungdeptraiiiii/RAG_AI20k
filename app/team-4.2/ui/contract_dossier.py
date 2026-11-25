"""Contract Studio: soát hồ sơ nhiều văn bản tải lên (hợp đồng chính + phụ lục, các bên).

Hai bước:
1. `upload`: đọc từng file (loader chung), nhận diện loại văn bản bằng LLM (loại của gói hoặc `amendment` = phụ lục) và trả
   bản nháp hồ sơ để người dùng sửa: loại, phụ lục thuộc hợp đồng nào, các bên.
2. `analyze`: hồ sơ người dùng đã xác nhận -> `rag.contracts.dossier` (trích LLM từng bộ hợp đồng + phụ lục, dựng đối
   tượng theo `object_types` của gói) -> rule engine. Chỉ trả kết quả của rule xuyên đối tượng (kết luận cấp hồ sơ);
   kiểm từng hợp đồng vẫn là luồng một hợp đồng. Trả lời câu hỏi chạy lại luật trên dữ kiện đã trích (không gọi LLM).

Bản nháp giữ trong bộ nhớ tiến trình (không lưu đĩa), hết khi server khởi động lại.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import secrets
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from starlette.responses import JSONResponse
from starlette.routing import Route

import contracts_api as api
from contract_studio import stream_work
from rag.bridge.user_form import question_payload, user_fact_fields
from rag.contracts.classify import UNKNOWN, classify_contract, document_kinds
from rag.contracts.dossier import AMENDMENT, Dossier, DossierDoc, Party, dossier_objects, extract_dossier_facts
from rag.contracts.models import Contract
from rag.contracts.structure import parse_contract, to_contract_units
from rag.rules.evaluator import default_kind, evaluator_for
from rag.rules.explain import explain
from rag.rules.loader import load_pack, packs_for_kind
from rag.rules.questions import next_questions
from rag.rules.semantics import Fact, is_unresolved

AMENDMENT_LABEL = "Phụ lục hợp đồng (sửa đổi, bổ sung một hợp đồng đã ký)"
MAX_FILES = 20

_drafts: dict[str, dict] = {}
_guard = threading.Lock()


class UnknownDraft(LookupError):
    pass


def _draft(did: str) -> dict:
    with _guard:
        d = _drafts.get(did)
    if d is None:
        raise UnknownDraft("Hồ sơ này đã hết phiên — hãy tải lại các văn bản")
    return d


def _kinds() -> dict[str, str]:
    return {**document_kinds(), AMENDMENT: AMENDMENT_LABEL}


def _packs(kinds: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(p for k in kinds if k != AMENDMENT for p in packs_for_kind(k)))


def _object_types(packs: tuple[str, ...]) -> dict:
    out: dict = {}
    seen: set[str] = set()

    def visit(pid: str) -> None:
        if pid in seen:
            return
        seen.add(pid)
        spec = load_pack(pid)
        for parent in spec.extends:
            visit(parent)
        out.update(spec.object_types)
    for p in packs:
        visit(p)
    return out


def kind_refs(kind: str) -> list[str]:
    """Tham chiếu tới các bên mà văn bản loại `kind` khai trong `object_types` của gói (vd. labor: `employee`)."""
    if kind == AMENDMENT:
        return []
    types = _object_types(tuple(packs_for_kind(kind)))
    return sorted({r for ot in types.values() if kind in ot.documents for r in ot.refs if r != ot.amends})


def form_meta(kinds: list[str]) -> dict:
    """Phần biểu mẫu phụ thuộc gói: vai trò các bên, dữ kiện người dùng, kiểu đối tượng có dựng được từ văn bản không."""
    packs = _packs(kinds)
    if not packs:
        return {"packs": [], "roles": [], "user_fields": [], "supports_dossier": False}
    cat = api._packs_catalog(packs)
    types = _object_types(packs)
    return {"packs": list(packs),
            "roles": [{"id": rid, "label": r.get("label") or rid} for rid, r in cat.roles.items()],
            "user_fields": user_fact_fields(cat),
            "supports_dossier": any(ot.documents for ot in types.values())}


def _contract_of(name: str, text: str) -> Contract:
    doc = parse_contract([api.PageText(1, text)])
    units = to_contract_units(doc)
    return Contract(secrets.token_urlsafe(8), name, False, datetime.now(timezone.utc), text, units, len(units), doc=doc)


def create_draft(files: list[tuple[str, bytes]], *, on_event=None) -> dict:
    emit = on_event or (lambda e: None)
    if not files:
        raise ValueError("Hãy chọn ít nhất một văn bản")
    if len(files) > MAX_FILES:
        raise ValueError(f"Hồ sơ tối đa {MAX_FILES} văn bản")
    kinds = _kinds()
    llm = api.CONFIG.llm_factory()
    docs = []
    for i, (name, data) in enumerate(files, start=1):
        emit({"type": "dossier_file", "index": i, "filename": name, "status": "read"})
        _, texts = api._load_pages(data, name)
        text = "\n\n".join(t.text for t in texts if t.text.strip())
        emit({"type": "dossier_file", "index": i, "filename": name, "status": "classify"})
        found = classify_contract(llm, _contract_of(name, text), kinds=kinds)
        doc = {"doc_id": f"d{i}", "filename": Path(name).name, "text": text, "pages": len(texts),
               "kind": None if found["kind"] == UNKNOWN else found["kind"], "confidence": found.get("confidence"),
               "evidence": (found.get("evidence") or [{}])[0].get("quote"), "reason": found.get("reason")}
        docs.append(doc)
        emit({"type": "dossier_file", "index": i, "filename": name, "status": "done", "kind": doc["kind"]})
    mains = [d for d in docs if d["kind"] and d["kind"] != AMENDMENT]
    for d in docs:      # phụ lục: chỉ đoán khi hồ sơ có đúng một hợp đồng chính, còn lại để người dùng chọn
        d["refs"] = {"contract": mains[0]["doc_id"]} if d["kind"] == AMENDMENT and len(mains) == 1 else {}
    did = secrets.token_urlsafe(12)
    with _guard:
        _drafts[did] = {"docs": {d["doc_id"]: d for d in docs}, "facts": {}}
    return draft_payload(did)


def draft_payload(did: str) -> dict:
    d = _draft(did)
    docs = list(d["docs"].values())
    kinds = _kinds()
    return {"dossier_id": did,
            "documents": [{k: v for k, v in x.items() if k != "text"} | {"excerpt": x["text"][:600]} for x in docs],
            "kinds": [{"id": k, "label": v, "refs": kind_refs(k)} for k, v in kinds.items()],
            "review_date": date.today().isoformat(),
            **form_meta([x["kind"] for x in docs if x["kind"]])}


# ── soát ──
def _spec(did: str, body: dict) -> Dossier:
    draft = _draft(did)
    parties = []
    for p in body.get("parties") or []:
        if not str(p.get("id") or "").strip() or not str(p.get("role") or "").strip():
            raise ValueError("Mỗi bên cần mã và vai trò")
        parties.append(Party(str(p["id"]), str(p["role"]), str(p.get("name") or ""),
                             p.get("continuous_employment") if isinstance(p.get("continuous_employment"), bool) else None))
    pids = {p.id for p in parties}
    docs = []
    for x in body.get("documents") or []:
        src = draft["docs"].get(x.get("doc_id"))
        if src is None:
            raise ValueError(f"Văn bản {x.get('doc_id')!r} không có trong hồ sơ")
        kind = str(x.get("kind") or "")
        if not kind:
            raise ValueError(f"Hãy chọn loại cho văn bản {src['filename']}")
        if kind != AMENDMENT and not packs_for_kind(kind):
            raise ValueError(f"Loại {kind!r} không có gói luật")
        refs = {k: str(v) for k, v in (x.get("refs") or {}).items() if v}
        if kind != AMENDMENT:
            bad = [v for v in refs.values() if v not in pids]
            if bad:
                raise ValueError(f"{src['filename']}: bên {bad[0]!r} chưa khai trong danh sách các bên")
        docs.append(DossierDoc(src["doc_id"], src["filename"], kind, refs, src["text"]))
    if not docs:
        raise ValueError("Hồ sơ chưa có văn bản")
    mains = {x.doc_id for x in docs if x.kind != AMENDMENT}
    if not mains:
        raise ValueError("Hồ sơ cần ít nhất một hợp đồng chính (không phải phụ lục)")
    for x in docs:
        if x.kind == AMENDMENT and x.refs.get("contract") not in mains:
            raise ValueError(f"Phụ lục {x.file}: hãy chọn hợp đồng mà nó sửa đổi")
    review = date.fromisoformat(str(body.get("review_date") or date.today().isoformat()))
    user = {k: v for k, v in (body.get("user_facts") or {}).items() if v is not None}
    return Dossier(did, review, _packs([x.kind for x in docs]), tuple(parties), tuple(docs), user, Path("."))


def _facts_key(d: Dossier) -> str:
    groups = [(m.doc_id, m.kind, [x.doc_id for x in d.parts(m.doc_id)]) for m in d.documents if m.kind != AMENDMENT]
    return hashlib.sha256(json.dumps([groups, list(d.packs)]).encode()).hexdigest()[:16]


def _fact_json(f) -> dict:
    if is_unresolved(f):
        return {"value": None, "unresolved": repr(f)}
    return {"value": f.value.isoformat() if isinstance(f.value, date) else f.value, "unit": f.unit, "quote": f.quote}


def _object_label(obj: str | None, d: Dossier) -> str | None:
    """`employee=e1` -> `employee: <tên bên>`."""
    if not obj:
        return obj
    parts = []
    for item in obj.split(","):
        k, _, v = item.partition("=")
        p = d.party(v)
        parts.append(f"{k}: {p.name or p.id}" if p else item)
    return ", ".join(parts)


def analyze(did: str, body: dict, *, on_event=None) -> dict:
    emit = on_event or (lambda e: None)
    d = _spec(did, body)
    draft = _draft(did)
    if not d.packs:
        raise ValueError("Không có gói luật cho các loại văn bản đã chọn")
    cat = api._packs_catalog(d.packs)
    key = _facts_key(d)
    facts = draft["facts"].get(key)
    if facts is None:
        emit({"type": "stage", "stage": "facts", "status": "start"})
        facts = extract_dossier_facts(api.CONFIG.llm_factory(), d, extra_fields=cat.context.extract_fields)
        draft["facts"] = {key: facts}          # chỉ giữ bộ trích của cách ghép hiện tại
        emit({"type": "stage", "stage": "facts", "status": "done"})
    objs = dossier_objects(d, facts)
    names = {x.doc_id: x.file for x in d.documents}
    emit({"type": "objects", "objects": [_object_json(o, names) for o in objs]})
    answers = {k: v for k, v in (body.get("answers") or {}).items() if v is not None}
    user = {**d.user_facts, **answers}
    session = evaluator_for(cat, default_kind()).session(
        day=d.review_date, facts={k: Fact(v, None, "user") for k, v in user.items()}, present=set(), evidence={},
        objects=objs)
    results = [r for r in session.results() if r.object is not None]
    out = []
    for r in results:
        concept = cat.concepts.get(r.concept_id)
        out.append({**dataclasses.asdict(r), "concept_label": concept.label if concept else r.concept_id,
                    "verdict": cat.verdict_label(r.finding), "object_label": _object_label(r.object, d),
                    "explain": explain(cat, session, r.concept_id, r.rule_id, r.object).to_json()})
    missing = {f for r in results if r.status == "UNKNOWN" for f in r.missing_facts}
    questions = [question_payload(cat, q) for q in next_questions(cat, session) if q.fact in missing]
    return {"dossier_id": did, "review_date": d.review_date.isoformat(), "packs": list(d.packs),
            "objects": [_object_json(o, names) for o in objs], "results": out, "questions": questions,
            "user_facts": user, "supports_dossier": bool(objs) and form_meta([x.kind for x in d.documents])["supports_dossier"]}


def _object_json(o, names: dict) -> dict:
    return {"id": o.id, "filename": names.get(o.id), "type": o.type,
            "valid_from": o.valid_from.isoformat() if o.valid_from and o.valid_from != date.min else None,
            "valid_to": o.valid_to.isoformat() if o.valid_to else None, "refs": dict(o.refs),
            "attrs": {k: _fact_json(f) for k, f in o.attrs.items()}}


# ── HTTP ──
async def upload(request):
    form = await request.form(max_part_size=api.MAX_BYTES)
    files = []
    for f in form.getlist("files"):
        if not getattr(f, "filename", None):
            continue
        if Path(f.filename).suffix.lower() not in api.ALLOWED:
            return JSONResponse({"error": f"Không hỗ trợ định dạng của {f.filename}"}, status_code=400)
        data = await f.read(api.MAX_BYTES + 1)
        if len(data) > api.MAX_BYTES:
            return JSONResponse({"error": f"{f.filename} quá lớn: tối đa 50 MB"}, status_code=413)
        files.append((f.filename, data))
    if not files:
        return JSONResponse({"error": "Hãy chọn các văn bản của hồ sơ"}, status_code=400)
    return stream_work(lambda emit: create_draft(files, on_event=emit))


async def get_meta(request):
    kinds = [k for k in request.query_params.get("kinds", "").split(",") if k]
    return await api._call(form_meta, kinds)


async def analyze_stream(request):
    did = request.path_params["did"]
    body = await api._json(request)
    try:
        _draft(did)
    except UnknownDraft as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    return stream_work(lambda emit: analyze(did, body, on_event=emit))


routes = [
    Route("/api/contract-studio/dossier/upload/stream", upload, methods=["POST"]),
    Route("/api/contract-studio/dossier/meta", get_meta, methods=["GET"]),
    Route("/api/contract-studio/dossier/{did}/analyze/stream", analyze_stream, methods=["POST"]),
]
