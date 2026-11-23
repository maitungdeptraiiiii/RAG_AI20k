"""H2: nhận diện loại hợp đồng (quyết định gói nào được chạy). LLM chọn trong `document_kinds` của các gói; không chắc /
câu trích bịa / loại lạ -> `unknown` (không đoán, không rơi về gói lao động)."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from rag.contracts.classify import UNKNOWN, classify_contract, document_kinds
from rag.contracts.models import Contract
from rag.contracts.parse import split_units

ROOT = Path(__file__).resolve().parents[3]
LEASE = ROOT / "data" / "team-4.2" / "contracts_demo" / "hop_dong_thue_nha_2023.txt"
LOAN = Path(__file__).parent / "fixtures" / "rete" / "loan" / "l1_hop_le.txt"


def contract(path: Path) -> Contract:
    text = path.read_text(encoding="utf-8")
    units = split_units(text)
    return Contract("c1", path.name, False, datetime(2026, 11, 23, tzinfo=timezone.utc), text, units, len(units))


class FakeLLM:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def complete(self, system, user):
        self.calls.append((system, json.loads(user)))
        if isinstance(self.reply, Exception):
            raise self.reply
        r = self.reply(json.loads(user)) if callable(self.reply) else self.reply
        return json.dumps(r, ensure_ascii=False)


def answer(kind, quote, confidence=0.95):
    def reply(payload):
        uid = next((u["uid"] for u in payload["units"] if quote in u["text"]), payload["units"][0]["uid"])
        return {"kind": kind, "confidence": confidence, "unit": uid, "quote": quote}
    return reply


def test_document_kinds_come_from_packs():
    kinds = document_kinds()
    assert {"labor_contract", "loan_contract", "lease_contract"} <= set(kinds)
    assert kinds["lease_contract"] == "hợp đồng thuê nhà ở"


def test_lease_is_recognized_with_checked_evidence():
    llm = FakeLLM(answer("lease_contract", "HỢP ĐỒNG THUÊ NHÀ Ở"))
    r = classify_contract(llm, contract(LEASE))
    assert r["kind"] == "lease_contract" and r["confidence"] == 0.95
    assert r["evidence"][0]["quote"] == "HỢP ĐỒNG THUÊ NHÀ Ở"
    system, payload = llm.calls[0]
    assert {k["id"] for k in payload["kinds"]} >= {"labor_contract", "loan_contract", "lease_contract"}
    assert "lao động" not in system                   # prompt không giả định loại nào


def test_loan_is_recognized():
    r = classify_contract(FakeLLM(answer("loan_contract", "HỢP ĐỒNG VAY TIỀN")), contract(LOAN))
    assert r["kind"] == "loan_contract"


@pytest.mark.parametrize("reply,reason", [
    (answer("lease_contract", "HỢP ĐỒNG THUÊ XE Ô TÔ"), "quote_not_found"),       # câu trích bịa
    (answer("sale_contract", "HỢP ĐỒNG THUÊ NHÀ Ở"), "unknown_kind"),           # loại không có gói
    (answer("lease_contract", "HỢP ĐỒNG THUÊ NHÀ Ở", 0.4), "low_confidence"),   # không chắc
    (answer("unknown", "HỢP ĐỒNG THUÊ NHÀ Ở", 0.9), "model_unknown"),
    (RuntimeError("mạng lỗi"), "llm_error"),
    ({"kind": "lease_contract"}, "quote_not_found"),                             # thiếu bằng chứng
])
def test_uncertain_answers_become_unknown(reply, reason):
    r = classify_contract(FakeLLM(reply), contract(LEASE))
    assert r["kind"] == UNKNOWN and r["reason"] == reason and r["evidence"] == []
