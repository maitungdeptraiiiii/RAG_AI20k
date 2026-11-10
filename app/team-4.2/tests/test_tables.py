"""W02-02b — bảng CSV/XLSX/DOCX: header + đơn vị có ở mọi chunk, bảng 1 hàng, ô trống, encoding."""

from pathlib import Path

from rag.ingest.loaders import TablePage, load_source
from rag.ingest.tables import chunk_tables, load_xlsx_tables, parse_csv, table_markdown

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "data/team-4.2/fixtures/raw"


def _write_csv(path: Path, text: str, encoding: str = "utf-8") -> Path:
    path.write_bytes(text.encode(encoding))
    return path


def test_long_table_repeats_caption_unit_header_in_every_chunk(tmp_path):
    lines = ["Bảng 2. Lương tối thiểu theo vùng", "Đơn vị: nghìn đồng", "Vùng,Mức lương tháng,Kỳ"]
    lines += [f"Vùng {i},{4000 + i},2026" for i in range(1, 61)]
    lines += ["Ghi chú: số liệu giả lập"]
    table = parse_csv(_write_csv(tmp_path / "luong.csv", "\n".join(lines)))
    assert table.caption == "Bảng 2. Lương tối thiểu theo vùng" and table.unit == "nghìn đồng"
    assert len(table.rows) == 60 and table.notes[0][0].startswith("Ghi chú")

    chunks = chunk_tables([table], doc_id="d", source="luong.csv", max_rows=25)
    assert len(chunks) == 3
    for chunk in chunks:
        assert chunk.section == "table:0"
        assert "Bảng: Bảng 2. Lương tối thiểu theo vùng" in chunk.text
        assert "Đơn vị: nghìn đồng" in chunk.text
        assert "| Vùng | Mức lương tháng | Kỳ |" in chunk.text
        assert "Ghi chú: số liệu giả lập" in chunk.text
    assert chunks[0].text.endswith("(Hàng 1–25/60)") and chunks[2].text.endswith("(Hàng 51–60/60)")
    assert [c.chunk_id for c in chunks] == ["d:0000", "d:0001", "d:0002"]


def test_chunk_splits_by_syllable_budget_without_cutting_rows(tmp_path):
    rows = "\n".join(f"Hành vi số {i} rất dài để vượt ngân sách âm tiết,{i}000,VND,2026-Q1" for i in range(20))
    table = parse_csv(_write_csv(tmp_path / "t.csv", "Hành vi,Mức phạt,Đơn vị,Kỳ\n" + rows))
    chunks = chunk_tables([table], doc_id="d", source="t.csv", max_syllables=120)
    assert len(chunks) > 1
    assert sum(c.text.count("\n| Hành vi số") for c in chunks) == 20      # đủ hàng, không lặp, không cắt


def test_single_row_and_empty_cells(tmp_path):
    table = parse_csv(_write_csv(tmp_path / "a.csv", "Hành vi,Giá trị,Đơn vị,Kỳ\nNộp chậm,100,,\n"))
    assert table.rows == (("Nộp chậm", "100", "", ""),)
    text = chunk_tables([table], doc_id="d", source="a.csv")[0].text
    assert "| Nộp chậm | 100 |  |  |" in text and "(Hàng" not in text


def test_header_only_table_still_produces_a_chunk(tmp_path):
    table = parse_csv(_write_csv(tmp_path / "h.csv", "Hành vi,Giá trị\n"))
    assert table.rows == () and len(chunk_tables([table], doc_id="d", source="h.csv")) == 1


def test_cp1258_and_semicolon_delimiter(tmp_path):
    path = _write_csv(tmp_path / "w.csv", "Vung;Muc\r\nVùng I;4960\r\n", encoding="cp1258")
    table = parse_csv(path)
    assert table.headers == (("Vung", "Muc"),) and table.rows == (("Vùng I", "4960"),)


def test_multilevel_header_labels_and_markdown_escaping(tmp_path):
    table = parse_csv(FIXTURES / "tables/19_budget_valid_multiline_header.csv", header_rows=2)
    assert table.column_labels() == ("Mức xử phạt 2026 / Hành vi", "Mức xử phạt 2026 / Đơn vị",
                                     "Thực tế áp dụng / Khung phạt", "Thực tế áp dụng / Áp dụng")
    pipe = parse_csv(_write_csv(tmp_path / "p.csv", "A,B\nx|y,1\n"))
    assert "| x\\|y | 1 |" in table_markdown(pipe)


def test_xlsx_all_sheets_merged_caption_unit_and_empty_sheet_skipped():
    tables = load_xlsx_tables(FIXTURES / "tables/28_fee_schedule_pii.xlsx")
    assert len(tables) == 1                         # sheet "Trống" bị bỏ
    t = tables[0]
    assert t.sheet == "Bảng phí" and t.caption == "Bảng phí cấp bản sao năm 2026" and t.unit == "nghìn đồng"
    assert t.headers == (("Thủ tục", "Mức phí", "Kỳ", "Số điện thoại liên hệ"),)
    assert len(t.rows) == 2                         # hàng trống cuối bị bỏ


def test_docx_table_structured_with_caption():
    pages = load_source(FIXTURES / "docs/27_application_pii.docx")
    tables = [p.table for p in pages if isinstance(p, TablePage)]
    assert len(tables) == 1 and tables[0].caption == "Bảng 1. Thông tin thanh toán"
    assert tables[0].headers[0] == ("Mã số thuế", "Số tài khoản", "Email", "Thủ tục")


def test_load_source_csv_and_pipeline_question_chunk_has_header_and_unit():
    pages = load_source(FIXTURES / "tables/09_output_january_kg.csv")
    assert len(pages) == 1 and isinstance(pages[0], TablePage)
    text = chunk_tables([pages[0].table], doc_id=pages[0].doc_id, source=pages[0].source)[0].text
    assert "| Hành vi | Mức phạt | Đơn vị | Kỳ | Vùng |" in text
    assert "| Nộp hồ sơ quá hạn | 1500000 | VND | 2026-01 | Bắc |" in text
