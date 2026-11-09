import json
from datetime import date, datetime, timezone

from rag.temporal.timeline import build_timeline, needs_llm, parse_llm_events
from rag.temporal.rules import extract_rule_anchors

ASKED = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)


class FakeLLM:
    def __init__(self, reply: str):
        self.reply = reply
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        return self.reply


def test_no_anchor_defaults_to_today():
    t = build_timeline("Điều khoản phạt vi phạm này có hợp pháp không?", asked_at=ASKED)
    assert (t.primary.role, t.primary.start, t.primary.source) == ("evaluation", date(2026, 11, 9), "default")
    assert "timeline.default_today" in t.warnings and len(t.anchors) == 1


def test_calendar_wins_and_warns_on_conflict():
    t = build_timeline("Theo luật năm 2025 thì điều khoản này có hợp pháp không?", asked_at=ASKED,
                       calendar_date=date(2023, 6, 15))
    assert (t.primary.source, t.primary.start) == ("calendar", date(2023, 6, 15))
    assert any(w.startswith("timeline.calendar_conflict") for w in t.warnings)
    assert any(a.source == "question" and a.start == date(2025, 1, 1) for a in t.anchors)


def test_calendar_inside_question_range_is_not_conflict():
    t = build_timeline("Ký hợp đồng trong năm 2023 thì sao?", asked_at=ASKED, calendar_date=date(2023, 6, 15))
    assert not any(w.startswith("timeline.calendar_conflict") for w in t.warnings)


def test_llm_assigns_roles_without_changing_dates():
    q = "Tôi mua nhà tháng 3/2023, đến cuối năm ngoái mới biết có vấn đề, bây giờ tôi muốn kiện."
    reply = json.dumps({"events": [
        {"role": "signing", "date": {"start": "2023-03", "end": None, "precision": "month"},
         "evidence": "Tôi mua nhà tháng 3/2023", "confidence": 0.95},
        {"role": "discovery", "date": {"start": "2025-12-31", "end": None, "precision": "day"},
         "relative_expression": "cuối năm ngoái", "evidence": "cuối năm ngoái mới biết có vấn đề", "confidence": 0.8},
        {"role": "dispute", "date": None, "relative_expression": "bây giờ", "evidence": "bây giờ tôi muốn kiện",
         "confidence": 0.9},
    ]}, ensure_ascii=False)
    llm = FakeLLM(reply)
    t = build_timeline(q, asked_at=ASKED, llm=llm)
    assert llm.calls == 1
    by_role = {a.role: a for a in t.anchors}
    assert (by_role["signing"].start, by_role["signing"].end) == (date(2023, 3, 1), date(2023, 3, 31))
    assert (by_role["discovery"].start, by_role["discovery"].end) == (date(2025, 10, 1), date(2025, 12, 31))
    assert by_role["dispute"].start == date(2026, 11, 9)


def test_llm_invented_event_rejected():
    q = "Hợp đồng ký ngày 15/06/2023 và năm 2024 có tranh chấp."
    reply = json.dumps({"events": [
        {"role": "performance", "date": {"start": "2024-02-01", "end": None, "precision": "day"},
         "evidence": "thực hiện ngày 01/02/2024", "confidence": 0.9}]}, ensure_ascii=False)
    t = build_timeline(q, asked_at=ASKED, llm=FakeLLM(reply))
    assert date(2024, 2, 1) not in {a.start for a in t.anchors}
    assert "timeline.evidence_not_found" in t.warnings


def test_llm_not_called_for_single_clear_anchor():
    llm = FakeLLM("{}")
    t = build_timeline("Hợp đồng ký ngày 15/06/2023 có hợp pháp không?", asked_at=ASKED, llm=llm)
    assert llm.calls == 0 and t.primary.role == "signing"


def test_llm_garbage_falls_back():
    t = build_timeline("Ký năm 2023, tranh chấp năm 2025 thì luật nào áp dụng?", asked_at=ASKED, llm=FakeLLM("xin lỗi"))
    assert "timeline.llm_failed" in t.warnings
    assert {a.role for a in t.anchors} == {"signing", "dispute"}


def test_needs_llm_rules():
    assert not needs_llm("ký ngày 15/06/2023", extract_rule_anchors("ký ngày 15/06/2023", asked_at=ASKED))
    assert needs_llm("năm 2023 ra sao", extract_rule_anchors("năm 2023 ra sao", asked_at=ASKED))


def test_parse_llm_events_rejects_unknown_role():
    events, _ = parse_llm_events('{"events":[{"role":"hacker","date":{"start":"2024","precision":"year"},'
                                 '"evidence":"năm 2024","confidence":1}]}', "Năm 2024 thế nào?", asked_at=ASKED)
    assert events[0].role == "unspecified" and events[0].start == date(2024, 1, 1)


def test_unresolved_relative_warns():
    reply = json.dumps({"events": [{"role": "discovery", "date": None, "relative_expression": "hôm kia nữa",
                                    "evidence": "hôm kia nữa", "confidence": 0.5}]}, ensure_ascii=False)
    t = build_timeline("Tôi phát hiện từ hôm kia nữa, năm 2023 ký hợp đồng.", asked_at=ASKED, llm=FakeLLM(reply))
    assert any(w.startswith("timeline.relative_unresolved") for w in t.warnings)
