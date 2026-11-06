# Phân tích — benchmark 6 Bộ luật (baseline hybrid)

Dataset: `evals/team-4.2/datasets/benchmark_6_bo_luat.jsonl` (20 câu: 8 lookup, 8 paraphrase, 4 multi).
Gold = section của Điều (khớp mọi chunk thuộc Điều đó); `gold_chunk_ids` ghi kèm để tra cứu.
Corpus: 6 Bộ luật (Hình sự, TTHS, Lao động, Dân sự, TTDS, Hàng hải) từ VBPL, 3.422 chunk.
Cấu hình: text-embedding-3-small, BM25 (pyvi), RRF k=60, không rerank, LLM `gpt-5.6-luna` (temperature mặc định).

## Retrieval (hybrid)

| type | n | Recall@5 | Hit@5 | MRR@5 | Recall@20 |
|---|---|---|---|---|---|
| lookup | 8 | 1.000 | 1.000 | 1.000 | 1.000 |
| paraphrase | 8 | 0.500 | 0.500 | 0.438 | 0.875 |
| multi | 4 | 0.250 | 0.500 | 0.500 | 0.250 |
| **tổng** | 20 | 0.650 | 0.700 | 0.675 | 0.800 |

Hybrid tốt hơn từng arm riêng (BM25 0.617 / Dense 0.633 Recall@5).

## Câu trả lời

- Từ chối nhầm 5/20 câu trong phạm vi (q11, q12, q17, q19, q20); trong đó q17, q20 context **có** gold
  nhưng LLM vẫn từ chối vì cần suy luận nối nhiều Điều.
- q18 trả lời "không thể kết luận" vì thiếu Điều 429 (thời hiệu) và Điều 468 (lãi suất) trong context.
- Các câu lookup trả lời đúng cả 8; q04 suy ra đúng tổng 09 ngày.

## Lỗi chính

1. **Paraphrase lệch từ vựng**: "lấy lãi" ≠ "lãi suất" (q11), "bố mẹ mất không di chúc" ≠ "thừa kế theo pháp luật" (q12),
   "nghỉ việc" kéo về Điều 36 (người sử dụng lao động) thay vì Điều 35 (q09). Gold nằm ở top-20 nhưng không lên top-5
   → rerank có khả năng giúp nhiều.
2. **Multi-hop**: một truy vấn chỉ kéo được một Điều; Điều 9 (phân loại tội phạm) gần như không bao giờ được lấy vì
   câu hỏi không nhắc tới nó. Cần query decomposition / HyDE.
3. **q19 hỏng hoàn toàn**: câu đời thường dài ("đuổi việc trái luật") kéo về BLHS/TTDS.
4. **Generation quá thận trọng**: có gold trong context vẫn từ chối khi phải suy luận (q17, q20).

## Chưa làm

- Rerank Jev: `TYPESAFE_API_KEY` trong `.env` không hợp lệ (chứa ký tự không in được/khoảng trắng) → chưa đo.
- Chấm đúng/sai câu trả lời và citation mới xem nhanh, chưa điền cột `correct`/`citation_ok` trong `answers.csv`.
- 20 câu là mẫu nhỏ: chênh lệch 1 câu = 0.05 Recall.
