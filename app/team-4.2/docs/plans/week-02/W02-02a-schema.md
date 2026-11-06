# W02-02a — Schema DocMeta + provenance

Owner: D · Reviewer: A · Ngày 1 (PR nháp) → ngày 2 (merge) · File: `src/rag/schema.py`, `tests/test_schema.py`

> Đổi `schema.py` phải báo cả nhóm. Mọi trường mới có mặc định để `chunks.jsonl` cũ vẫn đọc được.

## Checklist

- [ ] Thêm dataclass `DocMeta`:
  - [ ] `doc_id`, `checksum_sha256`, `source`, `source_type` (`pdf_text|pdf_scan|docx|csv|xlsx|html|txt|pptx`)
  - [ ] `language`
  - [ ] `collected_at`, `published_at`, `effective_from`, `effective_to`
  - [ ] `version`, `version_group`, `is_current`
  - [ ] `quality_status` (`ok|needs_review|superseded|rejected`), `quality_issues: list[QualityIssue]`
- [ ] Thêm `QualityIssue` (`type`, `severity`, `location`, `detail`, `detector`)
- [ ] Mở rộng `Chunk`:
  - [ ] `heading_path`, `slide`, `table_id`, `row_range`
  - [ ] `chunk_strategy` (`fixed|structural`)
  - [ ] `content_origin` (`source|ocr|llm_description`), `ocr_confidence`
  - [ ] `pii_masked: bool`
  - [ ] `version_group`, `is_current` (sao chép từ DocMeta để lọc nhanh lúc retrieve)
- [ ] `to_dict`/`from_dict` tương thích ngược (đọc file cũ thiếu trường)
- [ ] Nơi lưu DocMeta: `docs.jsonl` cạnh `chunks.jsonl` (cập nhật `ChunkStore`)
- [ ] Test: round-trip, đọc chunk cũ, validate enum
- [ ] `pytest` xanh toàn bộ
- [ ] Cập nhật docstring luồng dữ liệu đầu file `schema.py`
- [ ] PR, A review, merge

## Tiêu chí nghiệm thu

- Mỗi chunk truy ngược được: tài liệu, checksum, nguồn, heading, trang/slide/bảng, loại, ngôn ngữ, ngày, version, quality status.

## Ghi chú

-
