"""Hợp đồng mẫu ngoài lao động chạy qua check_contract với LLM giả (dùng cho tests/test_pack_modularity.py)."""
import json
from datetime import datetime, timezone

from rag.bridge.check import check_contract
from rag.contracts.doc import PageText
from rag.contracts.models import Contract
from rag.contracts.structure import parse_contract, to_contract_units

AT = datetime(2026, 11, 14, 9, 0)
LOAN_TEXT = ("Bên A: ông Trần Văn B, là Bên cho vay. Bên B: bà Lê Thị C, là Bên vay. Ký ngày 02 tháng 01 năm 2025.\n"
             "Điều 1. Bên A cho Bên B vay 100.000.000 đồng.\n"
             "Điều 2. Lãi suất vay là 30%/năm.")


class ScriptedLoanLLM:
    """Trả lời theo nội dung payload (không theo câu chữ prompt), ghi lại mọi system prompt nhận được."""

    def __init__(self):
        self.systems: list[str] = []

    def complete(self, system, user):
        payload = json.loads(user)
        self.systems.append(system)
        if "fields_wanted" in payload:
            return json.dumps({"type": "Hợp đồng vay tiền",
                               "parties": [{"name": "Trần Văn B", "role": "Bên cho vay", "unit": "p0.pre",
                                            "quote": "là Bên cho vay"},
                                           {"name": "Lê Thị C", "role": "Bên vay", "unit": "p0.pre", "quote": "là Bên vay"}],
                               "sign_date": {"value": "2025-01-02", "unit": "p0.pre",
                                             "quote": "Ký ngày 02 tháng 01 năm 2025"},
                               "fields": {}}, ensure_ascii=False)
        uids = [u["uid"] for u in payload.get("units") or []]
        items = [{"concept": "loan.interest_cap", "uid": "p0.d2", "quote": "Lãi suất vay là 30%/năm",
                  "slots": {"interest_rate": "30%/năm"}}] if "p0.d2" in uids else []
        return json.dumps({"items": items}, ensure_ascii=False)


def loan_contract() -> Contract:
    pages = [PageText(1, LOAN_TEXT)]
    doc = parse_contract(pages)
    units = to_contract_units(doc)
    return Contract("c1", "vay.txt", False, datetime(2026, 11, 14, tzinfo=timezone.utc),
                    "\n".join(u.text for u in units), list(units), len(units), doc=doc, page_texts=list(pages),
                    file_checksum="x")


def run_loan_contract(**kw):
    llm = ScriptedLoanLLM()
    report = check_contract(llm, loan_contract(), at=AT, packs=["civil_loan"],
                            user_facts={"special_law_applies": False}, **kw)
    return llm, report
