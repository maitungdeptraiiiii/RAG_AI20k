# Query decomposition — benchmark chính 64 câu

Chỉ chạy cấu hình mới; không chạy lại baseline, không dùng BM25.
Metric giữ nguyên cách chấm chunk đại diện của benchmark chính; thời gian có ảnh hưởng cache.
Đây là đánh giá retrieval, chưa đánh giá chất lượng câu trả lời cuối.

## Toàn bộ

| config | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|
| decomposition+hyde+jev | 64 | 0.852 | 0.938 | 0.803 | 0.938 |

## Theo loại câu hỏi

| config | type | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|---|
| decomposition+hyde+jev | multi | 27 | 0.759 | 0.963 | 0.699 | 0.926 |
| decomposition+hyde+jev | paraphrase | 37 | 0.919 | 0.919 | 0.878 | 0.946 |
