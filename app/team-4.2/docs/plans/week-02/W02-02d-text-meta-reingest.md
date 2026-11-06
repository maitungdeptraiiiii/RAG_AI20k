# W02-02d — Nhóm văn bản + metadata + ingest lặp

Owner: A · Reviewer: D · Ngày 2–3 · File: `src/rag/ingest/loaders.py`, `src/rag/pipeline.py`, `tests/test_pipeline.py`

## Checklist

- [ ] Loader PDF/DOCX/TXT/URL điền `DocMeta` (`source_type`, `language`, `collected_at`, checksum)
- [ ] Văn bản vbpl: lấy `published_at`, `effective_from`, tình trạng hiệu lực từ `manifest.json` / `.meta.json`
- [ ] Giữ `heading_path` (Chương › Mục › Điều) trong chunker structural
- [ ] Nối các bước mới vào `RAGPipeline.ingest` theo thứ tự:
      load → checksum/exact dedup → PII mask → validate → near-dup/conflict/version → chunk → index → lưu
- [ ] `IngestReport` thêm: `quality_status`, số issue, `superseded` doc_ids
- [ ] Test ingest lặp: ingest 2 lần → số dòng `chunks.jsonl` và số điểm Qdrant **không đổi**
- [ ] Test đổi tên file cùng nội dung → vẫn skip (checksum)
- [ ] Script demo `scripts/team-4.2/demo_w02.py`: ingest → ingest lại → cập nhật version → in trạng thái

## Tiêu chí nghiệm thu

- Demo được ingest lặp và cập nhật phiên bản, có output in số chunk/điểm trước và sau.

## Ghi chú

-
