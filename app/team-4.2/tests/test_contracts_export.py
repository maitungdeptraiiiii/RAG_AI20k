import io
from datetime import date, datetime, timezone

import docx
import fitz

from rag.contracts.export import report_docx, report_pdf
from rag.contracts.models import Contract
from rag.contracts.parse import split_units

REFUSAL = ("Kho chưa có Luật Thương mại — chưa thể kết luận điều khoản này có hợp pháp không. "
           "Có thể upload luật ở trang Nạp văn bản pháp luật (/upload).")


def contract():
    text = "Điều 8. Phạt vi phạm\nPhạt 20%.\nĐiều 9. Đơn phương chấm dứt\nBên A được chấm dứt bất cứ lúc nào."
    c = Contract("c1", "hop_dong.docx", False, datetime(2026, 11, 11, tzinfo=timezone.utc), text, split_units(text), 2)
    c.party, c.sign_date = "Bên thuê", date(2023, 3, 15)
    return c


REVIEW = {"rid": "r1", "op": "review", "created_at": "2026-11-11T08:00:00+00:00", "party": "Bên thuê",
          "anchor": "2023-03-15", "coverage": {"reviewed": 2, "total": 2}, "scope": ["Điều 8", "Điều 9"],
          "findings": [
              {"id": "F1", "unit_label": "Điều 9", "quote": "Bên A được chấm dứt bất cứ lúc nào", "group": "illegal",
               "severity": "critical", "disadvantaged": "Bên thuê", "explanation": "Đơn phương chấm dứt không báo trước.",
               "suggestion": "Báo trước 30 ngày.", "legal": True, "legal_status": "concluded", "refusal": None,
               "note": None, "needs_check": False,
               "evidence": [{"eid": "L1", "store": "versioned", "source_title": "Luật Nhà ở số 65/2014/QH13",
                             "section": "Điều 132", "text": "Điều 132. Đơn phương chấm dứt hợp đồng thuê nhà ở",
                             "valid_from": "2015-07-01", "valid_to": "2024-08-01", "status": "verified"}]},
              {"id": "F2", "unit_label": "Điều 8", "quote": "Phạt 20%.", "group": "illegal", "severity": "major",
               "disadvantaged": "Cả hai bên", "explanation": "Mức phạt có thể vượt giới hạn.", "suggestion": "Giảm.",
               "legal": True, "legal_status": "cannot_conclude", "refusal": REFUSAL, "note": None,
               "needs_check": False, "evidence": []}]}

REDLINE = {"rid": "r2", "op": "redline", "created_at": "2026-11-11T08:05:00+00:00", "party": "Bên thuê",
           "anchor": "2023-03-15", "coverage": {"reviewed": 2, "total": 2},
           "redlines": [{"finding_id": "F1", "unit_label": "Điều 9", "old": "Bên A được chấm dứt bất cứ lúc nào",
                         "old_ok": True, "new": "Bên A chỉ được chấm dứt khi Bên B vi phạm, báo trước 30 ngày",
                         "reason": "Bảo vệ bên thuê", "legal_note": None}]}


def docx_text(data: bytes) -> str:
    d = docx.Document(io.BytesIO(data))
    parts = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            parts.extend(c.text for c in row.cells)
    return "\n".join(parts)


def test_review_docx_contains_required_parts():
    text = docx_text(report_docx(contract(), REVIEW))
    for needle in ("hop_dong.docx", "Bên thuê", "15/03/2023", "Đã soát 2/2", "Luật Nhà ở số 65/2014/QH13",
                   "01/07/2015", REFUSAL, "Không thay thế tư vấn pháp lý", "Bên A được chấm dứt bất cứ lúc nào"):
        assert needle in text, needle


def test_redline_docx_has_old_and_new():
    text = docx_text(report_docx(contract(), REDLINE))
    assert "Bên A được chấm dứt bất cứ lúc nào" in text and "báo trước 30 ngày" in text


def test_pdf_keeps_vietnamese_diacritics():
    data = report_pdf(contract(), REVIEW)
    with fitz.open(stream=data, filetype="pdf") as doc:
        text = "".join(page.get_text() for page in doc).replace("\xa0", " ")   # Story xuất dấu cách không ngắt
    assert "Điều 9" in text and "Đã soát 2/2" in text and "Luật Nhà ở" in text
