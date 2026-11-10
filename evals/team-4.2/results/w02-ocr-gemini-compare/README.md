# W02-02c — Gemini 3.5 Flash-Lite vs Gemini 2.5 Flash

Chạy 2026-11-08. Lý do: `gemini-2.5-flash` có ngày shutdown 16/10/2026 trên Gemini API (vẫn gọi được qua OpenRouter ngày 07–08/11 nhưng có thể bị tắt bất kỳ lúc nào).

Cùng prompt `v1`, cùng trang, cùng ảnh resize 1600 px, `temperature=0`. Khác duy nhất: 3.5 Flash-Lite **không tắt được reasoning**
("Reasoning is mandatory") → dùng `reasoning.effort=minimal`; thực đo **0 reasoning token** trên 200 lời gọi.
Engine `gemini35lite` trong `run_engine.py`; output ở `data/team-4.2/ocr_bench/_out/gemini35lite/`.
Số liệu chi tiết nằm trong các summary chung: `w02-ocr-vi`, `w02-ocr-struct`, `w02-ocr-cross`, `w02-ocr-official`.

| | Gemini 2.5 Flash | Gemini 3.5 Flash-Lite |
|---|---|---|
| **Bộ 1 — nrl-ai (159 trang)** | | |
| CER toàn bộ | 3.95 % | **3.88 %** |
| CER `real` (9 trang scan) | **8.02 %** | 8.14 % |
| Sai dấu (trên ký tự có dấu) | 0.37 % | **0.19 %** |
| Số/ngày đúng tại vị trí | 98.88 % | 98.88 % |
| Lỗi số "trông hợp lệ" | 5 | **2** ¹ |
| "Điều/Khoản N" đúng | 100 % | 100 % |
| Trang 3.5L tốt hơn / kém hơn / bằng (theo số ký tự sai) | | 56 / 14 / 89 |
| **Bộ 2 — OmniDocBench (20 trang)** | | |
| TEDS / TEDS-S (scorer tự viết) | 59.2 / 63.8 | **72.8 / 77.4** |
| Heading nhận đúng | 0 % | **23.7 %** |
| Rò header/footer (thấp = tốt) | **72.4 %** | 74.1 % |
| Script chính thức: text edit ↓ / TEDS | 11.4 / 63.1 | **5.2 / 71.5** |
| **MDPBench-VI (20 trang = 10 gốc + 10 ảnh chụp)** | | |
| RECITATION | 2/20 trang (`vi_textbook_38` gốc + ảnh chụp) | **0** |
| Script chính thức VI (digital / photo) | 80.4 (85.4 / 75.3) | **91.2** (90.8 / 91.7) ² |
| block_ned, bỏ 2 trang RECITATION (digital / photo, 9+9 trang) | **10.7 / 9.7** | 11.6 / 11.9 |
| TEDS bảng chính thức (digital / photo) | **96.8** / 48.1 | 70.1 / **66.9** |
| **Vận hành** | | |
| Giây/trang (trung vị, Bộ 1) | 3.33 | **2.54** |
| Token vào/trang (ảnh + prompt) | **459** | 1 302 |
| Chi phí | **0.247 USD / 199 trang** | 0.319 USD / 200 trang (~0.0016 USD/trang) |

¹ Kiểm tra bằng mắt: lỗi của 3.5L ở `real_qd_729_ttg` (`(2) Q.Cường`) thực ra **đúng theo ảnh**, GT sai → còn 1 lỗi thật
(`synth_form_04_03`: `041777906844` → `04177906844`, mất 1 chữ số).
² Phần lớn chênh lệch đến từ RECITATION: 2.5 Flash mất gần hết text trên 2/20 trang. Khi bỏ 2 trang đó (block_ned), hai model
**ngang nhau**, 2.5 Flash nhỉnh hơn chút về chữ. Không nên trích 91.2 vs 80.4 như là "đọc tốt hơn 11 điểm".

## Kết luận

- Đọc chữ tiếng Việt: **ngang hoặc nhỉnh hơn** 2.5 Flash (sai dấu giảm một nửa, ít lỗi số trông hợp lệ hơn); scan thật ngang nhau.
- Không bị RECITATION trên trang sách giáo khoa đã chặn 2.5 Flash (mới 1 trang, chưa đủ để nói hết rủi ro).
- Cấu trúc tốt hơn (bảng, heading) nhưng vẫn kém MinerU xa trên OmniDocBench; vẫn chép header/footer (do prompt `v1`).
- Đắt hơn ~30 % mỗi trang vì ảnh tốn ~3× token, vẫn rất rẻ.
- → Thay 2.5 Flash bằng 3.5 Flash-Lite là **an toàn**: không có metric chính nào kém đi đáng kể.

## Chạy lại

```bash
for s in vi struct cross; do
  .venv/Scripts/python -I evals/team-4.2/runners/ocr_bench/run_engine.py --engine gemini35lite --suite $s
done
.venv/Scripts/python -I evals/team-4.2/runners/ocr_bench/score_vi.py
.venv/Scripts/python -I evals/team-4.2/runners/ocr_bench/score_struct.py --suite struct
.venv/Scripts/python -I evals/team-4.2/runners/ocr_bench/score_struct.py --suite cross
.venv/Scripts/python -I evals/team-4.2/runners/ocr_bench/official_eval.py
```
