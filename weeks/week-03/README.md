# Tuần 3 — Retrieval engineering

[Trang chủ](../../README.md) · [Tracker](TRACKER.md) · [Bài nộp](../../reports/week-03/README.md)

## Mục tiêu

Nối loại câu hỏi với bằng chứng cần thiết và retrieval phù hợp; triển khai sâu một phương pháp có lợi ích đo được.

## Phạm vi và bài thực hành bắt buộc

- Khảo sát metadata + hybrid, parent–child, reranking, tabular/SQL, temporal, knowledge graph và multimodal.
- Phân loại câu hỏi: trực tiếp, metadata, tính toán, thời điểm, nhiều bước, không đủ dữ liệu.
- Chọn một phương pháp theo lỗi tuần 2; viết giả thuyết trước khi code.
- Ví dụ: bảng → SQL; phiên bản → temporal; quan hệ → graph; mất ngữ cảnh → parent–child.
- Giao diện retrieval trả bằng chứng và provenance; phép tính giữ dòng nguồn, kỳ và đơn vị.
- So sánh BM25, Dense, Hybrid RRF và Hybrid + phương pháp mới; ablation thay từng yếu tố.
- Giữ snapshot/câu hỏi/generation cố định; báo cáo chất lượng, latency và chi phí theo loại câu hỏi.
- Với SQL/graph, bổ sung đúng kết quả/đủ quan hệ; không ép tất cả thành chunk-level metric.

## Lịch 5 ngày full-time

| Ngày | Công việc |
|---|---|
| 1 | Phân loại câu hỏi, khảo sát phương pháp, chốt giả thuyết và cấu hình baseline. |
| 2 | Thiết kế và triển khai phương pháp chuyên sâu. |
| 3 | Tích hợp app, chuẩn hóa output và bộ đánh giá. |
| 4 | Chạy baseline/ablation, phân tích trade-off và lỗi. |
| 5 | Demo kết quả, bảo vệ lựa chọn và quyết định giữ/bỏ phương pháp mới. |

## Deliverables và checklist nghiệm thu

- [ ] Bảng ánh xạ loại câu hỏi → phương pháp → bằng chứng.
- [ ] Một phương pháp chuyên sâu chạy end-to-end.
- [ ] Evaluation ≥40 câu tổng; kết quả theo nhóm, latency và chi phí cùng điều kiện.
- [ ] Cấu hình tái lập, ablation và ít nhất 5 failure cases.
- [ ] README và slides; kết luận dựa trên dữ liệu kể cả khi phương pháp mới không thắng.

## Bonus

- Router đơn giản chọn retrieval theo loại truy vấn.
- Thử phương pháp thứ hai sau khi hoàn thành thực nghiệm chính.

## Câu hỏi Q&A/quiz gợi ý

- Khi nào metadata hữu ích hơn semantic similarity?
- Tại sao tính tổng nên dùng dữ liệu cấu trúc?
- Reranker có tìm được tài liệu không có trong candidate set không?
- Khi nào graph tăng độ phức tạp nhưng không tăng chất lượng?
- Chất lượng tăng nhưng latency gấp ba thì quyết định ra sao?
- Làm sao tránh tuning theo test?

Q&A không giới hạn danh sách này. Mỗi người phải hiểu toàn bộ pipeline.

## Cách nộp

Cập nhật tracker, điền báo cáo trong `reports/week-03/team-4.1/` hoặc `reports/week-03/team-4.2/`, liên kết config/kết quả thực nghiệm, README chạy lại và slides. Ghi commit trước demo; bổ sung tag sau nghiệm thu. Áp dụng [evaluation](../../docs/EVALUATION.md) và [rubric 45 phút](../../docs/ASSESSMENT.md).
