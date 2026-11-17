"""Xác minh dữ kiện và trích theo lô (spec 2026-11-13-contract-fact-verification-design.md)."""
import json
from contextlib import contextmanager
from datetime import date, datetime, timezone

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from rag.contracts import verify
from rag.contracts.batches import make_batches, run_batches
from rag.contracts.facts import extract_facts
from rag.contracts.graph.oplog import human_op
from rag.contracts.llm_json import ContractAIError
from rag.contracts.models import Contract
from rag.contracts.structure import parse_contract, to_contract_units
from rag.contracts.doc import PageText
from tests.test_contracts_api import contracts_api

NOW = datetime(2026, 11, 13, tzinfo=timezone.utc)

LABOR = ("HỢP ĐỒNG LAO ĐỘNG\nHôm nay, ngày 01 tháng 3 năm 2025, tại Hà Nội.\n"
         "NGƯỜI SỬ DỤNG LAO ĐỘNG: Công ty TNHH ABC\nNGƯỜI LAO ĐỘNG: Nguyễn Văn B\n"
         "Điều 1. Giải thích từ ngữ\n\"Lương\" là mức lương theo công việc.\n"
         "Điều 2. Công việc\nNgười lao động làm Nhân viên IT tại số 1 Cầu Giấy, Hà Nội.\n"
         "Điều 3. Thời hạn\nHợp đồng xác định thời hạn 36 tháng. Thử việc 90 ngày theo Điều 4.\n"
         "Điều 4. Lương thử việc\nLương thử việc bằng 70% lương chính thức.\n")


def make(text=LABOR, cid="c1"):
    doc = parse_contract([PageText(None, text)])
    c = Contract(cid, "hd.txt", False, NOW, text, to_contract_units(doc), len(doc.top_units()), doc=doc)
    return c


def uid(c, label):
    return next(u.uid for u in c.units if u.label == label)


class ScriptLLM:
    """Trả lời theo hàm của payload; ghi lại mọi payload."""

    def __init__(self, fn):
        self.fn, self.calls = fn, []

    def complete(self, system, user):
        payload = json.loads(user)
        self.calls.append((system, payload))
        out = self.fn(system, payload)
        if isinstance(out, Exception):
            raise out
        return out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)


# --- lô ------------------------------------------------------------------------------------

def test_batches_respect_budget_and_carry_context_and_references():
    c = make()
    batches = make_batches(c, budget=120)
    assert [u.uid for b in batches for u in b.units] == [u.uid for u in c.units]      # đủ, đúng thứ tự
    assert all(sum(len(u.text) for u in b.units) <= 120 or len(b.units) == 1 for b in batches)
    later = [b for b in batches if uid(c, "Điều 3") in b.uids][0]
    assert {x["label"] for x in later.context} >= {"Phần mở đầu", "Điều 1"}           # bên + định nghĩa
    if uid(c, "Điều 4") not in later.uids:                                             # "theo Điều 4" -> tham khảo
        assert [r["uid"] for r in later.references] == [uid(c, "Điều 4")]


def test_very_long_unit_is_split_into_pieces_with_same_uid():
    text = "Điều 1. Dài\n" + ("Nội dung rất dài. " * 3000) + "\nĐiều 2. Ngắn\nX.\n"
    c = make(text)
    batches = make_batches(c)
    pieces = [u for b in batches for u in b.units if u.uid == uid(c, "Điều 1")]
    assert len(pieces) >= 3 and all(len(p.text) <= 24_000 for p in pieces)
    assert "".join(p.text for p in pieces) == c.unit(uid(c, "Điều 1")).text


def test_failed_batch_is_retried_then_reported():
    c = make()
    batches = make_batches(c, budget=120)
    attempts = {}

    def fn(b):
        attempts[b.index] = attempts.get(b.index, 0) + 1
        if b.index == 1:
            raise ContractAIError()
        return {"ok": b.index}

    run = run_batches(batches, fn)
    assert attempts[1] == 2 and [b.index for b in run.failed] == [1]
    assert run.warnings() == [f"Chưa đọc được {batches[1].span_label()} (AI lỗi hai lần)"]
    assert len(run.results) == len(batches) - 1


# --- trích dữ kiện ----------------------------------------------------------------------------

def labor_reply(system, p):
    uids = {u["uid"]: u for u in p["units"]}
    out = {"type": "Hợp đồng lao động", "parties": [], "fields": {}}
    for u in p["units"]:
        if u["label"] == "Phần mở đầu":
            out["parties"] = [{"name": "ABC", "role": "Người sử dụng lao động", "unit": u["uid"],
                               "quote": "NGƯỜI SỬ DỤNG LAO ĐỘNG"},
                              {"name": "B", "role": "Người lao động", "unit": u["uid"], "quote": "NGƯỜI LAO ĐỘNG: Nguyễn"}]
            out["sign_date"] = {"value": "2025-03-01", "unit": u["uid"], "quote": "ngày 01 tháng 3 năm 2025"}
        if u["label"] == "Điều 2":
            out["fields"]["job_title"] = {"value": "Nhân viên IT", "unit": u["uid"], "quote": "Nhân viên IT"}
            out["fields"]["workplace"] = {"value": "số 1 Cầu Giấy, Hà Nội", "unit": "Điều 2",   # nhãn thay vì uid
                                          "quote": "số 1 Cầu Giấy, Hà Nội"}
        if u["label"] == "Điều 3":
            out["fields"]["labor_kind"] = {"value": "xác định thời hạn", "unit": u["uid"],
                                           "quote": "Hợp đồng xác định thời hạn 36 tháng"}
            out["fields"]["probation_period"] = {"value": "90 ngày", "unit": u["uid"], "quote": "Thử việc 90 ngày"}
            out["fields"]["salary"] = {"value": "50 triệu", "unit": u["uid"], "quote": "lương 50 triệu"}   # bịa
        if u["label"] == "Điều 4" and "Điều 3" not in [x["label"] for x in p["units"]]:
            # lô khác thấy giá trị khác -> mâu thuẫn giữa các lô (trong một lô mô hình chỉ trả một giá trị)
            out["fields"]["probation_period"] = {"value": "60 ngày", "unit": u["uid"], "quote": "Lương thử việc"}
    assert uids
    return out


def extract(c, budget=None, llm=None):
    """Trích dữ kiện; `budget` nhỏ -> nhiều lô."""
    import rag.contracts.facts as facts_mod
    orig = facts_mod.make_batches
    if budget:
        facts_mod.make_batches = lambda contract: orig(contract, budget=budget)
    try:
        extract_facts(llm or ScriptLLM(labor_reply), c)
    finally:
        facts_mod.make_batches = orig
    return c


def test_extract_facts_reads_all_batches_and_merges():
    c = make()
    llm = ScriptLLM(labor_reply)
    extract(c, llm=llm)                                        # ngân sách mặc định: một lô
    small = extract(make(cid="c2"), budget=120)
    assert [x["value"] for x in c.facts["candidates"]["probation_period"]] == ["90 ngày"]
    for contract in (c, small):
        cands = contract.facts["candidates"]
        assert cands["job_title"] == [{"value": "Nhân viên IT", "unit": uid(contract, "Điều 2"), "quote": "Nhân viên IT"}]
        assert cands["workplace"][0]["unit"] == uid(contract, "Điều 2")        # nhãn -> sửa thành uid chứa trích dẫn
        assert cands["labor_kind"] == [{"value": "Xác định thời hạn", "unit": uid(contract, "Điều 3"),
                                        "quote": "Hợp đồng xác định thời hạn 36 tháng"}]
        assert "salary" not in cands                                            # trích dẫn bịa -> bỏ
        assert contract.sign_date == date(2025, 3, 1) and contract.facts["coverage"]["read"] == len(contract.units)
    assert len(llm.calls) == 1 and len(make_batches(small, budget=120)) > 1
    assert [x["value"] for x in small.facts["candidates"]["probation_period"]] == ["90 ngày", "60 ngày"]
    payload = llm.calls[0][1]
    assert {f["key"] for f in payload["fields_wanted"]} >= {"job_title", "workplace", "job_level", "rent"}
    job_level = next(f for f in payload["fields_wanted"] if f["key"] == "job_level")
    assert job_level["options"][0] == "Người quản lý doanh nghiệp"


def test_enum_normalization_does_not_confuse_indefinite_term():
    spec = next(s for s in verify.all_specs() if s["key"] == "labor_kind")
    c = make()
    assert verify.normalize_value(spec, "Hợp đồng không xác định thời hạn", c) == "Không xác định thời hạn"
    assert verify.normalize_value(spec, "xác định thời hạn 36 tháng", c) == "Xác định thời hạn"
    assert verify.normalize_value(spec, "thời vụ", c) is None
    date_spec = next(s for s in verify.all_specs() if s["key"] == "sign_date")
    assert verify.normalize_value(date_spec, "01/03/2025", c) is None


# --- bảng xác minh ---------------------------------------------------------------------------

def labor_contract():
    return extract(make(), budget=120)


def row(c, key):
    return next(f for f in verify.fields(c) if f["key"] == key)


def test_fields_follow_contract_type_and_statuses():
    c = labor_contract()
    s = verify.summary(c)
    assert s["catalog_type"] == "labor"
    keys = [f["key"] for f in s["fields"]]
    assert keys[:3] == ["party", "sign_date", "type"] and "job_title" in keys and "rent" not in keys
    assert row(c, "job_title")["status"] == "found" and row(c, "job_title")["quote"] == "Nhân viên IT"
    assert row(c, "probation_period")["status"] == "conflict"
    assert row(c, "job_level")["status"] == "missing"
    assert row(c, "party")["options"] == ["Người sử dụng lao động", "Người lao động", "neutral"]
    assert {p["key"] for p in s["pending"]} == {"party", "sign_date", "type", "labor_kind", "job_title", "workplace"}
    with pytest.raises(verify.NeedsVerification) as e:
        verify.check_gate(c, "review")
    assert "Bạn là bên nào" in str(e.value)
    verify.check_gate(c, "summary")                                         # tóm tắt không bị chặn


def test_apply_answers_records_ops_and_syncs_party_and_date():
    c = labor_contract()
    verify.apply_answers(c, {"party": {"action": "set", "value": "Người lao động"},
                             "sign_date": {"action": "set", "value": "2025-03-02"},
                             "type": {"action": "confirm"}, "labor_kind": {"action": "confirm"},
                             "job_title": {"action": "confirm"}, "workplace": {"action": "set", "value": "Hà Nội"},
                             "job_level": {"action": "unknown"},
                             "probation_period": {"action": "set", "value": "90 ngày"}}, "Lan", NOW)
    assert c.party == "Người lao động" and c.sign_date == date(2025, 3, 2) and c.sign_date_source == "user"
    assert verify.pending_required(c) == []
    statuses = {k: row(c, k)["status"] for k in ("sign_date", "job_title", "workplace", "job_level", "probation_period")}
    assert statuses == {"sign_date": "corrected", "job_title": "confirmed", "workplace": "corrected",
                        "job_level": "unknown", "probation_period": "confirmed"}
    assert row(c, "probation_period")["quote"] == "Thử việc 90 ngày"       # chọn một ứng viên: giữ trích dẫn của nó
    assert row(c, "workplace")["quote"] is None and row(c, "job_title")["by"] == "Lan"
    targets = [o.target for o in c.oplog.active() if o.origin == "human"]
    assert "fact:job_title" in targets and "party" in targets and c.oplog.field("sign_date") == "2025-03-02"
    known = verify.known_facts(c)["facts"]
    assert known["Nhóm trình độ công việc"] == "không biết" and known["Chức danh / công việc"] == "Nhân viên IT"
    # trả lời lại: thay thế, không chồng
    verify.apply_answers(c, {"job_title": {"action": "set", "value": "Trưởng nhóm IT"}}, "Lan", NOW)
    assert row(c, "job_title")["value"] == "Trưởng nhóm IT"
    assert len([o for o in c.oplog.active() if o.target == "fact:job_title"]) == 1


@pytest.mark.parametrize("answers, message", [
    ({"party": {"action": "set", "value": "Bên thứ ba"}}, "không hợp lệ"),
    ({"sign_date": {"action": "set", "value": "01/03/2025"}}, "không hợp lệ"),
    ({"sign_date": {"action": "unknown"}}, "cần một giá trị"),
    ({"probation_period": {"action": "confirm"}}, "chưa có một giá trị"),
    ({"rent": {"action": "set", "value": "x"}}, "không có trong bảng"),
    ({"job_title": {"action": "maybe"}}, "không hợp lệ"),
    ({"q:none": {"action": "set", "value": "x"}}, "Không có câu hỏi"),
    ({}, "Không có câu trả lời"),
])
def test_apply_answers_rejects_bad_input_without_writing(answers, message):
    c = labor_contract()
    before = len(c.oplog.all())
    with pytest.raises(ValueError, match=message):
        verify.apply_answers(c, ({"job_title": {"action": "confirm"}} if answers else {}) | answers, "Lan", NOW)
    assert len(c.oplog.all()) == before


def test_changing_type_switches_catalog_and_keeps_shared_answers():
    c = labor_contract()
    verify.apply_answers(c, {"party": {"action": "set", "value": "neutral"}}, "Lan", NOW)
    verify.apply_answers(c, {"type": {"action": "set", "value": "Hợp đồng thuê nhà ở"}}, "Lan", NOW)
    keys = [f["key"] for f in verify.fields(c)]
    assert "rent" in keys and "job_title" not in keys
    assert row(c, "party")["status"] == "corrected" and row(c, "property")["status"] == "missing"


def test_legacy_contract_builds_table_from_old_facts():
    c = make()
    c.facts = {"type": "Hợp đồng thuê nhà ở", "parties": [{"role": "Bên thuê", "unit": "u1", "quote": "x"}],
               "sign_date": {"value": "2023-03-15", "unit": "u1", "quote": "x"}, "term": None}
    assert row(c, "sign_date")["status"] == "found" and row(c, "type")["value"] == "Hợp đồng thuê nhà ở"
    assert verify.catalog_type(verify.current_type(c)) == "lease"
    c.oplog.add(human_op(c.contract_id, "SET_FIELD", "party", {"value": "Bên thuê"}, "cũ", at=NOW))   # API cũ
    assert row(c, "party")["status"] == "confirmed" or row(c, "party")["status"] == "corrected"


# --- API + câu hỏi trong lúc soát ---------------------------------------------------------------

def find_with_question(system, p):
    stage = system.split("\n", 1)[0].removeprefix("BƯỚC:").strip() if system.startswith("BƯỚC:") else "facts"
    if stage == "facts":
        return labor_reply(system, p)
    if stage == "find":
        u3 = next(u["uid"] for u in p["units"] if u["label"] == "Điều 3")
        known = p["known_facts"]
        if any("trình độ" in q["question"] for q in known["answered_questions"]):
            return {"findings": [], "questions": []}
        return {"findings": [{"unit": u3, "quote": "Thử việc 90 ngày", "group": "unfavorable", "severity": "major",
                              "disadvantaged": "Người lao động", "explanation": "Thử việc dài.", "legal_question": None,
                              "law_hint": None, "suggestion": "Rút ngắn.", "needs_info": True,
                              "cases": [{"if": "Công việc khác", "conclusion": "Vượt 6 ngày làm việc"},
                                        {"if": "Người quản lý doanh nghiệp", "conclusion": "Hợp lệ"}]}],
                "questions": [{"question": "Công việc của bạn cần trình độ nào?",
                               "options": ["Cao đẳng trở lên", "Công việc khác"], "unit": u3,
                               "quote": "Thử việc 90 ngày"},
                              {"question": "Câu hỏi về đơn vị ngoài lô", "options": [], "unit": "p9.d9"}]}
    raise AssertionError(stage)


@pytest.fixture
def client(tmp_path):
    @contextmanager
    def lease():
        yield None

    contracts_api.CONFIG.root = tmp_path / "contracts"
    contracts_api.CONFIG.llm_factory = lambda: ScriptLLM(find_with_question)
    contracts_api.CONFIG.lease = lease
    contracts_api.CONFIG.legacy_search = lambda q, k: []
    contracts_api.CONFIG.ocr_factory = lambda: None
    contracts_api.CONFIG.today = lambda: date(2026, 11, 13)
    contracts_api.CONFIG.document_source = None
    contracts_api.CONFIG.agent_baseline = None
    contracts_api.CONFIG.agent_config = None
    contracts_api.CONFIG.graph = None
    contracts_api.reset()
    return TestClient(Starlette(routes=contracts_api.routes))


def test_api_gate_answers_and_questions(client):
    card = client.post("/api/contracts", files={"file": ("hd.txt", LABOR.encode("utf-8"))}, data={"persist": "0"}).json()
    cid = card["contract_id"]
    assert card["verification"]["complete"] is False and card["verification"]["catalog_type"] == "labor"
    r = client.post(f"/api/contracts/{cid}/run", json={"op": "review"})
    assert r.status_code == 409 and {p["key"] for p in r.json()["pending"]} >= {"party", "job_title"}
    assert client.post(f"/api/contracts/{cid}/run", json={"op": "summary"}).status_code != 409
    bad = client.post(f"/api/contracts/{cid}/facts", json={"answers": {"sign_date": {"action": "set", "value": "x"}}})
    assert bad.status_code == 400
    answers = {"party": {"action": "set", "value": "Người lao động"}, "sign_date": {"action": "confirm"},
               "type": {"action": "confirm"}, "labor_kind": {"action": "confirm"}, "job_title": {"action": "confirm"},
               "workplace": {"action": "confirm"}}
    card = client.post(f"/api/contracts/{cid}/facts", json={"answers": answers, "by": "Lan"}).json()
    assert card["verification"]["complete"] is True and card["party"] == "Người lao động"

    rep = client.post(f"/api/contracts/{cid}/run", json={"op": "review"}).json()
    f = rep["findings"][0]
    assert f["needs_info"] is True and [c["if"] for c in f["cases"]] == ["Công việc khác", "Người quản lý doanh nghiệp"]
    assert f["group_label"] == "Bất lợi? — tùy trường hợp, cần thêm thông tin"
    assert [q["question"] for q in rep["questions"]] == ["Công việc của bạn cần trình độ nào?"]     # câu ngoài lô bị bỏ
    qid = rep["questions"][0]["qid"]
    assert f["questions"] == [qid]
    card = client.get(f"/api/contracts/{cid}").json()
    assert [q["status"] for q in card["verification"]["questions"]] == ["open"]

    card = client.post(f"/api/contracts/{cid}/facts",
                       json={"answers": {f"q:{qid}": {"action": "set", "value": "Công việc khác"}}}).json()
    assert card["verification"]["questions"][0] | {} == card["verification"]["questions"][0]
    assert card["verification"]["questions"][0]["answer"] == "Công việc khác"
    again = client.post(f"/api/contracts/{cid}/run",
                        json={"op": "partial", "unit_ids": [card["verification"]["questions"][0]["unit"]]}).json()
    assert again["findings"] == [] and again["questions"] == []
    llm_payloads = contracts_api.get(cid).facts["questions"]
    assert len(llm_payloads) == 1                                            # không nhân bản câu hỏi
