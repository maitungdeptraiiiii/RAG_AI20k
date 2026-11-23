# Human-in-the-loop cho bước Kiểm tra concept — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dữ kiện còn thiếu sau khi soát được hỏi lại người dùng bằng câu có đáp án chọn sẵn, lấy từ gói luật đang dùng; trả lời xong chỉ chạy lại rule, không gọi LLM.

**Architecture:** Biểu mẫu dữ kiện người dùng sinh từ `Context.questions` / `input_units` của gói (không còn danh sách viết cứng trong UI). `check_contract` trả thêm `questions` (từ `next_questions` trên phiên đánh giá cuối) và có chế độ `rules_only` đọc lại đồ thị đã có rồi chạy lại rule. UI vẽ câu hỏi và gửi câu trả lời qua một endpoint mới.

**Tech Stack:** Python 3 (Starlette, pytest, uv), YAML pack, JS thuần trong `ui/`.

**Spec:** không có spec riêng; căn cứ là phân tích luồng trong phiên 2026-11-24 (mục "Còn thiếu" 1, 2, 6) và `docs/superpowers/notes/w04-rule-engine/han_che_va_loi_ton_dong.md`.

## Global Constraints

- Chạy lệnh từ `app/team-4.2`: `uv run pytest tests/<file> -q`.
- Chú thích, docstring, thông báo cho người dùng viết tiếng Việt, theo giọng các file xung quanh.
- Không thêm regex / heuristic mới; tên dữ kiện, câu hỏi, giá trị, nhãn đều lấy từ pack (memory: ưu tiên tổng quát hơn regex).
- UI không giữ danh sách dữ kiện cố định: mọi thứ hiện ra do server trả.
- Pack `labor` phải giữ nguyên kết quả của mọi test hiện có (golden, bench, fixtures rete).
- `ui/contracts_api.py`, `ui/contract_page.js`, `ui/contracts.js` đang có thay đổi chưa commit của người dùng (gỡ `run`/review, thêm `answer.py`): chỉ sửa đúng chỗ cần, không commit các file này; báo lại cho người dùng.

## Review Focus

- Gói không khai `user_fact_questions` (vd. `civil_loan`, `user_facts: []`): biểu mẫu rỗng, UI không vẽ khung "Thông tin thêm".
- Dữ kiện người dùng không có câu hỏi và không có đơn vị: rơi về ô văn bản, giá trị gửi lên là chuỗi.
- Trả lời câu hỏi cho hợp đồng chưa từng kiểm tra: 409 với thông điệp rõ, không 500.
- Trả lời với tên dữ kiện lạ: 400 (cùng đường với `user_fact_set`).
- Người dùng trả lời hai lần, lần sau thắng và các câu trả lời trước không mất.

---

### Task 1: Nhãn lựa chọn cho câu hỏi của gói

**Files:**
- Modify: `src/rag/rules/model.py:92-98` (`UserQuestion`), `src/rag/rules/loader.py:283-299`
- Modify: `src/rag/rules/packs/labor/pack.yaml:63-80`
- Test: `tests/test_rules_questions.py`

**Interfaces:**
- Produces: `UserQuestion.labels: tuple[tuple[Any, str], ...] = ()` — cặp (giá trị, nhãn hiển thị); rỗng thì UI dùng chính giá trị.
- Produces: pack `labor` có thêm câu hỏi cho `work_condition`, `wage_region`, `pregnancy_month`.

- [ ] **Step 1: Viết test hỏng** trong `tests/test_rules_questions.py`: `test_question_labels_are_loaded` dùng `write_pack` với `"a": {"question": "A?", "values": ["x", "y"], "labels": {"x": "Nhãn X"}}` và khẳng định `catalog.context.questions["a"].labels == (("x", "Nhãn X"),)`; `test_question_label_for_unknown_value_is_rejected` với `labels: {"z": "Z"}` ném `CatalogError`.
- [ ] **Step 2: Chạy** `uv run pytest tests/test_rules_questions.py -q`, mong đợi FAIL (`labels` chưa có).
- [ ] **Step 3: Thêm trường `labels` vào `UserQuestion`** (mặc định `()`), và trong `loader.py` đọc `q.get("labels")`: phải là dict mà mọi khóa nằm trong `values`, nếu không thì thêm vào `problems` theo dạng câu lỗi quanh đó.
- [ ] **Step 4: Thêm câu hỏi vào `labor/pack.yaml`**: `work_condition` (values `binh_thuong`, `nang_nhoc_doc_hai`, `dac_biet_nang_nhoc` — các giá trị `concepts.yaml:717-719` đang so; labels tiếng Việt), `wage_region` (values `I`..`IV`), `pregnancy_month` (values `[3, 8]` quanh ngưỡng `gte 7` ở `concepts.yaml:958`).
- [ ] **Step 5: Chạy** `uv run pytest tests/test_rules_questions.py tests/test_rules_pack.py tests/test_rules_packs_merge.py tests/test_rete_dossiers.py -q`, mong đợi PASS. Ca nào lệch vì `next_questions` giờ hỏi thêm dữ kiện thì sửa kỳ vọng đúng nơi đó, ghi lý do.
- [ ] **Step 6: Commit** `feat(team-4.2): câu hỏi của gói có nhãn lựa chọn; labor khai work_condition, wage_region, pregnancy_month`.

### Task 2: Biểu mẫu dữ kiện người dùng sinh từ gói

**Files:**
- Create: `src/rag/bridge/user_form.py`
- Modify: `ui/contracts_api.py` (`card`), `ui/contract_page.js` (`USER_FACTS`, `userFactInput`, `collectUserFacts`, `renderStep2`)
- Test: `tests/test_user_form.py`, `tests/test_contracts_api.py`

**Interfaces:**
- Produces: `user_fact_fields(catalog: Catalog) -> list[dict]`, mỗi phần tử `{"key", "label", "kind": "bool"|"number"|"choice"|"text", "question": str|None, "unit": str|None, "options": [{"value", "label"}]}` (`options` chỉ có khi `kind == "choice"`).
  Quy tắc `kind`: có `UserQuestion` thì theo `values` (toàn bool → `bool`, toàn số → `number`, còn lại → `choice`); không có thì có đơn vị → `number`, không có → `text`. Thứ tự: dữ kiện có câu hỏi theo thứ tự khai trước, còn lại theo nhãn.
  Tập tên = `catalog.context.input_units` trừ `catalog.context.document_facts`.
- Produces: `card(c)["user_form"]: list[dict]` tính từ `_catalog_or_labor(c)`.

- [ ] **Step 1: Viết test hỏng** `tests/test_user_form.py`: với pack tổng hợp (`write_pack`) gồm bool, số có đơn vị, lựa chọn chuỗi, và một dữ kiện không câu hỏi/không đơn vị, khẳng định `kind`, `options`, `label` (từ `catalog.fact_label`), thứ tự; với pack `civil_loan` khẳng định `[]`; với `load_catalog()` (labor) khẳng định có `fixed_term_contract_count` kiểu `number` (values `[1, 3]`), `wage_region` kiểu `choice`, `pregnant` kiểu `bool`, và không chứa `sign_date`, `term_months` (dữ kiện hợp đồng).
- [ ] **Step 2: Chạy** `uv run pytest tests/test_user_form.py -q`, mong đợi FAIL (module chưa có).
- [ ] **Step 3: Viết `user_fact_fields`** theo quy tắc ở Interfaces.
- [ ] **Step 4: Chạy lại**, mong đợi PASS.
- [ ] **Step 5: Test hỏng ở API** trong `tests/test_contracts_api.py`: `test_card_has_user_form_from_pack` — tạo hợp đồng bằng fixture `client` hiện có, khẳng định `card["user_form"]` là list và mỗi phần tử có `key`, `label`, `kind`.
- [ ] **Step 6: Thêm `"user_form": user_fact_fields(_catalog_or_labor(c))` vào `card()`**; chạy test API, mong đợi PASS.
- [ ] **Step 7: UI** — bỏ hằng `USER_FACTS`; `renderStep2` vẽ từ `c.user_form` (ẩn cả khung khi rỗng); `kind` `choice` vẽ `<select>` với `options`, `bool` giữ Có/Không, `number` ô số, `text` ô chữ; `collectUserFacts` đọc cùng danh sách; tiêu đề đổi thành "Thông tin thêm (tùy chọn — dùng cho Kiểm tra concept)". Kiểm tay: tạo hợp đồng lao động, bước ② hiện đủ 14 dữ kiện, không còn ô nhập mã `binh_thuong`.
- [ ] **Step 8: Commit** chỉ `src/rag/bridge/user_form.py` và `tests/test_user_form.py`; các file `ui/` giữ lại chưa commit (xem Global Constraints).

### Task 3: Hỏi lại dữ kiện thiếu và chạy lại chỉ rule

**Files:**
- Modify: `src/rag/bridge/check.py` (`CheckReport`, `check_contract`, `report_json`), `ui/contracts_api.py`, `ui/contract_page.js`
- Test: `tests/test_bridge_check.py`, `tests/test_contracts_api.py`

**Interfaces:**
- Consumes: `next_questions(catalog, session) -> list[Question]` (`rules/questions.py`), `user_fact_fields` (Task 2).
- Produces: `CheckReport.questions: list[dict]` — `{"fact", "question", "unit", "guaranteed", "possible", "options": [{"value", "label"}]}` lấy từ `dataclasses.asdict(Question)` cộng nhãn của Task 1; có trong `report_json(report)["questions"]` và trong kết quả `concept_check`.
- Produces: tham số `rules_only: bool = False` của `check_contract`: bỏ qua bước trích dữ kiện, gán khái niệm và kiểm lại (không gọi LLM), chỉ `read_graph` + chạy rule với `user_facts` mới.
- Produces: `contracts_api.answer_questions(cid: str, answers: dict) -> dict` và `POST /api/contracts/{cid}/concept-check/answer` body `{"answers": {fact: value}}` -> cùng dạng kết quả `concept_check`. Câu trả lời được cộng vào `c.concept_check["user_facts"]` (lần sau thắng); chưa từng kiểm tra -> `ValueError(NEEDS_CHECK)` đi đường 409 sẵn có.

- [ ] **Step 1: Test hỏng** `test_report_has_questions_for_unknown_results` trong `tests/test_bridge_check.py` (mẫu hợp đồng của file đó, gói labor): khẳng định `report.questions` không rỗng khi còn kết quả `needs_facts`/`possible_right` và mỗi phần tử có `fact` thuộc `catalog.context.questions`.
- [ ] **Step 2: Test hỏng** `test_rules_only_makes_no_llm_calls_and_applies_answers`: chạy `check_contract` đầy đủ, rồi chạy lại với `rules_only=True` và `user_facts` có câu trả lời của câu hỏi đứng đầu; khẳng định `stats["llm_calls"] == 0` và số kết quả `UNKNOWN` giảm.
- [ ] **Step 3: Chạy hai test**, mong đợi FAIL.
- [ ] **Step 4: Cài `CheckReport.questions` và `rules_only`** trong `check_contract`; `questions` tính sau lần `read_graph` cuối từ `session_state["session"]`. Với `rules_only`, `session` mới vẫn dựng từ `read_graph()` (đồ thị đã nằm trong oplog).
- [ ] **Step 5: Chạy lại hai test**, mong đợi PASS; chạy cả `tests/test_bridge_check.py`.
- [ ] **Step 6: Test hỏng ở API**: `test_answer_endpoint_runs_rules_only` (không gọi LLM thứ hai, `views` đổi theo câu trả lời), `test_answer_without_prior_check_is_409`, `test_answer_unknown_fact_is_400`, `test_answers_accumulate` (trả lời hai lần giữ cả hai).
- [ ] **Step 7: Cài `answer_questions`, `handle_answer` và Route**; chạy test API, mong đợi PASS.
- [ ] **Step 8: UI** — dưới kết quả hiện khung "Câu hỏi gợi ý" từ `result.report.questions`: mỗi câu là `<select>` các `options`, chọn xong gọi endpoint và thay `state.result`; không chặn xem kết quả cũ khi chưa trả lời. Kiểm tay trên hợp đồng lao động có `possible_right`.
- [ ] **Step 9: Commit** chỉ `src/rag/bridge/check.py` và các test của nó; file `ui/` giữ lại chưa commit.

---

## Việc kế tiếp (kế hoạch riêng, chưa làm)

Cần đọc thêm code trước khi chốt chi tiết nên không đưa vào đây: (4) hiện `searched_uids` của `concept_absent` và cho người dùng ghi "hợp đồng có ghi ở đoạn…" bằng thao tác của người; (5) thiếu slot thì mở thẳng đoạn văn để nhập giá trị; (6) trường `extract_fields` của gói hiện ở bước ② (`verify.specs_for` chỉ biết `fact_catalog.json`).
