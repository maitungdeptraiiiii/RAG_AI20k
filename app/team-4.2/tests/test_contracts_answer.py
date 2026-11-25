"""Hỏi đáp với hợp đồng (không Think): quy tắc kết luận pháp lý + che PII trong câu tra luật."""
import json
from datetime import date, datetime, timezone
from pathlib import Path

from rag.contracts import answer as ca
from rag.contracts.evidence import LawEvidence
from rag.contracts.models import Contract
from rag.contracts.parse import split_units
from rag.schema import Chunk

ROOT = Path(__file__).resolve().parents[3]
TEXT = (ROOT / "data" / "team-4.2" / "contracts_demo" / "hop_dong_thue_nha_2023.txt").read_text(encoding="utf-8")
LEGACY = Chunk("blds:418", "blds", "bo_luat_dan_su_2015.txt", 1, 1, "Điều 418. Thỏa thuận phạt vi phạm",
               "Điều 418. Thỏa thuận phạt vi phạm\n1. Phạt vi phạm là sự thỏa thuận giữa các bên trong hợp đồng.")
QUESTION = "Bên cho thuê có được chấm dứt không?"


def contract(sign=date(2023, 3, 15)):
    units = split_units(TEXT)
    c = Contract("c1", "hd.txt", False, datetime(2026, 11, 11, tzinfo=timezone.utc), TEXT, units, len(units))
    c.sign_date, c.party = sign, "Bên thuê"
    c.facts = {"type": "Hợp đồng thuê nhà ở", "parties": [{"role": "Bên cho thuê"}, {"role": "Bên thuê"}]}
    return c


class StageLLM:
    """Trả lời theo bước (dòng đầu của prompt hệ thống: 'BƯỚC: <tên>')."""

    def __init__(self, handlers):
        self.handlers, self.calls = handlers, []

    def complete(self, system, user):
        stage = system.split("\n", 1)[0].removeprefix("BƯỚC:").strip()
        payload = json.loads(user)
        self.calls.append((stage, payload))
        out = self.handlers[stage](payload)
        return out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)


def ctx(llm, legacy=None):
    return ca.AnswerContext(llm, None, legacy)


def verify_all(p):
    return {"results": [{"id": f["id"], "supporting": [x["eid"] for x in f["candidates"]]} for f in p["findings"]]}


def legal_answer(c, law_ids=True):
    return lambda p: {"answer": "Bên cho thuê được chấm dứt ngay.", "legal_conclusion": True,
                      "law_ids": [x["eid"] for x in p["laws"]] if law_ids else [], "units": [c.units[9].uid]}


def test_legacy_only_support_is_conditional():
    c = contract()
    llm = StageLLM({"answer": legal_answer(c), "verify": verify_all})
    out = ca.answer(ctx(llm, lambda q, k: [LEGACY]), c, QUESTION, [])
    assert out["legal_status"] == "conditional" and out["evidence"][0]["store"] == "legacy"
    assert out["answer"].endswith(ca.LEGACY_NOTE + ".")


def test_no_law_store_refuses_and_does_not_repeat_unverified_conclusion():
    c = contract()
    llm = StageLLM({"answer": legal_answer(c, law_ids=False)})
    out = ca.answer(ctx(llm), c, QUESTION, [])
    assert out["legal_status"] == "cannot_conclude"
    assert "chấm dứt ngay" not in out["answer"] and out["answer"].startswith("Kho chưa có")
    assert "Điều 9" in out["answer"]                      # vẫn chỉ ra điều khoản liên quan trong hợp đồng
    assert [s for s, _ in llm.calls] == ["answer"]        # không có ứng viên -> không gọi kiểm chứng


def test_missing_sign_date_blocks_legal_conclusion():
    c = contract(sign=None)
    llm = StageLLM({"answer": legal_answer(c)})
    out = ca.answer(ctx(llm, lambda q, k: [LEGACY]), c, QUESTION, [])
    assert out["legal_status"] == "blocked_no_date" and out["answer"].startswith(ca.NO_DATE_NOTE)
    assert out["anchor"] is None and llm.calls[0][1]["laws"] == []


def test_non_legal_answer_is_returned_as_is():
    c = contract()
    llm = StageLLM({"answer": lambda p: {"answer": "Giá thuê ghi ở Điều 4.", "legal_conclusion": False,
                                         "law_ids": [], "units": []}})
    out = ca.answer(ctx(llm), c, "Giá thuê ở đâu?", [])
    assert out == {"answer": "Giá thuê ghi ở Điều 4.", "legal_status": "not_legal", "units": [], "evidence": [],
                   "anchor": "2023-03-15", "warnings": []}


def test_law_search_query_is_pii_masked():
    c = contract()
    seen = []

    def legacy(q, k):
        seen.append(q)
        return [LEGACY]
    llm = StageLLM({"answer": lambda p: {"answer": "ok", "legal_conclusion": False, "law_ids": [], "units": []}})
    ca.answer(ctx(llm, legacy), c, "CCCD của tôi 001085012345 thì sao?", [])
    assert seen and all("001085012345" not in q for q in seen)


def test_conflicted_versioned_evidence_is_only_conditional():
    conflicted = LawEvidence("L1", "versioned", "Luật Nhà ở", "Điều 132", "t", date(2015, 7, 1), None, "conflicted",
                             "luat:65/2014/QH13", "luat:65/2014/QH13#d132")
    verified = LawEvidence("L2", "versioned", "Luật Nhà ở", "Điều 131", "t", date(2015, 7, 1), None, "needs_review",
                           "luat:65/2014/QH13", "luat:65/2014/QH13#d131")
    assert ca.legal_status([conflicted]) == "conditional"
    assert ca.legal_status([conflicted, verified]) == "concluded"
    assert ca.legal_status([]) == "cannot_conclude"
