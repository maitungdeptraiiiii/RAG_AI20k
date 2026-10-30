# Tuần 4 — Domain Agentic RAG

[Trang chủ](../../README.md) · [Tracker](TRACKER.md) · [Bài nộp](../../reports/week-04/README.md)

## Mục tiêu

Hoàn thiện sản phẩm chuyên ngành và chứng minh Agent cải thiện ít nhất một nhóm tác vụ; không cần multi-agent.

## Phạm vi và bài thực hành bắt buộc

- Chốt ba việc hệ thống làm tốt và ba việc ngoài phạm vi; tái sử dụng dữ liệu tuần 2–3.
- Chọn phạm vi nhỏ: một tỉnh và 20–30 địa điểm; một bảo tàng; một công ty với vài kỳ báo cáo; một giai đoạn lịch sử; hoặc một nhóm tình huống giao thông.
- Agent có ít nhất hai tool có ý nghĩa; chọn tool/bước tiếp theo từ câu hỏi và kết quả nhận được.
- Có hỏi lại, báo thiếu dữ liệu, giới hạn bước, timeout và ngân sách.
- Trace ghi tool, đầu vào/đầu ra và nguồn; không ghi thông tin nhạy cảm.
- Có một chốt duyệt của con người cho bản nháp hoặc đề xuất cập nhật.
- Demo: câu trực tiếp; metadata/version; tool chuyên biệt; hai bước bằng chứng; thiếu dữ kiện; ngoài phạm vi; tool lỗi/hết ngân sách; chỉ dẫn độc hại trong tài liệu; bản nháp chưa duyệt.
- So sánh RAG baseline và Agent cùng bộ câu hỏi: task success, độ đúng/citation, hỏi lại/từ chối, tool selection, bước, latency và chi phí.

## Lịch 5 ngày full-time

| Ngày | Công việc |
|---|---|
| 1 | Chốt phạm vi, acceptance criteria và test giữ lại trước tuning. |
| 2 | Tích hợp tools, vòng lặp Agent và nguồn bằng chứng. |
| 3 | Thêm giới hạn, xử lý lỗi, trace và human review. |
| 4 | Evaluation, tình huống lỗi, so sánh baseline và sửa lỗi ưu tiên. |
| 5 | Demo, phản biện, tổng kết giới hạn và chuẩn bị tuần 5. |

## Deliverables và checklist nghiệm thu

- [ ] App chuyên ngành với Agent, tool, trace và điều kiện dừng.
- [ ] ≥50 câu tổng, có test chưa dùng tuning; báo cáo so sánh với baseline.
- [ ] Demo đủ các tình huống bắt buộc và chốt human review.
- [ ] README, kiến trúc, giới hạn, backlog, slides và video dự phòng.

## Bonus

- Cải thiện UX hiển thị bằng chứng và lịch sử phiên bản.
- Thêm tool nếu có thí nghiệm chứng minh ích lợi.

## Câu hỏi Q&A/quiz gợi ý

- Vì sao tác vụ này cần Agent?
- Khi nào Agent phải hỏi lại hoặc dừng?
- Làm sao tránh coi chỉ dẫn trong tài liệu là quyền điều khiển tool?
- Tool chọn sai khác retrieval sai như thế nào?
- Agent có hiệu quả hơn baseline sau khi tính chi phí không?
- Người duyệt đang phê duyệt chính xác artifact/phiên bản nào?

Q&A không giới hạn danh sách này. Mỗi người phải hiểu toàn bộ pipeline.

## Cách nộp

Cập nhật tracker, điền báo cáo trong `reports/week-04/team-4.1/` hoặc `reports/week-04/team-4.2/`, liên kết config/kết quả thực nghiệm, README chạy lại và slides. Ghi commit trước demo; bổ sung tag sau nghiệm thu. Áp dụng [evaluation](../../docs/EVALUATION.md) và [rubric 45 phút](../../docs/ASSESSMENT.md).
