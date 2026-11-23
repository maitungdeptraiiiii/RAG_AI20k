# Rule engine v2 — Giai đoạn 1 (lõi + Reference + gói labor) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tách rule engine hiện tại thành lõi không biết gì về lao động (`src/rag/rules/`) + gói `labor` khai báo bằng YAML + `ReferenceEvaluator`, cho kết quả **giống hệt** engine cũ.

**Architecture:** Logic thuần (`semantics.py`) nhận một `Context` (bảng đơn vị, dữ kiện cấp hợp đồng, bảng `on_silence`) do gói cung cấp. `loader.py` nạp `pack.yaml` + `concepts.yaml` thành `Catalog`. `bridge/engine.py` và `bridge/catalog.py` thành lớp tương thích mỏng. Golden đóng băng kết quả engine cũ **trước** khi sửa.

**Tech Stack:** Python ≥ 3.12, PyYAML, pytest. Chạy test từ `app/team-4.2/` bằng `.venv/Scripts/python.exe -m pytest` (pytest đã cấu hình `pythonpath = ["src", "."]`).

**Spec:** `app/team-4.2/docs/superpowers/specs/2026-11-22-rete-rule-engine-design.md` (bản 2, đã duyệt) — giai đoạn 1 = §3, §5.1, §5.2, §5.5, §7, §10 (golden). Checklist: `docs/phan_cong_w04/tung_viec_can_lam.md` mục A3–A5, D1–D7.

## Global Constraints

- Thuần Python, không I/O trong `semantics.py`; không thêm dependency (spec §3).
- `concepts.yaml` hiện có nạp được **không sửa nội dung rule**; chỉ chuyển vị trí file. Giữ nguyên các trường `roles`, `id`, `label`, `scope`, `phase`, `applies_to`, `anchors`, `value_sources` (spec §3, LU đọc các trường này).
- API cũ giữ nguyên tên và chữ ký: `evaluate`, `evaluate_concept`, `RuleResult` (11 trường theo thứ tự hiện tại, tests dựng bằng vị trí), `Fact`, `CONFLICT`, `_Conflict`, `Facts`, `Tri`, `compare`, `convert`, `eval_cond`, `resolve_law`, `CONTRACT_FACTS`, `USER_FACTS`, `UNITS`, `OPS`, `DEFAULT_PATH`, `load_catalog`, `CatalogError`, `Catalog`, `Concept`, `Rule`, `Slot`, `_leaves` (spec §3).
- Bất biến cũ giữ nguyên: thiếu dữ kiện không bao giờ thành `FAIL` (spec §2).
- Đơn vị quy đổi do gói khai báo; gói `labor` khai báo **đúng** bảng cũ (`day`=24h, `week`=168h, `month`=720h, `hour`=1h, `minute`=1/60h), `workday` không quy đổi (spec §5.1).
- Chú thích / docstring bằng tiếng Việt như code xung quanh; định danh bằng tiếng Anh.
- Commit theo kiểu lịch sử repo (`feat(team-4.2): ...`), kèm dòng attribution mà phiên làm việc cung cấp. Nhánh: `feat/team-4.2/w04-rules-engine`.
- **Gate** (chạy sau mỗi task sửa code): `GATE` = `.venv/Scripts/python.exe -m pytest tests/test_bridge_*.py tests/test_contract_graph_tools.py tests/test_ask_contract_graph.py tests/test_contract_graph_agent.py tests/test_contracts_api.py -q`. Số liệu baseline ghi ở Task 1; không được có test mới fail.

## Review Focus

Các đầu vào mà spec ngụ ý nhưng task thường không thử; mỗi dòng có test ở task ghi trong ngoặc:

1. Dữ kiện `UNKNOWN` ở lá: so sánh / `present` / `absent` / khóa `by` của giá trị luật đều ra `U`; không vào `facts_used`, không vào `missing_facts` (Task 4).
2. `pack.yaml` hoặc rule sai nhiều chỗ cùng lúc: báo **hết** một lần trong một `CatalogError`; rule dùng `on_silence` mà gói không khai báo bị từ chối (Task 3, 5).
3. `unstated_false` ghi tay sai chỗ (true trên rule không có dạng "slot bool = false") bị từ chối; ghi `false` tắt suy luận tự động (Task 5).
4. `session.update` với giá trị `None` xóa dữ kiện (kết quả quay về `UNKNOWN`), cập nhật không đổi gì thì `Diff` rỗng, `fork()` độc lập với bản gốc (Task 8).
5. `evaluate_concept` gọi không có `ctx` dùng bảng đơn vị `labor`; gọi có `ctx` của gói khác dùng bảng của gói đó (Task 7).

## File Structure

| File | Trách nhiệm |
|---|---|
| `src/rag/rules/__init__.py` | Docstring gói |
| `src/rag/rules/units.py` | `Units`: bảng đơn vị + `convert` |
| `src/rag/rules/model.py` | Dataclass: `Slot`, `Rule`, `Concept`, `Catalog`, `Context`, `Silence`, `PackSpec`, `CatalogError`; hằng `OPS`, `MODES`, `DEROGATIONS`, `SLOT_KINDS`, `CORE_SILENCES`; hàm `leaves` |
| `src/rag/rules/semantics.py` | Logic thuần: `Fact`, `CONFLICT`, `UNKNOWN`, `compare`, `eval_cond`, `check_cond`, `resolve_law`, `RuleResult`, `evaluate_rule` |
| `src/rag/rules/loader.py` | `load_pack`, `load_concepts`, `load_packs`, `PACKS_ROOT` |
| `src/rag/rules/reference.py` | `evaluate_concept`, `evaluate_all` (tính toàn bộ) |
| `src/rag/rules/evaluator.py` | `Evaluator` / `Session` Protocol, `Diff`, `RuleChange`, `ReferenceEvaluator`, `make_evaluator`, `evaluator_for` |
| `src/rag/rules/packs/labor/pack.yaml`, `concepts.yaml` | Gói lao động (concepts.yaml chuyển từ `bridge/`) |
| `src/rag/bridge/engine.py`, `catalog.py` | Lớp tương thích |
| `tests/rules_golden_cases.py`, `tests/fixtures/rules/golden/engine_results.json`, `tests/test_rules_*.py` | Golden + test mới |

**Lệch spec (người viết kế hoạch quyết, Tùng xem lại):** (a) `roles` ở lại `concepts.yaml`, không chuyển vào `pack.yaml` (spec §3 cấm đổi vị trí; §5.5 nói ngược lại). (b) `outcome` truyền nguyên dạng và trường `kind` hoãn đến giai đoạn 5; `RuleResult` giữ nguyên 11 trường. (c) `user_facts` ở `pack.yaml` chỉ là danh sách tên; câu hỏi / kiểu thêm ở giai đoạn 4. (d) `load_packs` gộp nhiều gói: `version` = `"<id>@<version>"` nối bằng `+`, `law_values_valid_from` = ngày lớn nhất (spec không nói).

---

### Task 1: Nhánh, baseline, golden từ engine cũ (A5)

**Files:**
- Create: `tests/rules_golden_cases.py`, `tests/test_rules_golden.py`, `tests/fixtures/rules/golden/engine_results.json` (sinh ra)

**Interfaces:**
- Produces (dùng ở Task 6, 7, 8):
  - `GoldenCase` (dataclass frozen: `case_id: str`, `concept_id: str`, `rule_id: str`, `facts: dict`, `present: bool`, `day: date`)
  - `facts_from_spec(spec: Mapping) -> Facts` — `{"tên": [giá trị, đơn vị?]}` hoặc `"CONFLICT"`, cùng dạng với `tests/fixtures/bridge/engine_cases.yaml`
  - `golden_cases(catalog: Catalog) -> list[GoldenCase]`
  - `run_case(case: GoldenCase, catalog: Catalog, evaluate_concept_fn) -> dict` — kết quả của đúng rule đó, đã chuyển thành dict JSON (`asdict`, tuple→list)
  - `GOLDEN_PATH: Path`; chạy `python tests/rules_golden_cases.py --write` để ghi lại.

- [ ] **Step 1: Tạo nhánh và ghi baseline**

```bash
git switch -c feat/team-4.2/w04-rules-engine
cd app/team-4.2
.venv/Scripts/python.exe -m pytest tests/test_bridge_*.py tests/test_contract_graph_tools.py tests/test_ask_contract_graph.py tests/test_contract_graph_agent.py tests/test_contracts_api.py -q
```
Ghi số "passed / skipped / xfailed" của GATE vào `reports/week-04/team-4.2/phase1_baseline.md` (đã đo trên 11 file bridge: 261 passed, 1 skipped, 1 xfailed; GATE rộng hơn nên số sẽ lớn hơn). Chạy một lần toàn bộ: `.venv/Scripts/python.exe -m pytest -q --ignore=tests/test_agent_partial_review.py -rf` và lưu các dòng `FAILED` vào cùng file (đã đo: 35 failed, 1755 passed, 22 skipped, 16 xfailed; `test_agent_partial_review.py` lỗi import từ trước nên bị bỏ qua).

- [ ] **Step 2: Viết `golden_cases` và `run_case`**

Thuật toán của `golden_cases` (không suy ra được từ chữ ký), theo thứ tự cố định:
1. Mỗi dòng của `tests/fixtures/bridge/engine_cases.yaml` → một `GoldenCase` (day mặc định `2025-03-01`).
2. Quét theo từng rule (đúng thứ tự catalog): `names` = các dữ kiện rule tham chiếu (applicability, check, `cases[*].when`, khóa `by` của giá trị luật). Giá trị ứng viên cho mỗi tên, loại trùng giữ thứ tự: *thiếu* (bỏ khóa), `"CONFLICT"`; với mỗi lá có `fact == tên`: bool → `[True]`, `[False]`; số `v` → `[v-1, unit]`, `[v, unit]`, `[v+1, unit]` (unit của lá); chuỗi `v` → `[v]` và `["__other__"]`; danh sách → từng phần tử và `["__other__"]`; lá có `law: n` → với mọi giá trị số dưới `law[n]` (ở `rule.law`, `cases[*].law`, `periods[*].values[*]`) thêm `[t-1,u]`, `[t,u]`, `[t+1,u]` (u = unit của `law[n]`); với khóa `by` → mỗi khóa trong `periods[*].values` và `["__other__"]`.
3. Tích Descartes các ứng viên; nếu quá 48 tổ hợp thì lấy mẫu cách đều (stride) đúng 48. Nhân với `present ∈ {False, True}` và `day ∈ {2025-03-01, 2026-02-01}`.
4. `case_id` = `f"{concept}/{rule}/{index:04d}"`, index tăng theo thứ tự sinh.

`run_case` gọi `evaluate_concept_fn(concept, facts, present=..., evidence=(), day=...)`, lấy rule theo `rule_id`, trả `json.loads(json.dumps(asdict(r), ensure_ascii=False, sort_keys=True))`. `--write` ghi file golden mỗi case một dòng JSON (`case` + `result`), khóa sắp xếp. Giữ file dưới ~2 MB; nếu vượt, hạ ngưỡng 48 xuống.

- [ ] **Step 3: Viết test**

```python
def test_golden_has_every_rule_with_enough_cases():   # mỗi (concept, rule) của catalog có ≥ 3 case trong golden; tổng ≥ 500
def test_golden_via_bridge_api_unchanged():           # chạy golden_cases qua rag.bridge.engine.evaluate_concept; mismatches == [] (in 5 case_id đầu nếu lệch)
def test_golden_generation_is_deterministic():        # golden_cases(catalog) hai lần bằng nhau
```

- [ ] **Step 4: Sinh golden bằng engine CŨ chưa bị sửa, rồi chạy test**

Run: `.venv/Scripts/python.exe tests/rules_golden_cases.py --write` rồi `.venv/Scripts/python.exe -m pytest tests/test_rules_golden.py -q`
Expected: 3 passed. Kiểm tra `git diff --stat` chỉ có file mới, không file `src/` nào bị sửa.

- [ ] **Step 5: Commit**

```bash
git add tests/rules_golden_cases.py tests/test_rules_golden.py tests/fixtures/rules reports/week-04/team-4.2/phase1_baseline.md
git commit -m "test(team-4.2): đóng băng kết quả rule engine cũ làm golden"
```

---

### Task 2: Interface stub cho Khánh (A3)

**Files:**
- Create: `src/rag/rules/__init__.py`, `src/rag/rules/evaluator.py`
- Test: `tests/test_rules_evaluator_stub.py`

**Interfaces:**
- Consumes: không có.
- Produces (chữ ký công bố cho Khánh, giữ nguyên đến hết giai đoạn 7):

```python
EvaluatorKind = Literal["reference", "network"]

@dataclass(frozen=True)
class RuleChange: concept_id: str; rule_id: str; before: RuleResult | None; after: RuleResult | None
@dataclass(frozen=True)
class Diff: changes: tuple[RuleChange, ...]

class Session(Protocol):
    def results(self) -> list[RuleResult]: ...
    def update(self, changes: Mapping[str, Fact | None], *, present: set[str] | None = None,
               evidence: dict[str, list[dict]] | None = None, objects: Any = None) -> Diff: ...
    def fork(self) -> "Session": ...

class Evaluator(Protocol):
    def session(self, *, day: date, facts: Facts, present: set[str], evidence: dict[str, list[dict]],
                objects: Sequence[Any] = ()) -> Session: ...

def make_evaluator(packs: Sequence[str], kind: EvaluatorKind = "reference") -> Evaluator
```

Ở task này `RuleResult`, `Fact`, `Facts` chưa có trong `rag.rules`: import tạm từ `rag.bridge.engine` (Task 8 đổi sang `rag.rules.semantics`).

- [ ] **Step 1: Viết test thất bại**

```python
def test_make_evaluator_returns_session_with_typed_results():
    s = make_evaluator(["labor"]).session(day=date(2025, 3, 1), facts={}, present=set(), evidence={})
    r = s.results()
    assert r and all(isinstance(x, RuleResult) for x in r)
    assert isinstance(s.update({}, present=set()), Diff)
    assert s.fork() is not s
def test_network_kind_not_available_yet():
    with pytest.raises(NotImplementedError): make_evaluator(["labor"], "network")
```

- [ ] **Step 2: Chạy, xác nhận fail** — `pytest tests/test_rules_evaluator_stub.py -q` → ImportError.

- [ ] **Step 3: Cài đặt** `evaluator.py` với `StubEvaluator` / `StubSession`: `results()` trả 2 `RuleResult` cố định (một `PASS/ok`, một `FAIL/violation`); `update` trả `Diff(())`; `fork` trả bản sao. `make_evaluator("network")` ném `NotImplementedError("network: giai đoạn 2")`. Ghi rõ trong docstring: stub dùng để dựng khung benchmark, được thay ở Task 8.

- [ ] **Step 4: Chạy test** → 2 passed.

- [ ] **Step 5: Commit** — `feat(team-4.2): công bố interface Evaluator (stub) cho benchmark`. **Báo Khánh** (checklist A3).

---

### Task 3: `Units`, model, `pack.yaml` của labor, `load_pack` (D2)

**Files:**
- Create: `src/rag/rules/units.py`, `src/rag/rules/model.py`, `src/rag/rules/loader.py` (chỉ `load_pack`, `PACKS_ROOT`), `src/rag/rules/packs/labor/pack.yaml`
- Test: `tests/test_rules_pack.py`

**Interfaces:**
- Produces:

```python
# units.py
@dataclass(frozen=True)
class Units:
    names: frozenset[str]
    factors: Mapping[str, tuple[str, float]]          # đơn vị -> (đơn vị gốc, hệ số)
    def convert(self, value: float, unit: str | None, to: str | None) -> float | None
        # unit == to -> value; cả hai có trong factors và cùng gốc -> value * fa / fb (đúng thứ tự phép tính cũ); còn lại None

# model.py
@dataclass(frozen=True) class Silence: applicable: tuple[str, str]; unknown: tuple[str, str]   # (status, finding)
CORE_SILENCES = {"none": Silence(("PASS","ok"),("PASS","ok")),
                 "missing_content": Silence(("FAIL","missing_content"),("UNKNOWN","needs_facts"))}
@dataclass(frozen=True) class Context: units: Units; document_facts: frozenset[str]; silences: Mapping[str, Silence]
    # property reported -> frozenset[str] = {"violation"} | finding của mọi silence, trừ {"ok","needs_facts"}
@dataclass(frozen=True) class PackSpec:
    id: str; version: str; extends: tuple[str, ...]; document_kinds: tuple[str, ...]; units: Units
    document_facts: Mapping[str, str | None]; user_facts: frozenset[str]; findings: frozenset[str]
    silences: Mapping[str, Silence]                   # đã gộp CORE_SILENCES
    def context(self) -> Context
class CatalogError(ValueError)                        # giữ đúng định dạng thông điệp cũ: "Danh mục khái niệm lỗi:\n- ..." ; thuộc tính problems
# loader.py
PACKS_ROOT: Path
def load_pack(pack_id: str, *, root: Path = PACKS_ROOT) -> PackSpec
```
`pack.yaml` có các khóa: `id`, `version`, `extends`, `document_kinds`, `units` (danh sách), `conversions` (`{đơn vị: {base, factor}}`), `document_facts` (`{tên: đơn vị|null}`), `user_facts` (danh sách), `findings` (danh sách), `silences` (`{tên: {applicable: [status, finding], unknown: [status, finding]}}`).

- [ ] **Step 1: Viết test thất bại**

```python
def test_labor_pack_declarations_match_legacy_constants():
    p = load_pack("labor")
    assert p.document_facts == {"contract_kind": None, "term_months": "month", "base_salary_vnd": "vnd",
        "has_probation": None, "probation_length": "day", "probation_pay_pct": "percent",
        "job_level": None, "sign_date": None}
    assert p.user_facts == frozenset({"work_condition", "pregnant", "pregnancy_month", "child_under_12_months",
        "employee_consent", "medical_certificate", "wage_region", "employee_is_female"})
    assert p.units.names == frozenset({"day","workday","week","month","hour","minute","percent","vnd","count"})
    assert p.silences["hidden_right"] == Silence(("PASS","hidden_right"), ("UNKNOWN","possible_right"))
    assert p.silences["none"] == CORE_SILENCES["none"] and p.document_kinds == ("labor_contract",) and p.extends == ()
    assert p.context().reported == frozenset({"violation","missing_content","hidden_right","possible_right"})
def test_units_convert_matches_legacy_table():
    u = load_pack("labor").units
    assert (u.convert(2,"month","day"), u.convert(1,"week","day"), u.convert(1,"day","hour"), u.convert(48,"hour","day")) == (60, 7, 24, 2)
    assert u.convert(3,"workday","day") is None and u.convert(5,"percent","percent") == 5
    assert u.convert(1,"minute","hour") == 1/60
def test_pack_problems_reported_together(tmp_path):   # một pack.yaml có: conversions nhắc đơn vị không có trong units; factor <= 0;
    # silence trỏ finding không khai báo; extends không phải danh sách -> CatalogError.problems chứa đủ ≥ 4 vấn đề trong một lần
def test_unknown_pack_id_rejected(): # load_pack("khong_co") -> CatalogError, problems nhắc id
```

- [ ] **Step 2: Chạy, xác nhận fail** → ImportError.

- [ ] **Step 3: Cài đặt** `units.py`, `model.py`, `load_pack`, và viết `packs/labor/pack.yaml` với đúng giá trị trong test (factor `minute` = `0.016666666666666666`; `hour: {base: hour, factor: 1}`). Bộ nạp gom mọi lỗi vào một `CatalogError`.

- [ ] **Step 4: Chạy** `pytest tests/test_rules_pack.py -q` → 4 passed.

- [ ] **Step 5: Commit** — `feat(team-4.2): rules — Units, model và gói labor (pack.yaml)`.

---

### Task 4: `semantics.py` — logic thuần có `Context` (D1)

**Files:**
- Create: `src/rag/rules/semantics.py`; Modify: `src/rag/rules/model.py` (thêm `Rule`, `Concept`, `Slot`, `Catalog`, `leaves`, `OPS`, `MODES`, `DEROGATIONS`, `SLOT_KINDS`)
- Test: `tests/test_rules_semantics.py`

**Interfaces:**
- Consumes: `Units`, `Context`, `Silence` (Task 3).
- Produces (mọi hàm nhận `ctx: Context`, không có mặc định lao động):

```python
# model.py — Rule có thêm trường cuối `unstated_false: bool = False`; Catalog(version, law_values_valid_from, roles, concepts, context)
# semantics.py
Tri = Literal["T","F","U"]
@dataclass(frozen=True) class Fact: ...                # đúng các trường cũ (value, unit, source, uid, quote, amended_from, later_amendments)
CONFLICT: _Conflict; UNKNOWN: _Unknown                  # singleton; _Conflict giữ nguyên tên (facts_map import)
def is_unresolved(f: object) -> bool                    # f is CONFLICT or f is UNKNOWN
Facts = dict[str, "Fact | _Conflict | _Unknown"]
def compare(left, left_unit, op, right, right_unit, units: Units) -> Tri
def eval_cond(cond: dict | None, facts: Facts, ctx: Context) -> Tri
def check_cond(cond: dict, facts: Facts, law: dict, ctx: Context) -> Tri         # trước là `_check`
def resolve_law(rule: Rule, facts: Facts, day: date, ctx: Context) -> tuple[dict | None, Tri, tuple[str, ...]]
def fact_names(cond) -> list[str]; def referenced(rule: Rule) -> list[str]
@dataclass(frozen=True) class RuleResult: ...           # đúng 11 trường, thứ tự cũ
def evaluate_rule(concept_id: str, rule: Rule, facts: Facts, present: bool, evidence, day: date,
                  slots, ctx: Context) -> RuleResult
```

Hành vi phải giữ đúng engine cũ, chỉ đổi cách lấy dữ liệu:
- `_contract_level_check` → `fact_names(check)` không rỗng, mọi tên ∈ `ctx.document_facts`, và có ít nhất một tên mà `facts.get(n) is not None`.
- `_unstated_restriction` → `rule.unstated_false and facts.get(rule.check["fact"]) is None`.
- Nhánh `on_silence` theo bảng `ctx.silences[rule.on_silence]`: nếu `app == "U"` và `unknown != applicable` thì dùng `unknown` với `reasons = ("applicability_unknown",)`; ngược lại dùng `applicable` với `reasons` của luật (với `none`: `PASS/ok`).
- `UNKNOWN` xử lý như `CONFLICT` ở mọi lá (`op` so sánh, `present`, `absent`, khóa `by`, `check_cond`); không vào `facts_used`; không vào `missing_facts`; cờ `conflict` của finding vẫn chỉ xét `is CONFLICT`.
- `_REPORTED` → `finding in ctx.reported`.

- [ ] **Step 1: Viết test thất bại** (dùng `ctx = load_pack("labor").context()`; dựng `Rule` tay bằng hàm `mk_rule(**kw)` với mặc định `mode="threshold", derogation="floor", on_silence="none", applicability=None, law={}, cases=(), check=None, outcome={}`)

```python
def test_kleene_and_units_ported():      # chép từ tests/test_bridge_engine.py::test_kleene và ::test_units, thêm tham số ctx
def test_unknown_behaves_like_conflict_at_leaves():
    for op in ("eq", "lt", "present", "absent"):
        assert eval_cond({"fact": "d", "op": op, "value": 1}, {"d": UNKNOWN}, ctx) == "U"
    # resolve_law với by-fact = UNKNOWN -> (None, "U", ("missing_fact:wage_region",)) trên một rule có periods dựng tay
def test_unknown_excluded_from_facts_used_and_missing():
    # rule check d == 1; facts {"d": UNKNOWN}, present=True -> status UNKNOWN, "d" not in facts_used, "d" not in missing_facts
@pytest.mark.parametrize(...)            # bảng on_silence: (silence, app T|U, present False) -> (status, finding, reasons)
    # missing_content: T -> FAIL/missing_content ; U -> UNKNOWN/needs_facts, reasons == ("applicability_unknown",)
    # hidden_right  : T -> PASS/hidden_right     ; U -> UNKNOWN/possible_right
    # none          : T,U -> PASS/ok
def test_document_level_check_counts_as_present():
    # rule check base_salary_vnd gte 5_000_000, present=False, facts base_salary_vnd=Fact(4_000_000,"vnd") -> FAIL/violation
    # cùng rule, ctx có document_facts rỗng -> đi nhánh on_silence (hidden_right -> PASS/hidden_right)
def test_unstated_restriction_flag():
    # check {"fact":"x","op":"eq","value":False}, unstated_false=True, present=True, x thiếu -> PASS, "restriction_not_stated" in reasons
    # unstated_false=False -> UNKNOWN/needs_facts
```

- [ ] **Step 2: Chạy, xác nhận fail** → ImportError.

- [ ] **Step 3: Cài đặt** `semantics.py` bằng cách chuyển (không viết lại) thân hàm từ `src/rag/bridge/engine.py`, thay `convert` bằng `ctx.units.convert`, thay các hook như trên. Đưa `Rule`/`Concept`/`Slot`/`Catalog`/`leaves` và hằng `OPS`… sang `model.py` (giá trị hằng giữ nguyên: `OPS = {eq, lt, lte, gt, gte, in, present, absent}`; `MODES = {required, threshold, prohibited, default}`; `DEROGATIONS = {floor, mandatory, default}`; `SLOT_KINDS = {duration, percent, money, bool, enum}`). **Chưa sửa** `bridge/engine.py` hay `bridge/catalog.py` ở task này.

- [ ] **Step 4: Chạy** `pytest tests/test_rules_semantics.py -q` → passed; chạy GATE → không đổi so baseline (chưa đụng code cũ).

- [ ] **Step 5: Commit** — `feat(team-4.2): rules — semantics thuần có Context, UNKNOWN, bảng on_silence`.

---

### Task 5: `load_concepts`, chuyển `concepts.yaml`, `bridge/catalog.py` thành shim (D2, D3, D4)

**Files:**
- Move: `src/rag/bridge/concepts.yaml` → `src/rag/rules/packs/labor/concepts.yaml` (`git mv`; sửa dòng chú thích "Bộ nạp và kiểm" trỏ `src/rag/rules/loader.py`; không đổi gì khác)
- Modify: `src/rag/rules/loader.py` (thêm `load_concepts`), `src/rag/bridge/catalog.py` (còn lại là shim), `pyproject.toml` (`[tool.setuptools.package-data]` thêm `"rag.rules" = ["packs/*/*.yaml"]`)
- Test: `tests/test_rules_loader.py`

**Interfaces:**
- Consumes: `PackSpec`, `Context`, `Rule`… (Task 3, 4).
- Produces:

```python
def load_concepts(path: Path, pack: PackSpec) -> Catalog      # nội dung = load_catalog cũ, kiểm theo `pack`
# bridge/catalog.py (shim): DEFAULT_PATH = PACKS_ROOT/"labor"/"concepts.yaml"; load_catalog(path=DEFAULT_PATH) = load_concepts(path, labor_pack())
def labor_pack() -> PackSpec        # @lru_cache
def labor_context() -> Context
# hằng tương thích: CONTRACT_FACTS = dict(pack.document_facts); USER_FACTS = pack.user_facts; UNITS = pack.units.names; OPS; _leaves = model.leaves
```
Kiểm theo gói: dữ kiện hợp lệ = slot ∪ `pack.document_facts` ∪ `pack.user_facts`; đơn vị hợp lệ = `pack.units.names`; `on_silence` hợp lệ = `pack.silences`. Thông điệp lỗi giữ nguyên chuỗi cũ (test cũ tìm các từ "trùng id", "role", "toán tử", "law", "dữ kiện", "mode", "đơn vị", "not_about"); lỗi `on_silence` chứa từ "on_silence". `Rule.unstated_false`: lấy từ khóa YAML `unstated_false` nếu có; nếu không, `True` khi `check` có dạng `{fact ∈ slot của concept, op: eq, value: False}` và không có `law`.

- [ ] **Step 1: Viết test thất bại**

```python
def test_real_labor_catalog_via_new_loader():
    c = load_concepts(DEFAULT_PATH, load_pack("labor"))
    assert len(c.concepts) == 39 and sum(len(x.rules) for x in c.concepts.values()) == 44
    assert c.context.units.convert(2, "month", "day") == 60
def test_unstated_false_inferred_on_known_rules():
    c = load_catalog()
    assert c.concepts["probation.once"].rules[0].unstated_false is True
    assert c.concepts["probation.pay"].rules[0].unstated_false is False
def test_unstated_false_explicit_override_and_mismatch(tmp_path):   # BASE dict tối thiểu (chép từ tests/test_bridge_catalog.py)
    # khóa `unstated_false: false` trên rule khớp dạng -> False;  `unstated_false: true` trên rule check dạng `gte` -> CatalogError, problem chứa "unstated_false"
def test_on_silence_must_be_declared_by_pack(tmp_path):
    # pack dựng trong tmp_path không khai báo hidden_right; concept dùng on_silence: hidden_right -> problem chứa "on_silence"
def test_all_problems_reported_at_once(tmp_path):   # concepts.yaml có 3 lỗi khác loại -> len(problems) >= 3 trong một CatalogError
def test_labor_concepts_yaml_moved_and_old_path_gone():
    assert DEFAULT_PATH.parts[-4:] == ("rules", "packs", "labor", "concepts.yaml") and not Path("src/rag/bridge/concepts.yaml").exists()
```

- [ ] **Step 2: Chạy, xác nhận fail.**

- [ ] **Step 3: Cài đặt** `load_concepts` (chuyển thân `load_catalog`, `_rule`, `_slots`, `_check_law_values`, `_law_names` từ `bridge/catalog.py`, thay các hằng cứng bằng tham số `pack`); `git mv` file YAML; viết lại `bridge/catalog.py` thành shim giữ nguyên `__all__` cũ cộng `labor_pack`, `labor_context`. `bridge/engine.py` **chưa** đổi — nó vẫn chạy được trên `Catalog`/`Rule` mới vì dùng `Rule` theo tên trường và nhận `_leaves`, `CONTRACT_FACTS` từ shim.

- [ ] **Step 4: Chạy** `pytest tests/test_rules_loader.py tests/test_bridge_catalog.py tests/test_rules_golden.py -q` rồi GATE → mọi test cũ + golden xanh.

- [ ] **Step 5: Commit** — `feat(team-4.2): rules — load_concepts, chuyển concepts.yaml sang packs/labor`. **Báo Huy / LU** đường dẫn mới `src/rag/rules/packs/labor/concepts.yaml`.

---

### Task 6: Reference — tính toàn bộ, kiểm chứng với golden (D5)

**Files:**
- Create: `src/rag/rules/reference.py`
- Modify: `tests/test_rules_golden.py`
- Test: `tests/test_rules_reference.py`

**Interfaces:**
- Consumes: `evaluate_rule`, `Catalog`, `Context`.
- Produces:

```python
def evaluate_concept(concept: Concept, facts: Facts, *, present: bool, evidence=(), day: date, ctx: Context) -> list[RuleResult]
def evaluate_all(catalog: Catalog, facts: Facts, present: set[str], evidence: dict[str, list[dict]], day: date) -> list[RuleResult]
    # thứ tự concept theo catalog, rule theo concept; dùng catalog.context
```

- [ ] **Step 1: Viết test thất bại**

```python
# tests/test_rules_golden.py
def test_golden_via_rules_reference():   # golden_cases qua rules.reference.evaluate_concept với ctx=catalog.context; mismatches == []
# tests/test_rules_reference.py
def test_evaluate_all_matches_old_engine_on_whole_catalog():
    # so rag.bridge.engine.evaluate (engine cũ, chưa bị đổi) với evaluate_all trên: facts rỗng; và facts {"contract_kind": Fact("xac_dinh_thoi_han"), "term_months": Fact(48,"month")}; asdict từng cặp bằng nhau
def test_evaluate_all_count_and_order():
    assert len(res) == sum(len(c.rules) for c in cat.concepts.values())
```

- [ ] **Step 2: Chạy, xác nhận fail** → ImportError.

- [ ] **Step 3: Cài đặt** `reference.py` (mỗi concept gọi `evaluate_rule` cho từng rule với `slots=concept.slots`).

- [ ] **Step 4: Chạy** `pytest tests/test_rules_reference.py tests/test_rules_golden.py -q` → passed. Đây là điểm kiểm chứng chính: engine mới = engine cũ trên toàn golden **trước khi** engine cũ bị xóa.

- [ ] **Step 5: Commit** — `feat(team-4.2): rules — ReferenceEvaluator (hàm tính toàn bộ), khớp golden`.

---

### Task 7: `bridge/engine.py` thành shim (D6, D7)

**Files:**
- Modify: `src/rag/bridge/engine.py`, `src/rag/contracts/graph/tools.py:194` (truyền `ctx=catalog.context`)
- Test: `tests/test_rules_compat.py`

**Interfaces:**
- Consumes: `rag.rules.semantics`, `rag.rules.reference`, `rag.bridge.catalog.labor_context`.
- Produces — các tên công khai cũ, hành vi như cũ:

```python
def convert(value, unit, to) -> float | None                     # dùng labor_context().units
def compare(left, left_unit, op, right, right_unit) -> Tri        # dùng labor units
def eval_cond(cond, facts) -> Tri; def resolve_law(rule, facts, day) -> ...   # ctx = labor_context()
def evaluate_concept(concept, facts, *, present, evidence=(), day, ctx: Context | None = None)   # ctx None -> labor_context()
def evaluate(catalog, facts, present, evidence, day)              # dùng catalog.context
# re-export: CONFLICT, Fact, Facts, RuleResult, Tri, _Conflict ; __all__ giữ như cũ
```

- [ ] **Step 1: Viết test thất bại**

```python
def test_compat_exports_and_labor_defaults():
    from rag.bridge.engine import CONFLICT, Fact, Facts, RuleResult, Tri, _Conflict, compare, convert, eval_cond, evaluate, evaluate_concept, resolve_law
    assert convert(2, "month", "day") == 60 and isinstance(CONFLICT, _Conflict)
def test_evaluate_concept_without_ctx_uses_labor_units_and_with_ctx_uses_given():
    # Concept dựng tay, 1 rule: check {"fact":"h","op":"lte","value":8,"unit":"hour"}, fact Fact(1,"day"), present=True
    # không ctx: 1 day = 24h > 8 -> FAIL/violation ; ctx của pack tmp có conversions day: {base: hour, factor: 8} -> PASS/ok
def test_bridge_catalog_shim_exports():
    # CONTRACT_FACTS == dict(labor document_facts), USER_FACTS, UNITS, OPS, _leaves, DEFAULT_PATH tồn tại; load_catalog() trả Catalog có .context
```

- [ ] **Step 2: Chạy, xác nhận fail** (test `ctx=` fail vì engine cũ không nhận `ctx`).

- [ ] **Step 3: Cài đặt** — thay toàn bộ nội dung `bridge/engine.py` bằng lớp tương thích; trong `tools.py` thêm `ctx=catalog.context` vào lời gọi `evaluate_concept`.

- [ ] **Step 4: Chạy** `pytest tests/test_rules_compat.py tests/test_rules_golden.py tests/test_bridge_engine.py -q` rồi **GATE** → số passed bằng baseline Task 1, 0 test mới fail.

- [ ] **Step 5: Commit** — `refactor(team-4.2): bridge.engine thành lớp tương thích trên rag.rules`.

---

### Task 8: `ReferenceEvaluator` + `Session` + `Diff`, thay stub (A3, D5)

**Files:**
- Modify: `src/rag/rules/evaluator.py` (xóa `StubEvaluator`, đổi import sang `rag.rules.semantics`), `tests/test_rules_evaluator_stub.py` → đổi tên `tests/test_rules_evaluator.py`
- Test: `tests/test_rules_evaluator.py`

**Interfaces:**
- Consumes: `evaluate_all` (Task 6), `load_packs`/`load_concepts` (dùng `load_concepts(DEFAULT_PATH, load_pack("labor"))` cho `["labor"]` cho đến Task 9).
- Produces: `ReferenceEvaluator(catalog: Catalog)`; `evaluator_for(catalog: Catalog, kind: EvaluatorKind = "reference") -> Evaluator`; `make_evaluator(packs, kind)` nạp catalog thật. Quy tắc `update`: `None` trong `changes` xóa dữ kiện; `present` / `evidence` nếu truyền thì **thay hẳn** giá trị hiện có; `Diff` liệt kê (theo thứ tự catalog) các rule có `before != after`; `objects` khác rỗng/None → `NotImplementedError("objects: giai đoạn 7")`; `fork()` sao chép sâu dữ kiện, `present`, `evidence`.

- [ ] **Step 1: Viết test thất bại**

```python
def test_session_results_equal_evaluate_all(): ...
def test_update_diff_sequence_on_leave_annual():
    # facts {"work_condition": Fact("binh_thuong")}, present {"leave.annual"}, day 2025-03-01
    # ban đầu leave.annual/r1: UNKNOWN/needs_facts
    # update({"annual_leave": Fact(8,"day")}) -> Diff có đúng 1 RuleChange("leave.annual","r1"), after.status=="FAIL", after.finding=="violation"
    # update({"annual_leave": Fact(15,"day")}) -> after PASS/ok ; update cùng giá trị 15 lần nữa -> Diff(changes=()) 
    # update({"annual_leave": None}) -> after UNKNOWN/needs_facts
def test_fork_is_independent():     # sửa fork không đổi results() của bản gốc
def test_update_with_objects_not_supported_yet(): pytest.raises(NotImplementedError)
def test_network_kind_not_available_yet(): pytest.raises(NotImplementedError)
def test_stub_removed(): not hasattr(evaluator, "StubEvaluator")
```

- [ ] **Step 2: Chạy, xác nhận fail.** **Step 3: Cài đặt.** **Step 4: Chạy** `pytest tests/test_rules_evaluator.py -q` → passed; chạy lại GATE.

- [ ] **Step 5: Commit** — `feat(team-4.2): rules — ReferenceEvaluator, Session, Diff`. **Báo Khánh:** `make_evaluator(["labor"])` đã trả dữ liệu thật.

---

### Task 9: `extends` + `load_packs` + trùng id (D2) — có thể hoãn sang giai đoạn 5 nếu thiếu thời gian

**Files:**
- Modify: `src/rag/rules/loader.py`, `src/rag/rules/evaluator.py` (`make_evaluator` dùng `load_packs`)
- Test: `tests/test_rules_packs_merge.py`

**Interfaces:**
- Produces: `load_packs(pack_ids: Sequence[str], *, root: Path = PACKS_ROOT) -> Catalog`. Gói cha (theo `extends`) được nạp trước, gói con thấy dữ kiện / đơn vị / `silences` của cha; thứ tự concept: cha trước con. Lỗi gom một lần: `extends` thiếu hoặc vòng; concept trùng id giữa các gói; cùng một đơn vị khai báo hệ số khác nhau; role cùng id nhưng nội dung khác (giống hệt thì hợp nhất). `Catalog.version` = `"+".join(f"{id}@{version}")`; `law_values_valid_from` = ngày lớn nhất; `context` = hợp nhất.

- [ ] **Step 1: Viết test thất bại** (dựng thư mục gói trong `tmp_path`, truyền `root=tmp_path`)

```python
def test_child_sees_parent_declarations_and_parent_loads_first():  # concept con dùng user_fact và unit của cha -> nạp được; list(concepts) cha trước con
def test_duplicate_concept_id_across_packs_rejected():              # problems chứa "trùng id"
def test_extends_missing_and_cycle_rejected():                      # problems chứa "extends"
def test_conflicting_unit_factor_rejected(): ...
def test_identical_roles_merge_but_different_roles_rejected(): ...
def test_load_packs_labor_only_equals_load_catalog():               # concepts, version, context.units của load_packs(["labor"]) khớp load_catalog()
```

- [ ] **Step 2–4:** fail → cài đặt → `pytest tests/test_rules_packs_merge.py -q` passed, rồi GATE.
- [ ] **Step 5: Commit** — `feat(team-4.2): rules — extends và gộp nhiều gói`.

---

### Task 10: Nghiệm thu giai đoạn 1

**Files:**
- Modify: `docs/phan_cong_w04/tung_viec_can_lam.md` (đánh dấu A3–A5, D1–D7 đã xong)

- [ ] **Step 1: Chạy GATE** → số passed bằng baseline Task 1, 0 fail mới.
- [ ] **Step 2: Chạy toàn bộ** `.venv/Scripts/python.exe -m pytest -q --ignore=tests/test_agent_partial_review.py -rf` → đúng 35 test fail như baseline (so tên với `reports/week-04/team-4.2/phase1_baseline.md`; thêm test mới của giai đoạn 1 đều passed).
- [ ] **Step 3: Chạy golden lần cuối** `pytest tests/test_rules_golden.py -q` → 4 passed (bridge API và rules.reference).
- [ ] **Step 4: Kiểm không còn tham chiếu cũ**: `grep -rn "bridge/concepts" src ui scripts` không ra kết quả; `git status` không có file lạ.
- [ ] **Step 5: Cập nhật checklist, commit** — `docs(team-4.2): giai đoạn 1 rule engine hoàn tất`. Mở PR từ `feat/team-4.2/w04-rules-engine`.

---

## Self-Review

**Spec coverage:** §3 (API cũ, YAML không đổi, trường LU đọc) → Task 5, 7; §5.1 (`UNKNOWN`, đơn vị theo gói) → Task 3, 4; §5.2 (hai hook → khai báo, bảng trạng thái) → Task 4, 5; §5.5 (thư mục gói, `extends`, trùng id, `findings`, hằng tương thích, chuyển `labor`) → Task 3, 5, 9; §7 (module, `Evaluator`) → Task 2, 6, 8; §10 (golden, tương đương engine cũ) → Task 1, 6, 7, 10. **Hoãn có chủ đích:** §5.3, §5.4, §5.6, §6, §8, §9 (giai đoạn 2–7), `kind`, `outcome` nguyên dạng, câu hỏi `user_facts` (giai đoạn 4/5) — ghi ở mục "Lệch spec".

**Type consistency:** `Context` / `Silence` / `PackSpec` định nghĩa ở Task 3, dùng nguyên tên ở Task 4–9; `evaluate_concept(..., ctx=)` ở Task 6 khớp Task 7; `Diff` / `RuleChange` ở Task 2 khớp Task 8; `load_pack` / `load_concepts` / `load_packs` đồng nhất giữa Task 3, 5, 8, 9.

**Review Focus:** mục 1 → Task 4; mục 2 → Task 3, 5; mục 3 → Task 5; mục 4 → Task 8; mục 5 → Task 7.
