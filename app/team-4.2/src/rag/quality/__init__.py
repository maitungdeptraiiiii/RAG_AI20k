"""Chất lượng dữ liệu tuần 2 (Nhóm 2), đã nối vào ``RAGPipeline.ingest``.

    pii.py       mask PII trước chunk / contextual LLM / embedding / BM25 / chunks.jsonl / log  (W02-02f)
    numeric.py   chuẩn hoá số + đơn vị theo Decimal, so sánh có ngữ cảnh                        (W02-02h)
    validate.py  kiểm tra bảng (kiểu, locale, đơn vị, kỳ, tổng), conflict, ngày -> QualityIssue (W02-02h)
    issues.py    QualityIssue + mã issue dùng chung với data/team-4.2/fixtures/labels.jsonl
    apply.py     mask_pages / assess_tables — điểm nối với pipeline

Khi Nhóm 1 có contract ``rag.w02`` (SafeBlock, QualityIssue trong schema), chỉ cần adapter mỏng.
"""
