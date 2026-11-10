# W02 · Bộ 2 — cấu trúc (OmniDocBench, 30 trang)

Scorer tự viết (`evals/team-4.2/runners/ocr_bench/score_struct.py`), **không phải script chính thức** → không so trực tiếp với leaderboard. Đơn vị %; `hf_leak`, `block_ned`, `text_ned`, `cjk_rate` thấp = tốt; còn lại cao = tốt. Engine chạy trên tập trang khác nhau (xem `n`).

## ALL

| engine | n | gt_tables | TEDS | TEDS_S | heading_rec | order | hf_leak | sec_page |
|---|---|---|---|---|---|---|---|---|
| tesseract | 30 | 67 | N/A | N/A | N/A | 95.6 | 29.5 | 3.74 |
| gemini | 20 | 52 | 59.2 | 63.8 | 0.0 | 93.4 | 72.4 | 8.18 |
| gemini35lite | 20 | 52 | 72.8 | 77.4 | 23.7 | 93.9 | 74.1 | 5.21 |
| mineru | 30 | 67 | 94.2 | 97.3 | 69.1 | 96.8 | 6.8 | 8.85 |

## COMMON (trang mọi engine đều chạy)

| engine | n | gt_tables | TEDS | TEDS_S | heading_rec | order | hf_leak | sec_page |
|---|---|---|---|---|---|---|---|---|
| tesseract | 20 | 52 | N/A | N/A | N/A | 94.8 | 34.5 | 3.78 |
| gemini | 20 | 52 | 59.2 | 63.8 | 0.0 | 93.4 | 72.4 | 8.18 |
| gemini35lite | 20 | 52 | 72.8 | 77.4 | 23.7 | 93.9 | 74.1 | 5.21 |
| mineru | 20 | 52 | 93.0 | 96.6 | 65.8 | 95.2 | 6.9 | 8.85 |

## academic_literature

| engine | n | gt_tables | TEDS | TEDS_S | heading_rec | order | hf_leak | sec_page |
|---|---|---|---|---|---|---|---|---|
| tesseract | 6 | 13 | N/A | N/A | N/A | 95.8 | 93.3 | 3.12 |
| gemini | 4 | 9 | 58.2 | 72.2 |  | 82.6 | 84.6 | 8.88 |
| gemini35lite | 4 | 9 | 85.8 | 98.1 |  | 89.1 | 92.3 | 11.46 |
| mineru | 6 | 13 | 92.7 | 99.1 |  | 95.5 | 0.0 | 8.85 |

## book

| engine | n | gt_tables | TEDS | TEDS_S | heading_rec | order | hf_leak | sec_page |
|---|---|---|---|---|---|---|---|---|
| tesseract | 8 | 17 | N/A | N/A | N/A | 97.4 | 37.5 | 3.12 |
| gemini | 5 | 11 | 94.7 | 96.3 | 0.0 | 100.0 | 90.0 | 7.14 |
| gemini35lite | 5 | 11 | 92.4 | 94.6 | 0.0 | 97.4 | 100.0 | 4.43 |
| mineru | 8 | 17 | 97.4 | 98.0 | 100.0 | 96.1 | 6.2 | 8.85 |

## exam_paper

| engine | n | gt_tables | TEDS | TEDS_S | heading_rec | order | hf_leak | sec_page |
|---|---|---|---|---|---|---|---|---|
| tesseract | 3 | 12 | N/A | N/A | N/A |  | 0.0 | 3.82 |
| gemini | 3 | 12 | 61.9 | 64.9 | 0.0 | 98.0 | 16.7 | 6.21 |
| gemini35lite | 3 | 12 | 58.3 | 59.0 | 0.0 | 99.0 | 16.7 | 3.51 |
| mineru | 3 | 12 | 91.9 | 96.3 | 50.0 | 98.1 | 0.0 | 8.85 |

## magazine

| engine | n | gt_tables | TEDS | TEDS_S | heading_rec | order | hf_leak | sec_page |
|---|---|---|---|---|---|---|---|---|
| tesseract | 3 | 9 | N/A | N/A | N/A | 68.8 | 30.0 | 3.74 |
| gemini | 3 | 9 | 43.8 | 44.4 | 0.0 | 96.6 | 50.0 | 13.41 |
| gemini35lite | 3 | 9 | 70.1 | 76.8 | 66.7 | 100.0 | 40.0 | 16.17 |
| mineru | 3 | 9 | 86.9 | 91.6 | 66.7 | 62.1 | 10.0 | 8.85 |

## research_report

| engine | n | gt_tables | TEDS | TEDS_S | heading_rec | order | hf_leak | sec_page |
|---|---|---|---|---|---|---|---|---|
| tesseract | 10 | 16 | N/A | N/A | N/A | 100.0 | 7.3 | 6.0 |
| gemini | 5 | 11 | 34.0 | 39.1 | 0.0 | 91.5 | 84.2 | 9.43 |
| gemini35lite | 5 | 11 | 60.8 | 63.6 | 29.2 | 92.0 | 84.2 | 5.74 |
| mineru | 10 | 16 | 98.0 | 99.0 | 67.9 | 98.3 | 9.8 | 8.85 |
