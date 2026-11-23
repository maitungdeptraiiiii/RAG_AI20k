import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from rag.contracts.facts import extract_facts
from rag.contracts.llm_json import ContractAIError, ask_json, quote_ok
from rag.contracts.models import Contract, new_mask_state
from rag.contracts.parse import split_units

DEMO = Path(__file__).resolve().parents[3] / "data" / "team-4.2" / "contracts_demo" / "hop_dong_thue_nha_2023.txt"
TEXT = DEMO.read_text(encoding="utf-8")


class FakeLLM:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def complete(self, system, user):
        self.calls.append((system, user))
        if callable(self.reply):
            return json.dumps(self.reply(json.loads(user)), ensure_ascii=False)
        return self.reply


def contract():
    return Contract("c1", "hd.txt", False, datetime(2026, 11, 11, tzinfo=timezone.utc), TEXT, split_units(TEXT), 13)


def test_quote_ok_ignores_whitespace_but_rejects_invented_text():
    assert quote_ok(TEXT, "Bên A được quyền   đơn phương chấm dứt hợp đồng\nbất cứ lúc nào")
    assert not quote_ok(TEXT, "Bên A được quyền tăng giá 50%")
    assert not quote_ok(TEXT, "")


def test_quote_segments_must_be_literal_and_in_source_order():
    source = "First literal clause. An omitted clause. Last literal clause."
    quote = "First literal clause.\nLast literal clause."
    assert quote_ok(source, quote)
    assert not quote_ok(source, quote, multi=False)
    assert not quote_ok(source, "Last literal clause.\nFirst literal clause.")
    assert not quote_ok(source, "First invented clause.\nLast literal clause.")


def test_quote_can_omit_form_fillers_but_cannot_change_values():
    source = "Salary: ........ 5.000.000 VND; duration: ____ 12 months."
    assert quote_ok(source, "Salary: 5.000.000 VND; duration: 12 months.")
    assert not quote_ok(source, "Salary: 6.000.000 VND; duration: 12 months.")


def test_ask_json_masks_pii_going_out_and_unmasks_coming_back():
    state = new_mask_state()
    llm = FakeLLM(lambda p: {"echo": p["text"]})
    out = ask_json(llm, "sys", {"text": "Điện thoại: 0912 345 678, CCCD 001085012345"}, state)
    sent = llm.calls[0][1]
    assert "0912 345 678" not in sent and "001085012345" not in sent and "[HD_" in sent
    assert "0912 345 678" in out["echo"] and "001085012345" in out["echo"]


def test_ask_json_accepts_fenced_json_and_rejects_garbage():
    state = new_mask_state()
    assert ask_json(FakeLLM('```json\n{"a": 1}\n```'), "s", {}, state) == {"a": 1}
    with pytest.raises(ContractAIError):
        ask_json(FakeLLM("không phải JSON"), "s", {}, state)
    with pytest.raises(ContractAIError):
        ask_json(FakeLLM("[1, 2]"), "s", {}, state)


def facts_reply(_payload):
    return {
        "type": "Hợp đồng thuê nhà ở",
        "parties": [
            {"name": "Trần Văn Minh", "role": "Bên cho thuê", "unit": "u1", "quote": "BÊN CHO THUÊ (Bên A)"},
            {"name": "Lê Thị Hoa", "role": "Bên thuê", "unit": "u1", "quote": "BÊN THUÊ (Bên B)"},
        ],
        "sign_date": {"value": "2023-03-15", "unit": "u1", "quote": "Hôm nay, ngày 15 tháng 3 năm 2023"},
        "effective_date": {"value": "2023-03-15", "unit": "u13", "quote": "Hợp đồng có hiệu lực kể từ ngày ký"},
        "value": {"value": "12.000.000 đồng/tháng", "unit": "u5", "quote": "Giá thuê là 12.000.000 đồng/tháng"},
        "term": {"value": "24 tháng", "unit": "u4", "quote": "Thời hạn thuê là 24 tháng"},
        "other_dates": [{"label": "Bắt đầu thuê", "value": "2023-04-01", "unit": "u4",
                         "quote": "kể từ ngày 01 tháng 4 năm 2023"}],
    }


def test_extract_facts_sets_sign_date_from_text():
    c = contract()
    facts = extract_facts(FakeLLM(facts_reply), c)
    assert [p["role"] for p in facts["parties"]] == ["Bên cho thuê", "Bên thuê"]
    assert c.sign_date == date(2023, 3, 15) and c.sign_date_source == "text"
    assert facts["value"]["value"] == "12.000.000 đồng/tháng"


def test_invented_quotes_drop_the_value():
    def reply(p):
        data = facts_reply(p)
        data["sign_date"]["quote"] = "ký ngày 20/12/2022"
        data["parties"][1]["quote"] = "Bên thuê là công ty ABC"
        return data
    c = contract()
    facts = extract_facts(FakeLLM(reply), c)
    assert facts["sign_date"] is None and c.sign_date is None
    assert [p["role"] for p in facts["parties"]] == ["Bên cho thuê"]


def test_contract_pii_never_reaches_the_llm():
    llm = FakeLLM(facts_reply)
    extract_facts(llm, contract())
    sent = llm.calls[0][1]
    for raw in ("001085012345", "0912 345 678", "0451000123456", "lethihoa.demo@example.com"):
        assert raw not in sent


def test_fact_batches_share_known_parties_in_document_order(monkeypatch):
    import threading
    import rag.contracts.facts as module
    from rag.contracts.batches import Batch
    from rag.contracts.models import ContractUnit

    units = [ContractUnit("u1", "Điều 1", 'Alpha Holdings ("Alpha") signs the contract.'),
             ContractUnit("u2", "Điều 2", "Alpha and Beta Services agree to perform.")]
    c = Contract("c1", "hd.txt", False, datetime.now(timezone.utc),
                 "\n".join(u.text for u in units), units, len(units))
    monkeypatch.setenv("CONTRACT_BATCH_WORKERS", "4")
    monkeypatch.setattr(module, "make_batches", lambda c: [Batch(i, (u,)) for i, u in enumerate(units)])
    caller = threading.get_ident()

    def reply(payload):
        assert threading.get_ident() == caller
        uid = payload["units"][0]["uid"]
        if uid == "u1":
            assert payload["known_parties"] == []
            return {"parties": [{"name": "Alpha Holdings", "role": "Provider", "unit": uid,
                                  "quote": units[0].text}]}
        assert payload["known_parties"] == [{"name": "Alpha Holdings", "role": "Provider"}]
        return {"parties": [{"name": "Alpha", "role": "Provider", "unit": uid, "quote": units[1].text},
                            {"name": "Beta Services", "role": "Client", "unit": uid, "quote": units[1].text}]}

    facts = extract_facts(FakeLLM(reply), c)
    assert [p["name"] for p in facts["parties"]] == ["Alpha Holdings", "Beta Services"]
    assert facts["coverage"] == {"read": 2, "total": 2}


def test_fact_candidates_reject_quotes_from_another_batch(monkeypatch):
    import rag.contracts.facts as module
    from rag.contracts.batches import Batch
    from rag.contracts.models import ContractUnit

    units = [ContractUnit("u1", "Điều 1", "Signed on 2025-01-02."),
             ContractUnit("u2", "Điều 2", "Signed on 2025-01-03.")]
    c = Contract("c1", "hd.txt", False, datetime.now(timezone.utc),
                 "\n".join(u.text for u in units), units, len(units))
    monkeypatch.setattr(module, "make_batches", lambda c: [Batch(i, (u,)) for i, u in enumerate(units)])

    def reply(payload):
        if payload["units"][0]["uid"] == "u2":
            return {}
        return {"sign_date": [{"value": "2025-01-02", "unit": "u1", "quote": units[0].text},
                              {"value": "2025-01-03", "unit": "u2", "quote": units[1].text}]}

    facts = extract_facts(FakeLLM(reply), c)
    assert [x["value"] for x in facts["candidates"]["sign_date"]] == ["2025-01-02"]
    assert c.sign_date == date(2025, 1, 2)


def test_multiple_signing_dates_require_verification():
    from rag.contracts import verify
    from rag.contracts.models import ContractUnit

    unit = ContractUnit("u1", "Phần mở đầu", "Signed on 2025-01-02; countersigned on 2025-01-03.")
    c = Contract("c1", "hd.txt", False, datetime.now(timezone.utc), unit.text, [unit], 1)
    facts = extract_facts(FakeLLM(lambda p: {"sign_date": [
        {"value": "2025-01-02", "unit": "u1", "quote": "Signed on 2025-01-02"},
        {"value": "2025-01-03", "unit": "u1", "quote": "countersigned on 2025-01-03"}]}), c)
    assert len(facts["candidates"]["sign_date"]) == 2
    assert c.sign_date is None
    signing = next(f for f in verify.summary(c)["fields"] if f["key"] == "sign_date")
    assert signing["status"] == "conflict"


def test_typed_value_survives_into_candidates_and_prompt_asks_for_it():
    """Spec 2026-11-23: ứng viên giữ `norm` (dạng có kiểu) để bộ đọc dữ kiện dùng; prompt xin `norm` cho giá trị số."""
    def reply(p):
        data = facts_reply(p)
        data["term"]["norm"] = {"parts": [{"n": 24, "unit": "month"}]}
        return data
    llm = FakeLLM(reply)
    facts = extract_facts(llm, contract())
    assert facts["candidates"]["term"][0]["norm"] == {"parts": [{"n": 24, "unit": "month"}]}
    assert '"norm"' in llm.calls[0][0] and '"parts"' in llm.calls[0][0]
