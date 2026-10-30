# Tuần 1 — RAG foundation

[Trang chủ](../../README.md) · [Tracker](TRACKER.md) · [Bài nộp](../../reports/week-01/README.md)

## Objectives

Xây app RAG baseline end-to-end và hiểu ingestion, keyword/dense retrieval, fusion, generation và evaluation. Chưa yêu cầu Agent tự quyết định vòng lặp.

## Scope and required exercises

- Ingest PDF có text và Markdown; crawler là bonus. Tách interface reader/parser/chunker/indexer để thêm nguồn sau này.
- BM25, Dense và RRF đều chạy độc lập; UI hiển thị raw chunks, nguồn, thứ hạng và phương pháp.
- Chat trả lời từ context, citation trỏ về đoạn/trang nguồn; báo thiếu bằng chứng khi cần.
- Chuẩn bị ≥10 câu hỏi cho mỗi bộ tài liệu, nhãn bằng chứng và baseline Recall@5/MRR@5.
- Phân tích ít nhất 3 case sai; chốt lĩnh vực sơ bộ cho các tuần sau.

## Lịch 5 ngày full-time

| Ngày | Công việc |
|---|---|
| 1 | Chốt stack, dữ liệu, cấu trúc code và hợp đồng dữ liệu; dựng app tối thiểu. |
| 2 | Triển khai PDF/Markdown ingestion, chunking và metadata nguồn. |
| 3 | Triển khai BM25, Dense, RRF và giao diện raw chunks. |
| 4 | Tích hợp chat/citation; gán nhãn, chạy evaluation và phân tích lỗi. |
| 5 | Kiểm tra chạy lại từ README, đóng gói báo cáo và trình bày. |

## Deliverables and acceptance checklist

- [ ] App có UI chạy upload → ingest → hỏi → trả lời có citation.
- [ ] Chứng minh BM25, Dense và Fusion đều hoạt động với kết quả riêng.
- [ ] Evaluation report ≥10 câu/bộ tài liệu, Recall@5 và MRR@5, ít nhất 3 failure cases.
- [ ] README cài đặt/chạy lại, cấu hình mẫu không có bí mật; 5–10 slides.

## Bonus

- Hỗ trợ tiếng Việt được kiểm chứng bằng câu hỏi thực tế.
- Crawler; SPLADE, ColBERT hoặc HyDE nếu đã hoàn thành baseline.

## Câu hỏi Q&A/quiz gợi ý

- BM25 hoạt động thế nào, khác TF-IDF ra sao?
- Embedding là gì? RRF kết hợp thứ hạng như thế nào?
- Retriever khác reranker thế nào? Bi-encoder và cross-encoder?
- Chunk size ảnh hưởng gì? Hỏi ngoài phạm vi xử lý thế nào?
- Giải thích Recall@5 của nhóm; dữ liệu tăng 100 lần thì thay đổi gì?

Q&A không giới hạn danh sách này. Mỗi người phải hiểu toàn bộ pipeline.

## Submission guidelines

Cập nhật tracker, điền báo cáo trong `reports/week-01/team-4.1/` hoặc `reports/week-01/team-4.2/`, liên kết config/kết quả thực nghiệm, README chạy lại và slides. Ghi commit trước demo; bổ sung tag sau nghiệm thu. Áp dụng [evaluation](../../docs/EVALUATION.md) và [rubric 45 phút](../../docs/ASSESSMENT.md).
