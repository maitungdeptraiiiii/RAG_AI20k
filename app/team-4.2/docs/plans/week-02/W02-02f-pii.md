# W02-02f — Mask PII trước embedding/log

Owner: E · Reviewer: D · Ngày 2 (regex) → ngày 3 (tích hợp) · File: `src/rag/quality/pii.py`, `tests/test_pii.py`

## Checklist

- [x] Regex + kiểm tra: CCCD 12 số, CMND 9 số, SĐT VN (0/+84, 10 số), email, MST (10/13 số), STK ngân hàng
- [ ] (Tuỳ chọn) tên người trong ngữ cảnh "Họ và tên:", địa chỉ
- [x] Thay bằng placeholder có loại: `[CCCD_1]`, `[PHONE_1]` …
- [x] Mẫu âm trong test: số hiệu văn bản (`45/2019/QH14`), số tiền, ngày tháng, số Điều — **không** được mask
- [x] Mask chạy **trước** embed, BM25, contextual enhancer, ghi log và ghi `chunks.jsonl`
- [x] Không lưu bản gốc PII ra đĩa (nếu cần map thì chỉ trong RAM hoặc file riêng, gitignore)
- [ ] Đặt `pii_masked=True` trên chunk; đếm số PII theo loại vào IngestReport
- [x] Test kiểm tra rò rỉ: sau ingest fixtures, grep PII gốc trong file log, `chunks.jsonl`, payload Qdrant, cache SQLite → 0 kết quả
- [x] Ghi số phát hiện/bỏ sót/báo nhầm PII cho W02-03

## Tiêu chí nghiệm thu

- Test rò rỉ xanh; báo nhầm trên mẫu âm được báo cáo trung thực.

## Ghi chú

- Code: `src/rag/quality/pii.py`, nối trong `RAGPipeline.ingest` qua `quality/apply.py::mask_pages` (ngay sau loader); test: `tests/test_pii.py`.
- Loại: email, SĐT (di động + cố định), CCCD, CMND/MST/STK (chỉ khi có từ khoá), họ tên sau "Họ và tên:" hoặc theo header cột bảng. Chưa mask địa chỉ.
- Test rò rỉ quét embedding, BM25, contextual enhancer, log, `IngestReport`, `chunks.jsonl`, file Qdrant: 0 kết quả; khi tắt mask thì test bắt được 44 chỗ rò rỉ.
- `IngestReport.pii_counts` đếm theo loại. Cờ `pii_masked` trên `Chunk` chờ schema W02-02a.
