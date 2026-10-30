# Tuần 5 — Cập nhật và phát triển nội dung có giám sát

[Trang chủ](../../README.md) · [Tracker](TRACKER.md) · [Bài nộp](../../reports/week-05/README.md)

## Objectives

Xây Agent phát hiện thay đổi, tạo nội dung có bằng chứng, monitor chất lượng và cho phép con người duyệt/chỉnh/từ chối tại các chốt rõ ràng.

## Scope and required exercises

- Luồng dữ liệu: kiểm tra nguồn → diff → parse/validate → conflict check → regression evaluation → đề xuất → người duyệt → cập nhật index.
- Luồng sáng tạo: brief → bằng chứng → outline → người chỉnh/duyệt → bản nháp có citation → kiểm tra → duyệt xuất bản.
- Phân biệt bản nháp, đã duyệt, đã phát hành và bị từ chối; chỉnh sửa sau duyệt phải được duyệt lại.
- Không tự ingest mọi bản nháp như nguồn đã xác minh; giữ provenance và nhãn nội dung sinh.
- Monitor lỗi ingestion/schema, freshness theo chu kỳ, duplicate/conflict, hàng chờ duyệt, regression, citation, thiếu bằng chứng, latency, chi phí và tool errors.
- Chốt ngưỡng regression trước chạy; cảnh báo khi có thay đổi cần hành động, không tạo cảnh báo lặp vô ích.
- Audit ghi ai duyệt/từ chối, thời điểm, diff, version và lý do; rollback phải đưa dữ liệu/index về snapshot nhất quán.
- Hệ thống cho phép người dùng sửa brief, outline và nội dung, không chỉ bấm approve.

## Lịch 5 ngày full-time

| Ngày | Công việc |
|---|---|
| 1 | Thiết kế trạng thái, chốt review, ngưỡng chất lượng và snapshot. |
| 2 | Triển khai theo dõi nguồn, diff, validation và đề xuất cập nhật. |
| 3 | Triển khai brief/outline/draft, chỉnh sửa và approval. |
| 4 | Monitoring, regression gate, audit và diễn tập rollback. |
| 5 | Demo tích hợp toàn khóa, báo cáo cuối và bàn giao vận hành. |

## Deliverables and acceptance checklist

- [ ] Demo nguồn đổi số liệu → đề xuất có diff → người duyệt → cập nhật.
- [ ] Demo dữ liệu conflict → review; regression → chặn phát hành.
- [ ] Demo chỉnh/từ chối bản nháp và lưu quyết định; chưa duyệt không xuất bản.
- [ ] Rollback về phiên bản trước có kiểm tra kết quả truy xuất.
- [ ] Danh sách chờ duyệt, audit log, regression report, README vận hành và slides.
- [ ] Tổng kết toàn khóa: chất lượng, chi phí, giới hạn và backlog tiếp theo.

## Bonus

- Lập lịch chạy tự động trong môi trường demo.
- Dashboard xu hướng chất lượng và phát hiện các nhóm câu hỏi đang suy giảm.

## Câu hỏi Q&A/quiz gợi ý

- Làm sao phân biệt source update với lỗi parser?
- Người duyệt thay đổi outline thì bước nào cần chạy lại?
- Tại sao không dùng bản nháp làm nguồn chuẩn ngay?
- Snapshot rollback bao gồm những thành phần nào?
- Khi nào cảnh báo có thể hành động được?
- Đánh giá chất lượng nội dung mới khác regression câu hỏi cũ thế nào?

Q&A không giới hạn danh sách này. Mỗi người phải hiểu toàn bộ pipeline.

## Submission guidelines

Cập nhật tracker, điền báo cáo trong `reports/week-05/team-4.1/` hoặc `reports/week-05/team-4.2/`, liên kết config/kết quả thực nghiệm, README chạy lại và slides. Ghi commit trước demo; bổ sung tag sau nghiệm thu. Áp dụng [evaluation](../../docs/EVALUATION.md) và [rubric 45 phút](../../docs/ASSESSMENT.md).
