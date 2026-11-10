"""Đo thông tin bị mất của parser tuần 1 so với tuần 2 (bằng chứng cho data inventory W02-01).

Lấy ``app/team-4.2/src`` ở commit tuần 1 (mặc định ``89f07de``) bằng ``git archive`` vào thư mục
tạm, chạy cùng đầu vào với parser hiện tại, ghi ``summary.json``. Chạy tại gốc repo:

    python evals/team-4.2/runners/measure_w02_parser_loss.py --out evals/team-4.2/results/w02-inventory
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data/team-4.2/fixtures/raw"
UNSUPPORTED = ["tables/19_budget_valid_multiline_header.csv", "tables/28_fee_schedule_pii.xlsx",
               "scans/24_legal_fee_table_clear.png"]


def _import_rag(src: Path):
    for name in [m for m in sys.modules if m == "rag" or m.startswith("rag.")]:
        del sys.modules[name]
    sys.path.insert(0, str(src))
    try:
        from rag.ingest import chunker, loaders
        return loaders, chunker
    finally:
        sys.path.remove(str(src))


def _long_docx(path: Path) -> None:
    import docx

    d = docx.Document()
    for text in ("Điều 3. Mức lương tối thiểu", "Bảng 2. Lương tối thiểu theo vùng", "Đơn vị: nghìn đồng"):
        d.add_paragraph(text)
    t = d.add_table(rows=61, cols=3)
    for c, v in enumerate(("Vùng", "Mức lương tháng", "Mức lương giờ")):
        t.cell(0, c).text = v
    for r in range(1, 61):
        for c, v in enumerate((f"Vùng {r}", str(4000 + r * 10), str(20 + r))):
            t.cell(r, c).text = v
    d.save(path)


def measure(src: Path, docx_path: Path, label: str) -> dict:
    loaders, chunker = _import_rag(src)
    out: dict = {"parser": label, "unsupported": {}}
    for rel in UNSUPPORTED:
        try:
            pages = loaders.load_source(RAW / rel)
            out["unsupported"][rel] = f"ok: {len(pages)} page(s)"
        except Exception as error:  # noqa: BLE001 - ghi lại đúng lỗi của parser
            out["unsupported"][rel] = f"{type(error).__name__}: {error}"
    pdf = loaders.load_source(RAW / "scans/29_legal_text_blurred_scan.pdf")
    out["pdf_scan_text_chars"] = sum(len(p.text) for p in pdf)
    pages = loaders.load_source(docx_path)
    table_pages = [p for p in pages if getattr(p, "table", None) is not None]
    text_pages = [p for p in pages if getattr(p, "table", None) is None]
    if table_pages:
        from rag.ingest.tables import chunk_tables
        chunks = chunk_tables([p.table for p in table_pages], doc_id="x", source="luong.docx", max_syllables=300)
    else:
        chunks = chunker.chunk_document(text_pages, max_syllables=300)
    out["long_docx_table"] = {
        "chunks": len(chunks),
        "with_header": sum("Mức lương tháng" in c.text for c in chunks),
        "with_unit": sum("nghìn đồng" in c.text for c in chunks),
    }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--baseline", default="89f07de", help="commit parser tuần 1")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        data = subprocess.run(["git", "archive", args.baseline, "app/team-4.2/src"], cwd=ROOT,
                              capture_output=True, check=True).stdout
        tarfile.open(fileobj=io.BytesIO(data)).extractall(tmp_path, filter="data")
        docx_path = tmp_path / "luong.docx"
        _long_docx(docx_path)
        result = {
            "baseline": measure(tmp_path / "app/team-4.2/src", docx_path, f"week-1 ({args.baseline})"),
            "current": measure(ROOT / "app/team-4.2/src", docx_path, "week-2 (working tree)"),
        }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
