# Query decomposition — benchmark chính 64 câu

So sánh cặp trên cùng index, model và cache; không dùng BM25.
Metric giữ nguyên cách chấm chunk đại diện của benchmark chính; thời gian có ảnh hưởng cache.
Đây là đánh giá retrieval, chưa đánh giá chất lượng câu trả lời cuối.

## Toàn bộ

| config | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|
| hyde+jev | 64 | 0.836 | 0.938 | 0.800 | 0.914 |
| decomposition+hyde+jev | 64 | 0.839 | 0.922 | 0.775 | 0.924 |

## Theo loại câu hỏi

| config | type | n | recall@5 | hit@5 | mrr@5 | recall@20 |
|---|---|---|---|---|---|---|
| decomposition+hyde+jev | multi | 27 | 0.728 | 0.926 | 0.634 | 0.895 |
| decomposition+hyde+jev | paraphrase | 37 | 0.919 | 0.919 | 0.878 | 0.946 |
| hyde+jev | multi | 27 | 0.722 | 0.963 | 0.693 | 0.870 |
| hyde+jev | paraphrase | 37 | 0.919 | 0.919 | 0.878 | 0.946 |
