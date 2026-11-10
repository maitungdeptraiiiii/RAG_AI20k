"""Báo cáo chi tiết sau ingest: mỗi trang lấy text từ đâu, OCR tin cậy tới đâu, tài liệu đủ hay thiếu.

Chạy trên các trang ĐÃ mask PII (preview không chứa PII gốc). Không gọi mạng, không ghi đĩa.

    details = page_details(pages)
    summary = summarize_pages(details, quality_issues)

``kind`` của một trang:
    text     text layer gốc (PDF có chữ, DOCX, TXT, URL)
    ocr      text do OCR sinh (PDF scan, ảnh, trang text layer hỏng đã đọc lại)
    flagged  có text nhưng đáng ngờ (font cũ vỡ dấu) và không OCR lại được
    table    bảng có cấu trúc (CSV / XLSX / bảng trong DOCX)
    empty    không có chữ nào (PDF scan khi chưa bật OCR)

Một trang "đầy đủ" khi có text và output OCR không bị cắt. ``completeness_pct`` = tỉ lệ trang đầy đủ.
Độ tin cậy OCR là điểm trung bình của Tesseract (0-100) đo trên chính ảnh trang; Gemini không trả
điểm tin cậy nên đây là thước đo độc lập, ngưỡng thấp lấy từ ``OCR_MIN_CONFIDENCE``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Any

from rag.ingest.loaders import FlaggedPage, OCRPage, TablePage
from rag.ingest.ocr import OCR_EMPTY, OCR_LOW_CONFIDENCE, OCR_TRUNCATED
from rag.schema import Page

PREVIEW_CHARS = 280

_ISSUE_TEXT = {
    OCR_LOW_CONFIDENCE: "Độ tin cậy OCR thấp, cần đối chiếu ảnh gốc",
    OCR_TRUNCATED: "Output OCR bị cắt, thiếu nội dung trang",
    OCR_EMPTY: "OCR không đọc được chữ nào",
}


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def page_details(pages: Sequence[Page]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, p in enumerate(pages):
        text = p.text or ""
        has_text = bool(text.strip())
        row: dict[str, Any] = {
            "index": i,
            "page": p.page,
            "kind": "text",
            "chars": len(text),
            "words": len(text.split()),
            "confidence": None,           # Tesseract 0-100, chỉ với trang OCR
            "confidence_status": None,    # good | low | unavailable
            "ocr_reason": None,           # image | bad_chars | empty_text ...
            "ocr_model": None,
            "cached": None,
            "cost_usd": 0.0,
            "complete": has_text,
            "issues": [],
            "preview": " ".join(text.split())[:PREVIEW_CHARS],
        }
        if isinstance(p, OCRPage):
            meta = p.ocr_meta
            conf = _number(meta.get("tesseract_confidence"))
            row.update(
                kind="ocr",
                confidence=round(conf, 1) if conf is not None else None,
                confidence_status=("low" if OCR_LOW_CONFIDENCE in p.ocr_issues
                                   else "good" if conf is not None else "unavailable"),
                ocr_reason=meta.get("reason"),
                ocr_model=meta.get("model"),
                cached=bool(meta.get("cached")),
                cost_usd=0.0 if meta.get("cached") else float(meta.get("cost") or 0),
                complete=has_text and OCR_TRUNCATED not in p.ocr_issues and OCR_EMPTY not in p.ocr_issues,
                issues=[{"code": c, "detail": _ISSUE_TEXT.get(c, c)} for c in p.ocr_issues],
            )
        elif isinstance(p, FlaggedPage):
            row.update(kind="flagged",
                       issues=[{"code": f"extraction.{x.kind}", "detail": x.detail} for x in p.extraction_issues])
        elif isinstance(p, TablePage):
            row.update(kind="table")
        if not has_text and row["kind"] == "text":
            row["kind"] = "empty"
        out.append(row)
    return out


def summarize_pages(details: Sequence[dict[str, Any]],
                    quality_issues: Iterable[dict[str, Any]] = ()) -> dict[str, Any]:
    total = len(details)
    kinds = Counter(d["kind"] for d in details)
    ocr = [d for d in details if d["kind"] == "ocr"]
    confs = [d["confidence"] for d in ocr if d["confidence"] is not None]
    complete = sum(1 for d in details if d["complete"])

    def pages_where(pred) -> list[int | None]:
        return [d["page"] if d["page"] is not None else d["index"] + 1 for d in details if pred(d)]

    incomplete = pages_where(lambda d: not d["complete"])
    low = pages_where(lambda d: d["confidence_status"] == "low")
    flagged = pages_where(lambda d: d["kind"] == "flagged")
    severities = Counter(i.get("severity") for i in quality_issues)
    if incomplete:
        status = "incomplete"
    elif low or flagged or severities["warning"] or severities["error"]:
        status = "review"
    else:
        status = "ok"
    return {
        "status": status,                       # ok | review | incomplete
        "pages_total": total,
        "pages_by_kind": {k: kinds.get(k, 0) for k in ("text", "ocr", "flagged", "table", "empty")},
        "pages_complete": complete,
        "completeness_pct": round(100 * complete / total, 1) if total else 0.0,
        "incomplete_pages": incomplete,
        "ocr_pages": len(ocr),
        "mean_confidence": round(sum(confs) / len(confs), 1) if confs else None,
        "min_confidence": round(min(confs), 1) if confs else None,
        "confidence_measured_pages": len(confs),
        "low_confidence_pages": low,
        "flagged_pages": flagged,
        "ocr_cost_usd": round(sum(d["cost_usd"] for d in ocr), 6),
        "ocr_cached_pages": sum(1 for d in ocr if d["cached"]),
        "issues_by_severity": {k: v for k, v in severities.items() if k},
    }


__all__ = ["PREVIEW_CHARS", "page_details", "summarize_pages"]
