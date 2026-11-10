# W02-02h — Kiểm tra số liệu

Owner: B · Reviewer: E · Ngày 3 · File: `src/rag/quality/validate.py`, `tests/test_validate.py`

> Nhất quán số học không chứng minh nguồn đúng — ghi rõ trong report.

## Checklist

- [x] Chuẩn hoá số kiểu VN: `1.500` = 1500, `1,5` = 1.5; phát hiện chuỗi mơ hồ (`1,500`) → issue `ambiguous_number`
- [x] Chuẩn hoá đơn vị tiền: đồng / nghìn đồng / triệu / tỷ → giá trị đồng; lấy đơn vị từ header/caption bảng
- [x] Kiểm tra kiểu cột (số / ngày / text) trong bảng
- [x] Kiểm tra kỳ: tháng/quý/năm hợp lệ, khớp tiêu đề
- [x] Quy tắc tổng: dòng "Tổng"/"Cộng" = tổng các dòng (sai số cho phép)
- [x] Ngày: `effective_from` ≤ `effective_to`; `published_at` hợp lệ
- [x] Xuất `QualityIssue` có `location` (bảng, hàng, cột)
- [x] Cung cấp hàm so sánh giá trị đã chuẩn hoá cho W02-02g (phát hiện conflict)
- [x] Test với 3 file đơn vị + 2 file tổng/kỳ của fixtures, và file sạch (không báo nhầm)

## Tiêu chí nghiệm thu

- Phát hiện lỗi đơn vị, tổng, kỳ trên fixtures; báo nhầm trên file sạch được đếm.

## Ghi chú

- Code: `src/rag/quality/validate.py`, `numeric.py`, `issues.py`; nối trong `RAGPipeline.ingest` (`IngestReport.quality_issues`); test: `tests/test_validate.py`.
- Mã issue: `numeric.conflict`, `numeric.invalid_locale`, `numeric.sum_mismatch`, `table.missing_unit`, `table.missing_period`, `table.invalid_period`, `table.type_mismatch`, `date.invalid`, `date.range_invalid`.
- API cho W02-02g: `compare()` và `detect_conflicts(new_facts, existing_facts)`. Kiểu cột: kiểm tra cột số; cột ngày kiểm qua `validate_dates`.
- Sửa lỗi: `parse_decimal("1,500.000", vi-VN)` trước đây trả 1.5.
