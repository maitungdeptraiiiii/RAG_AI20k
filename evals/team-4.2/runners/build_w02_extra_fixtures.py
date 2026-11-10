"""Sinh 5 fixture bổ sung (w02-26 … w02-30) một cách xác định, cho đủ checklist W02-01a.

    26  TXT   exact duplicate thứ 2 (bản sao bytes của w02-14)
    27  DOCX  phiếu tiếp nhận có PII giả trong đoạn văn + bảng (CCCD, SĐT, MST, STK, email, họ tên)
    28  XLSX  bảng phí có caption gộp ô, dòng "Đơn vị", sheet trống, cột SĐT giả
    29  PDF   scan văn bản (ảnh w02-25 làm mờ, nghiêng, nhiễu) -> OCR kém, PDF không có text layer
    30  PNG   bảng phí (ảnh w02-24 nghiêng 7°, nhiễu, nén JPEG) -> OCR kém

Mọi PII là giả lập (example.test, dải số minh hoạ). Chạy lại cho ra cùng bytes với 26/27/28
(ảnh 29/30 dùng seed cố định). Chạy tại gốc repo:

    python evals/team-4.2/runners/build_w02_extra_fixtures.py
"""

from __future__ import annotations

import io
import random
import shutil
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data/team-4.2/fixtures/raw"
FIXED_ZIP_TIME = (2026, 11, 9, 0, 0, 0)


def _zinfo(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def build_exact_copy() -> Path:
    out = RAW / "text/26_regulation_v1_exact_copy.txt"
    shutil.copyfile(RAW / "text/14_regulation_v1.txt", out)
    return out


def build_docx() -> Path:
    import docx

    out = RAW / "docs/27_application_pii.docx"
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = docx.Document()
    doc.core_properties.author = "fixture"
    doc.add_paragraph("PHIẾU TIẾP NHẬN HỒ SƠ")
    doc.add_paragraph("Căn cứ Nghị định số 10/2026/NĐ-CP ngày 15/12/2025.")
    doc.add_paragraph("Họ và tên: Trần Thị Bình")
    doc.add_paragraph("Số CCCD: 001190000001, cấp ngày 01/07/2021.")
    doc.add_paragraph("Điện thoại liên hệ: 0912 000 002.")
    doc.add_paragraph("Lệ phí đã nộp: 1.500.000 đồng theo Điều 5 khoản 2.")
    doc.add_paragraph("Bảng 1. Thông tin thanh toán")
    table = doc.add_table(rows=2, cols=4)
    for c, text in enumerate(("Mã số thuế", "Số tài khoản", "Email", "Thủ tục")):
        table.cell(0, c).text = text
    for c, text in enumerate(("0100000003", "1903 0000 0004", "tran.thi.binh@example.test", "Cấp bản sao")):
        table.cell(1, c).text = text
    buf = io.BytesIO()
    doc.save(buf)
    out.write_bytes(_normalize_zip(buf.getvalue()))
    return out


def _normalize_zip(data: bytes) -> bytes:
    """Đặt thời gian cố định cho mọi entry để file tái tạo ra cùng bytes."""
    src = zipfile.ZipFile(io.BytesIO(data))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            content = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                import re
                content = re.sub(rb"<dcterms:(created|modified)[^>]*>[^<]*</dcterms:\1>", b"", content)
            dst.writestr(_zinfo(info.filename), content)
    return buf.getvalue()


def _sheet_xml(rows: list[list[str]], merges: list[str]) -> str:
    def col(i: int) -> str:
        s = ""
        i += 1
        while i:
            i, r = divmod(i - 1, 26)
            s = chr(65 + r) + s
        return s

    body = []
    for r, row in enumerate(rows, start=1):
        cells = "".join(
            f'<c r="{col(c)}{r}" t="inlineStr"><is><t>{escape(v)}</t></is></c>' if not v.replace(".", "").isdigit()
            else f'<c r="{col(c)}{r}"><v>{v}</v></c>'
            for c, v in enumerate(row) if v != ""
        )
        body.append(f'<row r="{r}">{cells}</row>')
    merge_xml = (f'<mergeCells count="{len(merges)}">' + "".join(f'<mergeCell ref="{m}"/>' for m in merges)
                 + "</mergeCells>") if merges else ""
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(body)}</sheetData>{merge_xml}</worksheet>')


def build_xlsx() -> Path:
    out = RAW / "tables/28_fee_schedule_pii.xlsx"
    sheets = [
        ("Bảng phí", _sheet_xml([
            ["Bảng phí cấp bản sao năm 2026", "", "", ""],
            ["Đơn vị: nghìn đồng", "", "", ""],
            ["Thủ tục", "Mức phí", "Kỳ", "Số điện thoại liên hệ"],
            ["Cấp bản sao", "20", "2026-Q1", "0900000005"],
            ["Chứng thực chữ ký", "10", "2026-Q1", "0900000006"],
            ["", "", "", ""],
        ], ["A1:D1"])),
        ("Trống", _sheet_xml([], [])),
    ]
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    workbook = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="{ns}" xmlns:r="{rel_ns}">'
                "<sheets>" + "".join(f'<sheet name="{escape(n)}" sheetId="{i}" r:id="rId{i}"/>'
                                     for i, (n, _) in enumerate(sheets, start=1)) + "</sheets></workbook>")
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(f'<Relationship Id="rId{i}" Type="{rel_ns}/worksheet" Target="worksheets/sheet{i}.xml"/>'
                      for i in range(1, len(sheets) + 1)) + "</Relationships>")
    content_types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                     '<Default Extension="xml" ContentType="application/xml"/>'
                     '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                     + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                               for i in range(1, len(sheets) + 1)) + "</Types>")
    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 f'<Relationship Id="rId1" Type="{rel_ns}/officeDocument" Target="xl/workbook.xml"/></Relationships>')
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in [("[Content_Types].xml", content_types), ("_rels/.rels", root_rels),
                           ("xl/workbook.xml", workbook), ("xl/_rels/workbook.xml.rels", rels),
                           *[(f"xl/worksheets/sheet{i}.xml", x) for i, (_, x) in enumerate(sheets, start=1)]]:
            z.writestr(_zinfo(name), data)
    return out


def _degrade(src: Path, *, angle: float, blur: float, noise: int, scale: float, quality: int, seed: int):
    from PIL import Image, ImageEnhance, ImageFilter

    rng = random.Random(seed)
    img = Image.open(src).convert("L")
    w, h = img.size
    img = img.resize((int(w * scale), int(h * scale)), Image.BILINEAR)
    img = img.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=235)
    img = img.filter(ImageFilter.GaussianBlur(blur))
    img = ImageEnhance.Contrast(img).enhance(0.55)
    px = img.load()
    for _ in range(img.size[0] * img.size[1] // 12):
        x, y = rng.randrange(img.size[0]), rng.randrange(img.size[1])
        px[x, y] = max(0, min(255, px[x, y] + rng.randint(-noise, noise)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)       # nén mạnh gây vỡ nét dấu tiếng Việt
    return Image.open(io.BytesIO(buf.getvalue()))


def build_scan_pdf() -> Path:
    import fitz  # PyMuPDF

    out = RAW / "scans/29_legal_text_blurred_scan.pdf"
    img = _degrade(RAW / "scans/25_legal_text_clear.png", angle=2.5, blur=1.6, noise=70, scale=0.55,
                   quality=18, seed=29)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    doc = fitz.open()
    page = doc.new_page(width=img.size[0], height=img.size[1])
    page.insert_image(page.rect, stream=buf.getvalue())
    doc.set_metadata({})
    out.write_bytes(doc.tobytes(garbage=4, deflate=True, no_new_id=True))
    return out


def build_skewed_png() -> Path:
    out = RAW / "scans/30_legal_fee_table_skewed.png"
    img = _degrade(RAW / "scans/24_legal_fee_table_clear.png", angle=-7, blur=1.1, noise=60, scale=0.6,
                   quality=20, seed=30)
    img.save(out, format="PNG")
    return out


def main() -> int:
    for build in (build_exact_copy, build_docx, build_xlsx, build_scan_pdf, build_skewed_png):
        path = build()
        print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
