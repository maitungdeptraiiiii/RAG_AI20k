# Rule engine giai đoạn 3: dữ kiện suy ra và ngoại lệ giữa rule — Kế hoạch triển khai

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm `derived` (dữ kiện suy ra có cây ngoại lệ, spec §5.3) và `exception_of` giữa rule (§5.4) vào cả `ReferenceEvaluator` lẫn `NetworkEvaluator`, rồi viết rule thật cho Điều 20.2 BLLĐ 45/2019.

**Architecture:** Hai hàm thuần mới (`rules/derived.py`, `rules/exceptions.py`) dùng chung cho hai evaluator, như `semantics.py`. Dữ kiện suy ra được tính vào cùng bảng dữ kiện mà lá điều kiện đọc (ghi đè dữ kiện cùng tên), nên mạng điều kiện giai đoạn 2 không đổi; phiên mạng chỉ thêm bước "tính lại dữ kiện suy ra theo thứ tự topo rồi coi tên đổi như dữ kiện đổi". Ngoại lệ giữa rule là bước hậu xử lý kết quả cơ sở của từng rule.

**Tech Stack:** Python 3.11+, PyYAML, pytest (chạy trong `app/team-4.2`).

**Spec:** `app/team-4.2/docs/superpowers/specs/2026-11-22-rete-rule-engine-design.md` §5.3, §5.4, §6.3, §10, §11 giai đoạn 3. Văn bản luật đã đọc: `data/team-4.2/legal/raw/bo-luat_45_2019_QH14/*.txt` dòng 135–142 (Điều 20), Điều 149.1, 151.2, 177.4.

## Global Constraints

- Mọi test cũ và golden (`tests/fixtures/rules/golden/engine_results.json`, 2571 ca) giữ nguyên kỳ vọng. Rule cũ không tham chiếu dữ kiện suy ra nên `facts_used` / `missing_facts` của chúng không đổi.
- Hai evaluator cho kết quả giống hệt (đối chiếu ngẫu nhiên, có `derived` và `exception_of`).
- Bất biến: thiếu dữ kiện không bao giờ thành `FAIL`. Dữ kiện suy ra `UNKNOWN` xử lý như `CONFLICT` ở lá (mọi so sánh ra `U`).
- Dữ kiện đầu vào truyền vào có trùng tên dữ kiện suy ra thì bị bỏ qua (cả hai evaluator); dữ kiện suy ra luôn do định nghĩa quyết định.
- Thông báo lỗi, docstring, ghi chú: tiếng Việt, như code hiện có. Không thêm regex hay heuristic mới.
- Gate: `uv run pytest tests/test_rules_*.py tests/test_bridge_*.py tests/test_contract_graph_tools.py tests/test_ask_contract_graph.py tests/test_contract_graph_agent.py tests/test_contracts_api.py -q -p no:cacheprovider`, chạy cả với `RAG_RULE_EVALUATOR=reference`. Xanh trước mỗi commit (cơ sở: 424 passed, 1 skipped, 1 xfailed). Toàn bộ suite có 35 test fail có sẵn (`reports/team-4.2/w04/phase1_baseline.md`), chạy với `--ignore=tests/test_agent_partial_review.py`.

## Quyết định của kế hoạch (ghi vào ledger là `Ruling:` khi thực hiện)

- **Đ22.2 và phần "một lần một công việc" của Đ25 không làm ở giai đoạn này.** Cả hai cần đối tượng phụ lục / nhiều hợp đồng (a1, b5); chỉ có chỗ dùng ở giai đoạn 7b. Đ25 theo từng văn bản đã có (`probation.duration`, `probation.once`). Checklist D16 ghi lại việc này.
- **Giới hạn số lần ký HĐ xác định thời hạn (Đ20.2.c) viết bằng dữ kiện vô hướng `fixed_term_contract_count` do người dùng cung cấp**; giai đoạn 7b thay nguồn bằng phép đếm đối tượng, không đổi rule.
- **Điều kiện chuyển thành không xác định thời hạn dùng `worked_after_expiry_days > 30 day`** (Đ20.2.b: "hết thời hạn 30 ngày kể từ ngày hết hạn"; đúng 30 ngày vẫn trong thời hạn ký). Rủi ro nếu sai: ca biên đúng 30 ngày.
- **Con CONFLICT của một nút định nghĩa thắng giá trị của anh em** (spec §5.3 bước 1 chỉ nói "khác nhau → CONFLICT"; chọn thận trọng). Con UNKNOWN thì thua giá trị (đúng chữ spec, xem Review Focus 1).
- **Ngoại lệ giữa rule: "áp dụng" = applicability T và giá trị luật chọn được** (cả hai T); F nếu applicability F hoặc không case nào khớp; còn lại U. Ngoại lệ lồng nhau: một rule coi là áp dụng nếu bản thân nó hoặc bất kỳ ngoại lệ (kể cả gián tiếp) của nó áp dụng (như cây ngoại lệ Catala).
- **`evaluate_concept` (từng concept) chỉ áp dụng ngoại lệ giữa các rule cùng concept**; ngoại lệ chéo concept chỉ có ở `evaluate_all` và phiên. Rule labor giai đoạn này đặt ngoại lệ cùng concept `content.term`.
- Cạnh `exception_of` chéo gói chỉ kiểm tồn tại ở `load_packs` (sau khi gộp).

## Review Focus

1. Nút có một ngoại lệ cho giá trị và một ngoại lệ khác `UNKNOWN` → ra giá trị (đúng chữ §5.3). Ghim bằng bảng chân lý Task 2.
2. Dữ kiện đầu vào trùng tên dữ kiện suy ra bị bỏ qua và không làm hai evaluator lệch (Task 5).
3. Dữ kiện đầu vào đổi `1` ↔ `True` làm dữ kiện suy ra tính lại (Task 5; lỗi tương tự đã gặp ở giai đoạn 2).
4. Ngoại lệ lồng nhau: rule gốc bị thay thế khi chỉ ngoại lệ của ngoại lệ áp dụng (Task 3).
5. `missing_facts` mở dữ kiện suy ra thành dữ kiện đầu vào còn thiếu, và thêm dữ kiện của ngoại lệ chưa quyết định khi rule gốc `FAIL` bị hạ (Task 4).

## Cấu trúc file

| File | Vai trò |
|---|---|
| `src/rag/rules/model.py` (sửa) | `Definition`, `DerivedFact`; `PackSpec.derived`, `Context.derived`, `Rule.exception_of`, `Fact.derived_by` (ở `semantics.py`) |
| `src/rag/rules/derived.py` (mới) | `derived_order`, `derived_inputs`, `eval_derived`, `derive_all`, `missing_inputs` |
| `src/rag/rules/exceptions.py` (mới) | `ExceptionIndex`, `rule_state`, `applies_states`, `Override`, `finalize`, `exception_open` |
| `src/rag/rules/loader.py` (sửa) | nạp / kiểm `derived`, `exception_of`; gộp gói |
| `src/rag/rules/semantics.py` (sửa) | `Fact.derived_by`, `_result` mở `missing_facts`, `facts_used` |
| `src/rag/rules/reference.py` (sửa) | `evaluate_rules` chung cho `evaluate_concept` / `evaluate_all` |
| `src/rag/rules/network/{network,session}.py` (sửa) | chỉ mục phụ thuộc mới; phiên tính lại dữ kiện suy ra và ngoại lệ |
| `src/rag/rules/packs/labor/{pack,concepts}.yaml` (sửa) | rule Đ20.2 |
| `src/rag/bridge/view.py` (sửa) | nhãn cho dữ kiện người dùng mới |
| `tests/rules_synth.py` (mới) | `write_pack(root, pack, concepts)` ghi gói tổng hợp vào thư mục tạm cho test |

---

### Task 1: Khai báo `derived` trong pack.yaml và bộ nạp

**Files:**
- Modify: `src/rag/rules/model.py`, `src/rag/rules/loader.py`
- Test: `tests/test_rules_derived_loader.py` (mới), `tests/rules_synth.py` (mới)

**Interfaces:**
- Produces (model.py):
  - `@dataclass(frozen=True) class Definition: id: str; when: dict | None; exception_of: str | None; from_fact: str | None; has_value: bool; value: Any; anchors: tuple[dict, ...] = ()` (YAML `from` → `from_fact`; `has_value` = YAML có khóa `value`).
  - `@dataclass(frozen=True) class DerivedFact: fact: str; unit: str | None; definitions: tuple[Definition, ...]`.
  - `PackSpec.derived: Mapping[str, DerivedFact]` và `Context.derived: Mapping[str, DerivedFact]`, cả hai là field cuối với `default_factory=dict`; `PackSpec.context()` truyền `derived`.
- Produces (tests/rules_synth.py): `write_pack(root: Path, pack: dict, concepts: dict | None = None, pack_id: str | None = None) -> str` ghi `root/<id>/pack.yaml` (+ `concepts.yaml` nếu có) bằng `yaml.safe_dump(allow_unicode=True)`, trả về id. `pack` mặc định gộp `{"id", "version": "t", "extends": [], "document_kinds": ["x"], "units": ["day", "count"], "conversions": {"day": {"base": "day", "factor": 1}}, "document_facts": {}, "user_facts": [], "findings": []}` với các khóa người gọi truyền.

- [ ] **Step 1: Viết test lỗi** trong `tests/test_rules_derived_loader.py`, mỗi test dùng `write_pack` + `load_pack` / `load_packs(root=tmp_path)`:
  - `test_derived_loaded_from_pack_yaml`: pack khai `derived: [{fact: kind_eff, unit: null, definitions: [{id: base, from: kind}, {id: x, exception_of: base, when: {fact: a, op: eq, value: 1}, value: k2, anchors: [{pid: "p#d1", role: basis}]}]}]` → `spec.derived["kind_eff"].definitions[0].from_fact == "kind"`, `definitions[1].exception_of == "base"`, `has_value` đúng, `definitions[0].when is None`.
  - `test_derived_problems_reported_together`: một pack có đồng thời id định nghĩa trùng, `exception_of` trỏ id không có, định nghĩa vừa có `from` vừa có `value`, định nghĩa không có `from` lẫn `value`, đơn vị lạ, tên trùng một `user_facts` → `CatalogError` có ≥ 5 `problems`, mỗi lỗi nêu tên dữ kiện và id định nghĩa.
  - `test_derived_cycle_between_facts_rejected`: `a` có `from: b`, `b` có `when` đọc `a` → lỗi chứa chữ `vòng` và cả hai tên.
  - `test_exception_of_cycle_inside_one_fact_rejected`: hai định nghĩa trỏ `exception_of` lẫn nhau.
  - `test_derived_merged_across_extends_and_duplicates_rejected`: gói con `extends: [cha]` thấy `derived` của cha (`load_packs(["con"]).context.derived` có tên của cả hai); hai gói cùng khai tên suy ra → lỗi `trùng`.
  - `test_derived_name_clashing_with_slot_or_fact_rejected_with_concepts`: `concepts.yaml` có slot trùng tên dữ kiện suy ra → `load_packs` lỗi; rule dùng tên dữ kiện suy ra trong `check` / `applicability` thì hợp lệ (không báo "không phải slot, dữ kiện hợp đồng hay người dùng"); `derived` tham chiếu dữ kiện không ai khai → lỗi.
- [ ] **Step 2: Chạy, xác nhận FAIL** — `uv run pytest tests/test_rules_derived_loader.py -q -p no:cacheprovider`. Expected: lỗi vì thiếu `derived` (không phải lỗi cú pháp test).
- [ ] **Step 3: Thêm `Definition`, `DerivedFact`, field `derived` vào `model.py`.**
- [ ] **Step 4: Trong `loader.py`:** `load_pack` đọc khóa `derived` → `PackSpec.derived`, kiểm: id định nghĩa duy nhất; `exception_of` trỏ id cùng dữ kiện; không vòng `exception_of`; đúng một trong `from` / `value`; `unit` nằm trong `units`; tên không trùng `document_facts` / `user_facts` của chính pack; mọi lá trong `when` có `op` thuộc `OPS`. Tính phụ thuộc giữa các dữ kiện suy ra (qua `from` và lá `when`) và báo vòng bằng `derived_order` (Task 2 cung cấp; ở bước này cài tạm hàm phát hiện vòng nội bộ trong `loader.py` rồi Task 2 chuyển sang gọi `derived_order`). `_merge_packs` gộp `derived` (trùng tên giữa các gói → lỗi) và chạy lại kiểm vòng trên bản gộp. `load_concepts` thêm `set(pack.derived)` vào tập `known` của `_rule` (lá và `by`), báo lỗi khi slot trùng tên dữ kiện suy ra, và kiểm mọi dữ kiện mà định nghĩa dùng (`from`, lá `when`) là slot / dữ kiện hợp đồng / người dùng / dữ kiện suy ra khác.
- [ ] **Step 5: Chạy** `uv run pytest tests/test_rules_derived_loader.py tests/test_rules_loader.py tests/test_rules_pack.py tests/test_rules_packs_merge.py -q -p no:cacheprovider`. Expected: PASS.
- [ ] **Step 6: Commit** — `git add src/rag/rules/model.py src/rag/rules/loader.py tests/rules_synth.py tests/test_rules_derived_loader.py && git commit -m "feat(team-4.2): rules - khai báo derived trong pack, bộ nạp kiểm vòng và trùng tên"`.

---

### Task 2: Ngữ nghĩa dữ kiện suy ra (`derived.py`) và bảng chân lý §5.3

**Files:**
- Create: `src/rag/rules/derived.py`
- Modify: `src/rag/rules/semantics.py` (`Fact.derived_by: str | None = None`, field cuối), `src/rag/rules/loader.py` (gọi `derived_order`)
- Test: `tests/test_rules_derived.py`

**Interfaces:**
- Consumes: `DerivedFact`, `Definition`, `Context` (Task 1); `eval_cond`, `Fact`, `CONFLICT`, `UNKNOWN`, `Facts`, `is_unresolved`, `fact_names`, `leaves` (semantics / model).
- Produces:
  - `derived_inputs(d: DerivedFact) -> tuple[str, ...]` — tên dữ kiện mà các định nghĩa đọc (`from_fact` và lá `when`), không trùng.
  - `derived_order(derived: Mapping[str, DerivedFact]) -> tuple[str, ...]` — thứ tự topo (dữ kiện suy ra mà nó đọc đứng trước); vòng → `CatalogError([...])` nêu các tên trong vòng.
  - `eval_derived(d: DerivedFact, facts: Facts, ctx: Context) -> Fact | _Conflict | _Unknown | None` theo §5.3 bước 1–3, kèm quyết định đã ghi ở trên: nút có con → tính con trước; có giá trị: mọi con giá trị cùng `==` → giá trị đó, khác nhau hoặc có con `CONFLICT` → `CONFLICT`; không con nào cho giá trị: có `CONFLICT` → `CONFLICT`, có `UNKNOWN` → `UNKNOWN`; mọi con "không áp dụng" (`None`) → xét `when(n)`: T → `value` hằng, hoặc dữ kiện `from` (thiếu → `None`; `CONFLICT` / `UNKNOWN` → giữ nguyên), F → `None`, U → `UNKNOWN`. Các gốc kết hợp như anh em theo cùng bước 1–2; không gốc nào cho gì → `None`. Giá trị trả về là `Fact(value, unit, source="derived", derived_by=<id định nghĩa thắng>)`; `unit` = `d.unit` với hằng, = đơn vị của dữ kiện nguồn với `from`.
  - `derive_all(ctx: Context, facts: Facts) -> Facts` — bản sao `facts` đã bỏ mọi khóa trùng tên dữ kiện suy ra, rồi thêm kết quả theo `derived_order` (kết quả `None` không thêm; `UNKNOWN` / `CONFLICT` thêm nguyên mốc). Nhận được dữ kiện suy ra đứng trước khi tính dữ kiện sau (chuỗi).
  - `missing_inputs(names: Iterable[str], facts: Facts, ctx: Context) -> tuple[str, ...]` — tên không trùng, theo thứ tự gặp: tên không phải suy ra mà `facts.get(n) is None` → chính nó; tên suy ra mà kết quả là `None` hoặc `UNKNOWN` → mở thành dữ kiện đầu vào thiếu của các định nghĩa chưa quyết định: với mỗi định nghĩa có `when` khác F, các tên lá `when` thiếu (chỉ khi `when` = U) và `from_fact` thiếu (`None`); tên nào lại là dữ kiện suy ra thì mở đệ quy. Dữ kiện suy ra đã có giá trị / `CONFLICT` không thêm gì.

- [ ] **Step 1: Viết test lỗi** trong `tests/test_rules_derived.py` (dựng `DerivedFact` trực tiếp bằng dataclass, `CTX = load_pack("labor").context()`; lá `{fact: a, op: eq, value: 1}` cho T khi `a=1`, F khi `a=2`, U khi thiếu):
  - `test_single_definition_when_truth_table`: `when` T/F/U → giá trị hằng / `None` / `UNKNOWN`; `when: None` → luôn giá trị.
  - `test_from_fact_missing_conflict_unknown`: `from` thiếu → `None`; `from` = `CONFLICT` → `CONFLICT`; `from` = `UNKNOWN` → `UNKNOWN`; `from` có giá trị → giá trị + đơn vị của nguồn, `source == "derived"`, `derived_by` = id.
  - `test_one_exception_all_nine_combinations`: gốc `when` ∈ {T,F,U} × ngoại lệ `when` ∈ {T,F,U}; kỳ vọng: ngoại lệ T → giá trị ngoại lệ (kể cả gốc F hoặc U); ngoại lệ U → `UNKNOWN` (kể cả gốc F); ngoại lệ F → như gốc đứng một mình.
  - `test_two_exceptions_same_value_different_value_and_unknown`: hai con cùng giá trị → giá trị; khác nhau → `CONFLICT`; một giá trị + một `UNKNOWN` → giá trị (**Review Focus 1**); hai `UNKNOWN` → `UNKNOWN`; một giá trị + một `CONFLICT` → `CONFLICT`.
  - `test_nested_exception_and_sibling_roots`: ngoại lệ của ngoại lệ (giá trị thắng từ lá sâu nhất khi các `when` T); hai gốc cùng T khác giá trị → `CONFLICT`; một gốc `None` một gốc giá trị → giá trị.
  - `test_chain_and_overwrite_of_raw_fact`: dữ kiện suy ra `b` có `from: a_eff` (suy ra); `derive_all` cho cả hai; khóa `a_eff` truyền trong `facts` thô bị bỏ và thay bằng kết quả suy ra (hoặc bị xóa nếu kết quả `None`).
  - `test_derived_order_topological_and_cycle_error`.
  - `test_missing_inputs_expansion`: dữ kiện suy ra `UNKNOWN` vì `when` của ngoại lệ có hai lá thiếu → trả đúng hai tên; định nghĩa `when = F` không đóng góp; `from` thiếu được liệt kê; suy ra lồng suy ra được mở đệ quy; dữ kiện thường thiếu → chính nó.
  - `test_unknown_derived_is_unresolved_at_leaf`: lá `{fact: kind_eff, op: eq, value: x}` trên bảng có `kind_eff = UNKNOWN` ra `U`, `present` / `absent` ra `U`.
- [ ] **Step 2: Chạy, xác nhận FAIL** (`ModuleNotFoundError: rag.rules.derived`).
- [ ] **Step 3: Cài `derived.py` và `Fact.derived_by`**; để `loader.py` gọi `derived_order` thay hàm tạm của Task 1.
- [ ] **Step 4: Chạy** `uv run pytest tests/test_rules_derived.py tests/test_rules_derived_loader.py tests/test_rules_semantics.py -q -p no:cacheprovider`. Expected: PASS.
- [ ] **Step 5: Commit** — `git add src/rag/rules/derived.py src/rag/rules/semantics.py src/rag/rules/loader.py tests/test_rules_derived.py && git commit -m "feat(team-4.2): rules - ngữ nghĩa dữ kiện suy ra (cây ngoại lệ, UNKNOWN, mở dữ kiện thiếu)"`.

---

### Task 3: `exception_of` giữa rule: bộ nạp và ngữ nghĩa §5.4

**Files:**
- Create: `src/rag/rules/exceptions.py`
- Modify: `src/rag/rules/model.py` (`Rule.exception_of: str | None = None`, field cuối), `src/rag/rules/loader.py`
- Test: `tests/test_rules_exceptions.py`

**Interfaces:**
- Consumes: `Rule`, `RuleInputs`, `RuleResult`, `Tri`, `Context`, `fact_names`, `missing_inputs`.
- Produces (`exceptions.py`):
  - `rule_key(concept_id: str, rule: Rule) -> str` = `f"{concept_id}/{rule.id}"`.
  - `ExceptionIndex` (dataclass bất biến) với `ExceptionIndex.build(items: Sequence[tuple[str, Rule]]) -> ExceptionIndex` (`items` = `(concept_id, rule)` theo thứ tự catalog); thuộc tính `children: tuple[tuple[int, ...], ...]` (ngoại lệ trực tiếp của rule i), `ancestors: tuple[tuple[int, ...], ...]` (mọi rule mà kết quả phụ thuộc rule i, gián tiếp cũng tính), `order: tuple[int, ...]` (chỉ rule tham gia quan hệ ngoại lệ, con trước cha), `involved: frozenset[int]`. Đích `exception_of` không có trong `items` thì bỏ qua.
  - `rule_state(inputs: RuleInputs) -> Tri` — F nếu `app == "F"` hoặc `law_st == "F"`; T nếu cả hai T; còn lại U.
  - `applies_states(index: ExceptionIndex, states: Sequence[Tri]) -> dict[int, Tri]` — với rule i trong `order`: Kleene-OR của `states[i]` và `applies[c]` với c trong `children[i]`.
  - `@dataclass(frozen=True) class Override: key: str; applies: Tri; open_facts: tuple[str, ...]`.
  - `finalize(base: RuleResult, overrides: Sequence[Override]) -> RuleResult` — bảng §5.4: có override T → `NOT_APPLICABLE`, finding `ok`, `legality` / `employee_impact` = `None`, `law_values = {}`, `missing_facts = ()`, `reasons` = `overridden_by:<key>` cho từng override T (giữ `facts_used`, `evidence`); không T nhưng có U: thêm `exception_unknown:<key>` vào `reasons`; nếu `base.status == "FAIL"` thì hạ thành `UNKNOWN` / `needs_facts`, `legality` / `employee_impact` = `None`, `missing_facts` = `base.missing_facts` + `open_facts` của các override U (không trùng); trạng thái khác giữ nguyên (chỉ thêm reason); không T không U → trả `base`.
  - `exception_open(rule: Rule, facts: Facts, ctx: Context) -> tuple[str, ...]` = `missing_inputs` của tên trong `applicability` và `cases[*].when`.
- Bộ nạp: `exception_of` phải là chuỗi `<concept_id>/<rule_id>` và không trỏ chính rule; `load_concepts` kiểm đích nằm trong cùng file nếu concept đích có trong file (rule phải có) và kiểm vòng cục bộ; `load_packs` sau khi gộp concept kiểm **mọi** đích tồn tại và không vòng toàn cục. Hàm kiểm dùng chung nằm trong `loader.py` (`_check_exceptions(concepts, problems, *, strict)`).

- [ ] **Step 1: Viết test lỗi** trong `tests/test_rules_exceptions.py`:
  - `test_finalize_three_rows`: `base` PASS / FAIL / UNKNOWN (dựng `RuleResult` tối thiểu) × override T / F / U — T → `NOT_APPLICABLE` + reason, F → nguyên, U: FAIL → `UNKNOWN` `needs_facts` + `exception_unknown` + `missing_facts` gồm dữ kiện của override; PASS / UNKNOWN giữ nguyên status chỉ thêm reason.
  - `test_two_true_overrides_list_both_and_u_loses_to_t`.
  - `test_rule_state_truth_table`: `RuleInputs` với (`app`, `law_st`) mọi tổ hợp T/F/U.
  - `test_nested_exception_applies_through_chain` (**Review Focus 4**): X ← R ← R2; `states` = (F, F, T) → `applies` của R = T, nên X bị `overridden_by` R; R2 T làm R `NOT_APPLICABLE` khi R cũng là gốc của ngoại lệ ở bước `finalize`.
  - `test_index_children_ancestors_order_and_unknown_target_ignored`.
  - `test_loader_rejects_missing_target_self_and_cycle` (dùng `write_pack`): đích không có, tự trỏ, vòng X→R→X, định dạng sai (thiếu `/`); lỗi nêu `<concept>/<rule>`. Ngoại lệ chéo gói hợp lệ khi gói con `extends` cha, lỗi khi đích ở gói không nạp.
- [ ] **Step 2: Chạy, xác nhận FAIL.**
- [ ] **Step 3: Cài `exceptions.py`; thêm `Rule.exception_of`; bộ nạp** đọc `exception_of`, gọi `_check_exceptions` (cục bộ trong `load_concepts`, `strict=True` trong `load_packs`).
- [ ] **Step 4: Chạy** `uv run pytest tests/test_rules_exceptions.py tests/test_rules_loader.py tests/test_rules_packs_merge.py -q -p no:cacheprovider`. Expected: PASS.
- [ ] **Step 5: Commit** — `git add src/rag/rules/exceptions.py src/rag/rules/model.py src/rag/rules/loader.py tests/test_rules_exceptions.py && git commit -m "feat(team-4.2): rules - exception_of giữa rule: bảng ba hàng, ngoại lệ lồng nhau, bộ nạp"`.

---

### Task 4: Nối vào ReferenceEvaluator

**Files:**
- Modify: `src/rag/rules/reference.py`, `src/rag/rules/semantics.py` (`_result`)
- Test: `tests/test_rules_reference_phase3.py`; sửa `tests/test_rules_semantics.py` nếu chữ ký `_result` đổi

**Interfaces:**
- Consumes: `derive_all`, `missing_inputs`, `ExceptionIndex`, `rule_state`, `applies_states`, `Override`, `finalize`, `exception_open`, `rule_inputs`, `decide_rule`.
- Produces:
  - `reference.evaluate_rules(items: Sequence[tuple[str, Rule, bool, Sequence[dict]]], facts: Facts, day: date, ctx: Context) -> list[RuleResult]` — `items` = `(concept_id, rule, present, evidence)`; thứ tự kết quả = thứ tự `items`; tính `facts2 = derive_all(ctx, facts)`, rồi `rule_inputs` và `decide_rule` cho mọi rule trên `facts2`, rồi `finalize` theo `ExceptionIndex`.
  - `evaluate_concept(...)` = `evaluate_rules` trên các rule của concept (chỉ ngoại lệ cùng concept); `evaluate_all(...)` = `evaluate_rules` trên mọi rule của catalog. Chữ ký công khai cũ không đổi.
  - `semantics._result`: `missing` = với mỗi tên trong `referenced(rule)` theo thứ tự: dùng `missing_inputs([n], facts, ctx)` (tên thường thiếu → chính nó, như cũ); tên suy ra mà kết quả `None` / `UNKNOWN` thêm reason `derived_unknown:<tên>` (một lần). `facts_used` giữ như cũ và thêm khóa `derived_by` khi dữ kiện mang `derived_by`.
- Ghi chú đã chốt: `evaluate_concept` trong `bridge/engine.py` giữ chữ ký; không đổi `bridge`.

- [ ] **Step 1: Viết test lỗi** trong `tests/test_rules_reference_phase3.py` với gói tổng hợp (`write_pack` + `load_packs(root=tmp_path)`; gói có dữ kiện suy ra `kind_eff` kiểu Đ20.2 và một rule dùng nó, một rule gốc có hai ngoại lệ):
  - `test_rule_reads_derived_fact_and_missing_inputs_expanded` (**Review Focus 5**): thiếu dữ kiện đầu vào → rule dùng `kind_eff` ra `UNKNOWN` / `needs_facts`, `missing_facts` là các dữ kiện đầu vào (không có `kind_eff`), `reasons` chứa `derived_unknown:kind_eff`; điền đủ → kết quả theo giá trị suy ra, `facts_used["kind_eff"]["derived_by"]` có mặt.
  - `test_override_rows_in_evaluate_all`: ngoại lệ T → gốc `NOT_APPLICABLE` + `overridden_by:<concept>/<rule>`; F → gốc nguyên; U và gốc `FAIL` → `UNKNOWN` `needs_facts` + `missing_facts` thêm dữ kiện của ngoại lệ; U và gốc `PASS` → `PASS` thêm reason.
  - `test_evaluate_concept_applies_only_same_concept_exceptions`: ngoại lệ cùng concept có hiệu lực; ngoại lệ ở concept khác không (đúng giới hạn đã ghi).
  - `test_invariant_missing_fact_never_causes_fail`: với gói tổng hợp, duyệt mọi tập con dữ kiện đầu vào (xóa dần từng dữ kiện từ một bộ đầy đủ): không rule nào đổi từ khác `FAIL` sang `FAIL` khi bớt dữ kiện.
  - `test_legacy_labor_results_unchanged`: `tests/test_rules_golden.py` vẫn xanh (chạy kèm).
- [ ] **Step 2: Chạy, xác nhận FAIL.**
- [ ] **Step 3: Cài `evaluate_rules`, sửa `_result`.**
- [ ] **Step 4: Chạy Gate** (tập lệnh ở Global Constraints) với `RAG_RULE_EVALUATOR=reference` rồi mặc định. Expected: PASS như cơ sở (cộng test mới).
- [ ] **Step 5: Commit** — `git add src/rag/rules/reference.py src/rag/rules/semantics.py tests/test_rules_reference_phase3.py tests/test_rules_semantics.py && git commit -m "feat(team-4.2): rules - Reference tính dữ kiện suy ra và ngoại lệ giữa rule"`.

---

### Task 5: Nối vào NetworkEvaluator và đối chiếu ngẫu nhiên

**Files:**
- Modify: `src/rag/rules/network/network.py`, `src/rag/rules/network/session.py`
- Test: `tests/test_rules_network_phase3.py`

**Interfaces:**
- Consumes: mọi hàm Task 2–3; `NetworkSession._compute`, `Network.compile`.
- Produces:
  - `Network` thêm: `derived_order: tuple[str, ...]`; `derived_deps: dict[str, frozenset[str]]` (đầu vào trực tiếp của từng dữ kiện suy ra); `exceptions: ExceptionIndex` (trên mọi rule theo `RuleSlot.index`). `rules_by_fact` thêm, cho mỗi rule tham chiếu dữ kiện suy ra, mọi dữ kiện đầu vào bắc cầu của nó (để `missing_facts` đổi thì rule được tính lại).
  - `NetworkSession`: bảng `_facts` là bảng đã gộp dữ kiện suy ra (khởi tạo bằng `derive_all`); `update` bỏ thay đổi có tên trùng dữ kiện suy ra; sau khi áp thay đổi, duyệt `derived_order`, tính lại dữ kiện suy ra nào có đầu vào trong tập đổi, ghi / xóa khi kết quả khác (so bằng `_same` đã có và đồng nhất mốc `CONFLICT` / `UNKNOWN`), thêm tên đó vào tập tên đổi; giữ `_base` (kết quả cơ sở từng rule), `_state` (`rule_state`) và `_results` (cuối). Rule bẩn = như cũ; vùng kết quả cần tính lại cuối = bẩn ∪ `ancestors` của rule bẩn; chỉ khi vùng này giao `involved` mới tính lại `applies_states` và `finalize` cho các rule trong vùng. `Diff` so `_results` cũ / mới. `stats["rules_recomputed"]` = số rule bẩn (cơ sở).
- `fork()` sao chép thêm `_base`, `_state`.

- [ ] **Step 1: Viết test lỗi** trong `tests/test_rules_network_phase3.py`:
  - `test_network_equals_reference_on_synthetic_pack_random_updates`: gói tổng hợp có dữ kiện suy ra nhiều tầng (tầng hai dùng tầng một), ngoại lệ lồng nhau và ngoại lệ chéo concept; 20 seed × 150 bước (thêm / xóa / đổi dữ kiện, `present`, `evidence`, `fork` giữa chừng), so `results()` và `Diff` với `ReferenceEvaluator` sau mỗi bước (cùng cách làm của `test_rules_network.py`).
  - `test_raw_fact_with_derived_name_ignored_in_both` (**Review Focus 2**): truyền `Fact` trùng tên dữ kiện suy ra khi tạo phiên và qua `update`; hai evaluator cho cùng kết quả và dữ kiện suy ra không bị ghi đè.
  - `test_derived_recomputed_on_type_changing_input` (**Review Focus 3**): đầu vào đổi `1` → `True` làm dữ kiện suy ra và rule phụ thuộc cập nhật giống Reference.
  - `test_update_recomputes_only_affected_rules`: đổi dữ kiện không liên quan → `stats["rules_recomputed"] == 0`; đổi đầu vào của dữ kiện suy ra → chỉ các rule dùng nó (và ancestors của ngoại lệ) được tính lại.
  - `test_missing_facts_follow_derived_inputs_when_derived_stays_unknown`: đầu vào thứ hai của dữ kiện suy ra được điền, dữ kiện suy ra vẫn `UNKNOWN` → `missing_facts` của rule dùng nó đổi (rule phải nằm trong vùng bẩn).
  - `test_labor_default_catalog_still_equal_to_reference` (chạy lại kiểm cũ `test_rules_network.py`).
- [ ] **Step 2: Chạy, xác nhận FAIL.**
- [ ] **Step 3: Cài chỉ mục và logic phiên.**
- [ ] **Step 4: Chạy** `uv run pytest tests/test_rules_network_phase3.py tests/test_rules_network.py tests/test_rules_network_nodes.py -q -p no:cacheprovider`, rồi Gate hai chế độ. Expected: PASS.
- [ ] **Step 5: Commit** — `git add src/rag/rules/network tests/test_rules_network_phase3.py && git commit -m "feat(team-4.2): rules - Network tính lại dữ kiện suy ra và ngoại lệ, khớp Reference"`.

---

### Task 6: Rule thật cho Điều 20.2 trong gói `labor`

**Files:**
- Modify: `src/rag/rules/packs/labor/pack.yaml`, `src/rag/rules/packs/labor/concepts.yaml` (concept `content.term`), `src/rag/bridge/view.py`, `tests/test_rules_pack.py`, `tests/test_rules_loader.py`, `tests/test_rules_golden.py`
- Test: `tests/test_rules_labor_term.py` (mới)

**Interfaces:**
- Consumes: Task 1–5. Dữ kiện người dùng đưa qua `user_facts` (đã có đường `user_fact_set` trong `bridge/check.py`, kiểm tên theo `USER_FACTS` của pack).
- Produces (nội dung pack, theo văn bản luật đã đọc):
  - `pack.yaml` `user_facts` thêm: `worked_after_expiry_days` (số ngày NLĐ tiếp tục làm việc kể từ ngày HĐ hết hạn, đơn vị `day`), `new_contract_signed` (đã ký HĐ mới, bool), `fixed_term_contract_count` (số HĐ xác định thời hạn đã ký liên tiếp với NLĐ, kể cả HĐ đang soát; không đơn vị), `is_state_enterprise_director` (được thuê làm giám đốc doanh nghiệp có vốn nhà nước), `is_elderly_employee` (Đ149.1), `is_foreign_employee` (Đ151.2), `is_union_leader_in_term` (thành viên ban lãnh đạo tổ chức đại diện NLĐ tại cơ sở đang trong nhiệm kỳ, Đ177.4).
  - `pack.yaml` `derived`: `contract_kind_effective` — định nghĩa `base` (`from: contract_kind`) và `d20k2b` (`exception_of: base`, `when: all[contract_kind eq xac_dinh_thoi_han, worked_after_expiry_days gt 30 unit day, new_contract_signed eq false]`, `value: khong_xac_dinh_thoi_han`, anchors `bo-luat:45/2019/QH14#d20.k2.b`).
  - `concepts.yaml` `content.term`: giữ nguyên `r1`, `r2`; thêm `r3` (mode `threshold`, `applicability: {fact: contract_kind, op: eq, value: xac_dinh_thoi_han}`, `law: {max_fixed_term_contracts: {value: 2, unit: null}}`, `check: {fact: fixed_term_contract_count, op: lte, law: max_fixed_term_contracts}`, `derogation: mandatory`, `on_silence: none`, outcome illegal / unfavorable) và bốn rule ngoại lệ `r3_state_director`, `r3_elderly`, `r3_foreign`, `r3_union_leader`, mỗi rule `exception_of: content.term/r3`, `mode: required`, `derogation: mandatory`, `on_silence: none`, không `check`, `applicability` là lá `eq true` của dữ kiện tương ứng, outcome illegal / unfavorable (không dùng được khi finding `ok`). Thêm một rule `r4` dùng dữ kiện suy ra: HĐ đã chuyển thành không xác định thời hạn mà văn bản vẫn ghi xác định thời hạn thì cần soát lại — `applicability: {fact: contract_kind_effective, op: eq, value: khong_xac_dinh_thoi_han}`, `mode: required`, `check: {fact: contract_kind, op: eq, value: khong_xac_dinh_thoi_han}`, `derogation: mandatory`, `on_silence: none`, outcome `legality: unknown, employee_impact: neutral` (HĐ tự chuyển loại theo luật không phải là hợp đồng trái luật; finding `violation` ở đây chỉ báo cần soát lại loại HĐ). Anchors của concept thêm `d20.k2.b`, `d20.k2.c`, `d149.k1`, `d151.k2`, `d177.k4` (role `basis` cho `d20.k2.b`, `d20.k2.c`; `exception` cho ba điều còn lại) và bỏ ghi chú "chưa có rule" ở anchor `d20.k2`.
  - `bridge/view.py` `FACT_LABELS` thêm nhãn tiếng Việt cho 7 dữ kiện người dùng mới (test hiện có buộc `FACT_LABELS` ⊇ `USER_FACTS`).

- [ ] **Step 1: Viết test lỗi** trong `tests/test_rules_labor_term.py` (dùng `load_catalog()` của bridge và `evaluator_for(catalog, kind)` cho cả `reference` và `network`, ngày soát `2025-03-01`, dữ kiện `Fact(giá trị, đơn vị)`, `contract_kind` = `xac_dinh_thoi_han` hoặc `khong_xac_dinh_thoi_han`; mỗi test chạy trên cả hai evaluator và so bằng nhau):
  - `test_effective_kind_boundary_30_days`: `contract_kind` (loại ghi trong văn bản) = `xac_dinh_thoi_han`, `new_contract_signed = false`: `worked_after_expiry_days` = 20 và đúng 30 → `content.term/r4` `NOT_APPLICABLE` (vẫn xác định thời hạn); = 31 → `r4` `FAIL` / `violation` (loại hiệu lực đã là không xác định thời hạn mà văn bản ghi khác). Với `contract_kind = khong_xac_dinh_thoi_han`, `r4` `PASS` bất kể dữ kiện khác.
  - `test_new_contract_signed_blocks_conversion`: 45 ngày nhưng `new_contract_signed = true` → vẫn xác định thời hạn (`r4` `NOT_APPLICABLE`).
  - `test_missing_inputs_are_unknown_not_violation`: thiếu `worked_after_expiry_days` hoặc `new_contract_signed` → `r4` `UNKNOWN` / `needs_facts`, `missing_facts` liệt kê đúng dữ kiện đầu vào thiếu; không bao giờ `FAIL`.
  - `test_limit_on_fixed_term_signings`: `fixed_term_contract_count` = 2 → `r3` `PASS`; 3 → `FAIL` (khi nội dung điều khoản `content.term` có mặt); thiếu → `UNKNOWN`; HĐ không xác định thời hạn → `r3` `NOT_APPLICABLE`.
  - `test_each_exception_overrides_limit`: với `count = 3`, từng dữ kiện trong bốn dữ kiện ngoại lệ = true → `r3` `NOT_APPLICABLE` có `overridden_by:content.term/r3_<tên>` và rule ngoại lệ đó ra kết quả riêng của nó; cả bốn false → `r3` vẫn `FAIL`; một ngoại lệ chưa biết (thiếu) + `count = 3` → `r3` hạ thành `UNKNOWN` / `needs_facts` với `exception_unknown:` và `missing_facts` gồm dữ kiện ngoại lệ thiếu.
  - `test_phase3_rules_pinned_by_law_text`: đọc `data/team-4.2/legal/raw/bo-luat_45_2019_QH14/*.txt` nếu có (bỏ qua test nếu thiếu) và khẳng định các cụm "không quá 36 tháng"/"01 lần" tương ứng số trong `r2` / `r3`, để rule không lệch văn bản.
  - Sửa `tests/test_rules_pack.py` (tập `user_facts` đúng như trên), `tests/test_rules_loader.py` (số rule của labor = 44 + 6 = 50, số concept vẫn 39), `tests/test_rules_golden.py`: thay "mọi rule của catalog có ≥ 3 ca golden" bằng "mọi rule có trong golden vẫn tồn tại với ≥ 3 ca, và tập rule không có trong golden đúng bằng `{content.term/r3, r3_state_director, r3_elderly, r3_foreign, r3_union_leader, r4}`".
- [ ] **Step 2: Chạy, xác nhận FAIL** (rule và dữ kiện chưa có).
- [ ] **Step 3: Sửa `pack.yaml`, `concepts.yaml`, `bridge/view.py`** như trên; không đổi rule cũ.
- [ ] **Step 4: Chạy** `uv run pytest tests/test_rules_labor_term.py -q -p no:cacheprovider`, rồi Gate hai chế độ (golden phải xanh không ghi lại golden). Expected: PASS.
- [ ] **Step 5: Commit** — `git add src/rag/rules/packs/labor src/rag/bridge/view.py tests/test_rules_labor_term.py tests/test_rules_pack.py tests/test_rules_loader.py tests/test_rules_golden.py && git commit -m "feat(team-4.2): rules - Đ20.2 BLLĐ: loại HĐ hiệu lực, giới hạn số lần ký và bốn ngoại lệ"`.

---

### Task 7: Tài liệu, checklist và kiểm toàn bộ

**Files:**
- Modify: `app/team-4.2/docs/phan_cong_w04/tung_viec_can_lam.md`, `app/team-4.2/docs/superpowers/specs/2026-11-22-rete-rule-engine-design.md` (§5.3, §5.4: ghi các quyết định ở đầu kế hoạch này), `reports/team-4.2/w04/` (thêm `phase3_notes.md` ngắn: số liệu và ca biên)

- [ ] **Step 1: Cập nhật spec §5.3 / §5.4** với các quyết định đã chốt (CONFLICT thắng giá trị anh em; "áp dụng" của rule ngoại lệ; ngoại lệ lồng nhau tính qua cây; `evaluate_concept` chỉ ngoại lệ cùng concept; dữ kiện trùng tên bị bỏ qua) và §12 nếu cần.
- [ ] **Step 2: Tick checklist** D13, D14, D15, D16 (ghi rõ Đ22.2 và Đ25 một lần một công việc chuyển sang 7b, kèm lý do); ghi vào D16 các user fact mới để Tú / Huy biết cần hỏi người dùng.
- [ ] **Step 3: Chạy Gate hai chế độ và toàn bộ suite** (`uv run pytest tests -q -p no:cacheprovider --ignore=tests/test_agent_partial_review.py`, chạy nền vì mất ~10 phút). Expected: chỉ 35 test fail của cơ sở, không test mới fail.
- [ ] **Step 3b: Đo nhanh** thời gian tạo phiên và `update` trên catalog labor sau giai đoạn này (cùng script đã dùng ở giai đoạn 2) và ghi vào `phase3_notes.md`.
- [ ] **Step 4: Commit** — `git add app/team-4.2/docs reports/team-4.2/w04/phase3_notes.md && git commit -m "docs(team-4.2): giai đoạn 3 - cập nhật spec, checklist, ghi chú số liệu"`.
