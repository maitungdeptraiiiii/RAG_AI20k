# Tích hợp temporal QA và multi-hop agent

Nhánh tích hợp: `codex/integrate-temporal-multihop`.

- Nền: `feat/team-4.2/w02-temporal-qa` tại `e6bf5f3`.
- Merge: `feat/team-4.2/w02-multihop-agent` tại `3a97432`.
- Hai conflict văn bản: `ui/server.py`, `ui/index.html`.
- `.env.example` và `config.py` tự merge, giữ cả cấu hình temporal và `AGENT_*`.

## Hành vi sau khi ghép

- Think tắt: giữ nguyên `_sync_chat`/`_sync_stream`, gồm temporal QA, `as_of`, timeline,
  quy định chuyển tiếp, ingest/review và PII theo phiên chat.
- Think bật, không chọn ngày: chạy multi-hop agent trên snapshot corpus. Câu hỏi và
  history được che PII bằng `MaskState` của phiên trước khi đến planner/condense/retrieval.
  Cache/trace giữ bản đã che; đáp án cuối được mở che cho chính phiên hỏi.
- Think bật cùng `as_of`: dùng temporal multi-hop. Pin generation của kho luật có phiên bản,
  lọc hiệu lực trước mỗi search/rerank và chỉ resolve xref trong cùng phạm vi mốc.
  Không gộp các phiên bản khác nhau của cùng Điều; giữ quota tìm kiếm theo từng mốc.
- Chuyển tiếp/điều kiện áp dụng được đưa vào các bước compose/verify và được review một lần
  nữa trước khi gửi đáp án. Backend hạ mức chắc chắn hoặc hỏi lại khi chưa đủ căn cứ.
- Nếu kho phiên bản chưa sẵn sàng, trả `temporal_scope_unavailable`; nếu không có phiên bản
  phù hợp, nêu thiếu căn cứ. Không thay bằng corpus legacy không xác minh ngày.
- UI giữ cả date picker và nút Think; payload có `session_id`, `history`, `as_of`, `think`.
- `AgentTrace` dùng keyword arguments để tương thích trường `query_pii` mới trong `AskTrace`.

Adapter theo ngày nằm tại `src/rag/agent/temporal.py`. Khi không chọn ngày, Think vẫn dùng
snapshot như trước. Khi chọn ngày, UI nhận timeline, hiệu lực/provenance từng nguồn, certainty,
đánh giá chuyển tiếp và follow-up questions theo schema temporal hiện có.

## Kiểm tra tay

Theo yêu cầu người dùng, không chạy thêm test agent hoặc gọi API benchmark khi merge.
Chỉ kiểm tra cú pháp và dấu conflict trước khi hoàn tất merge.

Chạy UI từ gốc repo:

```powershell
python app/team-4.2/ui/server.py
```

Sau đó kiểm tra Think tắt/bật, hỏi tiếp trong cùng chat, thông tin cá nhân được mở che
đúng phiên, cùng câu hỏi ở hai phía một ngày sửa luật, Think + ngày với nhiều mốc sự kiện,
kho chưa có phiên bản phù hợp, và các trang upload/review.
