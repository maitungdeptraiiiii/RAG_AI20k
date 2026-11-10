"""Quality components grouped by function.

    pii.py       mask PII (CCCD/CMND, SĐT, email, MST, STK, họ tên theo ngữ cảnh) trước embed/log  (W02-02f)
    numeric.py   chuẩn hoá số + đơn vị theo Decimal, so sánh có ngữ cảnh                          (W02-02h)
    validate.py  kiểm tra bảng (kiểu, locale, đơn vị, kỳ, tổng), conflict, ngày -> QualityIssue   (W02-02h)
    tables.py    đọc CSV/XLSX cho kiểm tra chất lượng (dùng parser ở rag.ingest.tables)           (W02-02b)
    issues.py    QualityIssue + mã issue dùng chung với data/team-4.2/fixtures/labels.jsonl
    apply.py     mask_pages / assess_tables — áp các kiểm tra trên cho list[Page] (điểm nối pipeline)
"""
