# Hỏi đáp trên đồ thị hợp đồng ở /contracts — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trang /contracts có khung hỏi đáp dùng GraphAgent trên đồ thị hợp đồng, stream từng bước.

**Architecture:** `GraphAgent.ask` thêm `history`, `on_step`; `contracts_api.contract_ask` mở đồ thị đã dựng, tạo agent,
trả lời + căn cứ luật có lời văn; SSE dùng chung cơ chế hàng đợi của concept-check; trang vẽ các lượt hỏi.

**Tech Stack:** Python, Starlette SSE, pytest/TestClient, vanilla JS.

**Spec:** `docs/superpowers/specs/2026-11-17-contract-page-graph-qa-design.md`

## Global Constraints
- Không thêm regex/heuristic mới (memory: prefer generalizable).
- `agent.py`, `tools.py`, `view.py` là WIP chưa commit của người dùng: sửa `agent.py` tối thiểu, không commit nó.
- Lỗi stream theo `_error_status`; sự kiện cuối là `done` hoặc `error`.

## Review Focus
- Câu hỏi rỗng / chỉ khoảng trắng → 400, không gọi LLM.
- Hợp đồng chưa Kiểm tra concept → 409 có thông điệp hướng dẫn.
- Đồ thị luật tắt (`legal=None`) → `law` vẫn trả pid, `citation`/`text` = None, không lỗi.
- `history` sai kiểu (không phải list, phần tử không phải dict) → bỏ qua, không lỗi.
- PII trong history → đã che trước khi vào payload LLM.

---

### Task 1: GraphAgent nhận history và báo từng bước

**Files:** Modify `src/rag/contracts/graph/agent.py`; Test `tests/test_contract_graph_agent.py`

**Interfaces — Produces:** `GraphAgent.ask(question: str, history: list[dict] | None = None, on_step: Callable[[dict], None] | None = None) -> GraphAnswer`.
Sự kiện: `{"type": "step", "n": int, "tool": str, "thought": str, "args": dict, "result": str}` (result = `_summary`).
Payload LLM có `"history": [{"query", "answer"}]` (3 lượt cuối, mỗi chuỗi ≤500 ký tự, đã che PII) khi history không rỗng.
AGENT_PROMPT thêm dòng: `- "history" (nếu có): các lượt hỏi đáp trước, dùng để hiểu câu hỏi nối tiếp.`

- [ ] Test `test_on_step_reports_each_tool_call`: DEMO_STEPS → 4 sự kiện, `[e["tool"] ...] == ["find_concept","find_path","contract_facts","check_concept"]`, `n` = 1..4.
- [ ] Test `test_history_is_masked_and_capped`: history 5 lượt, lượt cuối chứa tên người lao động trong DEMO → `seen[0]["history"]` dài 3, tên không xuất hiện; không history → khóa `history` vắng.
- [ ] Chạy thấy fail; cài đặt; `uv run pytest tests/test_contract_graph_agent.py -q` pass. Không commit (WIP người dùng).

### Task 2: contract_ask + endpoint stream

**Files:** Modify `ui/contracts_api.py`; Test `tests/test_contracts_api.py`

**Interfaces — Produces:**
- `contract_ask(cid, question, history=None, user_facts=None, *, on_event=None) -> dict` trả
  `{"answer", "confidence", "path", "law": [{"pid","citation","text"}], "warnings", "trace", "stats"}`.
- `class NeedsConceptCheck(Exception)` → `_error_status` trả `("Hãy chạy Kiểm tra concept trước khi hỏi", 409)`.
- `_events(fn, name) -> queue.Queue` dùng chung cho `concept_check_events` và `contract_ask_events(cid, question, history, user_facts)`.
- Route `POST /api/contracts/{cid}/ask/stream` body `{question, history?, user_facts?}`.
- LLM agent = `CONFIG.llm_factory()`; đồ thị luật = `(CONFIG.legal_graph or _default_legal_graph)()`; lời văn luật qua `legal.text_at(pid, day)` + `citation_text`.

- [ ] Tests: `test_ask_stream_steps_then_done` (stub `GraphAgent` trả GraphAnswer, gọi on_step một lần; đồ thị có ConceptInstance nhờ stub `contract_view`/kiểm tra) → sự kiện `["step","done"]`, `done.answer`; `test_ask_without_concept_check_is_409`; `test_ask_empty_question_is_400`; `test_ask_gone`; `test_ask_law_without_legal_graph` (law pid, citation None).
- [ ] Fail → cài đặt → pass `uv run pytest tests/test_contracts_api.py -q`; commit `ui/contracts_api.py tests/test_contracts_api.py`.

### Task 3: Khung hỏi đáp trên trang

**Files:** Modify `ui/contract_page.js`, `ui/contracts.html` (nếu cần style)

- `state.qa = []` (mỗi lượt `{q, steps: [], done: null, error: ''}`), xóa khi đổi hợp đồng.
- Bước ③ cuối: khi chưa có `state.result` → dòng "Chạy Kiểm tra concept để hỏi về hợp đồng"; có → các lượt + textarea + nút "Hỏi" (Enter gửi, Shift+Enter xuống dòng), khóa khi đang chạy.
- Mỗi lượt: câu hỏi; khi chạy: danh sách bước "⟳ <tool>"; xong: lời đáp (whitespace-pre-wrap), chip tin cậy (answer "Trả lời được", partial "Trả lời một phần", cannot "Không trả lời được"), "Đường đi trên đồ thị" (label → …, text nhỏ), "Căn cứ luật" (citation + text, hoặc pid mờ), cảnh báo, `<details>` "Các bước agent đã đi (n)" liệt kê tool, thought, args (JSON, gồm Cypher), result.
- history gửi = các lượt đã xong `{query, answer}`; đọc SSE dùng chung hàm đọc với concept stream (tách `readSse(res, onEvent)`).
- [ ] `node --check ui/contract_page.js`; commit.

### Task 4: Chạy thật với Neo4j
- [ ] Server + Neo4j: nạp `hdld_tvpl_2025_filled.txt`, Kiểm tra concept, hỏi "Lúc thử việc tôi được trả bao nhiêu? Có đúng luật không?" và một câu đếm (Cypher) qua endpoint; ghi kết quả vào ledger.
