# Rule engine giai đoạn 4: giải thích, câu hỏi gợi ý, sự kiện diff — Kế hoạch

> Thực thi bằng superpowers:executing-plans (Native). Spec: `docs/superpowers/specs/2026-11-22-rete-rule-engine-design.md` §8, §11 giai đoạn 4. Checklist D17–D19.

**Goal:** `explain()` (cây tới quote hợp đồng, nguồn giá trị luật, ngoại lệ bị loại; JSON + markdown), `next_questions()` (fork + update), sự kiện stream `evaluation_diff`.

**Gate** như giai đoạn 3 (cả hai evaluator); golden không đổi. Sổ tiến độ: `.superpowers/sdd/2026-11-23-rule-engine-phase4-explain-questions/progress.md`.

## Quyết định của kế hoạch

- Phiên (cả hai evaluator) thêm `facts() -> Facts` (bảng đã gộp dữ kiện suy ra, bản sao) và thuộc tính `day`; hai evaluator phải trả bảng giống nhau (test).
- `explain(catalog, session, concept_id, rule_id) -> ExplanationNode`; `ExplanationNode(kind, label, status, detail, children)` với `to_json()` và `to_markdown()`. Chỉ đọc kết quả + bảng dữ kiện, không đổi ngữ nghĩa.
- Miền giá trị câu hỏi do pack khai: `user_fact_questions: {<dữ kiện>: {question, values: [...], unit?}}` trong `pack.yaml` (đưa vào `Context.questions`, gộp qua extends). Dữ kiện người dùng không khai miền thì không được gợi ý (ghi vào danh sách hạn chế).
- Điểm câu hỏi: `guaranteed` = số kết quả UNKNOWN chắc chắn thành xác định qua mọi giá trị (nhỏ nhất); `possible` = lớn nhất. Xếp theo (`guaranteed`, `possible`) giảm dần; bỏ câu hỏi có `possible == 0`.
- `evaluation_diff` phát khi phiên được `update` (sau recheck): `{type, changes: [{concept_id, rule_id, before, after}], stats}` với `before/after = {status, finding, reasons, missing_facts}`.

## Task 1: Truy cập bảng dữ kiện + `explain.py`
Files: `rules/evaluator.py`, `rules/network/session.py` (thêm `facts()`, `day`), `rules/explain.py` (mới), test `tests/test_rules_explain.py`.
- Test: hai evaluator cho `facts()` bằng nhau (có dữ kiện suy ra); `explain` cho `content.term/r4` (FAIL do dữ kiện suy ra) có nút dữ kiện suy ra với `derived_by == "d20k2b"`, anchors, và ngoại lệ bị loại; `content.term/r3` bị `overridden_by` có nút ngoại lệ; rule có `cases` hiện case được chọn và nguồn kỳ giá trị luật; dữ kiện hợp đồng mang `uid`/`quote`/`amended_from`; markdown chứa các dòng chính; JSON round-trip.
- Impl: `explain_cond` đệ quy qua all/any/not, mỗi lá ghi dữ kiện, toán tử, vế phải, Tri (dùng `eval_cond` / `check_cond` hiện có).

## Task 2: `questions.py` + `user_fact_questions`
Files: `rules/model.py` (`UserQuestion`, `Context.questions`, `PackSpec.user_fact_questions`), `rules/loader.py`, `rules/questions.py`, `packs/labor/pack.yaml`, test `tests/test_rules_questions.py`.
- Test: gói tổng hợp: câu hỏi quyết định được nhiều kết quả xếp trước; dữ kiện không khai miền bị bỏ qua; bool, số có đơn vị; `fork` không đổi phiên gốc; bộ nạp kiểm tên có trong `user_facts`, `values` không rỗng, đơn vị hợp lệ; labor: với HĐ xác định thời hạn đã hết hạn, câu hỏi gợi ý đầu tiên liên quan Đ20.2 (`worked_after_expiry_days` hoặc `new_contract_signed`).

## Task 3: `evaluation_diff` trong `check_contract`
Files: `rules/events.py` (`diff_event`), `bridge/check.py`, test `tests/test_rules_events.py` + ca trong test check hiện có.
- Test: `diff_event` định dạng; `check_contract` với `on_event` phát `evaluation_diff` sau recheck và không phát lần đầu.

## Task 4: Tài liệu, checklist D17–D19, bảng hạn chế
