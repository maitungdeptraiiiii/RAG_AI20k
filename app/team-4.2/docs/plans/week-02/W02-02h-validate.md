# W02-02h — Kiểm tra số liệu

Owner: B · Reviewer: E · Ngày 3 · File: `src/rag/quality/validate.py`, `tests/test_validate.py`

> Nhất quán số học không chứng minh nguồn đúng — ghi rõ trong report.

## Checklist

- [ ] Chuẩn hoá số kiểu VN: `1.500` = 1500, `1,5` = 1.5; phát hiện chuỗi mơ hồ (`1,500`) → issue `ambiguous_number`
- [ ] Chuẩn hoá đơn vị tiền: đồng / nghìn đồng / triệu / tỷ → giá trị đồng; lấy đơn vị từ header/caption bảng
- [ ] Kiểm tra kiểu cột (số / ngày / text) trong bảng
- [ ] Kiểm tra kỳ: tháng/quý/năm hợp lệ, khớp tiêu đề
- [ ] Quy tắc tổng: dòng "Tổng"/"Cộng" = tổng các dòng (sai số cho phép)
- [ ] Ngày: `effective_from` ≤ `effective_to`; `published_at` hợp lệ
- [ ] Xuất `QualityIssue` có `location` (bảng, hàng, cột)
- [ ] Cung cấp hàm so sánh giá trị đã chuẩn hoá cho W02-02g (phát hiện conflict)
- [ ] Test với 3 file đơn vị + 2 file tổng/kỳ của fixtures, và file sạch (không báo nhầm)

## Tiêu chí nghiệm thu

- Phát hiện lỗi đơn vị, tổng, kỳ trên fixtures; báo nhầm trên file sạch được đếm.

## Ghi chú

-
