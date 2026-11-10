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
- Think bật cùng `as_of`: trả thông báo rõ `agent_temporal_unsupported`. V1 agent chưa
  dùng index phiên bản theo ngày; không bỏ qua ngày rồi trả lời như đã lọc hiệu lực.
- UI giữ cả date picker và nút Think; payload có `session_id`, `history`, `as_of`, `think`.
- `AgentTrace` dùng keyword arguments để tương thích trường `query_pii` mới trong `AskTrace`.

Đây là ghép hai chế độ vận hành, chưa phải một temporal multi-hop retriever hợp nhất.
Muốn dùng Think theo ngày cần một adapter giới hạn tất cả search/xref theo timeline và
giữ các kiểm tra chuyển tiếp của `TemporalQA`.

## Kiểm tra tay

Theo yêu cầu người dùng, không chạy thêm test agent hoặc gọi API benchmark khi merge.
Chỉ kiểm tra cú pháp và dấu conflict trước khi hoàn tất merge.

Chạy UI từ gốc repo:

```powershell
python app/team-4.2/ui/server.py
```

Sau đó kiểm tra Think tắt/bật, hỏi tiếp trong cùng chat, thông tin cá nhân được mở che
đúng phiên, date picker khi Think tắt, cảnh báo Think + ngày, và các trang upload/review.
