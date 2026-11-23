import json
from datetime import datetime, timezone

import pytest

from rag.bridge.catalog import load_catalog
from rag.bridge.tagger import TAG_PROMPT, TAG_PROMPT_VERSION, catalog_payload, tag_contract
from rag.contracts.llm_json import ContractAIError
from rag.contracts.models import Contract, ContractUnit

CAT = load_catalog()
AT = datetime(2026, 11, 14, 9, 0)
U1 = ContractUnit("u1", "Điều 1", "Điều 1. Bên B là ông Nguyễn Văn An, CCCD 001085012345, điện thoại 0912 345 678.")
U2 = ContractUnit("u2", "Điều 2", "Điều 2. Người lao động được nghỉ phép 08 ngày/năm và nghỉ lễ theo quy định.")


class FakeLLM:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def complete(self, system, user):
        self.calls.append((system, user))
        r = self.replies.pop(0) if self.replies else {"items": []}
        if isinstance(r, Exception):
            raise r
        return json.dumps(r(json.loads(user)) if callable(r) else r, ensure_ascii=False)


def contract(units=(U1, U2)):
    return Contract("c1", "hd.txt", False, datetime(2026, 11, 14, tzinfo=timezone.utc),
                    "\n".join(u.text for u in units), list(units), len(units))


def item(**kw):
    base = {"concept": "leave.annual", "uid": "u2", "quote": "được nghỉ phép 08 ngày/năm",
            "slots": {"annual_leave": "08 ngày"}}
    return {**base, **kw}


def test_catalog_payload_has_only_recognition_fields():
    p = catalog_payload(CAT)
    assert len(p) == 40
    assert set(p[0]) <= {"id", "label", "describe", "phrasing", "slots", "not_about"}
    leave = next(x for x in p if x["id"] == "leave.annual")
    assert leave["slots"] == {"annual_leave": {"kind": "duration", "unit": "day"}}
    text = json.dumps(p, ensure_ascii=False)
    assert "min_" not in text and "anchors" not in text and "rules" not in text and "bo-luat" not in text


def test_payload_carries_not_about_and_prompt_explains_it():
    # Lần chạy thật 14/11: câu "không tiếp tục hợp tác ... hoàn trả 100% phí đào tạo" bị gán NLĐ đơn phương chấm dứt.
    p = {x["id"]: x for x in catalog_payload(CAT)}
    na = p["termination.employee_unilateral"]["not_about"]
    assert any("training.cost_repayment" in s for s in na)
    assert "not_about" not in p["leave.annual"]
    assert "not_about" in TAG_PROMPT and TAG_PROMPT_VERSION == "concept-tag-3"


def test_valid_item_becomes_assert():
    run = tag_contract(FakeLLM([{"items": [item()]}]), contract(), CAT, at=AT, model="m1")
    assert len(run.ops) == 1 and run.rejected == []
    op = run.ops[0]
    assert (op.op_type, op.target, op.origin, op.status) == ("ASSERT", "leave.annual", "llm", "auto_accepted")
    assert op.content["kind"] == "concept" and op.content["found_by"] == "tagger"
    assert op.content["slots"]["annual_leave"] == {"value": 8, "unit": "day"}
    assert op.content["slots_raw"] == {"annual_leave": "08 ngày"}
    assert op.quote == ("được nghỉ phép 08 ngày/năm",) and op.source_uid == "u2"
    assert (op.model, op.prompt_version) == ("m1", TAG_PROMPT_VERSION)


@pytest.mark.parametrize("bad,reason", [
    (item(concept="leave.unknown"), "unknown_concept"),
    (item(uid="u9", quote="câu không có trong văn bản"), "unknown_uid"),
    (item(quote="được nghỉ phép 20 ngày/năm"), "quote_not_found"),
    (item(slots={"annual_leave": "10 ngày"}), "slot_not_in_quote"),
])
def test_bad_items_rejected(bad, reason):
    run = tag_contract(FakeLLM([{"items": [bad]}]), contract(), CAT, at=AT)
    assert run.ops == [] and [r["reason"] for r in run.rejected] == [reason]


def test_unknown_slot_dropped_concept_kept():
    # Lần chạy thật 14/11: LLM trả slot "probation.duration" cho khái niệm không có slot đó -> mất cả khái niệm.
    it = item(slots={"annual_leave": "08 ngày", "leave.annual": "08 ngày/năm"})
    run = tag_contract(FakeLLM([{"items": [it]}]), contract(), CAT, at=AT)
    assert len(run.ops) == 1 and run.ops[0].status == "auto_accepted"
    op = run.ops[0]
    assert op.content["slots"] == {"annual_leave": {"value": 8, "unit": "day"}}
    assert op.content["slots_raw"] == {"annual_leave": "08 ngày"}
    assert op.content["dropped_slots"] == {"leave.annual": "08 ngày/năm"}
    assert run.rejected == [{"item": it, "reason": "unknown_slot_dropped", "slots": ["leave.annual"]}]


def test_only_unknown_slots_gives_concept_without_slots():
    run = tag_contract(FakeLLM([{"items": [item(slots={"weekly_rest": "08 ngày"})]}]), contract(), CAT, at=AT)
    assert len(run.ops) == 1 and run.ops[0].content["slots"] == {}


def test_wrong_uid_fixed_to_batch_unit_holding_quote():
    run = tag_contract(FakeLLM([{"items": [item(uid="u1")]}]), contract(), CAT, at=AT)
    assert run.ops[0].source_uid == "u2"


def test_unparsable_slot_is_pending():
    it = item(quote="được nghỉ phép 08 ngày/năm", slots={"annual_leave": "08 ngày/năm"})
    run = tag_contract(FakeLLM([{"items": [it]}]), contract(), CAT, at=AT)
    assert run.ops[0].status == "auto_accepted"
    words = ContractUnit("u2", "Điều 2", "Điều 2. Người lao động được nghỉ phép tám ngày mỗi năm.")
    it = item(quote="được nghỉ phép tám ngày mỗi năm", slots={"annual_leave": "tám ngày"})
    run = tag_contract(FakeLLM([{"items": [it]}]), contract((U1, words)), CAT, at=AT)
    assert run.ops[0].status == "pending" and run.ops[0].status_reasons == ("slot_unparsable:annual_leave",)
    assert "annual_leave" not in run.ops[0].content["slots"]


def test_typed_slot_reads_written_words_and_rejects_invented_numbers():
    """Slot dạng có kiểu (spec 2026-11-23): 'tám ngày' đọc được qua norm; số không có trong câu trích -> chờ duyệt."""
    words = ContractUnit("u2", "Điều 2", "Điều 2. Người lao động được nghỉ phép tám ngày mỗi năm.")
    ok = item(quote="được nghỉ phép tám ngày mỗi năm",
              slots={"annual_leave": {"text": "tám ngày", "norm": {"parts": [{"n": 8, "unit": "day"}]}}})
    run = tag_contract(FakeLLM([{"items": [ok]}]), contract((U1, words)), CAT, at=AT)
    assert run.ops[0].status == "auto_accepted"
    assert run.ops[0].content["slots"]["annual_leave"] == {"value": 8, "unit": "day"}
    bad = item(quote="được nghỉ phép tám ngày mỗi năm",
               slots={"annual_leave": {"text": "tám ngày", "norm": {"parts": [{"n": 12, "unit": "day"}]}}})
    run = tag_contract(FakeLLM([{"items": [bad]}]), contract((U1, words)), CAT, at=AT)
    assert run.ops[0].status == "pending" and "annual_leave" not in run.ops[0].content["slots"]
    missing = item(quote="được nghỉ phép tám ngày mỗi năm",
                   slots={"annual_leave": {"text": "mười hai ngày", "norm": {"parts": [{"n": 12, "unit": "day"}]}}})
    run = tag_contract(FakeLLM([{"items": [missing]}]), contract((U1, words)), CAT, at=AT)
    assert run.ops == [] and run.rejected[0]["reason"] == "slot_not_in_quote"


def test_bool_and_enum_slots_need_not_be_in_quote():
    u = ContractUnit("u2", "Điều 2", "Điều 2. Người lao động phải nộp bản chính bằng đại học cho Công ty giữ.")
    it = {"concept": "prohibit.keep_documents", "uid": "u2", "quote": "phải nộp bản chính bằng đại học",
          "slots": {"employer_keeps_original_documents": True}}
    run = tag_contract(FakeLLM([{"items": [it]}]), contract((U1, u)), CAT, at=AT)
    assert run.ops[0].content["slots"]["employer_keeps_original_documents"] == {"value": True, "unit": None}


def test_failed_batch_warns_and_others_continue(monkeypatch):
    import rag.bridge.tagger as t
    monkeypatch.setattr(t, "BATCH_BUDGET", 60)       # mỗi đơn vị một lô
    llm = FakeLLM([ContractAIError(), ContractAIError(), {"items": [item()]}])
    run = tag_contract(llm, contract(), CAT, at=AT)
    assert len(run.warnings) == 1 and len(run.ops) == 1


def test_payload_masks_ids_and_sends_no_law():
    llm = FakeLLM([{"items": []}])
    tag_contract(llm, contract(), CAT, at=AT)
    system, user = llm.calls[0]
    assert "001085012345" not in user and "0912 345 678" not in user
    assert "min_annual_leave" not in user and "bo-luat" not in user and "anchors" not in user


@pytest.mark.xfail(strict=True, reason="che tên người chưa làm: theo spec 2026-11-14-pii-model-masking-design")
def test_payload_masks_person_names():
    llm = FakeLLM([{"items": []}])
    tag_contract(llm, contract(), CAT, at=AT)
    assert "Nguyễn Văn An" not in llm.calls[0][1]


def test_deterministic_op_ids():
    a = tag_contract(FakeLLM([{"items": [item()]}]), contract(), CAT, at=AT)
    b = tag_contract(FakeLLM([{"items": [item(), item()]}]), contract(), CAT, at=AT)
    assert [o.op_id for o in a.ops] == [o.op_id for o in b.ops]
