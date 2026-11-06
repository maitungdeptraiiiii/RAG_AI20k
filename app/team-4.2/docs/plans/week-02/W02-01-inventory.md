# W02-01 — Data inventory và lý do biểu diễn

Owner: C · Reviewer: A · Ngày 1 · Output: `reports/week-02/team-4.2/data_inventory.md`

## Checklist

- [ ] Khảo sát từng loại: HTML, PDF text, PDF scan, bảng, hình, slide, org chart, biểu đồ, flowchart, báo cáo, chuỗi số liệu
- [ ] Với mỗi loại, chạy parser hiện tại (`load_source`) trên 1 mẫu và ghi lại **thông tin bị mất** (chụp ví dụ)
  - [ ] Ví dụ bảng DOCX/PDF bị làm phẳng thành plain text
  - [ ] Ví dụ PDF scan → không có text
- [ ] Bảng inventory: `loại | ví dụ nguồn | rủi ro mất thông tin | cách biểu diễn chọn | lý do | trạng thái (làm/không làm tuần này)`
- [ ] Phân loại rủi ro (cao/trung bình/thấp) cho từng loại
- [ ] Ghi rõ biểu đồ/hình: giữ ảnh gốc, mô tả LLM gắn `content_origin=llm_description`, không dùng làm số liệu
- [ ] Đề xuất biểu diễn org chart/flowchart thành thực thể–quan hệ (bonus, chỉ cần mô tả)
- [ ] Gửi A review

## Tiêu chí nghiệm thu

- Mọi loại trong đề bài đều có một dòng; ba nhóm triển khai được đánh dấu rõ.
- Mỗi "mất thông tin" có ví dụ thật, không mô tả chung chung.

## Ghi chú

-
