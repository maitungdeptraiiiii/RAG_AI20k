# Kiểm tra concept: stream, lô song song, báo cáo dễ đọc — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kiểm tra concept hiện tiến trình và kết quả sơ bộ ngay khi chạy, các lô LLM chạy song song, và báo cáo là danh sách gọn mở được từng mục, không lộ mã nội bộ.

**Architecture:** `run_batches` chạy lô bằng `ThreadPoolExecutor` (giữ thứ tự) và báo `on_done`; `check_contract` phát sự kiện qua `on_event`; module mới `rag.bridge.view` soạn phần hiển thị; endpoint SSE mới trong `ui/contracts_api.py`; trang `ui/contract_page.js` đọc stream và vẽ danh sách mở rộng.

**Tech Stack:** Python 3.12, `concurrent.futures`, Starlette `StreamingResponse`, pytest; JS thuần (`fetch` + `ReadableStream`).

**Spec:** `docs/superpowers/specs/2026-11-17-concept-check-streaming-ui-design.md`

## Global Constraints

- Không sửa `ui/contracts.js`, `ui/index.html`.
- Không thêm khái niệm, regex hay heuristic; không đoán trích dẫn từ `pid`.
- Kết quả cuối với cùng đầu vào giống bản tuần tự; `run.results` giữ thứ tự lô ban đầu.
- `CONTRACT_BATCH_WORKERS` mặc định 4; 1 = tuần tự.
- Endpoint JSON `POST /api/contracts/{cid}/concept-check` giữ nguyên dạng.

## Review Focus

- Một lô ném `ContractAIError` cả hai lần khi chạy song song: lô vào `run.failed`, các lô khác vẫn có kết quả, `on_done` vẫn đếm tới `total`.
- `CONTRACT_BATCH_WORKERS` không phải số hoặc ≤ 0: dùng 1, không crash.
- Stream bị client đóng giữa chừng: luồng pipeline chạy hết không treo server (hàng đợi không chặn vô hạn).
- Lỗi trong pipeline khi stream (sai `user_facts`, cid hết phiên): sự kiện `error` có `status` 400/404, trang hiện thông báo, nút mở lại.
- Đồ thị luật tắt: `view.law[].citation` là `None`, trang hiện `pid` ở dòng phụ, không lỗi.

---

### Task 1: `run_batches` song song

**Files:**
- Modify: `src/rag/contracts/batches.py:120-131`
- Modify: `.env.example` (thêm `CONTRACT_BATCH_WORKERS=4` kèm chú thích)
- Test: `tests/test_contracts_batches.py` (mới)

**Interfaces:**
- Produces: `run_batches(batches, fn, *, retries: int = 1, workers: int | None = None, on_done: Callable[[int, int], None] | None = None) -> BatchRun`; `batch_workers() -> int` đọc env (lỗi/≤0 → 1).

- [ ] **Step 1: Test thất bại** (dùng lô giả là đối tượng bất kỳ; `fn` ngủ ngẫu nhiên để đảo thứ tự hoàn thành):
  - `test_results_keep_batch_order`: 6 lô, `workers=4` → `[b for b, _ in run.results] == batches`.
  - `test_failed_batch_recorded_others_kept`: `fn` ném `ContractAIError` cho lô 2 mọi lần → `run.failed == [batches[2]]`, 5 kết quả.
  - `test_on_done_counts_to_total`: ghi các `(done, total)` → `sorted(d for d, _ in calls) == [1..6]`, mọi `total == 6`.
  - `test_parallel_is_faster`: 4 lô mỗi lô ngủ 0.2 s, `workers=4` → tổng < 0.5 s.
  - `test_batch_workers_env`: `CONTRACT_BATCH_WORKERS` = `"abc"` → 1; `"0"` → 1; không đặt → 4.
- [ ] **Step 2: Chạy** `uv run pytest tests/test_contracts_batches.py -q` → FAIL.
- [ ] **Step 3: Cài đặt**: `workers == 1` giữ vòng lặp cũ; còn lại `ThreadPoolExecutor(max_workers=min(workers, len(batches)))`, mỗi lô một hàm `_one(b)` làm thử lại như cũ, trả `(b, result | _FAILED)`; gom theo chỉ số để giữ thứ tự; `on_done` gọi trong luồng chính khi mỗi future xong (`as_completed`).
- [ ] **Step 4: Chạy** test Step 2 → PASS; `uv run pytest tests -k "contracts or bridge" -q` xanh.
- [ ] **Step 5: Commit** `perf(team-4.2): run contract batches in parallel`

### Task 2: Sự kiện từ `check_contract`

**Files:**
- Modify: `src/rag/bridge/tagger.py:113-125` (`tag_contract(..., on_progress=None)` → chuyển cho `run_batches(on_done=...)`)
- Modify: `src/rag/bridge/check.py:48-149` (`_CountingLLM` đếm có khóa; `check_contract(..., on_event=None)`)
- Test: `tests/test_bridge_check.py`

**Interfaces:**
- Consumes: `run_batches(on_done=)` (Task 1).
- Produces: `check_contract(..., on_event: Callable[[dict], None] | None = None)`. Chuỗi sự kiện: `stage facts start/done` → `stage tag start` → ≥1 `progress {stage:"tag", done, total}` → `stage tag done` → `stage evaluate start/done` → `partial {results}` → (nếu có kiểm lại) `stage recheck start/done` → `stage basis start/done`. `partial.results` cùng dạng `report_json()["results"]`.

- [ ] **Step 1: Test thất bại** `test_check_contract_emits_events`: dùng fixture/fake LLM sẵn có trong `tests/test_bridge_check.py`, gom sự kiện → các `(type, stage, status)` của `stage` theo thứ tự trên (bỏ `recheck` nếu fixture không kiểm lại); có ít nhất một `progress` với `total ≥ 1`; đúng một `partial`; và báo cáo trả về giống hệt khi gọi không có `on_event` (`report_json` so sánh, bỏ `stats.seconds`).
- [ ] **Step 2: Chạy** → FAIL.
- [ ] **Step 3: Cài đặt**: hàm `emit = on_event or (lambda e: None)`; `partial` phát sau `read_graph()` lần đầu bằng `[asdict(x) for x in results]`; `_CountingLLM.complete` tăng `calls` trong `threading.Lock`.
- [ ] **Step 4: Chạy** → PASS; `uv run pytest tests -k bridge -q` xanh.
- [ ] **Step 5: Commit** `feat(team-4.2): concept check emits stage, progress and partial events`

### Task 3: Dữ liệu hiển thị `rag.bridge.view`

**Files:**
- Create: `src/rag/bridge/view.py`
- Test: `tests/test_bridge_view.py`

**Interfaces:**
- Produces: `result_views(results: list[dict], catalog: Catalog, contract: Contract, basis: dict[str, dict]) -> list[dict]` — mỗi phần tử là result gốc cộng khóa `view = {title, meaning, holder, verdict, law_values: [{key, text}], law: [{pid, citation, text, in_force}], contract: [{label, quote}], missing: [str]}`; `format_value(value, unit) -> str`; `FACT_LABELS: dict[str, str]` (đủ tên trong `USER_FACTS` ∪ `CONTRACT_FACTS`); `VERDICTS: dict[str, str]` theo `finding` (gồm `ok`).

- [ ] **Step 1: Test thất bại**:
  - `test_format_value`: `(150,"percent")→"150%"`, `(30,"day")→"30 ngày"`, `(14,"workday")→"14 ngày làm việc"`, `(60,"minute")→"60 phút"`, `(5000000,"vnd")→"5.000.000 đồng"`, `(3,None)→"3"`.
  - `test_fact_labels_cover_catalog`: `set(FACT_LABELS) >= USER_FACTS | set(CONTRACT_FACTS)`.
  - `test_view_for_hidden_right`: với `load_catalog()` và một result `probation.cancel_no_notice` finding `hidden_right`, evidence rỗng, basis có anchor `provision={"in_force":True,"citation":"Khoản 2 Điều 27 …","text":"…"}` → `view.title == concept.label`, `view.verdict == VERDICTS["hidden_right"]`, `view.contract == []`, `view.law[0].citation` đúng.
  - `test_view_without_legal_graph`: anchor `provision=None` → `view.law[0] == {"pid": pid, "citation": None, "text": None, "in_force": None}`.
  - `test_missing_slot_label`: `missing_facts` chứa tên slot của khái niệm → nhãn là `f"{concept.label} (nội dung trong hợp đồng)"`; tên dữ kiện → `FACT_LABELS[name]`.
- [ ] **Step 2: Chạy** `uv run pytest tests/test_bridge_view.py -q` → FAIL.
- [ ] **Step 3: Cài đặt** theo spec §4; `holder` lấy `catalog.roles[concept.holder]["label"]`; nhãn đoạn hợp đồng từ `contract.units` theo `uid` (không có thì `uid`).
- [ ] **Step 4: Chạy** → PASS.
- [ ] **Step 5: Commit** `feat(team-4.2): readable views for concept check results`

### Task 4: Endpoint stream

**Files:**
- Modify: `ui/contracts_api.py` (`concept_check_events`, `handle_concept_check_stream`, route; `concept_check` JSON thêm `views`)
- Test: `tests/test_contracts_api.py`

**Interfaces:**
- Consumes: `check_contract(on_event=)` (Task 2), `result_views` (Task 3).
- Produces: `concept_check_events(cid, user_facts) -> Iterator[dict]` — các sự kiện Task 2 (với `partial` thêm `views`), kết thúc bằng `{"type":"done", "report", "markdown", "labels", "graph", "views"}` hoặc `{"type":"error","error","status"}`; route `POST /api/contracts/{cid}/concept-check/stream` (`text/event-stream`, mỗi sự kiện `data: <json>\n\n`).

- [ ] **Step 1: Test thất bại** (stub `check_contract` gọi `on_event` vài sự kiện rồi trả `CheckReport`):
  - `test_stream_emits_events_then_done`: đọc thân phản hồi, tách các dòng `data:` → loại đầu là `stage`, cuối là `done`, `done.report.contract_id == cid`, `"views" in done`.
  - `test_stream_unknown_fact_error_event`: không stub, `user_facts={"abc":1}` → sự kiện cuối `{"type":"error","status":400}`.
  - `test_stream_gone`: cid `nope` → sự kiện `error` `status == 404`.
- [ ] **Step 2: Chạy** → FAIL.
- [ ] **Step 3: Cài đặt**: luồng nền chạy phần thân của `concept_check` với `on_event=queue.put`; lỗi ánh xạ status như `_call` (KeyError 404, ValueError 400, ContractAIError 502, khác 500); handler là async generator đọc hàng đợi qua `run_in_executor(None, q.get)`; hàng đợi không giới hạn để luồng không bị chặn khi client đóng. Rút phần chung với `concept_check` để không lặp code.
- [ ] **Step 4: Chạy** `uv run pytest tests/test_contracts_api.py -q` → PASS.
- [ ] **Step 5: Commit** `feat(team-4.2): streaming concept-check endpoint`

### Task 5: Trang — tiến trình và báo cáo mở rộng

**Files:**
- Modify: `ui/contract_page.js` (thay `conceptReport` và nhánh `concept` của `runOp`), `ui/contracts.html` (style nếu cần)

**Interfaces:**
- Consumes: SSE Task 4; `views` Task 3.

- [ ] **Step 1: Cài đặt** đọc stream: `fetch(.../concept-check/stream)`, đọc `res.body.getReader()`, tách theo `\n\n`, parse `data:`; cập nhật `state.progress` và vẽ lại mỗi sự kiện.
- [ ] **Step 2: Thanh tiến trình** 5 bước (Đọc hợp đồng · Gán khái niệm (n/m lô) · Đánh giá · Kiểm lại · Căn cứ luật) với ✔/⟳/mờ.
- [ ] **Step 3: Báo cáo**: chip đếm theo nhóm (bấm để lọc, "Không có vấn đề" thu gọn mặc định); mỗi mục là `<details>` với dòng tóm tắt `view.title` + `view.verdict`; phần mở: Ý nghĩa (`verdict`, `meaning`, `holder`) → Hợp đồng (trích hoặc "Không có điều khoản nào nhắc") → Luật (`citation` + `text`, `law_values[].text`; không có `citation` thì `pid` mờ) → Thiếu dữ kiện (`missing`, nút "Bổ sung ở bước ②") → dòng phụ nhỏ `concept_id/rule_id`. Khi chỉ có `partial`: nhãn "Sơ bộ — đang kiểm lại…".
- [ ] **Step 4: Kiểm** `node --check ui/contract_page.js`; chạy app, mở `/contracts`, chạy trên `data/team-4.2/contracts_demo/hdld_tvpl_2025_filled.txt`: thấy tiến trình chạy dần, kết quả sơ bộ rồi cuối, mở được một mục.
- [ ] **Step 5: Commit** `feat(team-4.2): contracts page streams concept check with expandable report`

### Task 6: Chạy thật với Neo4j

- [ ] **Step 1:** Neo4j đã chạy (`docker ps` có `docker-neo4j-1` Up), cổng 7687 mở; kiểm đồ thị luật đã công bố (`LegalGraph(open_store()).text_at("bo-luat:45/2019/QH14#d27.k2", date(2025,1,2))` trả `in_force: True`). Chưa công bố → chạy script công bố đồ thị luật có sẵn của dự án (tìm trong `scripts/`), ghi lại lệnh.
- [ ] **Step 2:** Chạy stream qua API trên hợp đồng mẫu; ghi thời gian tổng (so với lần tuần tự trước) và xác nhận `view.law[].citation` không rỗng.
- [ ] **Step 3:** Ghi kết quả vào `docs/superpowers/notes/2026-11-17-concept-check-streaming-run.md`; commit `docs(team-4.2): concept check streaming run with legal graph`.
