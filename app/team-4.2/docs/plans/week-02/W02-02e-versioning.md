# W02-02e — Version hiện hành / lịch sử

Owner: D · Reviewer: A · Ngày 3 · File: `src/rag/quality/versioning.py`, `src/rag/index/store.py`, retriever

## Checklist

- [ ] Xác định `version_group` (cùng văn bản): theo số hiệu/tiêu đề chuẩn hoá, hoặc khai báo trong metadata
- [ ] Ingest bản mới hơn (`effective_from` lớn hơn) → bản cũ `is_current=False`, `quality_status=superseded`
- [ ] Không xoá chunk cũ (giữ lịch sử); cập nhật cờ trong store **và** payload Qdrant
- [ ] Retriever mặc định lọc `is_current=True` (filter Qdrant + lọc BM25)
- [ ] Tuỳ chọn `include_history=True` / `as_of=<ngày>` cho câu hỏi lịch sử
- [ ] Xử lý ingest bản cũ **sau** bản mới (không được lật ngược hiện hành)
- [ ] Test: hỏi bản hiện hành → top-k không có chunk superseded
- [ ] Test: `as_of` trước ngày hiệu lực v2 → trả v1
- [ ] Hiển thị version + ngày hiệu lực trong citation UI

### Metadata pháp lý xuống tới chunk

- [ ] Ingest corpus vbpl: đọc `<stem>.meta.json` cạnh `.txt` và gắn `doc_number`, `effective_from`, `effective_to`, `effective_status` vào metadata của chunk (store + payload Qdrant). Hiện `pipeline.ingest` chưa đọc file meta này.
- [ ] `effective_status = "Hết hiệu lực"` → `is_current=False` ngay khi ingest, không cần chờ có bản mới
- [ ] Crawler trả `status=updated` (`vbpl.py` đã có `previous_sha256`) → re-ingest: chunk của `doc_id` cũ chuyển `superseded`, không để cả hai bản cùng `is_current`. Hiện store chỉ append, chunk cũ vẫn còn trong index.

### Văn bản sửa đổi, bổ sung một phần

- [ ] Lưu quan hệ `amends: [doc_number]` / `amended_by: [doc_number]` (lấy từ dữ liệu văn bản liên quan của API vbpl, fallback: regex tiêu đề "sửa đổi, bổ sung một số điều của Luật … số …")
- [ ] Văn bản sửa đổi có số hiệu khác nên **không** vào cùng `version_group` với văn bản gốc; văn bản gốc vẫn `is_current=True` (chỉ hết hiệu lực một phần)
- [ ] Mức điều khoản (nếu kịp): parse "Sửa đổi, bổ sung Điều X" → gắn cờ `amended=True` + `amended_by` cho chunk của Điều X ở văn bản gốc
- [ ] Retrieval: chunk có `amended_by` lọt top-k → kéo thêm chunk tương ứng của văn bản sửa đổi vào context (tương tự article merge)
- [ ] Prompt/citation: khi context có cả bản gốc và bản sửa đổi, câu trả lời ưu tiên nội dung sửa đổi và trích dẫn **cả hai** văn bản
- [ ] Test: hỏi về Điều đã bị sửa đổi → context có chunk văn bản sửa đổi, câu trả lời không dùng nội dung cũ

### File upload qua Streamlit (không có meta.json)

- [ ] Trích metadata từ phần đầu văn bản: số hiệu (regex `\d+/\d{4}/[A-ZĐ\-]+`), loại văn bản, ngày ban hành ("ngày … tháng … năm …"), ngày hiệu lực (điều khoản thi hành "có hiệu lực thi hành từ ngày …")
- [ ] Form upload cho phép người dùng sửa/nhập số hiệu + ngày hiệu lực trước khi ingest (prefill từ bước trích)
- [ ] Số hiệu trùng với văn bản đã có trong corpus → không index thẳng: đẩy vào review queue W02-02g (`type=version_candidate`) kèm diff với bản hiện hành
- [ ] Không trích được số hiệu/ngày → `version_group` riêng, `quality_status=needs_metadata`, UI cảnh báo
- [ ] Test: upload lại một luật trong corpus đã sửa vài từ → ra mục review, không có hai bản cùng `is_current`

## Tiêu chí nghiệm thu

- Cập nhật không làm chunk cũ lẫn vào truy vấn bản hiện hành; vẫn truy vấn được lịch sử.
- Văn bản sửa đổi một phần được trích dẫn cùng văn bản gốc khi câu hỏi chạm tới Điều bị sửa.
- File upload trùng số hiệu với corpus không tự lật bản hiện hành khi chưa qua review.

## Ghi chú

- Gap hiện tại (đến commit `18eae4b`): chỉ chặn được upload trùng byte (`doc_id` = sha1 nội dung, `store.has_doc`). Sửa một ký tự hoặc đổi PDF↔DOCX là thành văn bản mới và cả hai bản cùng được index.
