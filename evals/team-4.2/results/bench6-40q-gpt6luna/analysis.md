# Phân tích — benchmark 6 Bộ luật, 40 câu (baseline hybrid, gpt-6-luna)

Dataset: `evals/team-4.2/datasets/benchmark_6_bo_luat.jsonl` — 16 lookup, 16 paraphrase, 8 multi (1/5 là câu khó).
Sinh lại bằng `evals/team-4.2/runners/build_benchmark_6_bo_luat.py`. Gold = section của Điều.
Cấu hình: text-embedding-3-small, BM25 (pyvi), RRF k=60, không rerank, LLM `gpt-6-luna` (temperature mặc định).

## Retrieval (hybrid)

| type | n | Recall@5 | Hit@5 | MRR@5 | Recall@20 |
|---|---|---|---|---|---|
| lookup | 16 | 1.000 | 1.000 | 0.969 | 1.000 |
| paraphrase | 16 | 0.375 | 0.375 | 0.344 | 0.750 |
| multi | 8 | 0.417 | 0.750 | 0.667 | 0.417 |
| **tổng** | 40 | 0.633 | 0.700 | 0.658 | 0.783 |

## Câu trả lời

- Từ chối 11/40 câu trong phạm vi (27,5%). 9 câu do context không có gold (retrieval trượt) → từ chối là đúng hành vi;
  2 câu (q20, q38) context có một phần gold nhưng thiếu Điều 9 (phân loại tội phạm) để nối chuỗi suy luận.
- q30 trả lời lạc đề (nói về tiền phép năm chưa nghỉ thay vì trợ cấp thôi việc) vì Điều 46 không vào top-5.
- q39 kết luận "chưa thể kết luận" vì thiếu Điều 650; q40 trả lời đúng dù thiếu Điều 4 (BLDS).

## Nhận xét

1. Paraphrase là điểm yếu lớn nhất: Recall@5 0.375 nhưng Recall@20 0.750 → gold thường ở hạng 6-20, rerank có dư địa lớn.
2. Một số paraphrase trượt cả top-20 (q16, q31, q32, q36): từ đời thường ("lừa", "mượn ô tô", "bị bác đơn") không trùng
   thuật ngữ luật ("lừa đảo chiếm đoạt", "nguồn nguy hiểm cao độ", "án phí sơ thẩm").
3. Multi: Điều nền tảng (Điều 9 BLHS, Điều 4/650 BLDS) không được nhắc trong câu hỏi nên không được lấy.

Mẫu nhỏ: 1 câu = 0.025 điểm tổng, 0.0625 điểm trong nhóm 16 câu, 0.125 điểm trong nhóm multi.
