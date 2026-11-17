# Đồng bộ sang kho mới — Implementation Plan

> **For agentic workers:** superpowers:executing-plans (Claude làm trực tiếp, một lượt review cuối).

**Goal:** Văn bản pháp luật chỉ từ kho có phiên bản; kho cũ chỉ còn tài liệu thường.
**Spec:** `app/team-4.2/docs/superpowers/specs/2026-11-11-new-store-sync-design.md`

## Global Constraints
- Lệnh từ `app/team-4.2`; baseline full suite: 3 lỗi script demo.
- Nhãn kho cũ: `Tài liệu (không phải văn bản pháp luật)`.
- Thông báo kho mới chưa sẵn sàng: `Kho luật có phiên bản chưa sẵn sàng — hãy thử lại sau ít phút hoặc kiểm tra trang /review.`
- Commit mỗi task, `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus
1. Kho cũ trống sau khi loại 6 bộ luật (chưa upload tài liệu thường nào) → mọi đường tìm kho cũ trả rỗng, không lỗi.
2. Crawler thiếu một bộ luật (vbpl không có) → câu hỏi về nó ra "chưa đủ căn cứ", không lỗi.
3. Think tự do khi kho mới chưa sẵn sàng → báo lỗi rõ như chat thường.

### Task 1: Seeds 6 bộ luật + crawl thật
- `data/team-4.2/legal/seeds.yaml` thêm 5 bộ luật còn thiếu (Dân sự đã có). Test `tests/test_new_store_sync.py::test_seeds_cover_legacy_map` — mọi `number` trong `legacy_map.yaml` có trong `seeds.yaml`.
- Chạy `python -m rag.legal crawl` (mạng vbpl); ghi kết quả (văn bản thêm / bị loại) vào ledger. Kiểm tra 6 số hiệu có trong snapshot đang công bố.

### Task 2: Lọc kho cũ chỉ còn tài liệu thường
- `src/rag/temporal/status.py`: `def document_search(retrieve, chunks, legacy_map) -> Callable[[str,int], list[Chunk]]` — gọi `retrieve(query, k*3)`, bỏ chunk có `source` thuộc `legacy_map`, cắt `k`. Và `def legacy_documents(store_docs, legacy_map)` lọc danh sách tài liệu.
- Áp vào `ui/server.py` (legacy_search của `make_runtime`, `_contract_legacy_search`, agent legacy retriever) và nhãn nguồn kho cũ trong TemporalQA item title / UI = nhãn Global Constraints.
- Tests: chunk 6 bộ luật bị loại; tài liệu thường giữ; kho cũ chỉ có 6 bộ luật → rỗng.

### Task 3: `/api/info` + danh sách tài liệu hai nhóm
- `/api/info` thêm `legal_docs: [{document_key, title, doc_type, doc_number, status_today: in_force|repealed|not_yet, replaced_by}]`, `legal_total`, và `docs` = kho cũ trừ 6 bộ luật.
- `ui/index.html` `renderProjectsList` hiện 2 nhóm. Tests: API trả đúng nhóm; trang chứa tiêu đề hai nhóm.

### Task 4: Think tự do trên kho mới
- `rag/contracts/agent_view.py`: `ContractAgentRetriever` nhận `contract=None` + `anchor: date` + `mask_state` → chỉ nguồn luật có phiên bản + tài liệu thường. `run_store_agent(baseline, config, runtime, doc_chunks, doc_search, question, history, anchor, mask_state, stream)` (che/mở PII, hậu kiểm như phần 4 nhưng không cần hợp đồng).
- `ui/server.py` Think không có hợp đồng → `run_store_agent` với runtime lease, anchor = as_of hoặc hôm nay, mask_state của phiên.
- Tests: retriever không hợp đồng; PII không tới LLM; mốc lọc hiệu lực; định tuyến server.

### Task 5: Không lặng lẽ quay về kho cũ
- `_sync_chat` / `_sync_stream` / Think: holder None → trả thông báo Global Constraints (JSON 503 / SSE error), không gọi pipeline cũ để trả lời luật.
- Tests định tuyến.

### Cuối: full suite + review (subagent, model mạnh nhất) → một đợt sửa → chạy demo thật.
