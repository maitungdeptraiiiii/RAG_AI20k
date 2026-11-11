# Carryover tuần 1 — Team 4.2

`bench6-40q-gpt6luna_manual_review.csv` được sinh từ kết quả baseline 40 câu.
Đã có chấm sơ bộ đối chiếu với trường `reference`: 24/40 `correct=true`,
26/40 `citation_ok=true`. Đây chỉ là đánh giá câu trả lời so với answer key và
citation mức **source** của tuần 1, không phải xác nhận tư vấn pháp lý độc lập.
Mỗi hàng vẫn cần reviewer của nhóm audit lại trước khi dùng số liệu trong report.
Không suy ra hai nhãn này từ việc retrieval có gold context: đó chỉ là tín hiệu
hỗ trợ, không chứng minh câu trả lời đúng.

Tái tạo artefact:

```powershell
python evals/team-4.2/runners/prepare_w02_benchmark.py
python evals/team-4.2/runners/validate_w02_data.py
```

Runner mặc định giữ hàng đợi đã chấm; chỉ dùng `--reset-manual-review` nếu muốn
tạo lại từ `answers.csv` và chủ động bỏ toàn bộ nhãn chấm cũ.

`benchmark_doi_thuong_w02.jsonl` là dataset dẫn xuất. Nó giữ `source` +
`section` làm gold ổn định, loại `gold_chunk_ids`, chứa đúng 27 câu `multi` ở
split `test`, và thêm các câu `out_of_scope` để kiểm tra từ chối đúng phạm vi.
