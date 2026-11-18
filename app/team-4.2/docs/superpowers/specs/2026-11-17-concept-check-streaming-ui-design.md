# Kiểm tra concept: stream tiến trình, chạy lô song song, báo cáo dễ đọc — thiết kế

Ngày: 2026-11-17 · Cỡ: dự án nhỏ (backend pipeline + endpoint SSE + viết lại phần báo cáo của trang `/contracts`)
Tiếp nối: `2026-11-17-contract-demo-page-design.md`

## Ý định và lý do
Lần chạy demo đầu tiên trên trang `/contracts` có hai vấn đề:
1. **Khó đọc.** Báo cáo Kiểm tra concept hiện mã nội bộ (`probation.cancel_no_notice/r1`, `bo-luat:45/2019/QH14#d27.k2`),
   giá trị luật dạng JSON (`{"value":150,"unit":"percent"}`), tên dữ kiện tiếng Anh (`pregnancy_month`). Người xem không hiểu nó nói gì.
2. **Chờ lâu, màn hình trống.** Pipeline chạy tuần tự, các lô LLM gọi lần lượt; trang chỉ có spinner đến khi xong (vài phút).

Người dùng muốn: xem gọn trước, bấm vào từng mục để xem chi tiết; thấy kết quả sớm (stream); và chạy nhanh hơn thật (song song các lô).

## Mục tiêu
- Trang thấy tiến trình ngay: từng bước pipeline và số lô đã xong.
- Có **kết quả sơ bộ** sau lần đánh giá đầu, được thay bằng **kết quả cuối** sau bước kiểm lại.
- Tổng thời gian giảm nhờ chạy các lô song song (áp cho mọi chỗ dùng `run_batches`: trích dữ kiện, gán khái niệm, Soát luật).
- Báo cáo dạng danh sách gọn có thể mở từng mục; không còn mã nội bộ hay JSON ở chỗ người xem đọc.

## Không phải mục tiêu / chống mục tiêu
- Không thêm LLM diễn giải kết quả (giữ ổn định, không chậm thêm).
- Không thêm khái niệm, mẫu regex hay heuristic mới (quy ước dự án). Không tự đoán trích dẫn từ mã `pid` bằng regex:
  trích dẫn đẹp lấy từ đồ thị luật (`citation`); không có đồ thị thì hiện mã gốc ở dòng phụ.
- Không đổi kết luận của engine: cùng đầu vào, kết quả cuối giống bản tuần tự.
- Không làm mất kết quả khi một lô lỗi: hành vi thử lại / ghi lô lỗi của `run_batches` giữ nguyên.
- Thất bại dù chạy được: thứ tự kết quả lô thay đổi theo luồng (làm kết quả không lặp lại được) — phải giữ thứ tự lô.

## Các hướng đã cân nhắc
- **A. SSE stream sự kiện + song song lô — ĐÃ CHỌN.** Theo mẫu SSE có sẵn ở chat hợp đồng (`server.py` `_contract_chat`). Mất kết nối giữa chừng thì chạy lại.
- B. Job nền + polling: tải lại trang không mất job, nhưng thêm quản lý trạng thái job ở server; cảm giác demo gần như A.
- C. Chỉ song song, giữ spinner: không đúng ý (vẫn màn hình trống).

## Thiết kế

### 1. Chạy lô song song (`src/rag/contracts/batches.py`)
- `run_batches(batches, fn, *, retries=1, workers=None, on_done=None)`; `workers` mặc định đọc `CONTRACT_BATCH_WORKERS` (mặc định 4; 1 = tuần tự như cũ).
- Chạy bằng `ThreadPoolExecutor`; `run.results` giữ **thứ tự lô ban đầu**; thử lại / `run.failed` như cũ.
- `on_done(done: int, total: int)` gọi sau mỗi lô xong (thành công hay lỗi) — để báo tiến trình.
- `LLMCache` đã có khóa và `check_same_thread=False`, dùng chung giữa luồng được. Thêm `CONTRACT_BATCH_WORKERS` vào `.env.example`.

### 2. Sự kiện từ pipeline (`src/rag/bridge/check.py`)
- `check_contract(..., on_event: Callable[[dict], None] | None = None)`. Sự kiện (dict, có `type`):
  - `{"type": "stage", "stage": "facts" | "tag" | "evaluate" | "recheck" | "basis", "status": "start" | "done"}`
  - `{"type": "progress", "stage": "tag", "done": n, "total": m}` (từ `on_done` của `run_batches` qua `tag_contract`)
  - `{"type": "partial", "results": [...]}` — kết quả sau lần đánh giá đầu (trước kiểm lại), cùng dạng `report_json()["results"]`.
- `tag_contract` (và `extract_facts` nếu dễ) nhận `on_progress` để chuyển tiếp `on_done`. Không có `on_event` thì hành vi như cũ.

### 3. Endpoint stream (`ui/contracts_api.py`, `ui/server.py`)
- `POST /api/contracts/{cid}/concept-check` giữ nguyên dạng JSON hiện có (script CLI và test cũ dùng).
- Thêm `POST /api/contracts/{cid}/concept-check/stream` → `text/event-stream`. Pipeline chạy trong luồng, sự kiện đẩy qua hàng đợi;
  mỗi sự kiện là một dòng SSE `data: {...}`. Sự kiện cuối là `{"type": "done", ...}` có đủ nội dung như phản hồi JSON
  (`report`, `markdown`, `labels`, `graph`) cộng phần hiển thị ở mục 4; lỗi → `{"type": "error", "error": "...", "status": 400|404|502|500}`.
- `partial` cũng được bổ sung phần hiển thị ở mục 4 để trang vẽ cùng một cách.

### 4. Dữ liệu hiển thị (server soạn, trang chỉ vẽ)
Mỗi kết quả kèm `view`:
- `title`: `concept.label`; `meaning`: `concept.describe`; `holder`: vai người có quyền (`catalog.roles`).
- `verdict`: câu ngắn theo `finding` (vd. hidden_right → "Hợp đồng không nhắc, nhưng người lao động vẫn có quyền này theo luật").
- `law_values`: danh sách `{"key", "text"}` với `text` đã định dạng giá trị + đơn vị tiếng Việt (150 → "150%", day → "ngày", workday → "ngày làm việc", minute → "phút", vnd → "đồng").
- `law`: mỗi neo `{"pid", "citation", "text", "in_force"}` từ `basis.anchors[].provision` (đồ thị luật); không có đồ thị → `citation=None`, trang hiện `pid` ở dòng phụ.
- `contract`: các đoạn trích `{"label", "quote"}` (nhãn điều khoản lấy từ `contract.units`).
- `missing`: tên dữ kiện thiếu → nhãn tiếng Việt (bảng nhãn cho `USER_FACTS` ∪ `CONTRACT_FACTS`; slot thì dùng tên khái niệm + "(nội dung trong hợp đồng)").

### 5. Trang (`ui/contract_page.js`)
- Bước ③, khi bấm Kiểm tra concept: dùng `fetch` + đọc stream (POST nên không dùng `EventSource`).
- **Thanh tiến trình**: ✔ Đọc hợp đồng · ⟳ Gán khái niệm (3/5 lô) · Đánh giá · Kiểm lại · Căn cứ luật.
- **Kết quả**: hàng chip đếm theo nhóm (bấm chip để lọc); danh sách gọn mỗi dòng = tiêu đề + verdict; bấm để mở chi tiết theo thứ tự:
  1. Ý nghĩa với người lao động (`verdict` + `meaning`), 2. Hợp đồng (đoạn trích hoặc "không có điều khoản nào nhắc"),
  3. Luật (trích dẫn + lời văn; giá trị luật đã định dạng), 4. Thiếu dữ kiện (nhãn tiếng Việt, nút "Bổ sung ở bước ②").
- Kết quả sơ bộ hiện nhãn "Sơ bộ — đang kiểm lại…" và được thay khi có `done`. Nhóm "Không có vấn đề" thu gọn mặc định.
- Mã kỹ thuật (concept_id, rule_id, pid) chỉ hiện trong dòng phụ nhỏ ở cuối phần chi tiết.

## Ràng buộc
- Không sửa `ui/contracts.js` / `ui/index.html` (plugin chat).
- Đồ thị luật cần Neo4j chạy (`docker-neo4j-1` đang Exited 137) và đã công bố; thiếu thì báo cáo vẫn chạy, chỉ thiếu lời văn luật.
- Test: `run_batches` song song (thứ tự giữ nguyên, lô lỗi vẫn ghi `failed`, `on_done` đếm đúng); `check_contract` phát đủ chuỗi sự kiện; endpoint stream trả `done`/`error`; dữ liệu `view` (định dạng đơn vị, nhãn dữ kiện). Giao diện kiểm tay.

## Việc để người xây quyết
- Cách chia luồng / hàng đợi trong endpoint stream; tên hàm tạo `view`.
- Bố cục, màu sắc chi tiết của danh sách và phần mở rộng.
