import json
from datetime import date, datetime, timezone

from rag.bridge.catalog import load_catalog
from rag.bridge.check import check_contract, report_json, report_markdown
from rag.bridge.recheck import RECHECK_PROMPT
from rag.bridge.tagger import TAG_PROMPT
from rag.contracts.facts import FACTS_PROMPT
from rag.contracts.doc import PageText
from rag.contracts.models import Contract
from rag.contracts.structure import parse_contract, to_contract_units

CAT = load_catalog()
AT = datetime(2026, 11, 14, 9, 0)
PAGES = [PageText(1, "Bên A: Công ty TNHH Minh An, là Người sử dụng lao động. Bên B: ông Nguyễn Văn An, là Người lao "
                       "động. Ký ngày 02 tháng 01 năm 2025.\n"
                       "Điều 1. Loại hợp đồng: Không xác định thời hạn. Mức lương chính: 15.000.000 đồng/tháng.\n"
                       "Điều 2. Người lao động được nghỉ phép 08 ngày/năm.")]
DOC = parse_contract(PAGES)
UNITS = to_contract_units(DOC)          # p0.pre, p0.d1, p0.d2


class ScriptLLM:
    """Trả lời theo loại prompt: dữ kiện, gán khái niệm, kiểm lại."""

    def __init__(self):
        self.calls = []

    def complete(self, system, user):
        payload = json.loads(user)
        self.calls.append((system, payload))
        if system.startswith(FACTS_PROMPT[:40]):
            return json.dumps({
                "type": "Hợp đồng lao động",
                "parties": [{"name": "Công ty TNHH Minh An", "role": "Người sử dụng lao động", "unit": "p0.pre",
                             "quote": "là Người sử dụng lao động"},
                            {"name": "Nguyễn Văn An", "role": "Người lao động", "unit": "p0.pre",
                             "quote": "là Người lao động"}],
                "sign_date": {"value": "2025-01-02", "unit": "p0.pre", "quote": "Ký ngày 02 tháng 01 năm 2025"},
                "fields": {"labor_kind": {"value": "Không xác định thời hạn", "unit": "p0.d1",
                                          "quote": "Loại hợp đồng: Không xác định thời hạn"},
                           "salary": {"value": "15.000.000 đồng/tháng", "unit": "p0.d1",
                                      "quote": "Mức lương chính: 15.000.000 đồng/tháng"}}}, ensure_ascii=False)
        if system.startswith(TAG_PROMPT[:40]):
            uids = [u["uid"] for u in payload["units"]]
            items = [{"concept": "leave.annual", "uid": "p0.d2", "quote": "được nghỉ phép 08 ngày/năm",
                      "slots": {"annual_leave": "08 ngày"}}] if "p0.d2" in uids else []
            return json.dumps({"items": items}, ensure_ascii=False)
        assert system.startswith(RECHECK_PROMPT[:40])
        return json.dumps({"items": []})


def contract():
    return Contract("c1", "hd.txt", False, datetime(2026, 11, 14, tzinfo=timezone.utc),
                    "\n".join(u.text for u in UNITS), list(UNITS), len(UNITS), doc=DOC, page_texts=list(PAGES),
                    file_checksum="x")


def test_check_contract_end_to_end():
    llm, c = ScriptLLM(), contract()
    r = check_contract(llm, c, at=AT, model="m")
    by = {(x.concept_id, x.rule_id): x for x in r.results}
    assert by[("leave.annual", "r1")].finding == "needs_facts"          # chưa biết loại công việc
    assert by[("content.raise_policy", "r1")].finding == "missing_content"
    assert by[("wage.minimum_regional", "r1")].finding == "needs_facts"  # chưa biết vùng
    kinds = [o.content.get("kind") for o in c.oplog.all() if o.op_type == "ASSERT"]
    assert kinds.count("party") == 2 and "concept" in kinds and "concept_absent" in kinds
    absent = {o.content["concept_id"] for o in c.oplog.all() if o.content.get("kind") == "concept_absent"}
    assert "content.raise_policy" in absent and "leave.annual" not in absent
    assert r.day == date(2025, 1, 2)
    assert r.stats["graph_backend"] == "memory" and r.stats["build_id"].startswith("b")
    assert [e["uid"] for e in by[("leave.annual", "r1")].evidence] == ["p0.d2"]      # chứng cứ đọc qua đồ thị
    assert by[("leave.annual", "r1")].facts_used["annual_leave"]["value"] == 8
    assert r.stats["llm_calls"] == len(llm.calls) and r.stats["recheck_concepts"] == len(absent)
    sent = json.dumps([p for _, p in llm.calls], ensure_ascii=False)
    assert "pregnant" not in sent and "min_annual_leave" not in sent
    assert set(r.basis) == {x.concept_id for x in r.results if x.finding != "ok"}
    assert all(b["problems"] == ["basis_unavailable"] for b in r.basis.values())


def test_tag_llm_used_only_for_tagging():
    base, tagger = ScriptLLM(), ScriptLLM()
    r = check_contract(base, contract(), at=AT, tag_llm=tagger, tag_model="t1")
    assert tagger.calls and all(s.startswith(TAG_PROMPT[:40]) for s, _ in tagger.calls)
    assert not any(s.startswith(TAG_PROMPT[:40]) for s, _ in base.calls)
    assert r.stats["llm_calls"] == len(base.calls) + len(tagger.calls)
    assert r.stats["tag_model"] == "t1"


def test_reports():
    r = check_contract(ScriptLLM(), contract(), at=AT)
    js = report_json(r)
    json.dumps(js, ensure_ascii=False)
    assert js["contract_id"] == "c1" and js["day"] == "2025-01-02" and js["results"]
    md = report_markdown(r, CAT)
    assert "## Thiếu nội dung bắt buộc" in md and "Chế độ nâng bậc, nâng lương" in md
    assert "## Cần thêm dữ kiện" in md and "được nghỉ phép 08 ngày/năm" in md
    assert md.index("## Thiếu nội dung bắt buộc") < md.index("## Cần thêm dữ kiện")


def test_user_facts_answer_missing_facts():
    r = check_contract(ScriptLLM(), contract(), at=AT, user_facts={"wage_region": "I", "job_level": "cao_dang_tro_len"})
    by = {(x.concept_id, x.rule_id): x for x in r.results}
    assert by[("wage.minimum_regional", "r1")].finding == "ok"           # 15 triệu >= vùng I
    assert by[("wage.minimum_regional", "r1")].facts_used["wage_region"]["value"] == "I"


def test_unknown_user_fact_rejected():
    import pytest
    with pytest.raises(ValueError, match="khong_co"):
        check_contract(ScriptLLM(), contract(), at=AT, user_facts={"khong_co": 1})


def test_markdown_hidden_right_has_no_missing_facts_line_and_shows_amendment():
    from rag.bridge.engine import Fact
    import rag.bridge.check as chk
    r = check_contract(ScriptLLM(), contract(), at=AT)
    md = report_markdown(r, CAT)
    hidden = md.split(f"## {CAT.verdict_label('hidden_right')}")[1].split("\n## ")[0]
    assert "Thiếu dữ kiện" not in hidden
    x = next(x for x in r.results if x.concept_id == "wage.minimum_regional")
    x.facts_used["base_salary_vnd"] = {"value": 17000000, "unit": "vnd",
                                       "amended_from": [{"value": 15000000, "unit": "vnd", "uid": "p0.d2"}]}
    assert "sửa đổi từ 15000000 vnd [p0.d2]" in chk.report_markdown(r, CAT)
    assert Fact(1).amended_from == ()


def test_no_sign_date_uses_catalog_start_with_warning():
    c = contract()
    c.facts = {"type": "Hợp đồng lao động", "parties": [], "candidates": {}}
    llm = ScriptLLM()
    r = check_contract(llm, c, at=AT)
    assert r.day == CAT.law_values_valid_from
    assert any("ngày ký" in w for w in r.warnings)
    assert not any(s.startswith(FACTS_PROMPT[:40]) for s, _ in llm.calls)


def test_markdown_shows_later_amendment():
    import rag.bridge.check as chk
    r = check_contract(ScriptLLM(), contract(), at=AT)
    x = next(x for x in r.results if x.concept_id == "wage.minimum_regional")
    x.facts_used["base_salary_vnd"] = {"value": 15000000, "unit": "vnd", "later_amendments": [
        {"value": 17000000, "unit": "vnd", "uid": "p2.d1", "valid_from": "2025-07-01"}]}
    assert "base_salary_vnd từ 2025-07-01: 17000000 vnd [p2.d1]" in chk.report_markdown(r, CAT)


def test_check_with_graph_service_and_busy_lock_falls_back_to_memory():
    from rag.contracts.graph.service import ContractGraphService
    svc = ContractGraphService(None)
    r = check_contract(ScriptLLM(), contract(), at=AT, graph=svc)
    assert r.stats["graph_backend"] == "memory"
    c = contract()
    with svc.writing("c1"):
        r2 = check_contract(ScriptLLM(), c, at=AT, graph=svc)
    assert r2.stats["graph_backend"] == "memory" and any("đang được thay đổi" in w for w in r2.warnings)
    assert {(x.concept_id, x.rule_id, x.finding) for x in r.results} == {(x.concept_id, x.rule_id, x.finding) for x in r2.results}


def test_contract_without_pages_warns():
    c = contract()
    c.page_texts = []
    r = check_contract(ScriptLLM(), c, at=AT)
    assert any("không có văn bản theo trang" in w for w in r.warnings)
    leave = next(x for x in r.results if x.concept_id == "leave.annual")
    assert [e["uid"] for e in leave.evidence] == [None]           # đồ thị không có Unit: chứng cứ không gắn điều khoản


def test_check_contract_emits_events():
    events = []
    r = check_contract(ScriptLLM(), contract(), at=AT, on_event=events.append)
    stages = [(e["stage"], e["status"]) for e in events if e["type"] == "stage"]
    expected = [("facts", "start"), ("facts", "done"), ("tag", "start"), ("tag", "done"),
                ("evaluate", "start"), ("evaluate", "done")]
    if r.stats["recheck_concepts"]:
        expected += [("recheck", "start"), ("recheck", "done")]
    expected += [("basis", "start"), ("basis", "done")]
    assert stages == expected
    progress = [e for e in events if e["type"] == "progress"]
    assert progress and progress[-1]["stage"] == "tag" and progress[-1]["done"] == progress[-1]["total"] >= 1
    partial = [e for e in events if e["type"] == "partial"]
    assert len(partial) == 1 and partial[0]["results"]
    assert {"concept_id", "finding"} <= set(partial[0]["results"][0])
    plain = report_json(check_contract(ScriptLLM(), contract(), at=AT))
    streamed = report_json(r)
    for js in (plain, streamed):
        js["stats"].pop("seconds")
    assert streamed == plain


def test_report_has_questions_for_unknown_results():
    r = check_contract(ScriptLLM(), contract(), at=AT)
    unknown_facts = {f for x in r.results if x.status == "UNKNOWN" for f in x.missing_facts}
    assert r.questions and {q["fact"] for q in r.questions} <= unknown_facts & set(CAT.context.questions)
    top = next(q for q in r.questions if q["fact"] == "wage_region")
    assert top["question"] == CAT.context.questions["wage_region"].question and top["guaranteed"] >= 1
    assert [o["value"] for o in top["options"]] == ["I", "II", "III", "IV"]
    assert top["options"][0]["label"] == "Vùng I" and top["options"][0]["resolves"] >= 1
    assert report_json(r)["questions"] == r.questions
    json.dumps(report_json(r), ensure_ascii=False)


def test_rules_only_makes_no_llm_calls_and_applies_answers():
    c = contract()
    first = check_contract(ScriptLLM(), c, at=AT)
    unknown_before = sum(x.status == "UNKNOWN" for x in first.results)
    llm = ScriptLLM()
    again = check_contract(llm, c, at=AT, rules_only=True, user_facts={"wage_region": "I", "job_level": "cao_dang_tro_len"})
    assert llm.calls == [] and again.stats["llm_calls"] == 0
    by = {(x.concept_id, x.rule_id): x for x in again.results}
    assert by[("wage.minimum_regional", "r1")].finding == "ok"
    assert by[("content.raise_policy", "r1")].finding == "missing_content"       # khái niệm vắng mặt vẫn được giữ
    assert sum(x.status == "UNKNOWN" for x in again.results) < unknown_before
    assert again.day == first.day and "wage_region" not in {q["fact"] for q in again.questions}


def test_questions_same_for_both_evaluators():
    ref = check_contract(ScriptLLM(), contract(), at=AT, evaluator="reference")
    net = check_contract(ScriptLLM(), contract(), at=AT, evaluator="network")
    assert ref.questions == net.questions and ref.questions
