# W02-02g — Near-duplicate, conflict, review queue

Owner: A · Reviewer: B · Ngày 3 · File: `src/rag/quality/dedup.py`, `src/rag/quality/review.py`

> Không tự xoá bản khác biệt quan trọng. Near-dup/conflict → hàng đợi review.

## Checklist

- [ ] Exact dedup: dùng checksum (đã có `doc_id` = hash nội dung) — gom vào module, có log lý do skip
- [ ] Near-dup: MinHash/SimHash trên shingle 3–5 âm tiết (`datasketch` hoặc tự viết)
- [ ] Chỉnh ngưỡng Jaccard trên phần `dev` của fixtures, **không** trên `test`
- [ ] Phân biệt near-dup "vô hại" và "khác số quan trọng": diff số liệu/ngày giữa 2 bản → nếu khác → conflict
- [ ] Conflict: cùng chỉ tiêu/thực thể, khác giá trị (dùng kết quả chuẩn hoá số của W02-02h)
- [ ] `review_queue.jsonl`: `{id, type, doc_ids, evidence, suggested_action, status: open|approved|rejected|superseded, reviewer, decided_at}`
- [ ] CLI `python -m rag.quality.review list|approve|reject|supersede <id>` **hoặc** tab Streamlit
- [ ] Quyết định review cập nhật `quality_status` và index (approve → index; reject → không index)
- [ ] Test: bản khác 1 số quan trọng **không** bị gộp; bản khác khoảng trắng được gắn near-dup

### Upload trùng / sửa / mâu thuẫn với corpus

- [ ] Exact dedup theo **text đã chuẩn hoá** (NFC, gộp khoảng trắng) chứ không theo byte file, để cùng một luật ở PDF và DOCX vẫn được nhận là trùng
- [ ] Thêm `type=version_candidate` vào review queue (do W02-02e đẩy sang khi số hiệu trùng corpus). Evidence = diff theo Điều với bản hiện hành. `suggested_action`: `supersede` nếu `effective_from` mới hơn, `reject` nếu cũ hơn/bằng
- [ ] Conflict giữa các văn bản khác số hiệu (VD: Luật vs Nghị định quy định khác mức phạt) → **không** tự chọn bản đúng; ghi mục `type=conflict` kèm thứ bậc hiệu lực (Luật > Nghị định > Thông tư) làm gợi ý cho người duyệt
- [ ] Trong lúc mục review còn `open`: chunk của file upload gắn `quality_status=pending_review`, retriever mặc định loại ra; UI hiển thị "đang chờ duyệt"
- [ ] UI Streamlit: kết quả ingest báo rõ `duplicate` / `near-dup` / `version_candidate` / `conflict` thay vì chỉ "skipped"

## Tiêu chí nghiệm thu

- Ingest 25 fixtures sinh review queue; mỗi mục có bằng chứng (đoạn diff) để người duyệt quyết định.
- Upload một luật đã có trong corpus dưới định dạng khác → `duplicate`. Upload bản sửa vài Điều → `version_candidate` kèm diff, không lẫn vào truy vấn trước khi duyệt.

## Ghi chú

- Phối hợp W02-02e: 02e lo metadata (số hiệu, hiệu lực, quan hệ sửa đổi) và cờ `is_current`; 02g lo phát hiện + review queue và quyết định cuối.
