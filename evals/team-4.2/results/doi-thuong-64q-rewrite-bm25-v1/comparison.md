# Rewrite và BM25 — 64 câu

Chỉ chạy ba cấu hình được yêu cầu; v2 là kết quả đã lưu, không chạy lại baseline.

| Cấu hình | Recall@5 | Hit@5 | MRR@5 | Recall@20 | Multi đủ gold |
|---|---:|---:|---:|---:|---:|
| saved-v2 | 0.895833 | 0.984375 | 0.842187 | 0.947917 | 16/27 |
| rewrite-only | 0.885417 | 0.968750 | 0.854167 | 0.953125 | 15/27 |
| rewrite-bm25-w1 | 0.890625 | 0.953125 | 0.836458 | 0.919271 | 17/27 |
| rewrite-bm25-w03 | 0.885417 | 0.953125 | 0.850260 | 0.945312 | 16/27 |

## Khối lượng xử lý

| Cấu hình | Cặp query–chunk qua Jev | Cặp thiếu cache Jev trong lượt chạy |
|---|---:|---:|
| saved-v2 | 1774 | Không đo trong lượt này |
| rewrite-only | 1774 | 1714 |
| rewrite-bm25-w1 | 1886 | 751 |
| rewrite-bm25-w03 | 1821 | 17 |

64 lượt sinh rewrite được cache dùng chung; 62 câu thay đổi, 2 câu giữ gốc do kiểm tra đầu vào (d19, d32).
Số cặp thiếu cache không bao gồm retry nội bộ của SDK và không phải hóa đơn API.

## Recall@5 tăng/giảm theo câu

- rewrite-only vs saved-v2: tăng ['d04', 'd52']; giảm ['d12', 'd17', 'd40'].
- rewrite-bm25-w1 vs saved-v2: tăng ['d04', 'd52']; giảm ['d02', 'd17'].
- rewrite-bm25-w03 vs saved-v2: tăng ['d04', 'd52']; giảm ['d10', 'd12', 'd17'].

Dense/HyDE và câu con không thay đổi. Rewrite dùng cho Jev và nhánh BM25 của câu gốc.
Trọng số RRF: Dense=1; BM25=1 hoặc 0.3. Giới hạn pool và Jev instructions giữ nguyên.
API Jev dùng chung cache giữa các cấu hình; không dùng thời gian để so sánh tốc độ.
Chỉ đánh giá retrieval, không đánh giá chất lượng trả lời; tập 64 câu đã được dùng để phát triển.
