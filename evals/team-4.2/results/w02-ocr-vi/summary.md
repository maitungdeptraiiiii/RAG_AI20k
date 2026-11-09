# W02 · Bộ 1 — OCR tiếng Việt (nrl-ai/vn-ocr-documents-eval)

Tạo bởi `evals/team-4.2/runners/ocr_bench/score_vi.py`. Đơn vị %, trừ `n`, `num_plausible_err` (số lần), `khong_bad` (mất/sai / tổng), `sec_page` (trung vị giây/trang).

## ALL

| engine | n | CER | WER | CER_card | dia_missing | dia_wrong | base_err | num_acc | num_plausible_err | dieu_acc | khong_bad | sec_page |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tesseract | 159 | 5.79 | 7.23 | 5.83 | 0.03 | 0.77 | 0.4 | 96.83 | 7 | 97.87 | 1/97 | 1.22 |
| gemini | 159 | 3.95 | 4.74 | 4.04 | 0.05 | 0.37 | 0.23 | 98.88 | 5 | 100.0 | 1/97 | 3.33 |
| gemini35lite | 159 | 3.88 | 4.34 | 4.02 | 0.03 | 0.19 | 0.25 | 98.88 | 2 | 100.0 | 1/97 | 2.54 |
| mineru | 159 | 7.09 | 11.06 | 7.16 | 0.59 | 4.05 | 0.45 | 97.36 | 6 | 92.55 | 1/97 | 3.8 |

## real

| engine | n | CER | WER | CER_card | dia_missing | dia_wrong | base_err | num_acc | num_plausible_err | dieu_acc | khong_bad | sec_page |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tesseract | 9 | 11.88 | 18.19 | 12.08 | 0.17 | 4.55 | 1.81 | 85.97 | 7 | 92.31 | 1/4 | 1.63 |
| gemini | 9 | 8.02 | 9.37 | 8.25 | 0.2 | 0.75 | 1.38 | 94.6 | 3 | 100.0 | 1/4 | 5.42 |
| gemini35lite | 9 | 8.14 | 9.37 | 8.37 | 0.2 | 0.75 | 1.49 | 94.24 | 1 | 100.0 | 1/4 | 3.52 |
| mineru | 9 | 12.12 | 16.06 | 12.25 | 0.54 | 2.28 | 1.84 | 92.09 | 1 | 96.15 | 1/4 | 3.8 |

## contract

| engine | n | CER | WER | CER_card | dia_missing | dia_wrong | base_err | num_acc | num_plausible_err | dieu_acc | khong_bad | sec_page |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tesseract | 20 | 1.99 | 2.58 | 1.99 | 0.0 | 0.12 | 0.03 | 100.0 | 0 | 100.0 | 0/9 | 1.28 |
| gemini | 20 | 1.56 | 2.37 | 1.57 | 0.02 | 0.12 | 0.0 | 99.77 | 1 | 100.0 | 0/9 | 4.08 |
| gemini35lite | 20 | 1.37 | 1.51 | 1.39 | 0.0 | 0.0 | 0.0 | 100.0 | 0 | 100.0 | 0/9 | 2.67 |
| mineru | 20 | 5.58 | 7.75 | 5.67 | 0.64 | 3.02 | 0.28 | 98.84 | 2 | 91.18 | 0/9 | 3.8 |

## conversational

| engine | n | CER | WER | CER_card | dia_missing | dia_wrong | base_err | num_acc | num_plausible_err | dieu_acc | khong_bad | sec_page |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tesseract | 24 | 6.97 | 7.91 | 6.97 | 0.0 | 0.06 | 0.01 | 100.0 | 0 |  | 0/43 | 1.07 |
| gemini | 24 | 6.81 | 8.31 | 6.81 | 0.0 | 1.02 | 0.01 | 100.0 | 0 |  | 0/43 | 2.8 |
| gemini35lite | 24 | 6.25 | 7.1 | 6.25 | 0.0 | 0.18 | 0.0 | 100.0 | 0 |  | 0/43 | 2.17 |
| mineru | 24 | 10.32 | 16.34 | 10.32 | 0.96 | 7.14 | 0.09 | 100.0 | 0 |  | 0/43 | 3.8 |

## form

| engine | n | CER | WER | CER_card | dia_missing | dia_wrong | base_err | num_acc | num_plausible_err | dieu_acc | khong_bad | sec_page |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tesseract | 20 | 2.66 | 3.46 | 2.66 | 0.0 | 0.14 | 0.02 | 98.56 | 0 |  | 0/0 | 1.29 |
| gemini | 20 | 1.96 | 2.26 | 1.97 | 0.09 | 0.07 | 0.0 | 99.64 | 1 |  | 0/0 | 3.89 |
| gemini35lite | 20 | 1.98 | 2.37 | 2.03 | 0.05 | 0.17 | 0.0 | 99.64 | 1 |  | 0/0 | 2.66 |
| mineru | 20 | 6.28 | 11.18 | 6.28 | 1.04 | 3.61 | 0.07 | 98.92 | 2 |  | 0/0 | 3.8 |

## formal

| engine | n | CER | WER | CER_card | dia_missing | dia_wrong | base_err | num_acc | num_plausible_err | dieu_acc | khong_bad | sec_page |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tesseract | 24 | 14.28 | 14.75 | 14.28 | 0.0 | 0.47 | 1.45 | 95.45 | 0 |  | 0/20 | 1.12 |
| gemini | 24 | 7.62 | 8.03 | 7.62 | 0.0 | 0.1 | 0.0 | 100.0 | 0 |  | 0/20 | 3.0 |
| gemini35lite | 24 | 7.58 | 7.92 | 7.58 | 0.0 | 0.1 | 0.0 | 100.0 | 0 |  | 0/20 | 2.25 |
| mineru | 24 | 8.29 | 10.9 | 8.29 | 0.0 | 2.6 | 0.07 | 77.27 | 0 |  | 0/20 | 3.8 |

## literary

| engine | n | CER | WER | CER_card | dia_missing | dia_wrong | base_err | num_acc | num_plausible_err | dieu_acc | khong_bad | sec_page |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tesseract | 14 | 7.29 | 7.58 | 7.29 | 0.07 | 0.36 | 0.26 | 100.0 | 0 |  | 0/16 | 1.18 |
| gemini | 14 | 6.5 | 7.8 | 6.5 | 0.14 | 2.06 | 0.02 | 100.0 | 0 |  | 0/16 | 3.05 |
| gemini35lite | 14 | 6.1 | 6.44 | 6.1 | 0.0 | 0.5 | 0.02 | 100.0 | 0 |  | 0/16 | 2.23 |
| mineru | 14 | 9.34 | 19.96 | 9.34 | 0.85 | 12.86 | 0.28 | 100.0 | 0 |  | 0/16 | 3.8 |

## news_business

| engine | n | CER | WER | CER_card | dia_missing | dia_wrong | base_err | num_acc | num_plausible_err | dieu_acc | khong_bad | sec_page |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tesseract | 24 | 6.33 | 7.01 | 6.4 | 0.0 | 0.27 | 0.29 | 100.0 | 0 |  | 0/4 | 1.19 |
| gemini | 24 | 3.5 | 3.44 | 3.53 | 0.0 | 0.16 | 0.3 | 100.0 | 0 |  | 0/4 | 3.05 |
| gemini35lite | 24 | 3.61 | 3.49 | 3.64 | 0.0 | 0.11 | 0.3 | 100.0 | 0 |  | 0/4 | 2.42 |
| mineru | 24 | 2.89 | 5.86 | 2.94 | 0.22 | 3.57 | 0.27 | 99.07 | 0 |  | 0/4 | 3.8 |

## receipt

| engine | n | CER | WER | CER_card | dia_missing | dia_wrong | base_err | num_acc | num_plausible_err | dieu_acc | khong_bad | sec_page |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tesseract | 21 | 5.3 | 5.8 | 5.3 | 0.0 | 0.44 | 0.01 | 98.77 | 0 |  | 0/0 | 1.43 |
| gemini | 21 | 3.17 | 4.37 | 3.6 | 0.0 | 0.04 | 0.0 | 100.0 | 0 |  | 0/0 | 3.78 |
| gemini35lite | 21 | 3.1 | 3.66 | 3.74 | 0.0 | 0.0 | 0.0 | 100.0 | 0 |  | 0/0 | 3.33 |
| mineru | 21 | 8.28 | 12.17 | 8.49 | 0.48 | 3.88 | 0.66 | 98.77 | 1 |  | 0/0 | 3.8 |

## synthetic (all)

| engine | n | CER | WER | CER_card | dia_missing | dia_wrong | base_err | num_acc | num_plausible_err | dieu_acc | khong_bad | sec_page |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tesseract | 150 | 4.9 | 5.6 | 4.91 | 0.0 | 0.24 | 0.19 | 99.27 | 0 | 100.0 | 0/93 | 1.21 |
| gemini | 150 | 3.36 | 4.05 | 3.42 | 0.03 | 0.31 | 0.07 | 99.84 | 2 | 100.0 | 0/93 | 3.29 |
| gemini35lite | 150 | 3.25 | 3.59 | 3.38 | 0.01 | 0.12 | 0.06 | 99.92 | 1 | 100.0 | 0/93 | 2.51 |
| mineru | 150 | 6.35 | 10.32 | 6.41 | 0.6 | 4.3 | 0.25 | 98.55 | 5 | 91.18 | 0/93 | 3.8 |

## synthetic_scan

| engine | n | CER | WER | CER_card | dia_missing | dia_wrong | base_err | num_acc | num_plausible_err | dieu_acc | khong_bad | sec_page |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tesseract | 3 | 0.08 | 0.37 | 0.08 | 0.0 | 0.45 | 0.0 | 100.0 | 0 |  | 0/1 | 1.8 |
| gemini | 3 | 1.85 | 2.62 | 1.85 | 0.0 | 0.23 | 0.52 | 100.0 | 0 |  | 0/1 | 4.11 |
| gemini35lite | 3 | 1.85 | 2.62 | 2.93 | 0.0 | 0.23 | 0.56 | 100.0 | 0 |  | 0/1 | 3.25 |
| mineru | 3 | 2.97 | 5.99 | 2.97 | 0.23 | 3.6 | 0.24 | 100.0 | 0 |  | 0/1 | 3.8 |
