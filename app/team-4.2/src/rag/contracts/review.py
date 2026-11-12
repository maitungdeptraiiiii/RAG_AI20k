"""Sáu thao tác trên hợp đồng + quy tắc pháp lý (spec phần 4 §4.2–4.3, phạm vi demo §0).

Quy tắc:
- Kết luận pháp lý chỉ khi bước kiểm chứng (một lượt LLM cho cả báo cáo) xác nhận có căn cứ hỗ trợ:
  kho có phiên bản -> "concluded"; chỉ kho cũ -> "conditional"; không có -> "cannot_conclude" + câu từ chối.
- Thiếu ngày ký -> phần pháp lý "blocked_no_date"; không bao giờ ngầm dùng hôm nay.
- Trích dẫn điều khoản phải có thật trong hợp đồng; sai -> needs_check.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from rag.contracts.evidence import LawEvidence, LegacySearch, find_evidence, law_changes
from rag.contracts.llm_json import ContractAIError, ask_json, quote_ok
from rag.contracts.models import Contract
from rag.contracts.parse import llm_units
from rag.quality.pii import mask_text

GROUPS = ("illegal", "missing_required", "unfavorable", "ambiguous")
LEGAL_GROUPS = ("illegal", "missing_required")
SEVERITY = {"critical": 0, "major": 1, "minor": 2}
NOT_LEGAL_NOTE = "Nhận xét về câu chữ / thương mại — không phải kết luận pháp lý"
LEGACY_NOTE = "Căn cứ từ Kho cũ — chưa xác định phiên bản; kết luận có điều kiện"
NO_DATE_NOTE = "Chưa có ngày ký — hãy nhập ngày ký để kiểm tra pháp lý"
UPLOAD_HINT = "Có thể upload luật ở trang Nạp văn bản pháp luật (/upload)."
DEFAULT_LAW = "luật điều chỉnh vấn đề này"
GROUP_LABEL = {"illegal": "Trái luật", "missing_required": "Thiếu nội dung bắt buộc", "unfavorable": "Bất lợi",
               "ambiguous": "Mơ hồ / dễ tranh chấp"}
SUSPECT_LABEL = {"illegal": "Nghi vấn trái luật — chưa kết luận",
                 "missing_required": "Nghi vấn thiếu nội dung bắt buộc — chưa kết luận"}
UNVERIFIED_NOTE = "Nhận định của AI, chưa có căn cứ trong kho luật"


def refusal_text(law: str | None, in_store: bool = False) -> str:
    law = (law or "").strip() or DEFAULT_LAW
    if in_store:
        return (f"Chưa tìm thấy căn cứ trong kho ({law}) hỗ trợ kết luận này tại ngày ký — chưa thể kết luận "
                f"điều khoản này có hợp pháp không. {UPLOAD_HINT}")
    return f"Kho chưa có {law} — chưa thể kết luận điều khoản này có hợp pháp không. {UPLOAD_HINT}"


@dataclass
class ReviewContext:
    llm: Any
    runtime: Any                    # LegalRuntime đang lease (None nếu kho có phiên bản chưa dùng được)
    legacy_search: LegacySearch | None
    today: date


# --- prompt -----------------------------------------------------------------------------------

_ROLE = ("Bạn là luật sư Việt Nam soát hợp đồng. Chỉ dựa trên nội dung được cung cấp; không bịa căn cứ. "
         "Mọi 'quote' phải chép NGUYÊN VĂN từ hợp đồng.")

FIND = "BƯỚC: find\n" + _ROLE + """
Tìm các điểm có vấn đề trong các đơn vị được giao. Trả JSON:
{"findings": [{"unit": "uid", "quote": "trích nguyên văn", "group": "illegal|missing_required|unfavorable|ambiguous",
  "severity": "critical|major|minor", "disadvantaged": "vai trò bên chịu bất lợi hoặc 'Cả hai bên'",
  "explanation": "...", "legal_question": "câu tra cứu luật nếu là vấn đề pháp lý, không thì null",
  "law_hint": "tên luật điều chỉnh nếu biết, không thì null", "suggestion": "gợi ý sửa"}]}
Ưu tiên các điểm bất lợi cho bên "party". missing_required = thiếu nội dung bắt buộc theo luật (unit = đơn vị gần nhất)."""

SELECT = "BƯỚC: select\n" + _ROLE + """
Chọn các đơn vị liên quan tới các chủ đề người dùng yêu cầu. Trả JSON: {"units": ["uid", ...]}"""

VERIFY = "BƯỚC: verify\n" + _ROLE + """
Với mỗi nhận định, chỉ giữ những căn cứ (eid) mà nội dung THỰC SỰ hỗ trợ nhận định đó (không chỉ cùng chủ đề).
Trả JSON: {"results": [{"id": "...", "supporting": ["eid", ...]}]}"""

SUMMARY = "BƯỚC: summary\n" + _ROLE + """
Tóm tắt hợp đồng theo các mục: Các bên; Đối tượng; Giá và thanh toán; Thời hạn; Nghĩa vụ chính mỗi bên;
Các mốc thời gian; Luật áp dụng / giải quyết tranh chấp. Trả JSON:
{"sections": [{"title": "...", "items": [{"text": "...", "unit": "uid"}]}]}"""

REDLINE = "BƯỚC: redline\n" + _ROLE + """
Viết lại từng đoạn có vấn đề theo hướng bảo vệ bên "party" (nếu party là "neutral" thì cân bằng hai bên).
Trả JSON: {"redlines": [{"finding_id": "...", "old": "đoạn cũ nguyên văn", "new": "đoạn đề xuất", "reason": "..."}]}"""

ANSWER = "BƯỚC: answer\n" + _ROLE + """
Trả lời câu hỏi của người dùng về hợp đồng, dựa trên các đơn vị và căn cứ luật được cung cấp (laws).
"legal_conclusion" = true khi câu trả lời khẳng định điều gì đó hợp pháp / trái luật / được hay không được làm theo luật.
Trả JSON: {"answer": "...", "legal_conclusion": true|false, "law_ids": ["eid đã dùng"], "units": ["uid đã dùng"]}"""


# --- helpers ----------------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _warnings(contract: Contract) -> list[str]:
    """Cảnh báo chất lượng tách hợp đồng (rỗng với hợp đồng Phần 4 chưa có doc)."""
    return list(contract.doc.report.warnings) if contract.doc is not None else []


def _new_report(contract: Contract, op: str, coverage: dict | None = None, **extra) -> dict[str, Any]:
    rep = {"rid": uuid.uuid4().hex[:10], "op": op, "created_at": _now(), "party": contract.party or "neutral",
           "anchor": contract.sign_date.isoformat() if contract.sign_date else None,
           "coverage": coverage or {"reviewed": len(contract.units), "total": contract.total_units},
           "warnings": _warnings(contract), **extra}
    contract.reports[rep["rid"]] = rep
    return rep


def _units_payload(units) -> list[dict]:
    return [{"uid": u.uid, "label": u.label, "text": u.text} for u in units]


def _law_titles(runtime) -> list[str]:
    if runtime is None:
        return []
    try:
        return [d.title for d in runtime.service.store.documents()]
    except Exception:  # noqa: BLE001
        return []


def _in_store(law: str | None, titles: list[str]) -> bool:
    if not law:
        return False
    needle = law.casefold().strip()
    return any(needle in t.casefold() for t in titles)


def _verify(ctx: ReviewContext, contract: Contract, items: list[dict]) -> dict[str, list[str]]:
    """items: [{"id", "claim", "quote", "candidates": [LawEvidence]}] -> id -> eid hỗ trợ (đã lọc trong ứng viên)."""
    asks = [it for it in items if it["candidates"]]
    if not asks:
        return {}
    payload = {"findings": [{"id": it["id"], "claim": it["claim"], "quote": it.get("quote", ""),
                             "candidates": [{"eid": e.eid, "source_title": e.source_title, "section": e.section,
                                             "text": e.text[:1500]} for e in it["candidates"]]} for it in asks]}
    data = ask_json(ctx.llm, VERIFY, payload, contract.mask_state)
    allowed = {it["id"]: {e.eid for e in it["candidates"]} for it in asks}
    out: dict[str, list[str]] = {}
    for r in data.get("results") or []:
        if isinstance(r, dict) and r.get("id") in allowed:
            out[r["id"]] = [e for e in (r.get("supporting") or []) if e in allowed[r["id"]]]
    return out


def _legal_status(supporting: list[LawEvidence]) -> str:
    """Căn cứ kho có phiên bản (không mâu thuẫn) -> concluded; chỉ kho cũ / chỉ phiên bản mâu thuẫn -> conditional."""
    if any(e.store == "versioned" and e.status != "conflicted" for e in supporting):
        return "concluded"
    return "conditional" if supporting else "cannot_conclude"


def _masked(contract: Contract, text: str) -> str:
    """Câu tra luật đi qua embedding / rerank bên ngoài: che PII như đường chat thường."""
    return mask_text(text, state=contract.mask_state).masked_text


# --- thao tác ---------------------------------------------------------------------------------

def summarize(ctx: ReviewContext, contract: Contract) -> dict[str, Any]:
    data = ask_json(ctx.llm, SUMMARY, {"units": _units_payload(llm_units(contract.units)), "facts": contract.facts},
                    contract.mask_state)
    labels = {u.uid: u.label for u in contract.units}
    sections = []
    for s in data.get("sections") or []:
        if not isinstance(s, dict):
            continue
        items = [{"text": str(i.get("text") or ""), "unit": i.get("unit"), "unit_label": labels.get(i.get("unit"))}
                 for i in s.get("items") or [] if isinstance(i, dict) and i.get("text")]
        sections.append({"title": str(s.get("title") or ""), "items": items})
    if not sections:
        raise ContractAIError()
    return _new_report(contract, "summary", sections=sections)


def _scope(ctx: ReviewContext, contract: Contract, unit_ids, topics):
    if unit_ids:
        wanted = set(unit_ids)
        return [u for u in contract.units if u.uid in wanted]
    if topics:
        data = ask_json(ctx.llm, SELECT, {"topics": list(topics), "units": _units_payload(llm_units(contract.units))},
                        contract.mask_state)
        wanted = {str(x) for x in data.get("units") or []}
        by_label = {u.label.casefold(): u.uid for u in contract.units}
        wanted |= {by_label[w.casefold()] for w in wanted if w.casefold() in by_label}
        scope = [u for u in contract.units if u.uid in wanted]
        if not scope:
            raise ContractAIError("Không xác định được điều khoản thuộc chủ đề đã chọn — hãy chọn điều khoản cụ thể")
        return scope
    return llm_units(contract.units)          # soát toàn bộ: bản demo gửi LLM tối đa 30 đơn vị đầu


def review(ctx: ReviewContext, contract: Contract, *, unit_ids=None, topics=None) -> dict[str, Any]:
    scope = _scope(ctx, contract, unit_ids, topics)
    party = contract.party or "neutral"
    data = ask_json(ctx.llm, FIND, {"party": party, "contract_type": contract.facts.get("type"),
                                    "parties": contract.facts.get("parties"), "units": _units_payload(scope)},
                    contract.mask_state)
    raw = data.get("findings")
    if not isinstance(raw, list):
        raise ContractAIError()
    by_uid = {u.uid: u for u in scope}
    by_uid.update({u.label.casefold(): u for u in scope})        # mô hình đôi khi trả nhãn "Điều 8" thay vì uid
    titles = _law_titles(ctx.runtime)
    findings: list[dict[str, Any]] = []
    candidates: dict[str, list[LawEvidence]] = {}
    for i, f in enumerate(raw, 1):
        key = str(f.get("unit") or "") if isinstance(f, dict) else ""
        unit = by_uid.get(key) or by_uid.get(key.casefold())
        if unit is None:
            continue
        group = f.get("group") if f.get("group") in GROUPS else "ambiguous"
        quote = str(f.get("quote") or "")
        # "thiếu nội dung bắt buộc": không có câu chữ để trích -> không bắt trích dẫn
        ok = quote_ok(unit.text, quote) or (group == "missing_required" and not quote.strip())
        legal = group in LEGAL_GROUPS or bool(f.get("legal_question"))
        item = {"id": f"F{i}", "unit": unit.uid, "unit_label": unit.label, "quote": quote if ok else "",
                "quote_ok": ok, "needs_check": not ok, "group": group,
                "severity": f.get("severity") if f.get("severity") in SEVERITY else "minor",
                "disadvantaged": str(f.get("disadvantaged") or ""), "explanation": str(f.get("explanation") or ""),
                "suggestion": str(f.get("suggestion") or ""), "law_hint": f.get("law_hint"), "legal": legal,
                "legal_status": "not_legal", "evidence": [], "refusal": None, "note": None}
        if not legal:
            item["note"] = NOT_LEGAL_NOTE
        elif contract.sign_date is None:
            item["legal_status"], item["note"] = "blocked_no_date", NO_DATE_NOTE
        elif ok:
            q = _masked(contract, f.get("legal_question") or item["explanation"])
            candidates[item["id"]] = find_evidence(ctx.runtime, ctx.legacy_search, q, contract.sign_date, k=3)
        findings.append(item)
    if raw and not findings:
        raise ContractAIError()

    support = _verify(ctx, contract, [{"id": fid, "claim": next(x["explanation"] for x in findings if x["id"] == fid),
                                      "quote": next(x["quote"] for x in findings if x["id"] == fid),
                                      "candidates": cands} for fid, cands in candidates.items()])
    for item in findings:
        if item["id"] not in candidates:
            if item["legal"] and item["legal_status"] == "not_legal":      # trích dẫn sai: chưa xét pháp lý
                item["legal_status"] = "cannot_conclude"
                item["refusal"] = "Trích dẫn không khớp hợp đồng — cần kiểm tra lại trước khi kết luận."
            continue
        ev = {e.eid: e for e in candidates[item["id"]]}
        used = [ev[eid] for eid in support.get(item["id"], []) if eid in ev]
        item["legal_status"] = _legal_status(used)
        item["evidence"] = [e.to_dict() for e in used]
        if item["legal_status"] == "conditional":
            item["note"] = LEGACY_NOTE
        elif item["legal_status"] == "cannot_conclude":
            item["refusal"] = refusal_text(item["law_hint"], _in_store(item["law_hint"], titles))
    for item in findings:
        unverified = item["group"] in SUSPECT_LABEL and item["legal_status"] in ("cannot_conclude", "blocked_no_date")
        item["group_label"] = SUSPECT_LABEL[item["group"]] if unverified else GROUP_LABEL[item["group"]]
        item["explanation_note"] = UNVERIFIED_NOTE if unverified else None

    def rank(f):
        mine = party != "neutral" and party.casefold() in f["disadvantaged"].casefold()
        return (0 if mine else 1, SEVERITY.get(f["severity"], 3))

    findings.sort(key=rank)
    op = "partial" if (unit_ids or topics) else "review"
    # hợp đồng mới: total_units == len(units); bản Phần 4 đã cắt units còn 30 nhưng total_units giữ tổng thật
    coverage = {"reviewed": len(scope), "total": max(len(contract.units), contract.total_units)}
    return _new_report(contract, op, coverage=coverage, scope=[u.label for u in scope], topics=list(topics or []), findings=findings)


def _latest(contract: Contract, ops: tuple[str, ...]) -> dict | None:
    reps = [r for r in contract.reports.values() if r.get("op") in ops]
    return max(reps, key=lambda r: r["created_at"]) if reps else None


def law_changes_report(ctx: ReviewContext, contract: Contract) -> dict[str, Any]:
    base = _latest(contract, ("review", "partial")) or review(ctx, contract)
    seen: dict[str, LawEvidence] = {}
    affected: dict[str, list[str]] = {}
    for f in base["findings"]:
        for d in f["evidence"]:
            seen.setdefault(d["eid"], LawEvidence.from_dict(d))
            affected.setdefault(d["eid"], [])
            if f["unit_label"] not in affected[d["eid"]]:
                affected[d["eid"]].append(f["unit_label"])
    rows = law_changes(ctx.runtime, list(seen.values()), ctx.today)
    for r in rows:
        r["affected_units"] = affected.get(r["eid"], [])
    return _new_report(contract, "law_changes", coverage=base["coverage"], based_on=base["rid"], today=ctx.today.isoformat(), changes=rows)


def redline(ctx: ReviewContext, contract: Contract) -> dict[str, Any]:
    base = _latest(contract, ("review", "partial")) or review(ctx, contract)
    findings = base["findings"]
    if not findings:
        return _new_report(contract, "redline", coverage=base["coverage"], based_on=base["rid"], redlines=[])
    payload = {"party": contract.party or "neutral",
               "findings": [{"id": f["id"], "unit_label": f["unit_label"], "quote": f["quote"],
                             "unit_text": (contract.unit(f["unit"]).text if contract.unit(f["unit"]) else ""),
                             "explanation": f["explanation"], "suggestion": f["suggestion"]} for f in findings]}
    data = ask_json(ctx.llm, REDLINE, payload, contract.mask_state)
    by_id = {f["id"]: f for f in findings}
    out = []
    for r in data.get("redlines") or []:
        if not isinstance(r, dict) or r.get("finding_id") not in by_id:
            continue
        f = by_id[r["finding_id"]]
        old = str(r.get("old") or "")
        old_ok = quote_ok(contract.text, old)
        out.append({"finding_id": f["id"], "unit_label": f["unit_label"], "old": old, "old_ok": old_ok,
                    "new": str(r.get("new") or ""), "reason": str(r.get("reason") or ""),
                    "legal_note": "Chưa kiểm tra pháp lý" if f["legal_status"] in ("cannot_conclude", "blocked_no_date")
                    else None})
    if not out:
        raise ContractAIError()
    return _new_report(contract, "redline", coverage=base["coverage"], based_on=base["rid"], redlines=out)


def answer(ctx: ReviewContext, contract: Contract, question: str, history: list[dict]) -> dict[str, Any]:
    laws = (find_evidence(ctx.runtime, ctx.legacy_search, _masked(contract, question), contract.sign_date, k=4)
            if contract.sign_date else [])
    data = ask_json(ctx.llm, ANSWER, {
        "question": question, "party": contract.party or "neutral",
        "history": [{"query": str(h.get("query", ""))[:500], "answer": str(h.get("answer", ""))[:500]}
                    for h in (history or [])[-3:] if isinstance(h, dict)],
        "units": _units_payload(llm_units(contract.units)),
        "laws": [{"eid": e.eid, "source_title": e.source_title, "section": e.section, "text": e.text[:1500]}
                 for e in laws]}, contract.mask_state)
    text = str(data.get("answer") or "").strip()
    if not text:
        raise ContractAIError()
    labels = {u.uid: u.label for u in contract.units}
    units = [labels[u] for u in data.get("units") or [] if u in labels]
    status, used = "not_legal", []
    related = ("\n\nCác điều khoản liên quan trong hợp đồng: " + ", ".join(units) + ".") if units else ""
    if data.get("legal_conclusion"):
        if contract.sign_date is None:
            status = "blocked_no_date"
            text = NO_DATE_NOTE + "." + related          # không nhắc lại kết luận pháp lý chưa kiểm tra
        else:
            by = {e.eid: e for e in laws}
            cands = [by[e] for e in data.get("law_ids") or [] if e in by]
            support = _verify(ctx, contract, [{"id": "A", "claim": text, "quote": "", "candidates": cands}])
            used = [by[e] for e in support.get("A", [])]
            status = _legal_status(used)
            if status == "conditional":
                text += "\n\n" + LEGACY_NOTE + "."
            elif status == "cannot_conclude":
                text = refusal_text(None) + related      # không nhắc lại kết luận pháp lý chưa kiểm chứng
    return {"answer": text, "legal_status": status, "units": units, "evidence": [e.to_dict() for e in used],
            "anchor": contract.sign_date.isoformat() if contract.sign_date else None,
            "warnings": _warnings(contract)}
