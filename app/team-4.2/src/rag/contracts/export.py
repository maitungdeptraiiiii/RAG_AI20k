"""Xuất báo cáo hợp đồng ra Word (python-docx) và PDF (PyMuPDF Story).

Nội dung dựng một lần thành danh sách khối (heading / para / table) rồi render ra hai định dạng, nên Word và PDF
luôn cùng nội dung. PDF dùng font hệ thống có dấu tiếng Việt (Arial / DejaVu Sans); không có thì font mặc định.
"""

from __future__ import annotations

import html
import io
import logging
from pathlib import Path
from typing import Any

from rag.contracts.models import Contract

log = logging.getLogger(__name__)

DISCLAIMER = "Báo cáo do AI tạo để tham khảo. Không thay thế tư vấn pháp lý."
_OP_TITLE = {"review": "Báo cáo soát toàn bộ hợp đồng", "partial": "Báo cáo soát một phần hợp đồng",
             "law_changes": "Đối chiếu thay đổi của luật", "redline": "Đề xuất sửa hợp đồng",
             "summary": "Tóm tắt hợp đồng"}
_GROUP = {"illegal": "Trái luật", "missing_required": "Thiếu nội dung bắt buộc",
          "unfavorable": "Bất lợi", "ambiguous": "Mơ hồ / dễ tranh chấp"}
_SEV = {"critical": "Nghiêm trọng", "major": "Cần sửa", "minor": "Lưu ý"}
_STATUS = {"concluded": "Có căn cứ (kho luật có phiên bản)", "conditional": "Có điều kiện (kho cũ)",
           "cannot_conclude": "Chưa thể kết luận", "blocked_no_date": "Chưa có ngày ký",
           "not_legal": "Nhận xét câu chữ / thương mại"}
_PROVISION = {"verified": "đã xác minh", "needs_review": "cần xem lại", "conflicted": "có mâu thuẫn"}
_CHANGE = {"unchanged": "Không đổi", "changed": "Đã sửa đổi", "repealed": "Hết hiệu lực",
           "untracked": "Không theo dõi được (kho cũ)"}
_FONTS = ("C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
          "/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf")


def _day(iso: str | None) -> str:
    if not iso:
        return "—"
    y, m, d = iso[:10].split("-")
    return f"{d}/{m}/{y}"


def _evidence_line(e: dict) -> str:
    if e.get("store") == "versioned":
        return (f"{e['source_title']} — {e['section']} (hiệu lực {_day(e.get('valid_from'))} → "
                f"{_day(e.get('valid_to')) if e.get('valid_to') else 'nay'}; {_PROVISION.get(e.get('status'), e.get('status'))})")
    return f"{e['source_title']} — {e['section']} (Kho cũ — chưa xác định phiên bản)"


def blocks(contract: Contract, report: dict[str, Any]) -> list[tuple[str, Any]]:
    op = report["op"]
    party = report.get("party") or "neutral"
    cov = report.get("coverage") or {}
    out: list[tuple[str, Any]] = [
        ("title", _OP_TITLE.get(op, "Báo cáo hợp đồng")),
        ("para", f"Hợp đồng: {contract.filename}"),
        ("para", f"Góc nhìn: {'Trung lập' if party == 'neutral' else party}"),
        ("para", f"Mốc pháp lý (ngày ký): {_day(report.get('anchor'))}"),
        ("para", f"Ngày tạo báo cáo: {_day(report.get('created_at'))}"),
        ("para", f"Đã soát {cov.get('reviewed', 0)}/{cov.get('total', 0)} điều khoản"
                 + ("" if cov.get("reviewed") == cov.get("total") else " (bản demo giới hạn số điều khoản)")),
    ]
    if op in ("review", "partial"):
        if report.get("scope") and op == "partial":
            out.append(("para", "Phạm vi: " + ", ".join(report["scope"])))
        if not report.get("findings"):
            out.append(("para", "Không phát hiện vấn đề trong phạm vi đã soát."))
        for i, f in enumerate(report.get("findings") or [], 1):
            group = f.get("group_label") or _GROUP.get(f["group"], f["group"])
            out.append(("heading", f"{i}. {f['unit_label']} — {group} "
                                   f"({_SEV.get(f['severity'], f['severity'])})"))
            if f.get("quote"):
                out.append(("quote", f["quote"]))
            elif f.get("needs_check"):
                out.append(("para", "Trích dẫn không khớp hợp đồng — cần kiểm tra lại."))
            out.append(("para", f"Bất lợi cho: {f.get('disadvantaged') or '—'}"))
            note = f" ({f['explanation_note']})" if f.get("explanation_note") else ""
            out.append(("para", f"Giải thích{note}: {f.get('explanation') or ''}"))
            out.append(("para", f"Đánh giá pháp lý: {_STATUS.get(f.get('legal_status'), f.get('legal_status'))}"))
            for e in f.get("evidence") or []:
                out.append(("bullet", "Căn cứ: " + _evidence_line(e)))
            for extra in (f.get("refusal"), f.get("note")):
                if extra:
                    out.append(("para", extra))
            if f.get("suggestion"):
                out.append(("para", f"Gợi ý sửa: {f['suggestion']}"))
    elif op == "law_changes":
        rows = [["Căn cứ tại ngày ký", "Tình trạng hiện nay", "Chi tiết", "Điều khoản bị ảnh hưởng"]]
        for r in report.get("changes") or []:
            detail = ""
            if r["status"] == "repealed" and r.get("replaced_by"):
                detail = f"Thay bởi {r['replaced_by']['title']} từ {_day(r.get('replaced_from'))}"
                if r.get("transition_articles"):
                    detail += "; Điều chuyển tiếp: " + ", ".join(t["article"] for t in r["transition_articles"])
            elif r["status"] == "changed":
                detail = f"Nội dung mới từ {_day(r.get('current_from'))}"
            rows.append([f"{r['source_title']} — {r['section']}", _CHANGE.get(r["status"], r["status"]), detail,
                         ", ".join(r.get("affected_units") or [])])
        out.append(("table", rows) if len(rows) > 1 else ("para", "Chưa có căn cứ luật nào để đối chiếu."))
    elif op == "redline":
        rows = [["Điều khoản", "Nội dung hiện tại", "Đề xuất", "Lý do"]]
        for r in report.get("redlines") or []:
            reason = r.get("reason") or ""
            if r.get("legal_note"):
                reason += f" ({r['legal_note']})"
            rows.append([r["unit_label"], r["old"] if r.get("old_ok") else f"{r['old']} [không khớp hợp đồng]",
                         r["new"], reason])
        out.append(("table", rows) if len(rows) > 1 else ("para", "Không có điều khoản cần sửa."))
    elif op == "summary":
        for s in report.get("sections") or []:
            out.append(("heading", s["title"]))
            for item in s["items"]:
                out.append(("bullet", item["text"] + (f" ({item['unit_label']})" if item.get("unit_label") else "")))
    out.append(("para", DISCLAIMER))
    return out


def report_docx(contract: Contract, report: dict[str, Any]) -> bytes:
    import docx
    from docx.shared import Pt

    d = docx.Document()
    for kind, value in blocks(contract, report):
        if kind == "title":
            d.add_heading(value, level=1)
        elif kind == "heading":
            d.add_heading(value, level=2)
        elif kind == "quote":
            p = d.add_paragraph()
            run = p.add_run(f"“{value}”")
            run.italic = True
        elif kind == "bullet":
            d.add_paragraph(value, style="List Bullet")
        elif kind == "table":
            t = d.add_table(rows=len(value), cols=len(value[0]))
            t.style = "Table Grid"
            for i, row in enumerate(value):
                for j, cell in enumerate(row):
                    t.cell(i, j).text = cell
                    if i == 0:
                        for r in t.cell(i, j).paragraphs[0].runs:
                            r.bold = True
        else:
            p = d.add_paragraph(value)
            for r in p.runs:
                r.font.size = Pt(11)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _html(contract: Contract, report: dict[str, Any]) -> str:
    parts = []
    for kind, value in blocks(contract, report):
        if kind == "title":
            parts.append(f"<h1>{html.escape(value)}</h1>")
        elif kind == "heading":
            parts.append(f"<h2>{html.escape(value)}</h2>")
        elif kind == "quote":
            parts.append(f"<p><i>“{html.escape(value)}”</i></p>")
        elif kind == "bullet":
            parts.append(f"<p>• {html.escape(value)}</p>")
        elif kind == "table":
            rows = "".join("<tr>" + "".join(f"<{'th' if i == 0 else 'td'}>{html.escape(c)}</{'th' if i == 0 else 'td'}>"
                                            for c in row) + "</tr>" for i, row in enumerate(value))
            parts.append(f"<table>{rows}</table>")
        else:
            parts.append(f"<p>{html.escape(value)}</p>")
    return "<body>" + "".join(parts) + "</body>"


def _font() -> Path | None:
    for f in _FONTS:
        if Path(f).is_file():
            return Path(f)
    log.warning("Không tìm thấy font có dấu tiếng Việt; PDF dùng font mặc định")
    return None


def report_pdf(contract: Contract, report: dict[str, Any]) -> bytes:
    import fitz

    font = _font()
    css = ("body{font-size:10.5pt;line-height:1.35} h1{font-size:16pt} h2{font-size:12.5pt;margin-top:10pt} "
           "table{border-collapse:collapse;width:100%} td,th{border:0.5pt solid #888;padding:3pt;vertical-align:top}")
    archive = None
    if font is not None:
        archive = fitz.Archive(str(font.parent))
        css = f"@font-face {{font-family: vn; src: url({font.name});}} * {{font-family: vn;}} " + css
    story = fitz.Story(html=_html(contract, report), user_css=css, archive=archive)
    buf = io.BytesIO()
    writer = fitz.DocumentWriter(buf)
    page, area = fitz.paper_rect("a4"), fitz.paper_rect("a4") + (50, 50, -50, -50)
    more = True
    while more:
        dev = writer.begin_page(page)
        more, _ = story.place(area)
        story.draw(dev)
        writer.end_page()
    writer.close()
    return buf.getvalue()
