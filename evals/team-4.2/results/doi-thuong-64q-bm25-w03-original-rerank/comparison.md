# BM25 0.3, Jev nhận câu gốc — benchmark 64 câu

Chỉ chạy một cấu hình mới trên pool cố định của BM25=0.3. Các cấu hình đối chiếu đọc từ kết quả đã lưu.
Không chạy lại baseline, retrieval, rewrite, HyDE hoặc embedding.

| Cấu hình | Recall@5 | Hit@5 | MRR@5 | Recall@20 | Multi đủ gold |
|---|---:|---:|---:|---:|---:|
| saved-v2 | 0.895833 | 0.984375 | 0.842187 | 0.947917 | 16/27 |
| bm25-w03-rewrite-rerank | 0.885417 | 0.953125 | 0.850260 | 0.945312 | 16/27 |
| bm25-w03-original-rerank | 0.888021 | 0.968750 | 0.831250 | 0.945312 | 16/27 |

## Thay đổi Recall@5

- So với saved-v2: tăng []; giảm ['d10'].
- So với bm25-w03-rewrite-rerank: tăng ['d12', 'd17']; giảm ['d04', 'd52'].

Tổng 1821 cặp query–chunk; 246 cặp thiếu cache ở preflight.
Cache key gồm model, toàn bộ instructions/state và chunk_id. Số cặp thiếu cache không tính retry SDK hoặc hóa đơn.
Chỉ đánh giá retrieval, chưa đánh giá câu trả lời hoặc tập độc lập. Thời gian bị ảnh hưởng cache.
Đã thêm REWRITE_FOR_RERANK=false để chỉ dùng rewrite cho BM25; chưa thay đổi .env.
