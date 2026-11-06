# W02-04 — So sánh fixed-size vs structural chunking

Owner: C · Reviewer: D · Ngày 4 · File: `src/rag/ingest/chunker.py` (thêm `strategy`), `evals/team-4.2/results/w02-chunk-*`

## Checklist

- [ ] Thêm `strategy="fixed"`: N âm tiết (vd. 300), overlap (vd. 50), bỏ qua heading/bảng
- [ ] `strategy="structural"`: Điều/heading/paragraph, bảng giữ header, flow giữ thứ tự + điều kiện
- [ ] Hai `DATA_DIR` riêng, **cùng nguồn**, cùng embedding/retrieval config
- [ ] **Cùng bộ câu**: `w02_quality.jsonl` + tập con `benchmark_doi_thuong` (phần `test` sau khi tách dev/test)
- [ ] Đo R@5, MRR@5, số chunk, độ dài trung bình, thời gian ingest
- [ ] Tách kết quả theo loại câu: bảng / văn bản / OCR / version
- [ ] Ví dụ định tính: 2–3 chunk fixed cắt đôi bảng/Điều so với structural
- [ ] `summary.md` + config + per-question CSV

## Tiêu chí nghiệm thu

- Kết luận dựa trên số, kể cả khi structural không thắng ở mọi nhóm.

## Ghi chú

-
