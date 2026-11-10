# W02-02b — Nhóm bảng / CSV

Owner: B · Reviewer: C · Ngày 2 · File: `src/rag/ingest/tables.py`, `tests/test_tables.py`

## Checklist

- [x] Loader CSV (encoding UTF-8/UTF-8-BOM/cp1258, delimiter tự dò)
- [x] Loader XLSX (`openpyxl`): từng sheet, bỏ hàng trống, xử lý ô gộp
- [x] Trích bảng trong DOCX (hiện `_docx_blocks` làm phẳng) → bảng có cấu trúc
- [x] Biểu diễn chunk bảng: Markdown table, **lặp lại header** ở mọi chunk
- [x] Giữ caption/tiêu đề bảng, dòng đơn vị ("Đơn vị: nghìn đồng"), chú thích cuối bảng
- [x] Bảng dài: cắt theo nhóm hàng, ghi `row_range`, `table_id`
- [ ] Điền `source_type`, `content_origin=source`, `chunk_strategy=structural`
- [x] Nối vào `load_source` theo đuôi file
- [x] Test: header có trong mọi chunk; đơn vị không bị mất; bảng 1 hàng; ô trống
- [ ] Thử upload CSV qua UI Streamlit

## Tiêu chí nghiệm thu

- Hỏi "lương tối thiểu vùng II" trả đúng chunk và chunk đó có header + đơn vị.

## Ghi chú

- Code: `src/rag/ingest/tables.py` (`quality/tables.py` chỉ re-export để tương thích); test: `tests/test_tables.py`.
- XLSX đọc bằng thư viện chuẩn (zip + XML), không thêm dependency `openpyxl`; ô gộp điền lại giá trị ô gốc.
- `table_id`/`row_range` nằm trong `Chunk.section = "table:<i>"` và dòng `(Hàng a–b/N)` vì `Chunk` chưa có trường riêng; mục `source_type`/`content_origin`/`chunk_strategy` chờ schema W02-02a của Nhóm 1.
- UI Streamlit đã nhận `.csv`/`.xlsx`, nhưng chưa thử upload tay.
