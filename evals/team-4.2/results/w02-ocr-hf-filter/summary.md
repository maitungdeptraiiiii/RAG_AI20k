# W02-02c — Bộ lọc header/footer trên output OCR đã cache

Không gọi API. `hf_leak` = % header/footer/số trang GT còn lọt (thấp = tốt). `block_ned` = sai lệch text nội dung (thấp = tốt; tăng = bộ lọc xoá nhầm nội dung). Chỉ tầng 1 (mẫu theo trang) vì ảnh benchmark là trang rời.

| Suite / engine | Trang | Dòng bị bỏ | hf_leak trước → sau | block_ned trước → sau |
|---|---:|---:|---|---|
| cross/tesseract | 80 | 19 | 45.4 → 38.0 | 41.2 → 41.3 |
| cross/gemini | 20 | 13 | 90.9 → 59.1 | 20.2 → 20.2 |
| cross/gemini35lite | 20 | 15 | 95.5 → 63.6 | 10.1 → 10.1 |
| cross/mineru | 80 | 2 | 18.5 → 16.7 | 13.4 → 13.4 |
| struct/tesseract | 30 | 13 | 29.5 → 21.6 | — |
| struct/gemini | 20 | 15 | 72.4 → 58.6 | — |
| struct/gemini35lite | 20 | 15 | 74.1 → 58.6 | — |
| struct/mineru | 30 | 0 | 6.8 → 6.8 | — |

Các dòng bị bỏ: `removed_lines.jsonl` (đọc tay để kiểm tra xoá nhầm).

Chạy lại: `.venv/Scripts/python -I evals/team-4.2/runners/ocr_bench/eval_hf_filter.py`
