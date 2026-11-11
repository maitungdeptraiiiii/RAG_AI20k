# W02-02c A4 — chạy thử MinerU vs PP-StructureV3 (3 trang MDPBench tiếng Việt có bảng)

Ngày 2026-11-07 · RTX 3060 Laptop 6 GB · scorer `score_struct.py` (tự viết). MinerU 4.1.7 `mineru-kit parse --tier standard` (cục bộ); PaddleOCR 3.7.0 `PPStructureV3(lang='vi')` → rec model `latin_PP-OCRv5_mobile_rec`.

| engine | trang | TEDS | TEDS-S | block_ned % | heading | giây (MinerU trang 1 gồm warm-up) |
|---|---|---|---|---|---|---|
| MinerU | vi_academicpaper_16 | 100 | 100 | 1.6 | 3/3 | 56.2 |
| MinerU | vi_financialreport_46 | 96 | 96 | - | -/- | 17.7 |
| MinerU | vi_textbook_26 | 18, 62 | 35, 73 | 8.2 | -/- | 6.7 |
| PP-StructureV3 | vi_academicpaper_16 | 93 | 100 | 18.7 | 3/3 | 20.4 |
| PP-StructureV3 | vi_financialreport_46 | 78 | 84 | - | -/- | 7.6 |
| PP-StructureV3 | vi_textbook_26 | 16, 32 | 35, 47 | 27.2 | -/- | 27.9 |

Quan sát: PP-StructureV3 (model latin mobile) mất dấu tiếng Việt nặng — ví dụ dòng đầu `vi_textbook_26`: PP-StructureV3 ra `Điu đó chúng t rng, h i tana 5`, MinerU ra `Điều đó chứng tổ ràng, hàm số` (MinerU vẫn sai dấu nhẹ). MinerU giữ dấu tốt hơn rõ rệt.
**Quyết định: chọn MinerU** làm engine cấu trúc local. Model load lần đầu ~140 s (llama.cpp VLM) / Paddle ~350 s (gồm tải model).
