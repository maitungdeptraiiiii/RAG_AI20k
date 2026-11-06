# W02-02b — Nhóm bảng / CSV

Owner: B · Reviewer: C · Ngày 2 · File: `src/rag/ingest/tables.py`, `tests/test_tables.py`

## Checklist

- [ ] Loader CSV (encoding UTF-8/UTF-8-BOM/cp1258, delimiter tự dò)
- [ ] Loader XLSX (`openpyxl`): từng sheet, bỏ hàng trống, xử lý ô gộp
- [ ] Trích bảng trong DOCX (hiện `_docx_blocks` làm phẳng) → bảng có cấu trúc
- [ ] Biểu diễn chunk bảng: Markdown table, **lặp lại header** ở mọi chunk
- [ ] Giữ caption/tiêu đề bảng, dòng đơn vị ("Đơn vị: nghìn đồng"), chú thích cuối bảng
- [ ] Bảng dài: cắt theo nhóm hàng, ghi `row_range`, `table_id`
- [ ] Điền `source_type`, `content_origin=source`, `chunk_strategy=structural`
- [ ] Nối vào `load_source` theo đuôi file
- [ ] Test: header có trong mọi chunk; đơn vị không bị mất; bảng 1 hàng; ô trống
- [ ] Thử upload CSV qua UI Streamlit

## Tiêu chí nghiệm thu

- Hỏi "lương tối thiểu vùng II" trả đúng chunk và chunk đó có header + đơn vị.

## Ghi chú

-
