import importlib.util
import json
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from rag.contracts import review as rv
from rag.contracts.llm_json import ContractAIError
from rag.contracts.models import Contract
from rag.contracts.parse import split_units
from rag.legal.snapshots import SnapshotManager
from rag.schema import Chunk
from rag.temporal.index import VersionedIndex

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).parent / "fixtures" / "legal" / "realestate"
TEXT = (ROOT / "data" / "team-4.2" / "contracts_demo" / "hop_dong_thue_nha_2023.txt").read_text(encoding="utf-8")
TODAY = date(2026, 11, 11)
REFUSAL_NO_LAW = ("Kho chưa có Luật Thương mại — chưa thể kết luận điều khoản này có hợp pháp không. "
                  "Có thể upload luật ở trang Nạp văn bản pháp luật (/upload).")


@pytest.fixture(scope="module")
def runtime(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("seed", ROOT / "scripts" / "team-4.2" / "seed_legal_demo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    legal_dir = tmp_path_factory.mktemp("legal")
    sid = mod.seed(legal_dir, FIXTURES)
    service = SnapshotManager(legal_dir).service(sid)
    index = VersionedIndex(service.store, snapshot_id=sid)
    index.build()
    return SimpleNamespace(snapshot_id=sid, service=service, index=index)


LEGACY = Chunk("blds:418", "blds", "bo_luat_dan_su_2015.txt", 1, 1, "Điều 418. Thỏa thuận phạt vi phạm",
               "Điều 418. Thỏa thuận phạt vi phạm\n1. Phạt vi phạm là sự thỏa thuận giữa các bên trong hợp đồng.")


def contract(sign=date(2023, 3, 15), text=TEXT):
    units = split_units(text)
    c = Contract("c1", "hd.txt", False, datetime(2026, 11, 11, tzinfo=timezone.utc), text, units[:30], len(units))
    c.sign_date, c.sign_date_source, c.party = sign, ("text" if sign else None), "Bên thuê"
    c.facts = {"type": "Hợp đồng thuê nhà ở", "parties": [{"role": "Bên cho thuê"}, {"role": "Bên thuê"}]}
    return c


def unit_of(c, label):
    return next(u.uid for u in c.units if u.label == label)


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


def find_handler(c):
    def handle(payload):
        return {"findings": [
            {"unit": unit_of(c, "Điều 9"), "quote": "Bên A được quyền đơn phương chấm dứt hợp đồng bất cứ lúc nào",
             "group": "illegal", "severity": "critical", "disadvantaged": "Bên thuê",
             "explanation": "Bên cho thuê đơn phương chấm dứt không báo trước.",
             "legal_question": "bên cho thuê đơn phương chấm dứt hợp đồng thuê nhà ở", "law_hint": "Luật Nhà ở",
             "suggestion": "Chỉ cho đơn phương chấm dứt trong trường hợp luật định, báo trước 30 ngày."},
            {"unit": unit_of(c, "Điều 8"), "quote": "phạt vi phạm bằng 20% giá trị phần nghĩa vụ bị vi phạm",
             "group": "illegal", "severity": "major", "disadvantaged": "Cả hai bên",
             "explanation": "Mức phạt có thể vượt giới hạn.", "legal_question": "mức phạt vi phạm tối đa",
             "law_hint": "Luật Thương mại", "suggestion": "Giảm mức phạt."},
            {"unit": unit_of(c, "Điều 4"), "quote": "thanh toán đúng hạn bằng chuyển khoản",
             "group": "ambiguous", "severity": "minor", "disadvantaged": "Bên thuê",
             "explanation": "Không nêu hạn thanh toán cụ thể.", "legal_question": None, "law_hint": None,
             "suggestion": "Ghi rõ ngày thanh toán trong quý."},
            {"unit": unit_of(c, "Điều 6"), "quote": "Bên A được tăng giá 50% mỗi năm",
             "group": "unfavorable", "severity": "major", "disadvantaged": "Bên thuê",
             "explanation": "Trích dẫn bịa.", "legal_question": None, "law_hint": None, "suggestion": "-"},
        ]}
    return handle


def verify_handler(payload):
    out = []
    for f in payload["findings"]:
        ids = [cand["eid"] for cand in f["candidates"]]
        if "chấm dứt" in f["claim"]:
            ids = [cand["eid"] for cand in f["candidates"] if "nhà ở" in cand["source_title"].casefold()]
        elif "phạt" in f["claim"]:
            ids = []
        out.append({"id": f["id"], "supporting": ids})
    return {"results": out}


def ctx(llm, runtime=None, legacy=None):
    return rv.ReviewContext(llm, runtime, legacy, TODAY)


def test_full_review_applies_legal_rules(runtime):
    c = contract()
    llm = StageLLM({"find": find_handler(c), "verify": verify_handler})
    rep = rv.review(ctx(llm, runtime, lambda q, k: [LEGACY]), c)
    by_unit = {f["unit_label"]: f for f in rep["findings"]}
    term = by_unit["Điều 9"]
    assert term["legal_status"] == "concluded"
    assert term["evidence"] and all(e["store"] == "versioned" for e in term["evidence"])
    assert any(e["document_key"] == "luat:65/2014/QH13" for e in term["evidence"])
    assert by_unit["Điều 8"]["legal_status"] == "cannot_conclude" and by_unit["Điều 8"]["refusal"] == REFUSAL_NO_LAW
    assert by_unit["Điều 4"]["legal_status"] == "not_legal"
    assert by_unit["Điều 4"]["note"] == "Nhận xét về câu chữ / thương mại — không phải kết luận pháp lý"
    assert by_unit["Điều 6"]["quote_ok"] is False and by_unit["Điều 6"]["needs_check"] is True
    assert rep["coverage"] == {"reviewed": 13, "total": 13} and rep["anchor"] == "2023-03-15"
    assert [s for s, _ in llm.calls] == ["find", "verify"]


def test_legacy_only_support_is_conditional():
    c = contract()
    llm = StageLLM({"find": find_handler(c), "verify": lambda p: {"results": [
        {"id": f["id"], "supporting": [x["eid"] for x in f["candidates"]]} for f in p["findings"]]}})
    rep = rv.review(ctx(llm, None, lambda q, k: [LEGACY]), c)
    legal = [f for f in rep["findings"] if f["legal"] and f["quote_ok"]]
    assert legal and all(f["legal_status"] == "conditional" for f in legal)
    assert all("Kho cũ — chưa xác định phiên bản" in f["note"] for f in legal)


def test_empty_law_store_refuses_every_legal_conclusion():
    c = contract()
    llm = StageLLM({"find": find_handler(c), "verify": verify_handler})
    rep = rv.review(ctx(llm, None, None), c)
    legal = [f for f in rep["findings"] if f["legal"] and f["quote_ok"]]
    assert legal and all(f["legal_status"] == "cannot_conclude" for f in legal)
    assert all(f["refusal"].endswith("Có thể upload luật ở trang Nạp văn bản pháp luật (/upload).") for f in legal)


def test_missing_sign_date_blocks_legal_but_summary_runs():
    c = contract(sign=None)
    llm = StageLLM({"find": find_handler(c), "verify": verify_handler,
                    "summary": lambda p: {"sections": [{"title": "Các bên", "items": [
                        {"text": "Bên cho thuê và Bên thuê", "unit": c.units[0].uid}]}]}})
    rep = rv.review(ctx(llm, None, lambda q, k: [LEGACY]), c)
    assert all(f["legal_status"] == "blocked_no_date" for f in rep["findings"] if f["legal"])
    assert "verify" not in [s for s, _ in llm.calls]
    summ = rv.summarize(ctx(llm), c)
    assert summ["sections"][0]["items"][0]["unit_label"] == "Phần mở đầu"


def test_party_disadvantage_sorted_first():
    c = contract()
    llm = StageLLM({"find": find_handler(c), "verify": verify_handler})
    rep = rv.review(ctx(llm, None, None), c)
    first = rep["findings"][0]
    assert first["disadvantaged"] == "Bên thuê" and first["severity"] == "critical"


def test_partial_review_by_topic_limits_scope():
    c = contract()
    llm = StageLLM({"select": lambda p: {"units": [unit_of(c, "Điều 8"), unit_of(c, "Điều 9")]},
                    "find": lambda p: {"findings": []}, "verify": verify_handler})
    rep = rv.review(ctx(llm, None, None), c, topics=["phạt vi phạm", "chấm dứt hợp đồng"])
    assert rep["scope"] == ["Điều 8", "Điều 9"]
    find_payload = next(p for s, p in llm.calls if s == "find")
    assert [u["label"] for u in find_payload["units"]] == ["Điều 8", "Điều 9"]


def test_broken_ai_output_raises_not_empty_report():
    c = contract()
    with pytest.raises(ContractAIError):
        rv.review(ctx(StageLLM({"find": lambda p: "xin lỗi tôi không làm được"})), c)


def test_demo_limit_reported_in_coverage():
    text = "\n".join(f"Điều {i}. Nội dung {i}." for i in range(1, 41))
    c = contract(text=text)
    rep = rv.review(ctx(StageLLM({"find": lambda p: {"findings": []}, "verify": verify_handler})), c)
    assert rep["coverage"] == {"reviewed": 30, "total": 40}


def test_law_changes_report_uses_review_evidence(runtime):
    c = contract()
    llm = StageLLM({"find": find_handler(c), "verify": verify_handler})
    rep = rv.law_changes_report(ctx(llm, runtime, None), c)
    repealed = [r for r in rep["changes"] if r["status"] == "repealed"]
    assert repealed and repealed[0]["replaced_by"]["document_key"] == "luat:27/2023/QH15"
    assert "Điều 9" in repealed[0]["affected_units"]


def test_redline_keeps_real_old_text():
    c = contract()
    llm = StageLLM({"find": find_handler(c), "verify": verify_handler, "redline": lambda p: {"redlines": [
        {"finding_id": f["id"], "old": f["quote"], "new": "Nội dung đề xuất", "reason": "Cân bằng quyền lợi"}
        for f in p["findings"]]}})
    rep = rv.redline(ctx(llm, None, None), c)
    assert rep["redlines"] and all(r["old"] in c.text or r["old_ok"] is False for r in rep["redlines"])
    assert any(r["legal_note"] == "Chưa kiểm tra pháp lý" for r in rep["redlines"])


def test_answer_without_versioned_support_adds_refusal():
    c = contract()
    llm = StageLLM({"answer": lambda p: {"answer": "Bên cho thuê được chấm dứt ngay.", "legal_conclusion": True,
                                          "law_ids": [x["eid"] for x in p["laws"]], "units": [c.units[9].uid]},
                    "verify": lambda p: {"results": [{"id": f["id"], "supporting": [x["eid"] for x in f["candidates"]]}
                                                     for f in p["findings"]]}})
    out = rv.answer(ctx(llm, None, lambda q, k: [LEGACY]), c, "Bên cho thuê có được chấm dứt không?", [])
    assert out["legal_status"] == "conditional"
    out2 = rv.answer(ctx(llm, None, None), c, "Bên cho thuê có được chấm dứt không?", [])
    assert out2["legal_status"] == "cannot_conclude" and "chưa thể kết luận" in out2["answer"]
