# W02 · Chấm bằng script chính thức — MDPBench-VI + OmniDocBench

Tạo bởi `evals/team-4.2/runners/ocr_bench/official_eval.py`. Script chấm: `MultimodalOCR/MDPBench` @6ddb0a5 (`pdf_validation.py` + `tools/calculate_scores.py`), `OmniDocBench` @0604d98 v1.6.0 (`pdf_validation.py`). Đơn vị %.

**Khác leaderboard (đọc trước khi so):** CDM công thức **tắt** (cần LaTeX trên Linux) · không chạy đủ tập (xem `n`) · output là của lần chạy engine ngày 2026-11-07 (Gemini 3.5 Flash-Lite: 2026-11-08), không chạy lại engine.

## MDPBench — tiếng Việt

Điểm trang = trung bình các phần có mặt: (1 − text edit) và TEDS bảng (công thức bị bỏ vì không có CDM). `VI` = trung bình theo trang trên các trang đã chạy. Leaderboard chấm 40 trang gốc + 120 ảnh chụp, nên có thêm cột `VI (trọng số 1:3)` = 0.25·digital + 0.75·photo cho gần với cách leaderboard cân trọng số.

| engine | n | **VI** | VI (trọng số 1:3) | digital | photo | text edit ↓ (dig / photo) | TEDS bảng (dig / photo) | order edit ↓ |
|---|---|---|---|---|---|---|---|---|
| Tesseract | 80 | **48.0** | 38.1 | 68.0 | 28.1 | 42.9 (20.6 / 68.1) | 1.6 (0.2 / 3.0) | 32.9 |
| Gemini 2.5 Flash | 20 | **80.4** | 77.8 | 85.4 | 75.3 | 18.6 (14.9 / 23.9) | 72.4 (96.8 / 48.1) | 21.7 |
| Gemini 3.5 Flash-Lite | 20 | **91.2** | 91.5 | 90.8 | 91.7 | 7.5 (8.5 / 6.1) | 68.5 (70.1 / 66.9) | 15.4 |
| MinerU 4.1.7 | 80 | **77.6** | 71.8 | 89.3 | 66.0 | 19.2 (6.5 / 33.5) | 60.3 (65.3 / 55.4) | 22.0 |
| Tesseract (20 trang chung) | 20 | **50.1** | 39.4 | 71.4 | 28.7 | 39.7 (18.4 / 67.5) | 3.1 (0.0 / 6.3) | 29.1 |
| MinerU 4.1.7 (20 trang chung) | 20 | **68.7** | 58.3 | 89.4 | 47.9 | 24.8 (6.6 / 50.2) | 44.4 (62.4 / 26.3) | 24.6 |

Leaderboard công khai, cột VI (160 trang public, có CDM): Gemini-3-pro-preview 85.9 · MinerU-2.5-Pro-1.2B 74.2 · PaddleOCR-VL-1.6 80.9 · PP-StructureV3 52.7 · MinerU-2.5-VLM 46.0 · MinerU-2.5-pipeline 27.6. Không có Gemini 2.5 Flash, Gemini 3.5 Flash-Lite, Tesseract hay MinerU 4.x trên leaderboard.

## OmniDocBench — cấu trúc (EN/ZH)

Không tính được Overall chính thức (= ((1 − text edit)·100 + TEDS + CDM) / 3) vì thiếu CDM. Cột cuối là (text + TEDS)/2, **không** so được với Overall leaderboard.

| engine | n | text edit ↓ | TEDS | TEDS-S | order edit ↓ | formula edit ↓ | (text+TEDS)/2 |
|---|---|---|---|---|---|---|---|
| Tesseract | 30 | 31.0 | 0.3 | 0.6 | 51.6 | 100.0 | 34.7 |
| Gemini 2.5 Flash | 20 | 11.4 | 63.1 | 65.7 | 31.3 | 8.3 | 75.9 |
| Gemini 3.5 Flash-Lite | 20 | 5.2 | 71.5 | 74.8 | 29.9 | 2.8 | 83.2 |
| MinerU 4.1.7 | 30 | 2.8 | 92.3 | 94.3 | 27.4 | 2.8 | 94.8 |
| Tesseract (20 trang chung) | 20 | 32.9 | 0.4 | 0.7 | 56.8 | 100.0 | 33.7 |
| MinerU 4.1.7 (20 trang chung) | 20 | 3.9 | 91.1 | 93.5 | 28.8 | 2.8 | 93.6 |

Leaderboard end-to-end (toàn bộ 1.355 trang; text/order edit đổi sang %):

| model | Overall | text edit ↓ | TEDS | TEDS-S | order edit ↓ |
|---|---|---|---|---|---|
| MinerU2.5-Pro | 95.75 | 3.6 | 93.42 | 95.92 | 12.0 |
| MinerU-2.5 | 93.04 | 4.5 | 87.88 | 91.47 | 13.0 |
| Gemini 3 Flash | 92.62 | 6.6 | 89.29 | 93.51 | 17.2 |
| Gemini 3 Pro | 92.91 | 6.4 | 89.15 | 92.96 | 16.5 |
| MinerU-Pipeline | 86.47 | 5.5 | 81.88 | 88.68 | 15.3 |
