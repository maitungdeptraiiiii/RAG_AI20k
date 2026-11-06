# Query decomposition — benchmark chính 64 câu

Chỉ chạy cấu hình mới; không chạy lại baseline, không dùng BM25.
Metric giữ nguyên cách chấm chunk đại diện của benchmark chính; thời gian có ảnh hưởng cache.
Đây là đánh giá retrieval, chưa đánh giá chất lượng câu trả lời cuối.

## Toàn bộ

| config | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|
| decomposition+hyde+jev | 64 | 0.930 | 0.969 | 0.873 | 0.969 |

## Theo loại câu hỏi

| config | type | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|---|
| decomposition+hyde+jev | multi | 27 | 0.907 | 1.000 | 0.840 | 0.963 |
| decomposition+hyde+jev | paraphrase | 37 | 0.946 | 0.946 | 0.897 | 0.973 |
