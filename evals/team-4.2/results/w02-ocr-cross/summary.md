# W02 · Kiểm tra chéo — MDPBench tiếng Việt

Scorer tự viết (`evals/team-4.2/runners/ocr_bench/score_struct.py`), **không phải script chính thức** → không so trực tiếp với leaderboard. Đơn vị %; `hf_leak`, `block_ned`, `text_ned`, `cjk_rate` thấp = tốt; còn lại cao = tốt. Engine chạy trên tập trang khác nhau (xem `n`).

## ALL

| engine | n | gt_tables | TEDS | TEDS_S | heading_rec | order | hf_leak | sec_page | block_ned | text_ned | cjk_rate |
|---|---|---|---|---|---|---|---|---|---|---|---|
| tesseract | 80 | 40 | N/A | N/A | N/A | 96.6 | 45.4 | 3.11 | 41.2 | 46.2 | 0.0 |
| gemini | 20 | 14 | 61.0 | 71.7 | 0.0 | 97.2 | 90.9 | 4.86 | 20.2 | 36.3 | 0.0 |
| gemini35lite | 20 | 14 | 68.0 | 73.2 | 31.8 | 96.6 | 95.5 | 3.67 | 10.1 | 22.5 | 0.0 |
| mineru | 80 | 40 | 60.0 | 65.3 | 39.4 | 96.6 | 18.5 | 6.75 | 13.4 | 17.7 | 0.04 |

## COMMON (trang mọi engine đều chạy)

| engine | n | gt_tables | TEDS | TEDS_S | heading_rec | order | hf_leak | sec_page | block_ned | text_ned | cjk_rate |
|---|---|---|---|---|---|---|---|---|---|---|---|
| tesseract | 20 | 14 | N/A | N/A | N/A | 97.6 | 45.5 | 3.61 | 43.5 | 48.4 | 0.0 |
| gemini | 20 | 14 | 61.0 | 71.7 | 0.0 | 97.2 | 90.9 | 4.86 | 20.2 | 36.3 | 0.0 |
| gemini35lite | 20 | 14 | 68.0 | 73.2 | 31.8 | 96.6 | 95.5 | 3.67 | 10.1 | 22.5 | 0.0 |
| mineru | 20 | 14 | 39.7 | 43.3 | 47.7 | 99.0 | 4.5 | 6.75 | 20.4 | 23.0 | 0.02 |

## digital

| engine | n | gt_tables | TEDS | TEDS_S | heading_rec | order | hf_leak | sec_page | block_ned | text_ned | cjk_rate |
|---|---|---|---|---|---|---|---|---|---|---|---|
| tesseract | 40 | 20 | N/A | N/A | N/A | 97.5 | 85.2 | 2.58 | 19.0 | 29.7 | 0.0 |
| gemini | 10 | 7 | 83.1 | 97.3 | 0.0 | 99.2 | 100.0 | 4.48 | 20.6 | 25.4 | 0.0 |
| gemini35lite | 10 | 7 | 70.5 | 71.4 | 31.8 | 97.4 | 100.0 | 3.96 | 10.0 | 23.5 | 0.0 |
| mineru | 40 | 20 | 68.1 | 71.2 | 60.0 | 98.8 | 5.6 | 6.75 | 6.4 | 10.1 | 0.07 |

## photo

| engine | n | gt_tables | TEDS | TEDS_S | heading_rec | order | hf_leak | sec_page | block_ned | text_ned | cjk_rate |
|---|---|---|---|---|---|---|---|---|---|---|---|
| tesseract | 40 | 20 | N/A | N/A | N/A | 90.3 | 5.6 | 3.76 | 63.5 | 63.6 | 0.0 |
| gemini | 10 | 7 | 38.8 | 46.2 | 0.0 | 95.1 | 81.8 | 5.02 | 19.8 | 46.3 | 0.0 |
| gemini35lite | 10 | 7 | 65.6 | 74.9 | 31.8 | 95.7 | 90.9 | 3.44 | 10.1 | 21.4 | 0.0 |
| mineru | 40 | 20 | 51.8 | 59.4 | 18.9 | 93.3 | 31.5 | 6.75 | 20.4 | 25.3 | 0.02 |
