"""Hỏi đáp với hợp đồng (không Think) — đường `/api/chat` có `contract_id`.

Quy tắc pháp lý:
- Câu trả lời khẳng định điều gì đó hợp pháp / trái luật chỉ giữ khi một lượt LLM kiểm chứng xác nhận có căn cứ hỗ trợ:
  kho có phiên bản -> "concluded"; chỉ kho cũ -> "conditional"; không có -> "cannot_conclude" + câu từ chối.
- Thiếu ngày ký -> "blocked_no_date"; không bao giờ ngầm dùng hôm nay.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rag.contracts.evidence import LawEvidence, LegacySearch, find_evidence
from rag.contracts.llm_json import ContractAIError, ask_json
from rag.contracts.models import Contract
from rag.contracts.parse import llm_units
from rag.quality.pii import mask_text

LEGACY_NOTE = "Căn cứ từ Kho cũ — chưa xác định phiên bản; kết luận có điều kiện"
NO_DATE_NOTE = "Chưa có ngày ký — hãy nhập ngày ký để kiểm tra pháp lý"
UPLOAD_HINT = "Có thể upload luật ở trang Nạp văn bản pháp luật (/upload)."
DEFAULT_LAW = "luật điều chỉnh vấn đề này"


def refusal_text(law: str | None = None) -> str:
    law = (law or "").strip() or DEFAULT_LAW
    return f"Kho chưa có {law} — chưa thể kết luận điều khoản này có hợp pháp không. {UPLOAD_HINT}"


@dataclass
class AnswerContext:
    llm: Any
    runtime: Any                    # LegalRuntime đang lease (None nếu kho có phiên bản chưa dùng được)
    legacy_search: LegacySearch | None


_ROLE = ("Bạn là luật sư Việt Nam soát hợp đồng. Chỉ dựa trên nội dung được cung cấp; không bịa căn cứ. "
         "Mọi 'quote' phải chép NGUYÊN VĂN từ hợp đồng.")

VERIFY = "BƯỚC: verify\n" + _ROLE + """
Với mỗi nhận định, chỉ giữ những căn cứ (eid) mà nội dung THỰC SỰ hỗ trợ nhận định đó (không chỉ cùng chủ đề).
Trả JSON: {"results": [{"id": "...", "supporting": ["eid", ...]}]}"""

ANSWER = "BƯỚC: answer\n" + _ROLE + """
Trả lời câu hỏi của người dùng về hợp đồng, dựa trên các đơn vị và căn cứ luật được cung cấp (laws).
"legal_conclusion" = true khi câu trả lời khẳng định điều gì đó hợp pháp / trái luật / được hay không được làm theo luật.
Trả JSON: {"answer": "...", "legal_conclusion": true|false, "law_ids": ["eid đã dùng"], "units": ["uid đã dùng"]}"""


def _warnings(contract: Contract) -> list[str]:
    """Cảnh báo chất lượng tách hợp đồng (rỗng với hợp đồng Phần 4 chưa có doc)."""
    return list(contract.doc.report.warnings) if contract.doc is not None else []


def _supporting(ctx: AnswerContext, contract: Contract, claim: str, candidates: list[LawEvidence]) -> list[LawEvidence]:
    """Căn cứ (trong số ứng viên) mà LLM kiểm chứng xác nhận hỗ trợ nhận định."""
    if not candidates:
        return []
    payload = {"findings": [{"id": "A", "claim": claim, "quote": "",
                             "candidates": [{"eid": e.eid, "source_title": e.source_title, "section": e.section,
                                             "text": e.text[:1500]} for e in candidates]}]}
    data = ask_json(ctx.llm, VERIFY, payload, contract.mask_state)
    by = {e.eid: e for e in candidates}
    for r in data.get("results") or []:
        if isinstance(r, dict) and r.get("id") == "A":
            return [by[eid] for eid in r.get("supporting") or [] if eid in by]
    return []


def legal_status(supporting: list[LawEvidence]) -> str:
    """Căn cứ kho có phiên bản (không mâu thuẫn) -> concluded; chỉ kho cũ / chỉ phiên bản mâu thuẫn -> conditional."""
    if any(e.store == "versioned" and e.status != "conflicted" for e in supporting):
        return "concluded"
    return "conditional" if supporting else "cannot_conclude"


def answer(ctx: AnswerContext, contract: Contract, question: str, history: list[dict]) -> dict[str, Any]:
    # câu tra luật đi qua embedding / rerank bên ngoài: che PII như đường chat thường
    query = mask_text(question, state=contract.mask_state).masked_text
    laws = find_evidence(ctx.runtime, ctx.legacy_search, query, contract.sign_date, k=4) if contract.sign_date else []
    data = ask_json(ctx.llm, ANSWER, {
        "question": question, "party": contract.party or "neutral",
        "history": [{"query": str(h.get("query", ""))[:500], "answer": str(h.get("answer", ""))[:500]}
                    for h in (history or [])[-3:] if isinstance(h, dict)],
        "units": [{"uid": u.uid, "label": u.label, "text": u.text} for u in llm_units(contract.units)],
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
            used = _supporting(ctx, contract, text, [by[e] for e in data.get("law_ids") or [] if e in by])
            status = legal_status(used)
            if status == "conditional":
                text += "\n\n" + LEGACY_NOTE + "."
            elif status == "cannot_conclude":
                text = refusal_text() + related          # không nhắc lại kết luận pháp lý chưa kiểm chứng
    return {"answer": text, "legal_status": status, "units": units, "evidence": [e.to_dict() for e in used],
            "anchor": contract.sign_date.isoformat() if contract.sign_date else None,
            "warnings": _warnings(contract)}
