# Trang demo hợp đồng riêng (`/contracts`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trang `/contracts` riêng, đi 3 bước (Nạp → Dữ kiện → Soát), tách khỏi chat hỏi đáp luật; bước Soát có "Kiểm tra concept" (endpoint mới) và "Soát luật" (có sẵn).

**Architecture:** Endpoint `POST /api/contracts/{cid}/concept-check` đặt trong `ui/contracts_api.py`, dùng chung hàm `concept_check()` với `scripts/check_contract_concepts.py`. Trang là `ui/contracts.html` + `ui/contract_page.js` (vanilla JS + Tailwind CDN, theo `review.html`), gọi các API `/api/contracts/*` có sẵn. Plugin chat (`contracts.js`, `index.html`) không đụng.

**Tech Stack:** Python 3.12, Starlette, pytest + `starlette.testclient`; HTML/JS thuần, Tailwind CDN. Chạy lệnh từ `app/team-4.2` (`uv run pytest ...`).

**Spec:** `docs/superpowers/specs/2026-11-17-contract-demo-page-design.md`

## Global Constraints

- Không sửa `ui/contracts.js` và `ui/index.html`.
- Không thêm regex/heuristic mới, không thêm khái niệm mới vào `concepts.yaml`.
- Dữ kiện người dùng hợp lệ chỉ là tên trong `USER_FACTS` ∪ `CONTRACT_FACTS` (`rag.bridge.catalog`); sai tên → `ValueError` từ `rag.bridge.check.user_fact_set` → HTTP 400 qua `_call`.
- Tên route, thông điệp lỗi giao diện bằng tiếng Việt, như các file UI hiện có.
- Mọi chuỗi từ API chèn vào HTML phải qua hàm escape.

## Review Focus

- Hợp đồng không có ngày ký: concept-check vẫn chạy (check_contract tự thêm cảnh báo); trang hiển thị `warnings`, không báo lỗi.
- `user_facts` sai tên (`{"abc": 1}`): endpoint trả 400 kèm thông điệp, không 500.
- Mở lại hợp đồng đã hết phiên (cid không còn): trang báo "Hợp đồng này đã hết phiên" và về bước ①, không treo.
- "Soát luật" khi còn dữ kiện bắt buộc chưa xác minh: API trả 409 kèm `pending`; trang đưa người dùng về bước ② và nêu mục còn thiếu.
- Bấm "Kiểm tra concept" hai lần liên tiếp (chạy lâu): nút khóa trong lúc chạy, không gửi hai request.

---

### Task 1: Hàm và endpoint concept-check

**Files:**
- Modify: `ui/contracts_api.py` (thêm import, hàm `concept_check`, `handle_concept_check`, route)
- Test: `tests/test_contracts_api.py`

**Interfaces:**
- Produces: `contracts_api.concept_check(cid: str, user_facts: dict | None = None, *, tag_model: str | None = None, tag_temp: float | None = None) -> dict` trả `{"report": report_json(...), "markdown": str, "graph": {"enabled","published","error"}}`. Cũng thêm `CONFIG.tag_llm` (callable `(model, temp) -> llm | None`, mặc định hàm dựng như `_tag_llm` của script) và `CONFIG.legal_graph` (callable `() -> LegalGraph | None`) để test thay được.
- Produces: route `POST /api/contracts/{cid}/concept-check`, body `{"user_facts": {...}}`; 404 `GONE` khi không có cid, 400 khi dữ kiện sai tên.

- [ ] **Step 1: Viết test thất bại** trong `tests/test_contracts_api.py`, monkeypatch `contracts_api.check_contract` trả một `CheckReport` rỗng (`CheckReport(cid, date(2026,11,11), "v", [], {}, [], ["w"], {})`):
  - `test_concept_check_returns_report_and_markdown`: upload, POST `/api/contracts/{cid}/concept-check` body `{"user_facts": {"wage_region": "I"}}` → 200; `body["report"]["contract_id"] == cid`, `body["report"]["warnings"] == ["w"]`, `isinstance(body["markdown"], str)`; fake `check_contract` nhận `user_facts == {"wage_region": "I"}`.
  - `test_concept_check_unknown_fact_is_400`: không monkeypatch `check_contract`; body `{"user_facts": {"abc": 1}}` → 400 (cần `CONFIG.tag_llm = lambda m, t: StageLLM()` để không đòi OpenRouter).
  - `test_concept_check_gone_is_404`: cid `"nope"` → 404, `error == contracts_api.GONE`.
  - `test_concept_check_rebuilds_graph`: sau khi chạy, `contracts_api._rebuild` được gọi một lần (monkeypatch đếm).
- [ ] **Step 2: Chạy** `uv run pytest tests/test_contracts_api.py -k concept_check -v` → FAIL (thiếu route/hàm).
- [ ] **Step 3: Cài đặt** `concept_check` theo thân hàm `main` của `scripts/check_contract_concepts.py` (get contract, `load_catalog`, `AnchorLawBasis(catalog, CONFIG.legal_graph())`, `check_contract(..., graph=_graph())`, rồi `with _graph().writing(cid): _rebuild(c, now)`); `report_markdown(report, catalog)` cho `markdown`. Thêm `handle_concept_check` (`_json` + `_call`, `user_facts` lấy từ body, không phải dict thì `{}`) và Route. `CONFIG.tag_llm` mặc định: nếu `model` rỗng → `concept_tag_llm(Settings.load(), cache=LLMCache(...))` như `_tag_llm` trong script; `CONFIG.legal_graph` mặc định: logic `_legal_graph` trong script (None khi lỗi).
- [ ] **Step 4: Chạy lại** test ở Step 2 → PASS; chạy `uv run pytest tests/test_contracts_api.py -v` → không hỏng test cũ.
- [ ] **Step 5: Commit** `feat(team-4.2): concept-check endpoint for contracts`

### Task 2: Script CLI dùng chung hàm

**Files:**
- Modify: `scripts/check_contract_concepts.py`

**Interfaces:**
- Consumes: `contracts_api.concept_check` (Task 1).

- [ ] **Step 1: Sửa `main`** để gọi `api.concept_check(card["contract_id"], user_facts, tag_model=tag_model, tag_temp=tag_temp)` thay cho khối tự dựng; xóa `_legal_graph`, `_tag_llm` khỏi script (đã chuyển sang `contracts_api`). Giữ nguyên đầu ra: `report.json`, `report.md`, `oplog.json`, hai dòng in. `--tag-model app` vẫn nghĩa là dùng LLM của app.
- [ ] **Step 2: Kiểm** `uv run python scripts/check_contract_concepts.py --help` chạy được; `uv run pytest tests -k "concept or bridge" -q` xanh.
- [ ] **Step 3: Commit** `refactor(team-4.2): concept-check script shares contracts_api.concept_check`

### Task 3: Route và file tĩnh cho trang

**Files:**
- Modify: `ui/server.py` (hằng `CONTRACTS_HTML_PATH`, `CONTRACT_PAGE_JS_PATH`; handler `handle_contracts_page`, `handle_contract_page_js`; hai Route; dòng doc đầu file `GET /contracts`)
- Create: `ui/contracts.html` (khung, header, ba ô stepper rỗng, nạp `/contract_page.js`), `ui/contract_page.js` (chỉ `console.log` tạm là không được — để rỗng có IIFE)
- Test: `tests/test_server_docs.py` (hoặc file test server có sẵn dùng `TestClient` với `server.routes`)

**Interfaces:**
- Produces: `GET /contracts` → HTML; `GET /contract_page.js` → `text/javascript`, `Cache-Control: no-cache`. Khung HTML có ba vùng `#step-1`, `#step-2`, `#step-3` và thanh bước `#stepper` mà Task 4–6 điền.

- [ ] **Step 1: Test thất bại** `test_contracts_page_served`: GET `/contracts` → 200, chứa `id="step-1"`; GET `/contract_page.js` → 200, `media_type` javascript.
- [ ] **Step 2: Chạy** → FAIL (404).
- [ ] **Step 3: Cài đặt** handler theo mẫu `handle_review_page` / `handle_contracts_js`; `contracts.html` bám style `review.html` (header sticky, nút "Quay lại chat" về `/`, tiêu đề "Hợp đồng — soát từng bước").
- [ ] **Step 4: Chạy** → PASS.
- [ ] **Step 5: Commit** `feat(team-4.2): /contracts page shell`

### Task 4: Bước ① Nạp và stepper

**Files:**
- Modify: `ui/contracts.html`, `ui/contract_page.js`

**Interfaces:**
- Produces trong `contract_page.js`: `state = {cid, card, step}`; `api(path, opts) -> Promise<json>` (ném `Error(json.error)`, giữ `pending` nếu có); `esc(s)`; `goStep(n)`; `loadCard(card)` đặt `state.card` và mở bước ②.
- Consumes: `POST /api/contracts` (multipart `file`, `persist`), `GET /api/contracts?ids=`.

- [ ] **Step 1: Cài đặt** stepper 3 ô (bước đã xong tick xanh, bước chưa mở bị mờ), vùng kéo thả/chọn file (PDF, DOCX, TXT, ảnh scan, tối đa 50 MB, thông điệp lỗi lấy từ API), danh sách hợp đồng đã lưu từ `localStorage` (khóa riêng `ctpage.saved`, bọc try/catch) mở lại qua `GET /api/contracts/{cid}`; thẻ hợp đồng sau nạp: tên file, số điều khoản (`card.units.length`), `graph` đang cập nhật hay lỗi (`card.graph.error`). Cid hết phiên (404) → thông báo `Hợp đồng này đã hết phiên` và ở bước ①.
- [ ] **Step 2: Kiểm tay** `uv run python ui/server.py` (hoặc lệnh chạy app trong README), mở `/contracts`, nạp `data/team-4.2/contracts_demo/hop_dong_thue_nha_2023.txt` → thẻ hiện, stepper chuyển sang ②.
- [ ] **Step 3: Commit** `feat(team-4.2): contracts page step 1 upload`

### Task 5: Bước ② Dữ kiện

**Files:**
- Modify: `ui/contract_page.js`

**Interfaces:**
- Consumes: `state.card.verification` (`fields[]` có `key,label,required,status,value,options?`; `pending[]`; `complete`), `POST /api/contracts/{cid}/facts` (`{answers: {key: {action: "confirm"|"set"|"unknown", value?}}}`), `POST .../party`, `POST .../sign-date` (`{date: "YYYY-MM-DD"}`).
- Produces: `state.userFacts: {name: value}` — dữ kiện người dùng gửi kèm concept-check.

- [ ] **Step 1: Cài đặt** bảng dữ kiện bắt buộc / nên xác nhận với trạng thái từng dòng (tham khảo `verifyHtml`/`collectFacts` trong `contracts.js:246-305`, không import), nút "Xác nhận thông tin" gửi các câu trả lời đã đổi; xong chuyển `state.card` từ phản hồi, `complete` thì mở bước ③. Nút bước ② cũng cho đặt bên ký (`party`) và ngày ký.
- [ ] **Step 2: Thêm khối "Thông tin về người lao động (tùy chọn)"** với các tên `USER_FACTS` (`work_condition`, `pregnant`, `pregnancy_month`, `child_under_12_months`, `employee_consent`, `medical_certificate`, `wage_region`, `employee_is_female`) kèm nhãn tiếng Việt; chỉ đưa vào `state.userFacts` những ô đã điền; ô bool dùng chọn Có/Không/Bỏ trống, `wage_region` chọn I–IV.
- [ ] **Step 3: Kiểm tay** với hợp đồng demo: sửa một dữ kiện, xác nhận, thấy dòng chuyển "đã xác minh".
- [ ] **Step 4: Commit** `feat(team-4.2): contracts page step 2 facts`

### Task 6: Bước ③ Soát

**Files:**
- Modify: `ui/contract_page.js`

**Interfaces:**
- Consumes: `POST /api/contracts/{cid}/concept-check` (Task 1), `POST /api/contracts/{cid}/run` (`{op: "review"}`), `GET /api/contracts/{cid}/reports/{rid}.docx|.pdf`; kết quả concept-check: `report.results[]` (có `concept_id`, `finding`), `report.basis`, `report.warnings`, `report.stats`, `markdown`.

- [ ] **Step 1: Cài đặt** hai nút ("Kiểm tra concept" đứng đầu, "Soát luật"); khi đang chạy khóa cả hai nút và hiện trạng thái "đang chạy… (có thể mất vài phút)"; lỗi hiện thông điệp từ API.
- [ ] **Step 2: Báo cáo concept**: tóm tắt đếm theo `finding`; danh sách kết quả không `ok` kèm căn cứ luật từ `report.basis[concept_id]`; `warnings` hiển thị riêng; nút tải `report.md` (từ `markdown`, tạo Blob) và `report.json`.
- [ ] **Step 3: Báo cáo soát luật**: hiển thị `findings` theo nhóm giống `reportBody` trong `contracts.js:447-480` (viết lại gọn, không import); nút tải docx/pdf. API trả 409 có `pending` → về bước ② và liệt kê `pending[].label`.
- [ ] **Step 4: Kiểm tay** end-to-end trên hợp đồng demo (cả hai nút); thử bấm nhanh hai lần để chắc nút đã khóa.
- [ ] **Step 5: Commit** `feat(team-4.2): contracts page step 3 review`

---

## Self-review

- Spec coverage: route + file tĩnh (T3), stepper và nạp (T4), dữ kiện (T5), hai nút soát (T6), endpoint + dùng chung với script (T1–T2), test endpoint (T1); plugin chat không đụng (Global Constraints).
- Type consistency: `concept_check(...) -> {"report","markdown","graph"}` dùng nhất quán ở T1, T2, T6; `state.userFacts` sinh ở T5, dùng ở T6 (`user_facts` trong body).
- Review Focus: mỗi dòng có chỗ kiểm — T1 test (400/404), T4 (hết phiên), T6 (409 → bước ②, khóa nút), cảnh báo thiếu ngày ký hiển thị ở T6 Step 2.
