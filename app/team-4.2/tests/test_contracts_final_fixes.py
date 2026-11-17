"""Các lỗi review cuối phần 4 tìm ra — mỗi test tái hiện một lỗi."""

import io
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import docx
import pytest

from rag.contracts import review as rv
from rag.contracts.export import report_docx
from rag.contracts.llm_json import ContractAIError
from rag.contracts.models import Contract
from rag.contracts.parse import split_units
from rag.schema import Chunk

ROOT = Path(__file__).resolve().parents[3]
TEXT = (ROOT / "data" / "team-4.2" / "contracts_demo" / "hop_dong_thue_nha_2023.txt").read_text(encoding="utf-8")
LEGACY = Chunk("blds:418", "blds", "bo_luat_dan_su_2015.txt", 1, 1, "Phần thứ ba > Điều 418. Thỏa thuận phạt vi phạm",
               "Điều 418. Thỏa thuận phạt vi phạm\n1. Phạt vi phạm là sự thỏa thuận giữa các bên.")


def contract(sign=date(2023, 3, 15)):
    units = split_units(TEXT)
    c = Contract("c1", "hd.txt", False, datetime(2026, 11, 11, tzinfo=timezone.utc), TEXT, units, len(units))
    c.sign_date, c.party = sign, "Bên thuê"
    c.facts = {"type": "Hợp đồng thuê nhà ở", "parties": [{"role": "Bên cho thuê"}, {"role": "Bên thuê"}]}
    return c


def uid(c, label):
    return next(u.uid for u in c.units if u.label == label)


class StageLLM:
    def __init__(self, handlers):
        self.handlers, self.calls = handlers, []

    def complete(self, system, user):
        stage = system.split("\n", 1)[0].removeprefix("BƯỚC:").strip()
        p = json.loads(user)
        self.calls.append((stage, p))
        out = self.handlers[stage](p)
        return out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)


def ctx(llm, legacy=None):
    return rv.ReviewContext(llm, None, legacy, date(2026, 11, 11))


def verify_all(p):
    return {"results": [{"id": f["id"], "supporting": [x["eid"] for x in f["candidates"]]} for f in p["findings"]]}


# --- #2 kết luận chưa kiểm chứng không được trình bày như kết luận -------------------------------

def test_unverified_legal_finding_is_labelled_as_suspected_not_illegal():
    c = contract()
    llm = StageLLM({"find": lambda p: {"findings": [
        {"unit": uid(c, "Điều 8"), "quote": "phạt vi phạm bằng 20% giá trị phần nghĩa vụ bị vi phạm", "group": "illegal",
         "severity": "critical", "disadvantaged": "Bên thuê", "explanation": "Mức phạt vượt 8% là trái luật.",
         "legal_question": "mức phạt tối đa", "law_hint": "Luật Thương mại", "suggestion": "Giảm"}]},
        "verify": verify_all})
    f = rv.review(ctx(llm), c)["findings"][0]
    assert f["legal_status"] == "cannot_conclude"
    assert f["group_label"] == "Nghi vấn trái luật — chưa kết luận"
    assert f["explanation_note"] == "Nhận định của AI, chưa có căn cứ trong kho luật"
    text = "\n".join(p.text for p in docx.Document(io.BytesIO(report_docx(c, rv._latest(c, ("review",))))).paragraphs)
    assert "Nghi vấn trái luật — chưa kết luận" in text and "— Trái luật (" not in text


def test_concluded_finding_keeps_plain_group_label():
    c = contract()
    llm = StageLLM({"find": lambda p: {"findings": [
        {"unit": uid(c, "Điều 8"), "quote": "phạt vi phạm bằng 20%", "group": "illegal", "severity": "major",
         "disadvantaged": "Bên thuê", "explanation": "x", "legal_question": "phạt vi phạm", "law_hint": None,
         "suggestion": "y"}]}, "verify": verify_all})
    f = rv.review(ctx(llm, lambda q, k: [LEGACY]), c)["findings"][0]
    assert f["legal_status"] == "conditional" and f["group_label"] == "Trái luật"


def test_answer_without_support_does_not_repeat_the_unverified_conclusion():
    c = contract()
    llm = StageLLM({"answer": lambda p: {"answer": "Bên cho thuê được chấm dứt ngay.", "legal_conclusion": True,
                                         "law_ids": [], "units": [c.units[9].uid]}})
    out = rv.answer(ctx(llm), c, "Bên cho thuê có được chấm dứt không?", [])
    assert out["legal_status"] == "cannot_conclude"
    assert "chấm dứt ngay" not in out["answer"] and out["answer"].startswith("Kho chưa có")
    assert "Điều 9" in out["answer"]                      # vẫn chỉ ra điều khoản liên quan trong hợp đồng


# --- #3 PII không đi vào truy vấn tra luật -------------------------------------------------------

def test_law_search_queries_are_pii_masked():
    c = contract()
    seen = []

    def legacy(q, k):
        seen.append(q)
        return [LEGACY]
    llm = StageLLM({"find": lambda p: {"findings": [
        {"unit": uid(c, "Điều 8"), "quote": "phạt vi phạm bằng 20%", "group": "illegal", "severity": "major",
         "disadvantaged": "Bên thuê", "explanation": "x", "legal_question": "phạt ông 0912 345 678 bao nhiêu",
         "law_hint": None, "suggestion": "y"}]}, "verify": verify_all,
        "answer": lambda p: {"answer": "ok", "legal_conclusion": False, "law_ids": [], "units": []}})
    rv.review(ctx(llm, legacy), c)
    rv.answer(ctx(llm, legacy), c, "CCCD của tôi 001085012345 thì sao?", [])
    assert seen and all("0912 345 678" not in q and "001085012345" not in q for q in seen)


# --- #4 kết quả thiếu / lệch không được thành "không có vấn đề" ----------------------------------

def test_findings_with_labels_instead_of_uids_are_mapped():
    c = contract()
    llm = StageLLM({"find": lambda p: {"findings": [
        {"unit": "Điều 4", "quote": "thanh toán đúng hạn", "group": "ambiguous", "severity": "minor",
         "disadvantaged": "Bên thuê", "explanation": "Không nêu hạn.", "legal_question": None, "law_hint": None,
         "suggestion": "Ghi rõ"}]}, "verify": verify_all})
    assert rv.review(ctx(llm), c)["findings"][0]["unit_label"] == "Điều 4"


def test_findings_that_all_fail_to_map_raise_instead_of_empty_report():
    c = contract()
    llm = StageLLM({"find": lambda p: {"findings": [{"unit": "khoản lạ", "quote": "x", "group": "illegal"}]},
                    "verify": verify_all})
    with pytest.raises(ContractAIError):
        rv.review(ctx(llm), c)


def test_partial_review_with_empty_scope_raises():
    c = contract()
    llm = StageLLM({"select": lambda p: {"units": []}, "find": lambda p: {"findings": []}})
    with pytest.raises(ContractAIError):
        rv.review(ctx(llm), c, topics=["Bảo hiểm"])


def test_redline_with_no_usable_rows_raises():
    c = contract()
    llm = StageLLM({"find": lambda p: {"findings": [
        {"unit": uid(c, "Điều 4"), "quote": "thanh toán đúng hạn", "group": "ambiguous", "severity": "minor",
         "disadvantaged": "Bên thuê", "explanation": "x", "legal_question": None, "law_hint": None, "suggestion": "y"}]},
        "verify": verify_all, "redline": lambda p: {"redlines": [{"finding_id": "khong-co", "old": "a", "new": "b"}]}})
    with pytest.raises(ContractAIError):
        rv.redline(ctx(llm), c)


# --- #5 phạm vi soát ----------------------------------------------------------------------------

def test_partial_coverage_counts_only_scope_and_derived_reports_inherit():
    c = contract()
    llm = StageLLM({"find": lambda p: {"findings": [
        {"unit": uid(c, "Điều 4"), "quote": "thanh toán đúng hạn", "group": "ambiguous", "severity": "minor",
         "disadvantaged": "Bên thuê", "explanation": "x", "legal_question": None, "law_hint": None, "suggestion": "y"}]},
        "verify": verify_all, "redline": lambda p: {"redlines": [
            {"finding_id": f["id"], "old": f["quote"], "new": "z", "reason": "r"} for f in p["findings"]]}})
    rep = rv.review(ctx(llm), c, unit_ids=[uid(c, "Điều 4"), uid(c, "Điều 5")])
    assert rep["coverage"] == {"reviewed": 2, "total": 13}
    assert rv.redline(ctx(llm), c)["coverage"] == {"reviewed": 2, "total": 13}


# --- #6 trạng thái căn cứ ---------------------------------------------------------------------

def test_conflicted_versioned_evidence_is_only_conditional():
    from rag.contracts.evidence import LawEvidence
    conflicted = LawEvidence("L1", "versioned", "Luật Nhà ở", "Điều 132", "t", date(2015, 7, 1), None, "conflicted",
                             "luat:65/2014/QH13", "luat:65/2014/QH13#d132")
    verified = LawEvidence("L2", "versioned", "Luật Nhà ở", "Điều 131", "t", date(2015, 7, 1), None, "needs_review",
                           "luat:65/2014/QH13", "luat:65/2014/QH13#d131")
    assert rv._legal_status([conflicted]) == "conditional"
    assert rv._legal_status([conflicted, verified]) == "concluded"


def test_export_translates_provision_status():
    c = contract()
    rep = {"rid": "r", "op": "review", "created_at": "2026-11-11T00:00:00+00:00", "party": "Bên thuê",
           "anchor": "2023-03-15", "coverage": {"reviewed": 1, "total": 1}, "scope": [], "findings": [
               {"id": "F1", "unit_label": "Điều 9", "quote": "q", "group": "illegal", "group_label": "Trái luật",
                "severity": "major", "disadvantaged": "Bên thuê", "explanation": "e", "suggestion": "s", "legal": True,
                "legal_status": "concluded", "refusal": None, "note": None, "needs_check": False,
                "evidence": [{"eid": "L", "store": "versioned", "source_title": "Luật Nhà ở", "section": "Điều 132",
                              "text": "t", "valid_from": "2015-07-01", "valid_to": None, "status": "needs_review"}]}]}
    text = "\n".join(p.text for p in docx.Document(io.BytesIO(report_docx(c, rep))).paragraphs)
    assert "cần xem lại" in text and "needs_review" not in text


# --- #7 thiếu nội dung bắt buộc không cần trích dẫn ---------------------------------------------

def test_missing_required_finding_is_searched_without_a_quote():
    c = contract()
    llm = StageLLM({"find": lambda p: {"findings": [
        {"unit": uid(c, "Điều 10"), "quote": "", "group": "missing_required", "severity": "major",
         "disadvantaged": "Bên thuê", "explanation": "Thiếu trách nhiệm sửa chữa.",
         "legal_question": "trách nhiệm sửa chữa nhà cho thuê", "law_hint": "Luật Nhà ở", "suggestion": "Bổ sung"}]},
        "verify": verify_all})
    f = rv.review(ctx(llm, lambda q, k: [LEGACY]), c)["findings"][0]
    assert f["needs_check"] is False and f["legal_status"] == "conditional" and f["evidence"]


# --- #1 tải báo cáo khi tên file tiếng Việt ------------------------------------------------------

def test_download_header_is_ascii_with_utf8_filename():
    ui = Path(__file__).resolve().parents[1] / "ui"
    if str(ui) not in sys.path:
        sys.path.insert(0, str(ui))
    import contracts_api

    disp = contracts_api._disposition("Hợp đồng thuê nhà Đà Nẵng", "review", "pdf")
    disp.encode("latin-1")
    assert 'filename="Hop_dong_thue_nha_Da_Nang_review.pdf"' in disp
    assert "filename*=UTF-8''H%E1%BB%A3p" in disp
