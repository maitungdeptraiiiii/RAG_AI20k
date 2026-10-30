# Tuần 2 — Ingestion và chất lượng dữ liệu

[Trang chủ](../../README.md) · [Tracker](TRACKER.md) · [Bài nộp](../../reports/week-02/README.md)

## Mục tiêu

Hiểu garbage in, garbage out: nhận diện thông tin mất khi parsing, chọn cách biểu diễn và kiểm soát chất lượng trước retrieval.

## Phạm vi và bài thực hành bắt buộc

- Khảo sát HTML, PDF text/scan, bảng, hình, slide, org chart, biểu đồ, flowchart, báo cáo và chuỗi số liệu.
- Triển khai hoàn chỉnh ba nhóm: văn bản; bảng/CSV; một nhóm khó như scan, slide hoặc biểu đồ.
- Tạo 20–30 tài liệu nhỏ có lỗi cài sẵn: duplicate, near duplicate, conflict, phiên bản cũ/mới, đơn vị khác nhau, OCR kém và PII giả lập.
- Schema giữ document/chunk ID, checksum, nguồn, heading, trang/slide/table, loại, ngôn ngữ, ngày thu thập/xuất bản/hiệu lực, version và quality status.
- Phân biệt nội dung nguồn với mô tả LLM sinh. Biểu đồ cần giữ ảnh gốc; số liệu dùng tính toán phải được xác minh.
- Exact dedup không nhân index khi ingest lại; near duplicate/conflict phải có đường review, không tự xóa bản khác biệt quan trọng.
- Mask PII trước embedding/log; kiểm tra số liệu theo kiểu, đơn vị, kỳ và quy tắc tổng khi phù hợp. Tính nhất quán số học không chứng minh nguồn đúng.
- So sánh fixed-size với chunking theo heading/paragraph/table/slide; bảng giữ header, đơn vị, chú thích; flow giữ thứ tự và điều kiện.
- Version hỗ trợ hiện hành và lịch sử; cập nhật không làm chunk cũ lẫn vào truy vấn bản hiện hành.

## Lịch 5 ngày full-time

| Ngày | Công việc |
|---|---|
| 1 | Kiểm kê, phân loại rủi ro, tạo dữ liệu có lỗi và nhãn kiểm chứng. |
| 2 | Thiết kế schema, parser và provenance cho ba nhóm. |
| 3 | Thêm dedup, masking, validation, version và hàng đợi review. |
| 4 | So sánh chunking và ảnh hưởng retrieval; kiểm tra lỗi phát hiện/bỏ sót/báo nhầm. |
| 5 | Hoàn thiện data quality report, demo và phản biện. |

## Deliverables và checklist nghiệm thu

- [ ] Data inventory và lý do biểu diễn từng loại dữ liệu.
- [ ] Pipeline hoàn chỉnh cho ba nhóm; demo ingest lặp và cập nhật phiên bản.
- [ ] Data quality report có số lỗi phát hiện, bỏ sót, báo nhầm trên dữ liệu cài sẵn.
- [ ] So sánh hai chunking strategy trên cùng nguồn và câu hỏi.
- [ ] Ít nhất 5 failure cases, README và 5–10 slides.

## Bonus

- OCR/vùng ảnh có điểm chất lượng; xử lý thêm loại dữ liệu ngoài ba nhóm.
- Biểu diễn org chart/flowchart thành thực thể và quan hệ có provenance.

## Câu hỏi Q&A/quiz gợi ý

- Vì sao plain text làm mất ý nghĩa bảng hoặc sơ đồ?
- Khi nào tài liệu giống nhau không nên deduplicate?
- Ngày thu thập khác ngày hiệu lực thế nào?
- Kiểm tra số 1.500, header và đơn vị ra sao?
- Mask PII ở bước nào; làm sao kiểm tra log?
- Conflict tự động có đủ để quyết định nguồn nào đúng không?

Q&A không giới hạn danh sách này. Mỗi người phải hiểu toàn bộ pipeline.

## Cách nộp

Cập nhật tracker, điền báo cáo trong `reports/week-02/team-4.1/` hoặc `reports/week-02/team-4.2/`, liên kết config/kết quả thực nghiệm, README chạy lại và slides. Ghi commit trước demo; bổ sung tag sau nghiệm thu. Áp dụng [evaluation](../../docs/EVALUATION.md) và [rubric 45 phút](../../docs/ASSESSMENT.md).
