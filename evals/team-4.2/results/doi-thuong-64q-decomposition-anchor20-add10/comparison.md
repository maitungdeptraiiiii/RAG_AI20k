# Benchmark cấu hình giữ pool gốc 20 + thêm tối đa 10 Điều

Chỉ chạy cấu hình mới trên 64 câu. Các dòng đối chứng dưới đây được đọc từ CSV cũ, không chạy lại baseline hay cấu hình decomposition cũ.

| Cấu hình | Recall@5 | Hit@5 | MRR@5 | Recall@20 |
|---|---:|---:|---:|---:|
| Baseline đã lưu | 0.835938 | 0.937500 | 0.800000 | 0.914062 |
| Decomposition cũ đã lưu | 0.838542 | 0.921875 | 0.775260 | 0.924479 |
| Decomposition mới: giữ 20 + thêm tối đa 10 | 0.851562 | 0.937500 | 0.802604 | 0.937500 |

## Kiểm tra pool

- 64/64 câu giữ nguyên toàn bộ ứng viên gốc và thứ tự từ trace baseline đã lưu.
- Không câu nào thêm quá 10 Điều mới hoặc vượt tổng 30 Điều. Điều mới được xác định theo khóa (doc_id, section), không phải số chunk.
- 64/64 dòng thuộc duy nhất cấu hình mới; không lỗi, không fallback, tất cả có rerank Jev.
- Dữ liệu, prompt decomposition và HyDE giữ nguyên; chỉ đổi chính sách chọn pool.
- 165 test đạt, gồm kiểm tra giữ pool gốc, bỏ Điều trùng, giữ chunk cùng Điều và giới hạn 10 Điều mới khi pool gốc ít hơn 20.

## Hai câu từng bị mất gold

| ID | Recall@5 decomposition cũ | Recall@5 mới | MRR@5 cũ | MRR@5 mới |
|---|---:|---:|---:|---:|
| d02 | 0.000 | 0.333 | 0.000 | 1.000 |
| d10 | 0.500 | 1.000 | 0.250 | 1.000 |

## Phạm vi

Benchmark retrieval: Jina + HyDE + Jev, không BM25, không contextual header; chưa đánh giá câu trả lời cuối. Index nguồn đang được tiến trình khác sử dụng nên chạy trên bản sao SQLite nhất quán của index và cache. Nguồn và SHA-256 chunks được ghi trong config.json; không đóng tiến trình đang dùng index.
Thời gian có ảnh hưởng cache; không dùng lần chạy này để kết luận độ trễ production. Kết quả lịch sử khác (Recall@5=0.849, MRR@5=0.826) không phải đối chứng chạy lại trong thí nghiệm này.
