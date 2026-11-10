import json
from datetime import date, datetime, timezone

from rag.temporal.answer import ContextItem, build_messages, enforce, parse_answer
from rag.temporal.models import LegalTimeline, TimeAnchor, TransitionRule

NOW = datetime(2026, 11, 9, tzinfo=timezone.utc)
ANCHOR = TimeAnchor("signing", date(2023, 6, 15), date(2023, 6, 15), "day", "question", "ký ngày 15/06/2023", None, 0.9)
TL = LegalTimeline((ANCHOR,), ANCHOR, (), NOW)


def item(n, store="versioned", doc="verified", prov="verified"):
    return ContextItem(n, store, "luat:65/2014/QH13" if store == "versioned" else None, "Luật Nhà ở",
                       "luat:65/2014/QH13#d23" if store == "versioned" else None, "Điều 23", f"Nội dung {n}",
                       date(2015, 7, 1) if store == "versioned" else None, None, doc,
                       prov if store == "versioned" else None, (), ("signing",), f"c{n}")


RULE = TransitionRule("luat:27/2023/QH15#d198", "luat:27/2023/QH15", "Điều 198", "Điều 198. Quy định chuyển tiếp ...",
                      "luat:65/2014/QH13", "luat:27/2023/QH15", date(2024, 8, 1), ("signing", "evaluation"))


def reply(issues, assessments=(), answer="Trả lời [1]."):
    return "```json\n" + json.dumps({"answer_markdown": answer, "issues": issues,
                                     "transition_assessments": list(assessments),
                                     "follow_up_questions": ["Ngày bàn giao?"]}, ensure_ascii=False) + "\n```"


def test_build_messages_mentions_anchor_status_and_rule():
    system, user = build_messages("Hỏi?", TL, [item(1), item(2, "legacy", "unversioned")], [RULE])
    assert "JSON" in system and "không tự chọn phiên bản" in system.casefold()
    assert "2023-06-15" in user and "[1]" in user and "unversioned" in user and "Điều 198" in user


def test_parse_json_block():
    a = parse_answer(reply([{"issue": "x", "anchor_role": "signing", "citations": [1], "certainty": "firm"}]))
    assert a.raw_ok and a.certainty == "firm" and a.follow_up_questions == ["Ngày bàn giao?"]


def test_garbage_is_qualified_text():
    a = parse_answer("Theo Điều 23 [1] thì được.")
    assert not a.raw_ok and a.certainty == "qualified" and a.answer_markdown.startswith("Theo Điều 23")


def test_firm_on_legacy_downgraded():
    a = enforce(parse_answer(reply([{"issue": "x", "citations": [1], "certainty": "firm"}])),
                [item(1, "legacy", "unversioned")], [], TL, year_change=False)
    assert a.certainty == "qualified" and "certainty.unverified_source" in a.downgrade_reasons


def test_firm_on_needs_review_downgraded():
    a = enforce(parse_answer(reply([{"issue": "x", "citations": [1], "certainty": "firm"}])),
                [item(1, prov="needs_review")], [], TL, year_change=False)
    assert a.certainty == "qualified"


def test_firm_with_unresolved_transition_downgraded():
    raw = reply([{"issue": "x", "citations": [1], "certainty": "firm"}],
                [{"rule_id": RULE.rule_id, "assessment": "potentially_applicable"}])
    a = enforce(parse_answer(raw), [item(1)], [RULE], TL, year_change=False)
    assert a.certainty == "qualified" and "certainty.transition_unresolved" in a.downgrade_reasons
    missing = enforce(parse_answer(reply([{"issue": "x", "citations": [1], "certainty": "firm"}])), [item(1)], [RULE], TL,
                      year_change=False)
    assert missing.certainty == "qualified"
    assert any(t["rule_id"] == RULE.rule_id and t["assessment"] == "undetermined" for t in missing.transition_assessments)


def test_year_change_downgrades():
    a = enforce(parse_answer(reply([{"issue": "x", "citations": [1], "certainty": "firm"}])), [item(1)], [], TL,
                year_change=True)
    assert a.certainty == "qualified" and "certainty.version_changes_within_anchor" in a.downgrade_reasons


def test_invalid_citation_removed_and_cannot_conclude_when_none_left():
    a = enforce(parse_answer(reply([{"issue": "x", "citations": [9], "certainty": "firm"}], answer="Kết luận [9].")),
                [item(1)], [], TL, year_change=False)
    assert a.certainty == "cannot_conclude" and "[9]" not in a.answer_markdown


def test_firm_kept_when_all_verified_and_no_rules():
    a = enforce(parse_answer(reply([{"issue": "x", "citations": [1], "certainty": "firm"}])), [item(1)], [], TL,
                year_change=False)
    assert a.certainty == "firm" and a.downgrade_reasons == []


def test_numeric_string_citations_are_kept():
    # review M4: "citations": ["1"] là trích dẫn hợp lệ
    a = enforce(parse_answer(reply([{"issue": "x", "citations": ["1"], "certainty": "firm"}])),
                [item(1)], [], TL, year_change=False)
    assert a.issues[0]["citations"] == [1] and a.certainty == "firm"
