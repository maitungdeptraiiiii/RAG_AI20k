# Trang hỏi đáp hợp đồng `/contracts/ask` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trang riêng hỏi đáp hợp đồng trên đồ thị, có danh sách chọn hợp đồng đã dựng đồ thị.

**Architecture:** Server thêm `concepts` vào thẻ và route trang; phần vẽ câu trả lời tách sang `ui/contract_qa.js`
(`window.ContractQA`); trang mới `contract_ask.html/.js`; trang Hợp đồng bỏ khung hỏi, thêm nút + `?cid=`.

**Tech Stack:** Starlette, pytest/TestClient, vanilla JS + Tailwind CDN.

**Spec:** `docs/superpowers/specs/2026-11-17-contract-ask-page-design.md`

## Global Constraints
- Không sửa `ui/index.html`; không liệt kê hợp đồng toàn server.
- Mọi chuỗi từ server vào HTML qua `esc`.
- `/api/contracts/{cid}/ask/stream` giữ nguyên hợp đồng sự kiện (`step`, `done`, `error`).

## Review Focus
- Id trong localStorage đã hết phiên → `GET ?ids=` bỏ qua; trang không lỗi, xóa id khỏi danh sách.
- `?cid=` không tồn tại → thông báo "Hợp đồng đã hết phiên", vẫn hiện danh sách.
- Đang chờ câu trả lời mà đổi hợp đồng → câu trả lời vẫn ghi vào đúng hội thoại của hợp đồng cũ.
- Hợp đồng có `concepts == 0` → không gửi được câu hỏi (mờ, có link Kiểm tra concept).
- Trên điện thoại (≤640px) cột danh sách xếp trên khung chat, không cuộn ngang.

---

### Task 1: Thẻ có `concepts`, route trang
**Files:** `ui/contracts_api.py` (`card`), `ui/server.py`; Tests `tests/test_contracts_api.py`, `tests/test_server_docs.py`
- `card(c)["concepts"]` = số `concept_id` khác nhau trong `c.oplog.active()` có `content["kind"] == "concept"`.
- `GET /contracts/ask` → `ui/contract_ask.html`; `GET /contract_ask.js`, `GET /contract_qa.js` → file tương ứng (như `contract_page.js`).
- [ ] Tests: `test_card_counts_concepts` (upload → 0; thêm 2 op concept khác nhau + 1 trùng qua `contracts_api.get(cid).oplog.add(machine_op(...))` → `GET` thẻ = 2); `test_contract_ask_page_served` (200, chứa `contract_ask.js`), các JS trả `javascript`.
- [ ] RED → cài → GREEN; commit.

### Task 2: Tách `ui/contract_qa.js`
- `window.ContractQA = { answerHtml(done), stepsHtml(steps, open), readSse(res, onEvent), ask(cid, {question, history, userFacts}, onEvent) -> Promise<last> }`, chuyển từ `contract_page.js` (`qaAnswerHtml`, `qaStepsHtml`, `readSse`, CONF). `contract_page.js` dùng `ContractQA.readSse`; `contracts.html` nạp `contract_qa.js` trước.
- [ ] `node --check`; commit.

### Task 3: Trang `/contracts/ask`
**Files:** create `ui/contract_ask.html`, `ui/contract_ask.js`
- HTML: head như `contracts.html` (token, `.chip`, `.btn`, `.chev`, `.spin`); header: "← Quay lại chat", tiêu đề "Hỏi đáp hợp đồng (đồ thị)", link "Soát hợp đồng" → `/contracts`.
- Bố cục `md:grid-cols-[280px_1fr]`: `#list` | `#chat` (header hợp đồng, `#turns`, ô nhập kiểu viên thuốc như trang chat: `rounded-full`, textarea tự giãn, nút gửi tròn).
- Danh sách: hợp nhất id từ `ctpage.saved` + `justice_saved_contracts_v1` + `?cid=`; `GET /api/contracts?ids=` (`?cid=` không có trong kết quả → `GET /api/contracts/{cid}`, 404 → notice). Mỗi dòng: tên file, ngày ký, "n khái niệm"; `concepts == 0` → mờ + link `/contracts?cid=…` "Kiểm tra concept".
- Hội thoại: `convos[cid] = [{q, steps, done, error}]`; bong bóng người hỏi `bg-[#f4f4f4] rounded-3xl` căn phải; trả lời dùng `ContractQA.answerHtml` + `stepsHtml`; lúc chạy hiện các bước. Trống → 4 câu mẫu (`data-sample`): lương thử việc + đúng luật; thời gian làm việc / làm thêm; phụ lục sửa gì, từ ngày nào; quyền nghỉ phép năm.
- Gửi: Enter (không Shift, không IME), khóa khi lượt của hợp đồng đó đang chạy; 404 → notice hết phiên.
- [ ] `node --check`; commit.

### Task 4: Trang Hợp đồng
**Files:** `ui/contract_page.js`, `ui/contracts.html`
- Bỏ `#qa`, `renderQa`, `ask`, `state.qa/qaDraft`, listener input/keydown của qa.
- Bước ③: khi `state.result` → nút link `/contracts/ask?cid=…` "Hỏi về hợp đồng này →" (cạnh nút tải report).
- `?cid=` lúc nạp trang → `openSaved(cid)` rồi sang bước ③ nếu dữ kiện đã đủ.
- Header thêm link "Hỏi đáp hợp đồng" → `/contracts/ask`.
- [ ] `node --check`; commit.

### Task 5: Chạy thật
- [ ] Restart server; `curl /contracts/ask` 200; API thẻ có `concepts` > 0 sau Kiểm tra concept trên Neo4j; một câu qua `/ask/stream` vẫn chạy. Ghi ledger. (Chưa có trình duyệt: báo người dùng tự mở.)
