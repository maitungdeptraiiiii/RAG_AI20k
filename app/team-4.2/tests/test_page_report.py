from rag.ingest.extraction_check import PageIssue
from rag.ingest.loaders import FlaggedPage, OCRPage
from rag.ingest.ocr import OCR_LOW_CONFIDENCE, OCR_TRUNCATED
from rag.ingest.page_report import page_details, summarize_pages
from rag.schema import Page


def _ocr(page, text="Điều 1. Nội dung", issues=(), **meta):
    return OCRPage("d", "scan.pdf", page, text, ocr_engine="gemini", ocr_issues=tuple(issues),
                   ocr_meta={"reason": "image", "model": "m", **meta})


def test_text_pages_are_complete_and_ok():
    details = page_details([Page("d", "a.pdf", 1, "Điều 1"), Page("d", "a.pdf", 2, "Điều 2")])
    assert [d["kind"] for d in details] == ["text", "text"]
    s = summarize_pages(details)
    assert s["status"] == "ok" and s["completeness_pct"] == 100.0
    assert s["ocr_pages"] == 0 and s["mean_confidence"] is None


def test_ocr_confidence_cost_and_low_confidence():
    pages = [_ocr(1, tesseract_confidence=91.24, cost=0.002),
             _ocr(2, issues=[OCR_LOW_CONFIDENCE], tesseract_confidence=40.0, cost=0.001, cached=True)]
    details = page_details(pages)
    assert details[0]["confidence"] == 91.2 and details[0]["confidence_status"] == "good"
    assert details[1]["confidence_status"] == "low" and details[1]["cost_usd"] == 0.0   # cache -> miễn phí
    assert details[1]["issues"][0]["code"] == OCR_LOW_CONFIDENCE
    s = summarize_pages(details)
    assert s["status"] == "review" and s["low_confidence_pages"] == [2]
    assert s["mean_confidence"] == 65.6 and s["min_confidence"] == 40.0
    assert s["ocr_cost_usd"] == 0.002 and s["ocr_cached_pages"] == 1


def test_truncated_and_empty_pages_make_document_incomplete():
    pages = [_ocr(1, issues=[OCR_TRUNCATED], tesseract_confidence="unavailable"),
             Page("d", "scan.pdf", 2, "   "), Page("d", "scan.pdf", 3, "Điều 3")]
    details = page_details(pages)
    assert details[0]["confidence_status"] == "unavailable" and not details[0]["complete"]
    assert details[1]["kind"] == "empty"
    s = summarize_pages(details)
    assert s["status"] == "incomplete" and s["incomplete_pages"] == [1, 2]
    assert s["completeness_pct"] == 33.3
    assert s["pages_by_kind"]["ocr"] == 1 and s["pages_by_kind"]["empty"] == 1


def test_flagged_page_and_quality_warning_need_review():
    flagged = FlaggedPage("d", "old.pdf", 1, "§iÒu 1",
                          extraction_issues=(PageIssue(1, "bad_chars", "font TCVN3"),))
    details = page_details([flagged])
    assert details[0]["kind"] == "flagged" and details[0]["issues"][0]["code"] == "extraction.bad_chars"
    assert summarize_pages(details)["status"] == "review"
    clean = page_details([Page("d", "a.txt", None, "Điều 1")])
    s = summarize_pages(clean, [{"severity": "warning"}])
    assert s["status"] == "review" and s["issues_by_severity"] == {"warning": 1}


def test_preview_is_short_single_line():
    details = page_details([Page("d", "a.txt", None, "dòng 1\n\n" + "x " * 500)])
    assert "\n" not in details[0]["preview"] and len(details[0]["preview"]) <= 280
    assert details[0]["page"] is None
