# Terminology and writing conventions

Tài liệu dùng tiếng Việt để giải thích, giữ tiếng Anh cho thuật ngữ chuyên ngành và các heading/label kỹ thuật. Không dịch từng từ máy móc hoặc đổi tên file/API chỉ để đổi cách diễn đạt.

## Preferred terms

| Ngữ cảnh | Thuật ngữ sử dụng |
|---|---|
| Lệnh để chạy lại pipeline/thí nghiệm | Reproducibility scripts |
| Các bước chạy lại kết quả | Reproduction steps |
| Khả năng tạo lại kết quả với dữ liệu/cấu hình đã ghi | Reproducibility |
| Không gian theo team | Team workspace |
| Không gian sản phẩm | Project workspace |
| Trạng thái ban đầu | Initial status |
| Tiêu chí nghiệm thu | Acceptance criteria |
| Danh sách kiểm tra nghiệm thu | Acceptance checklist |
| Mốc nghiệm thu | Acceptance milestone |
| Nhật ký hằng ngày | Daily log |
| Phân vai luân phiên | Role rotation |
| Thiết kế thí nghiệm | Experiment design |
| Phân tích lỗi | Failure analysis |
| Quyết định kiến trúc | Architecture Decision Record (ADR) |

Giữ nguyên các thuật ngữ: ingestion, parsing, chunking, embedding, retrieval, hybrid search, reranking, fusion, citation, provenance, metadata, dataset, ground truth, baseline, ablation, evaluation, guardrails, human-in-the-loop, monitoring, regression, approval, audit log, rollback, snapshot, latency và trade-off.

## Status values

Tracker dùng thống nhất: `Not started`, `In progress`, `Blocked`, `In review`, `Done`. ADR dùng `Proposed`, `Accepted`, `Superseded`.

## Examples

- “Lưu config và snapshot để bảo đảm reproducibility.”
- “Mỗi team cập nhật daily log và liên kết evidence trong tracker.”
- “Agent chuyển bản nháp sang human review trước khi xuất bản.”

Giữ tiếng Việt tự nhiên cho hướng dẫn, câu hỏi, nhận xét và nội dung học tập; không cần chuyển toàn bộ tài liệu sang tiếng Anh.
