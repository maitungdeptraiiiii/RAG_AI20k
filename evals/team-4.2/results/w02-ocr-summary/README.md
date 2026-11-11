# W02-02c B4 — Tổng hợp benchmark OCR (3 engine)

Chạy 2026-11-07 → 08 · RTX 3060 Laptop 6 GB, 16 CPU · Windows 11.
Chi tiết: [`w02-ocr-vi`](../w02-ocr-vi/summary.md) · [`w02-ocr-struct`](../w02-ocr-struct/summary.md) · [`w02-ocr-cross`](../w02-ocr-cross/summary.md) · [script chấm chính thức](../w02-ocr-official/summary.md) · [chạy thử chọn engine](../w02-ocr-engine-trial/README.md)

| Engine | Phiên bản / cấu hình |
|---|---|
| **Tesseract** | 5.5 `vie` (Bộ 2: `eng+chi_sim`), grayscale + xoay theo OSD, `--psm 3`, 1 lần TSV |
| **Gemini** | `google/gemini-2.5-flash` qua OpenRouter, `temperature=0`, thinking tắt (0 reasoning token), ảnh resize cạnh dài 1600 px, prompt `v1` (trong `run_engine.py`) |
| **MinerU** | 4.1.7, `mineru-kit parse --tier standard` chạy **cục bộ** (VLM llama.cpp + OCR ONNX/DirectML), không dùng `--remote` |

PP-StructureV3 (PaddleOCR 3.7) đã chạy thử và bị loại: model `latin_PP-OCRv5_mobile_rec` làm mất dấu tiếng Việt nặng.

## Bảng so sánh

| | Tesseract | Gemini 2.5 Flash | MinerU |
|---|---|---|---|
| **Bộ 1 — OCR tiếng Việt** (nrl-ai, 159 trang) | | | |
| CER toàn bộ | 5.79 % | **3.95 %** | 7.09 % |
| CER 9 trang scan thật (`real`) | 11.88 % | **8.02 %** | 12.12 % |
| CER synthetic (150 trang) | 4.90 % | **3.36 %** | 6.35 % |
| Lỗi dấu: mất / sai (trên ký tự có dấu) | 0.03 / 0.77 % | 0.05 / **0.37 %** | 0.59 / 4.05 % |
| Số/ngày đúng tại vị trí (`real`) | 85.97 % | **94.60 %** | 92.09 % |
| Lỗi số "trông hợp lệ" (toàn bộ) | 7 | **5** | 6 |
| "Điều/Khoản N" đúng | 97.87 % | **100 %** | 92.55 % ¹ |
| **Bộ 2 — cấu trúc** (OmniDocBench, 20 trang chung) | | | |
| TEDS / TEDS-S (52 bảng) | N/A | 59.2 / 63.8 % | **93.0 / 96.6 %** |
| Heading nhận đúng | N/A | 0 % ² | **65.8 %** |
| Thứ tự đọc | 94.8 % | 93.4 % | **95.2 %** |
| Rò rỉ header/footer (thấp = tốt) | 34.5 % | 72.4 % ² | **6.9 %** |
| **Kiểm tra chéo MDPBench-VI** (20 trang chung = 10 gốc + 10 ảnh chụp) | | | |
| Lỗi chữ theo block, digital (bỏ trang RECITATION, 9 trang) | 26.6 % | 10.7 % | **9.6 %** |
| Lỗi chữ theo block, ảnh chụp (9 trang) | 66.9 % | **9.7 %** | 37.3 % |
| TEDS bảng (14 bảng) | N/A | **61.0 %** | 39.7 % |
| Nhận nhầm sang chữ Trung (`cjk_rate`) | 0 % | 0 % | 0.02 % |
| MinerU trên toàn bộ 80 trang: block_ned digital / photo | | | 6.4 % / 20.4 % |
| **Script chấm chính thức** ([`w02-ocr-official`](../w02-ocr-official/summary.md), CDM tắt) | | | |
| MDPBench VI, 20 trang chung (digital / photo) | 50.1 (71.4 / 28.7) | **80.4** (85.4 / **75.3**) | 68.7 (**89.4** / 47.9) |
| MDPBench VI, đủ 80 trang local | 48.0 | — | 77.6 (89.3 / 66.0) |
| ↳ leaderboard cột VI (160 trang, có CDM) | — | (Gemini-3-pro 85.9) | (MinerU-2.5-Pro 74.2) |
| OmniDocBench 20 trang chung: text edit ↓ / TEDS | 32.9 / 0.4 | 11.4 / 63.1 | **3.9 / 91.1** |
| ↳ leaderboard (1.355 trang) | — | (Gemini 3 Flash 6.6 / 89.3) | (MinerU2.5-Pro 3.6 / 93.4) |
| **Vận hành** | | | |
| Giây/trang (trung vị) | **1.2–3.7** | 3.3–8.2 | 3.8–8.9 ³ |
| VRAM | 0 (CPU) | 0 (API) | chưa đo riêng ⁴ |
| Chi phí | 0 | **0.247 USD / 199 trang** (trung vị 0.0008 USD/trang) | 0 |
| Dữ liệu rời máy | không | **có** (ảnh gửi qua OpenRouter → Google) | không |

¹ Một phần do scorer: MinerU chép thêm tiêu đề trang `Tuyên ngôn QTNQ — Đoàn N` (GT không có) nên căn chỉnh ghép nhầm số đầu trang (5 token, nhóm `formal`).
² Prompt `v1` có yêu cầu `#` cho tiêu đề và `<table>` cho bảng, nhưng Gemini gần như không dùng heading, và chép bảng dày/không viền thành text thường (4/20 trang mất hết bảng). Gemini còn chép cả header/footer vì prompt bảo "chép toàn bộ". Đây là lỗi tuân thủ định dạng, không phải lỗi đọc chữ.
³ Đã gồm thời gian load model chia đều (~140 s/lần chạy).
⁴ GPU 6 GB chạy được tier `standard`; chưa log đỉnh VRAM.

## Failure case (→ W02-05)

1. **Gemini RECITATION**: `vi_textbook_38` (sách giáo khoa) bị Gemini dừng vì `native_finish_reason=RECITATION` (cả trang gốc lẫn ảnh chụp). Chỉ trả về ~1/3 trang, block_ned 0.76. Runner đã gắn cờ `truncated_or_recitation` → trang kiểu này cần fallback sang engine local.
2. **MinerU sai dấu "trông hợp lệ"**: các cặp nhầm hay gặp nhất là `ế→ể` (35), `đ→d` (33), `ề→ê/ế/ể`, `ư→u`, `ơ→o`. Ví dụ `Tuyên bố` → `Tuyên bổ`. Ra từ có nghĩa nên khó phát hiện tự động.
3. **Tesseract sai số trên scan thật**: `Số: 115/NQ-CP` → `445`, `64/2025/QH15` → `64/2023`, `năm 2026` → `2096`. Đây là lỗi số có nghĩa, đúng loại nguy hiểm nhất.
4. **Gemini mất bảng**: bảng tài chính dày (OmniDocBench research_report, magazine) bị chép thành chuỗi dòng text → mất cấu trúc hàng/cột.

## Lỗi GT phát hiện được

Có 2 chỗ cả 3 engine đọc giống nhau nhưng khác GT của nrl-ai. Mình đã kiểm tra bằng mắt trên ảnh gốc: **GT sai, engine đúng**. Hai chỗ này được sửa qua `runners/ocr_bench/gt_fixes_vi.json` (có bằng chứng từng dòng), scorer áp dụng trước khi chấm:
- `real_tt_37_bca_vehicle`: GT `NGÀY 31 THÁNG 3` → ảnh `NGÀY 30 THÁNG 6`
- `real_qd_707_ttg`: GT `ngày 11 tháng 11 năm 2019` → ảnh `ngày 01 tháng 11 năm 2019`

Sanity check theo plan: Tesseract trên 9 trang `real`, chuẩn hoá giống card (NFC + gộp khoảng trắng), cho CER **12.1 %**, card công bố 12.62 % → khớp.

## Hạn chế — đọc trước khi trích số

- **Đã chấm lại bằng script chính thức** (OmniDocBench @0604d98, MDPBench @6ddb0a5) → [`w02-ocr-official`](../w02-ocr-official/summary.md). Số chính thức xác nhận cùng thứ hạng với scorer tự viết. Vẫn còn 3 điểm khác leaderboard: (1) **CDM tắt** (cần LaTeX/ImageMagick trên Linux) nên không có Overall OmniDocBench chính thức, và điểm MDPBench bỏ phần công thức; (2) **tập con**: MDPBench 40 gốc + 40 ảnh chụp (leaderboard 40 + 120, nên cột "trọng số 1:3" gần leaderboard hơn), OmniDocBench 20–30/1.355 trang; (3) engine của mình (Gemini 2.5 Flash, MinerU 4.1.7, Tesseract) **không có trên leaderboard**, nên dòng leaderboard chỉ là mốc tham chiếu, không phải so cùng model.
- Scorer tự viết (`w02-ocr-struct`, `w02-ocr-cross`) vẫn giữ cho các metric script chính thức không có: heading, rò header/footer, `block_ned`, `cjk_rate`. `block_ned` căn từng block GT vào output: không phạt việc đổi thứ tự đọc, cũng không phạt chữ thừa.
- Cỡ mẫu nhỏ: Bộ 2 có 20–30 trang, phần chung với Gemini ở MDPBench chỉ 20 trang (10 + 10) → chỉ để định hướng.
- Gemini chạy tập con theo ngân sách plan (Bộ 2: 20/30 trang, MDPBench: 20/80). Engine local chạy 40 trang gốc + 40 ảnh chụp (1 ảnh chụp/trang gốc), không phải đủ 120 ảnh chụp.
- **Chưa làm** lớp trang luật tự tạo (12–15 trang, trang bẫy, CEM, Page Pass Rate) và phần niits (repo không có ảnh) — cần người làm.
- Gemini chỉ chạy prompt `v1`, chưa tối ưu prompt cho bảng/heading.

## Gợi ý chọn engine mặc định (nhóm chốt)

- **Đọc đúng chữ tiếng Việt** (văn bản luật, số/ngày): Gemini tốt nhất trên mọi nhóm của Bộ 1, kể cả scan thật. Nhưng ảnh bị gửi ra ngoài (chỉ dùng cho tài liệu public/giả), có rủi ro RECITATION, và cấu trúc bảng kém với prompt v1.
- **Cấu trúc (bảng, heading, bỏ header/footer)**: MinerU vượt trội trên OmniDocBench EN/ZH (TEDS chính thức 91 % so với 63 %), chạy cục bộ, miễn phí. Nhưng trên **trang tiếng Việt** (MDPBench) lợi thế này không còn: TEDS bảng MinerU 44 % so với Gemini 72 % trên 20 trang chung, và trên ảnh chụp MinerU tụt mạnh (VI photo 47.9 so với 75.3). MinerU chỉ thắng rõ trên **trang digital** (89.4 so với 85.4). Ngoài ra MinerU sai dấu nhiều hơn rõ rệt (4 % so với 0.4 %).
- **Tesseract**: nhanh và ổn trên bản in sạch, nhưng yếu trên scan thật và ảnh chụp, không có cấu trúc.
- Hướng hợp lý cho pipeline: **MinerU làm mặc định cục bộ**, dùng **đối chiếu chéo với Gemini** (mục A5) cho trang có số/ngày/"Điều N" hoặc confidence thấp. Lệch giữa 2 engine → `needs_review`. Trang RECITATION thì fallback về MinerU.

## Chạy lại

```bash
# tải dữ liệu
.venv/Scripts/python -I evals/team-4.2/runners/ocr_bench/download.py
# engine (Gemini cache theo sha256 ảnh + model + prompt_version, có ngưỡng dừng 1.8 USD)
for s in vi struct cross; do
  .venv/Scripts/python -I evals/team-4.2/runners/ocr_bench/run_engine.py --engine tesseract --suite $s
  .venv/Scripts/python -I evals/team-4.2/runners/ocr_bench/run_engine.py --engine gemini --suite $s      # cần `openrouter=` trong app/team-4.2/.env
  data/team-4.2/ocr_bench/_envs/mineru/Scripts/python.exe -I evals/team-4.2/runners/ocr_bench/run_engine.py --engine mineru --suite $s
done
# chấm
.venv/Scripts/python -I evals/team-4.2/runners/ocr_bench/score_vi.py
.venv/Scripts/python -I evals/team-4.2/runners/ocr_bench/score_struct.py --suite struct
.venv/Scripts/python -I evals/team-4.2/runners/ocr_bench/score_struct.py --suite cross
# script chấm chính thức (cần _tools/ + _envs/officialeval, xem docstring official_eval.py)
.venv/Scripts/python -I evals/team-4.2/runners/ocr_bench/official_eval.py
```

Venv MinerU: `uv venv --python 3.12` + `torch torchvision` (cu128) + `mineru[core]`. Scorer cần thêm `rapidfuzz apted lxml` trong `.venv`.
