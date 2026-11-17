# Soát HĐLĐ theo danh mục khái niệm — Kế hoạch triển khai

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Đọc một HĐLĐ, gán điều khoản vào danh mục khái niệm bằng LLM, rồi dùng rule tất định ba trị để báo vi phạm, thiếu nội dung bắt buộc và quyền ẩn, kèm trích dẫn hợp đồng và khoản luật.

**Architecture:** Gói mới `src/rag/bridge/` đọc `concepts.yaml`. LLM (tagger) chỉ nhận diện khái niệm + trích giá trị, ghi thành thao tác `ASSERT` trong nhật ký đồ thị hợp đồng. Engine thuần Python đánh giá rule trên bảng dữ kiện phẳng (dữ kiện từ `facts.py` + slot của `ASSERT`). Recheck tìm lại khái niệm im lặng trước khi báo. Báo cáo ghép kết quả engine với căn cứ luật.

**Tech Stack:** Python 3.12, PyYAML (đã có), pytest, `rag.contracts` (batches, llm_json, values, oplog, graph), `rag.index.bm25_index.BM25Index`, `rag.legal.graph.query.LegalGraph`.

**Spec:** `app/team-4.2/docs/superpowers/specs/2026-11-14-contract-concept-check-design.md`

Mọi lệnh chạy trong `app/team-4.2`. Test: `uv run pytest <path> -q`.

## Global Constraints

- LLM không bao giờ nhận ngưỡng luật, rule hay neo; chỉ nhận `id`, `label`, `describe`, `phrasing`, `slots` của khái niệm.
- Mọi lời gọi LLM đi qua `rag.contracts.llm_json.ask_json` (che PII bằng `contract.mask_state`).
- Dữ kiện nguồn `user` không bao giờ vào payload LLM.
- Thiếu dữ kiện hoặc dữ kiện `conflict` → `UNKNOWN`, không bao giờ `FAIL`.
- Engine không I/O, tất định.
- Trạng thái kết quả: `PASS | FAIL | UNKNOWN | NOT_APPLICABLE`. Loại phát hiện: `ok | violation | missing_content | hidden_right | possible_right | needs_facts | conflict`.
- Nội dung `ASSERT` khái niệm: `{"kind": "concept", "concept_id", "slots_raw": {..}, "slots": {name: {"value", "unit"}}, "catalog_version", "found_by": "tagger"|"recheck"}`; vắng mặt: `{"kind": "concept_absent", "concept_id", "searched_uids": [...], "catalog_version"}`; bên: `{"kind": "party", "role": "NLD"|"NSDLD", "label"}`. `target` của op = `concept_id` (hoặc `"party:<role>"`).
- Đơn vị dùng chung: `day, workday, week, month, hour, minute, percent, vnd, count`, hoặc `None` cho `bool`/`enum`. Quy đổi duy nhất được phép: `week=7 day`, `month=30 day`, `day=24 hour`. `workday` không quy đổi.
- Không lưu tên người / công ty vào đồ thị; mọi chuỗi vào đồ thị đã qua `mask_text`.

## Review Focus

1. Hợp đồng ghi cùng khái niệm ở hai nơi với hai giá trị (hợp đồng chính 15 triệu, phụ lục 17 triệu) → phải ra `conflict`, không chọn bừa (Task 6).
2. LLM trả `uid` của đơn vị tham khảo / ngữ cảnh chứ không phải của lô → item sửa về đơn vị của lô chứa trích dẫn, hoặc loại (Task 7).
3. LLM trả `concept` lạ, slot lạ, hoặc JSON hỏng hai lần → không crash, ghi cảnh báo, các lô khác vẫn chạy (Task 7).
4. Hợp đồng không có ngày ký → giá trị luật theo kỳ (lương vùng) ra `UNKNOWN`, các rule giá trị cố định vẫn chạy với ngày mặc định `law_values_valid_from` (Task 5).
5. Đồ thị luật chưa công bố / Neo4j tắt → báo cáo vẫn sinh, căn cứ chỉ có neo, ghi `basis_unavailable` (Task 10).

---

### Task 1: Ranh giới phụ lục bắt đầu từ khối quốc hiệu / ngày tháng

**Files:**
- Modify: `src/rag/contracts/parts.py` (`detect_parts`)
- Test: `tests/test_contracts_parts.py`

**Interfaces:**
- Produces: `detect_parts(text) -> list[PartSpec]` giữ chữ ký; `start` của phần phụ lục lùi về dòng đầu của khối đầu trang liền trên tiêu đề.

- [ ] **Step 1: Viết test hỏng**

```python
def test_appendix_starts_at_letterhead_and_date():
    text = ("Điều 1. Nội dung\nA\n<<PAGEBREAK>>\nCỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\n"
            "Độc lập - Tự do - Hạnh phúc\nHà Nội, ngày 01 tháng 07 năm 2025\n"
            "PHỤ LỤC HỢP ĐỒNG LAO ĐỘNG\nNội dung phụ lục dài hơn hai mươi ký tự\n")
    parts = detect_parts(text)
    assert len(parts) == 2
    assert text[parts[1].start:].startswith("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM")
    assert parts[1].title == "PHỤ LỤC HỢP ĐỒNG LAO ĐỘNG"

def test_appendix_without_letterhead_unchanged():
    text = "Điều 1. A\nB\n\nPhụ lục 1\nNội dung phụ lục dài hơn hai mươi ký tự\n"
    parts = detect_parts(text)
    assert text[parts[1].start:].startswith("Phụ lục 1")
```

- [ ] **Step 2:** `uv run pytest tests/test_contracts_parts.py -q` → test đầu FAIL (start ở dòng "PHỤ LỤC").
- [ ] **Step 3: Sửa `detect_parts`.** Thêm `_LETTERHEAD` khớp (không phân biệt hoa thường) một trong: `^CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM`, `^Độc lập\s*[-–]\s*Tự do\s*[-–]\s*Hạnh phúc`, dòng chỉ gồm `[-_=*.\s]+`, `^Số\s*:`, `^[^\d\n]{2,40},\s*ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4}`. Khi nhận một tiêu đề ở dòng `i`, lùi `j` từ `i-1` qua các dòng rỗng hoặc khớp `_LETTERHEAD`; nếu có ít nhất một dòng khớp thì `start` = offset của dòng khớp sớm nhất. Không lùi qua dòng không khớp (kể cả `<<PAGEBREAK>>`), không lùi về trước `start` của phần trước.
- [ ] **Step 4:** chạy lại file test và `tests/test_contracts_structure.py` → PASS.
- [ ] **Step 5: Commit** `fix(team-4.2): appendix part starts at its letterhead and date line`

### Task 2: "Điều N Hợp đồng lao động" trong phụ lục trỏ về hợp đồng chính

**Files:**
- Modify: `src/rag/contracts/xrefs.py:24` (`_BASE_CONTRACT_RE`)
- Test: `tests/test_contracts_xrefs.py`

- [ ] **Step 1: Viết test hỏng** — dựng hai phần qua `parse_contract` (theo mẫu test sẵn có trong file): `p0` có `Điều 2`, `p1` (phụ lục) có `Điều 1` chứa "Sửa đổi Điều 2 Hợp đồng lao động về lương căn bản" và `Điều 2`. Khẳng định dẫn chiếu từ `p1.d1` có `to_uid == "p0.d2"`. Thêm ca "theo Điều 2 của Phụ lục này" vẫn trỏ `p1.d2`, và "Điều 2 Hợp đồng đào tạo" không trỏ `p0.d2` (giữ `p1.d2` hoặc missing).
- [ ] **Step 2:** chạy → FAIL (`p1.d2`).
- [ ] **Step 3:** đổi `_BASE_CONTRACT_RE` thành `\s*(?:của\s+)?(?:bản\s+)?Hợp\s+đồng(?:\s+lao\s+động|\s+gốc|\s+số)?(?!\s+(?:thử\s+việc|đào\s+tạo))\b`.
- [ ] **Step 4:** chạy `tests/test_contracts_xrefs.py tests/test_contracts_structure.py` → PASS.
- [ ] **Step 5: Commit** `fix(team-4.2): appendix reference to "Điều N Hợp đồng lao động" resolves to main contract`

### Task 3: `_in_store` nhận tên luật viết thông thường

**Files:**
- Modify: `src/rag/contracts/review.py:137` (`_in_store`)
- Test: `tests/test_contracts_review.py`

- [ ] **Step 1: Viết test hỏng**

```python
from rag.contracts.review import _in_store
TITLES = ["Bộ Luật lao động số 45/2019/QH14", "Nghị định 145/2020/NĐ-CP quy định chi tiết..."]
def test_in_store_common_names():
    assert _in_store("Bộ luật Lao động 2019", TITLES)
    assert _in_store("BLLĐ 45/2019/QH14", TITLES)
    assert _in_store("Nghị định 145/2020", TITLES)
    assert not _in_store("Bộ luật Lao động 2012", TITLES)
    assert not _in_store("Luật Việc làm", TITLES)
    assert not _in_store(None, TITLES)
```

- [ ] **Step 2:** chạy → FAIL.
- [ ] **Step 3:** viết lại `_in_store(law, titles) -> bool`: (a) nếu `law` có số hiệu `\d+/\d{4}` thì khớp khi tiêu đề chứa đúng số đó; (b) không có số: chuẩn hóa (NFC, casefold, gộp khoảng trắng) và tách năm `\b(19|20)\d{2}\b`; tên gốc = phần trước năm / trước "số"; khớp khi tên gốc của `law` bằng tên gốc của tiêu đề và (không có năm, hoặc năm trùng năm trong số hiệu của tiêu đề).
- [ ] **Step 4:** chạy `tests/test_contracts_review.py` → PASS.
- [ ] **Step 5: Commit** `fix(team-4.2): law-in-store check matches common law names and numbers`

### Task 4: Danh mục — bổ sung `concepts.yaml` và bộ nạp có kiểm tra

**Files:**
- Modify: `src/rag/bridge/concepts.yaml`
- Create: `src/rag/bridge/__init__.py`, `src/rag/bridge/catalog.py`
- Test: `tests/test_bridge_catalog.py`, `tests/fixtures/bridge/` (file YAML hỏng)

**Interfaces:**
- Produces (trong `rag.bridge.catalog`):
  - `DEFAULT_PATH: Path` (trỏ `concepts.yaml`)
  - `UNITS: frozenset[str]`, `OPS = frozenset({"eq","lt","lte","gt","gte","in","present","absent"})`
  - `CONTRACT_FACTS: dict[str, str | None]` = `{"contract_kind": None, "term_months": "month", "base_salary_vnd": "vnd", "has_probation": None, "probation_length": "day", "probation_pay_pct": "percent", "job_level": None, "sign_date": None}`
  - `USER_FACTS: frozenset[str]` = `{"work_condition","pregnant","pregnancy_month","child_under_12_months","employee_consent","medical_certificate","wage_region"}`
  - `@dataclass(frozen=True) Slot(name: str, kind: Literal["duration","percent","money","bool","enum"], unit: str|None, options: tuple[str,...] = ())`
  - `@dataclass(frozen=True) Rule(id, mode, derogation, on_silence, applicability: dict|None, law: dict, cases: tuple[dict,...], check: dict|None, outcome: dict)`
  - `@dataclass(frozen=True) Concept(id, label, scope, phase, holder, counterparty, applies_to: tuple[str,...], describe: str, phrasing: tuple[str,...], slots: dict[str, Slot], anchors: tuple[dict,...], value_sources: tuple[dict,...], rules: tuple[Rule,...])`
  - `@dataclass(frozen=True) Catalog(version: str, law_values_valid_from: date, roles: dict[str, dict], concepts: dict[str, Concept])` — `concepts` giữ thứ tự file.
  - `class CatalogError(ValueError)` có `.problems: list[str]`
  - `load_catalog(path: Path = DEFAULT_PATH) -> Catalog`

**Định dạng giá trị luật** (trong `law` và `cases[].law`): `{name: {value, unit}}`; `value` có thể là số, chuỗi, hoặc danh sách (cho `in`); giá trị theo kỳ: `{name: {by: <fact>, unit, periods: [{valid_from: YYYY-MM-DD, values: {<key>: number}, source: <document_key>}]}}`. `check`: lá `{fact, op, law: <name>}` hoặc `{fact, op, value: <literal>}`, hoặc `{all: [...]}`.

**Sửa `concepts.yaml`** (thêm `slots` + `phrasing` 3–6 cụm cho mọi khái niệm; đổi mọi giá trị luật sang dạng có đơn vị; tên dữ kiện như bảng):

| Khái niệm | `slots` | Giá trị luật / check |
|---|---|---|
| content.insurance | `waives_compulsory_insurance: bool` | r2 giữ |
| content.term | — | r2: `max_term {36, month}`, check `term_months lte` |
| probation.duration | — | cases `max_probation`: `{180,day}`, `{60,day}`, `{30,day}`, `{6,workday}`; check `probation_length lte max_probation` |
| probation.once | `allows_probation_extension: bool` | giữ |
| probation.pay | — | `min_probation_pay {85, percent}`, check `probation_pay_pct gte` |
| probation.cancel_no_notice | `probation_requires_notice_or_compensation: bool` | giữ |
| wage.minimum_regional | — | `min_wage {by: wage_region, unit: vnd, periods:}` NĐ 38/2022 từ 2022-07-01 `{I: 4680000, II: 4160000, III: 3640000, IV: 3250000}`; NĐ 74/2024 từ 2024-07-01 `{I: 4960000, II: 4410000, III: 3860000, IV: 3450000}`; NĐ 293/2025 từ 2026-01-01 `{I: 5310000, II: 4730000, III: 4140000, IV: 3700000}`; check `base_salary_vnd gte min_wage` |
| wage.pay_period | `pay_frequency: enum [hang_thang, nua_thang, hang_tuan, hang_ngay, theo_gio, khac]` | `allowed_pay_frequency {[hang_thang, nua_thang, hang_tuan, hang_ngay, theo_gio], None}`, check `pay_frequency in` |
| wage.overtime_pay | `ot_weekday_pct, ot_weekly_rest_pct, ot_holiday_pct: percent` | `{150}, {200}, {300}` percent; `gte` từng cái |
| wage.night_pay | `night_extra_pct: percent` | `{30, percent}` |
| wage.deduction_limit | `deduction_pct: percent`, `deducts_for_reason_other_than_damage: bool` | `{30, percent}` `lte` |
| hours.normal | `hours_per_day, hours_per_week: duration hour` | `{8,hour}`, `{48,hour}` |
| hours.overtime_limit | `ot_hours_per_month, ot_hours_per_year: duration hour`, `overtime_without_consent: bool` | `{40,hour}`, `{200,hour}`; r2 `on_silence: none` |
| rest.weekly | `weekly_rest: duration hour` | `{24, hour}` `gte` |
| rest.holidays | `paid_holidays: duration day` | `{11, day}` `gte` |
| leave.annual | `annual_leave: duration day` | cases `{12,day}`, `{14,day}`, `{16,day}` (ngày phép đọc là ngày làm việc: quy ước) |
| leave.personal_paid | `marriage_leave: duration day` | `{3, day}` `gte` |
| termination.employee_unilateral | `employee_notice: duration day` | cases `notice {45,day}`, `{30,day}`, `{3,workday}`; check `employee_notice lte notice` |
| termination.employer_unilateral | `employer_notice: duration day`, `employer_termination_ground_outside_law: bool` | cases như trên; r2 check `employer_notice gte notice` |
| termination.severance | `waives_severance: bool` | bỏ `applicability` |
| termination.settlement_deadline | `settlement_period: duration workday` | `{14, workday}` `lte` |
| prohibit.keep_documents / deposit / fine_instead_of_discipline | bool như YAML hiện có | giữ |
| training.cost_repayment | `has_separate_training_contract: bool` | bỏ `applicability`; check `has_separate_training_contract eq true` |
| maternity.no_dismissal | `restricts_marriage_or_pregnancy: bool` | giữ |
| maternity.leave | `maternity_leave: duration month` | `{6, month}` `gte` |
| maternity (còn lại), các content.* khác | — | giữ |

- [ ] **Step 1: Viết test**

```python
def test_real_catalog_loads():
    c = load_catalog()
    assert len(c.concepts) == 39
    assert c.concepts["leave.annual"].slots["annual_leave"].unit == "day"
    assert all(len(x.phrasing) >= 3 for x in c.concepts.values())

@pytest.mark.parametrize("name,needle", [
    ("dup_id.yaml", "trùng id"), ("bad_role.yaml", "role"), ("bad_op.yaml", "toán tử"),
    ("missing_law.yaml", "law"), ("unknown_fact.yaml", "dữ kiện"), ("bad_mode.yaml", "mode"),
    ("bad_unit.yaml", "đơn vị")])
def test_broken_catalog_rejected(name, needle):
    with pytest.raises(CatalogError) as e:
        load_catalog(FIX / name)
    assert any(needle in p for p in e.value.problems)
```
Mỗi file hỏng là một danh mục 1 khái niệm, sai đúng một chỗ.

Thêm `test_min_wage_values_match_decree_text`: với mỗi kỳ của `min_wage`, tìm file raw của `source` dưới `data/team-4.2/legal/raw/` (thư mục `nghi-dinh_<số>_<năm>_*`); có file thì mỗi số (định dạng `4.960.000`) phải xuất hiện trong văn bản; không có file thì `pytest.skip("kho luật chưa giải nén")`. Các số lương vùng trong bảng là do người lập kế hoạch nhớ, phải qua test này mới tin.

- [ ] **Step 2:** chạy → FAIL (module chưa có).
- [ ] **Step 3:** viết `catalog.py` và sửa YAML. `load_catalog` gom **mọi** lỗi rồi mới raise. Kiểm: id trùng; `holder`/`counterparty`/`applies_to`/`subtype_of` thuộc `roles`; `mode ∈ {required,threshold,prohibited,default}`, `derogation ∈ {floor,mandatory,default}`, `on_silence ∈ {missing_content,hidden_right,none}`; toán tử ∈ `OPS`; đơn vị ∈ `UNITS ∪ {None}`; mọi `check.law` có trong `law` hoặc trong **mọi** `cases[].law`; mọi `fact` trong `check`/`applicability`/`when`/`by` là slot của khái niệm, hoặc thuộc `CONTRACT_FACTS`/`USER_FACTS`.
- [ ] **Step 4:** chạy `tests/test_bridge_catalog.py` → PASS.
- [ ] **Step 5: Commit** `feat(team-4.2): labor concept catalog with slots, unit-tagged law values and validating loader`

### Task 5: Engine — điều kiện ba trị và giá trị luật

**Files:**
- Create: `src/rag/bridge/engine.py`
- Test: `tests/test_bridge_engine.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) Fact(value: Any, unit: str|None = None, source: Literal["contract","concept","user"] = "contract", uid: str|None = None, quote: str|None = None)`
  - `CONFLICT` (sentinel đơn nhất); `Facts = dict[str, Fact | type(CONFLICT)]`
  - `convert(value: float, unit: str, to: str) -> float | None` (chỉ các quy đổi trong Global Constraints)
  - `eval_cond(cond: dict | None, facts: Facts) -> Literal["T","F","U"]` (`None` → `"T"`)
  - `resolve_law(rule: Rule, facts: Facts, day: date) -> tuple[dict[str, dict] | None, Literal["T","F","U"], tuple[str, ...]]` — trả (giá trị luật đã chọn `{name: {value, unit}}`, trạng thái chọn case, lý do)

- [ ] **Step 1: Viết test**

```python
F = lambda v, u=None: Fact(v, u)
def test_kleene():
    facts = {"a": F(1), "b": CONFLICT}
    assert eval_cond({"fact": "a", "op": "eq", "value": 1}, facts) == "T"
    assert eval_cond({"fact": "x", "op": "eq", "value": 1}, facts) == "U"
    assert eval_cond({"fact": "b", "op": "eq", "value": 1}, facts) == "U"
    assert eval_cond({"all": [{"fact": "a", "op": "eq", "value": 2}, {"fact": "x", "op": "eq", "value": 1}]}, facts) == "F"
    assert eval_cond({"any": [{"fact": "a", "op": "eq", "value": 1}, {"fact": "x", "op": "eq", "value": 1}]}, facts) == "T"
    assert eval_cond({"fact": "x", "op": "absent"}, facts) == "T"

def test_units():
    assert convert(2, "month", "day") == 60
    assert convert(1, "day", "hour") == 24
    assert convert(3, "workday", "day") is None
    assert eval_cond({"fact": "h", "op": "lte", "value": 8, "unit": "hour"}, {"h": F(10, "hour")}) == "F"
    assert eval_cond({"fact": "h", "op": "lte", "value": 3, "unit": "workday"}, {"h": F(3, "day")}) == "U"

def test_cases_pick_first_true_and_unknown_blocks():
    rule = load_catalog().concepts["probation.duration"].rules[0]
    law, st, _ = resolve_law(rule, {"job_level": F("cao_dang_tro_len")}, date(2025, 1, 2))
    assert st == "T" and law["max_probation"] == {"value": 60, "unit": "day"}
    assert resolve_law(rule, {}, date(2025, 1, 2))[1] == "U"

def test_periods_by_sign_date():
    rule = load_catalog().concepts["wage.minimum_regional"].rules[0]
    law, st, _ = resolve_law(rule, {"wage_region": F("I")}, date(2025, 3, 1))
    assert law["min_wage"] == {"value": 4960000, "unit": "vnd"}
    assert resolve_law(rule, {"wage_region": F("I")}, date(2026, 2, 1))[0]["min_wage"]["value"] == 5310000
    assert resolve_law(rule, {}, date(2026, 2, 1))[1] == "U"
```

- [ ] **Step 2:** chạy → FAIL.
- [ ] **Step 3:** cài đặt. So sánh số: quy đổi đơn vị của fact sang đơn vị của vế phải bằng `convert`; không quy đổi được → `"U"` kèm lý do `unit_mismatch`. Giá trị theo kỳ: kỳ có `valid_from` lớn nhất `<= day`; không có kỳ nào → `"U"` lý do `law_period_not_covered`; `by` thiếu → `"U"`.
- [ ] **Step 4:** chạy → PASS.
- [ ] **Step 5: Commit** `feat(team-4.2): three-valued conditions and dated law values for concept rules`

### Task 6: Engine — đánh giá rule và bảng ca kiểm cho mọi rule

**Files:**
- Modify: `src/rag/bridge/engine.py`
- Create: `tests/fixtures/bridge/engine_cases.yaml`
- Test: `tests/test_bridge_engine.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) RuleResult(concept_id, rule_id, status, finding, legality: str|None, employee_impact: str|None, law_values: dict, facts_used: dict, missing_facts: tuple[str,...], evidence: tuple[dict,...], reasons: tuple[str,...])`
  - `evaluate_concept(concept: Concept, facts: Facts, *, present: bool, evidence: Sequence[dict] = (), day: date) -> list[RuleResult]`
  - `evaluate(catalog: Catalog, facts: Facts, present: set[str], evidence: dict[str, list[dict]], day: date) -> list[RuleResult]`

Thuật toán đúng theo spec §8 (bước 1–5). Thêm: một fact được `check` dùng mà là `CONFLICT` → `UNKNOWN`, finding `conflict`. `legality`/`employee_impact` lấy từ `outcome` chỉ khi finding ∈ {violation, missing_content, hidden_right, possible_right}.

- [ ] **Step 1: Viết bảng ca** `engine_cases.yaml`: danh sách `{concept, rule, present, facts: {name: [value, unit]}, day, expect: {status, finding}}`, mỗi rule của danh mục ≥ 3 ca (đúng / sai hoặc im lặng / thiếu dữ kiện). Bắt buộc có: `leave.annual` 15 ngày việc bình thường → PASS ok (`floor`); 8 ngày → FAIL violation; 8 ngày thiếu `work_condition` → UNKNOWN needs_facts; im lặng + `work_condition` → PASS hidden_right; `maternity.leave` im lặng không có `pregnant` → UNKNOWN possible_right; `prohibit.deposit` im lặng → PASS ok; `content.raise_policy` im lặng → FAIL missing_content; `termination.employee_unilateral` HĐ 24 tháng, `employee_notice` 60 day → FAIL violation; `probation_length` 6 day với job `cong_viec_khac` → UNKNOWN (`unit_mismatch`); `base_salary_vnd` CONFLICT → UNKNOWN conflict.
- [ ] **Step 2: Viết test**

```python
CASES = yaml.safe_load((FIX / "engine_cases.yaml").read_text(encoding="utf-8"))
@pytest.mark.parametrize("case", CASES, ids=lambda c: f'{c["concept"]}/{c["rule"]}/{c["expect"]["finding"]}')
def test_engine_case(case): ...  # dựng Facts, gọi evaluate_concept, so status + finding của rule đó

def test_every_rule_has_three_cases():
    cat = load_catalog()
    count = Counter((c["concept"], c["rule"]) for c in CASES)
    assert [ (k, r.id) for k, x in cat.concepts.items() for r in x.rules if count[(k, r.id)] < 3 ] == []
```

- [ ] **Step 3:** chạy → FAIL.
- [ ] **Step 4:** cài `evaluate_concept`, `evaluate`.
- [ ] **Step 5:** chạy `tests/test_bridge_engine.py` → PASS.
- [ ] **Step 6: Commit** `feat(team-4.2): concept rule evaluation with per-rule case table`

### Task 7: Dữ kiện — từ `facts.py` và từ `ASSERT`

**Files:**
- Create: `src/rag/bridge/facts_map.py`
- Test: `tests/test_bridge_facts_map.py`

**Interfaces:**
- Consumes: `CONTRACT_FACTS` (Task 4), `Fact`, `CONFLICT` (Task 5), `rag.contracts.values.extract_values`.
- Produces:
  - `normalize_slot(slot: Slot, raw: Any) -> Fact | None`
  - `contract_facts(facts: dict, *, sign_date: date | None) -> Facts` — đầu vào là `contract.facts` của `extract_facts`
  - `@dataclass(frozen=True) FactSet(facts: Facts, present: frozenset[str], evidence: dict[str, list[dict]], absent_checked: frozenset[str])`
  - `build_factset(contract_level: Facts, ops: Sequence[GraphOperation]) -> FactSet`

Ánh xạ cấp hợp đồng (lấy từ `facts["candidates"][key]`, mỗi ứng viên `{value, unit(=uid), quote}`; hai ứng viên khác giá trị sau chuẩn hóa → `CONFLICT`):

| fact | nguồn | chuẩn hóa |
|---|---|---|
| `contract_kind` | `labor_kind` | "Không xác định thời hạn" → `khong_xac_dinh_thoi_han`, "Xác định thời hạn" → `xac_dinh_thoi_han` |
| `term_months` | `term` | duration: tháng → n; năm → 12n; ngày → n/30 |
| `base_salary_vnd` | `salary` | money **đầu tiên** trong chuỗi |
| `has_probation` | `probation_period` | có ứng viên → True |
| `probation_length` | `probation_period` | duration: "ngày làm việc" → workday; ngày → day; tháng → month; tuần → week |
| `probation_pay_pct` | `probation_salary` | percent |
| `job_level` | `job_level` | 4 chuỗi của `job_levels` theo thứ tự → `quan_ly_doanh_nghiep`, `cao_dang_tro_len`, `trung_cap_ky_thuat`, `cong_viec_khac` |
| `sign_date` | tham số `sign_date` | `Fact(date)` |

`normalize_slot`: `duration` → `extract_values` lấy giá trị duration đầu tiên, đơn vị theo bảng trên ("giờ" → hour); không có → `None`; `percent`/`money` tương tự; `bool` nhận `true/false` (bool hoặc chuỗi); `enum` nhận giá trị thuộc `options`.

`build_factset`: chỉ op đang hiệu lực (`status ∈ {auto_accepted, approved}`) kiểu `ASSERT`; `kind=concept` → `present` + `evidence[concept_id].append({"uid": op.source_uid, "quote": op.quote[0], "op_id": op.op_id})` + slot thành `Fact(source="concept")`; cùng slot hai giá trị khác → `CONFLICT`; trùng tên với dữ kiện cấp hợp đồng mà khác giá trị → `CONFLICT`. `kind=concept_absent` → `absent_checked`.

- [ ] **Step 1: Viết test** — `contract_facts` trên dict mẫu dạng thật (copy từ `notes/2026-11-14-contract-pipeline-real-run.md` §[6]: lương 15.000.000 và 17.000.000) → `base_salary_vnd is CONFLICT`; `probation_period` "02 tháng" → `Fact(2, "month")`; "06 ngày làm việc" → `Fact(6, "workday")`; `job_level` "Công việc cần trình độ cao đẳng trở lên" → `cao_dang_tro_len`. `build_factset` với hai op giả cùng `leave.annual` slot 12 và 14 → `annual_leave` là `CONFLICT`, `present == {"leave.annual"}`, evidence có 2 phần tử; op `rejected` bị bỏ qua.
- [ ] **Step 2:** chạy → FAIL. **Step 3:** cài. **Step 4:** → PASS.
- [ ] **Step 5: Commit** `feat(team-4.2): map contract facts and concept assertions into rule facts`

### Task 8: Tagger — LLM gán khái niệm cho điều khoản

**Files:**
- Create: `src/rag/bridge/tagger.py`
- Test: `tests/test_bridge_tagger.py`

**Interfaces:**
- Consumes: `make_batches`, `run_batches`, `unit_text` (`rag.contracts.batches`); `ask_json`, `quote_ok`; `machine_op`; `normalize_slot` (Task 7).
- Produces:
  - `TAG_PROMPT_VERSION = "concept-tag-1"`
  - `catalog_payload(catalog: Catalog) -> list[dict]` — mỗi khái niệm `{id, label, describe, phrasing, slots: {name: {kind, unit, options?}}}`, không có khóa nào khác
  - `@dataclass TagRun(ops: list[GraphOperation], rejected: list[dict], warnings: list[str])` — `rejected[i] = {"item": ..., "reason": "unknown_concept"|"unknown_uid"|"quote_not_found"|"slot_not_in_quote"|"unknown_slot"}`
  - `tag_contract(llm, contract: Contract, catalog: Catalog, *, at: datetime, model: str | None = None) -> TagRun`

Prompt (`TAG_PROMPT`, tiếng Việt): đọc các đơn vị trong `units`; với mỗi khái niệm trong `concepts` mà một đơn vị **nói tới**, trả `{"items": [{"concept", "uid", "quote", "slots": {name: raw}}]}`; `quote` chép nguyên văn; slot số chép nguyên cụm chứa số trong câu; slot `bool`/`enum` trả giá trị; không đánh giá đúng sai; không có thì trả `items: []`. Payload: `{"units": batch.payload_units(), "context", "references", "concepts": catalog_payload(...)}`.

Kiểm item theo spec §6.1. `uid` sai nhưng `quote` khớp đơn vị khác **của lô** → sửa `uid` (như `facts._checked`). Item hợp lệ → `machine_op(contract_id, "ASSERT", concept_id, content, "llm", "auto_accepted", source_uid=uid, quote=(quote,), at=at)` rồi `dataclasses.replace(..., model=model, prompt_version=TAG_PROMPT_VERSION)`; slot số không chuẩn hóa được → cùng op nhưng `status="pending"`, `status_reasons=("slot_unparsable:<name>",)`. Op trùng mã bị bỏ qua. Không ghi vào `contract.oplog` (người gọi ghi).

- [ ] **Step 1: Viết test** với `FakeLLM` trả JSON cố định theo lô (dựng `Contract` nhỏ 2 đơn vị như `tests/test_contracts_facts.py`):
  - item đúng → 1 op, `content["slots"]["annual_leave"] == {"value": 8, "unit": "day"}`, `quote == ("được nghỉ phép 08 ngày/năm",)`;
  - concept lạ / uid lạ không có quote khớp / quote bịa / slot "10 ngày" không nằm trong quote → `rejected` đúng `reason`, không op;
  - slot "tám ngày" (không số) → op `pending`;
  - LLM ném `ContractAIError` cả hai lần ở lô 2 → `warnings` có 1 dòng, op của lô 1 vẫn có;
  - payload gửi đi không chứa chuỗi "min_", "anchors", "rules", và không chứa tên "Nguyễn Văn An" có trong văn bản đơn vị (che PII);
  - chạy hai lần cùng đầu vào → cùng danh sách `op_id`.
- [ ] **Step 2:** chạy → FAIL. **Step 3:** cài. **Step 4:** → PASS.
- [ ] **Step 5: Commit** `feat(team-4.2): LLM concept tagger over contract batches with quote and slot checks`

### Task 9: Đồ thị hợp đồng — `Party`, `ConceptInstance`

**Files:**
- Modify: `src/rag/contracts/graph/schema.json`, `src/rag/contracts/graph/build.py`
- Test: `tests/test_contracts_graph_build.py`

**Interfaces:**
- Consumes: nội dung `ASSERT` (Global Constraints).
- Produces: schema `version "2"`, nút `Party`, `ConceptInstance`; cạnh `HAS_PARTY (Contract→Party)`, `ABOUT (ConceptInstance→Unit)`, `HOLDER (ConceptInstance→Party)`. Mã nút: `<cid>:party:<role>`, `<cid>:ci:<op_id>`.
- Produces (trong `rag.bridge.facts_map`): `party_ops(facts: dict, contract_id: str, *, at: datetime) -> list[GraphOperation]` — từ `facts["parties"]`: vai trò chứa "sử dụng lao động" / "công ty" / "người sử dụng" → `NSDLD`, chứa "người lao động" → `NLD`, khác bỏ qua; mỗi vai trò tối đa một op `origin="rule"`, `status="auto_accepted"`, `content={"kind":"party","role","label": "Người lao động"|"Người sử dụng lao động"}`.

`build_graph`: với mỗi `ASSERT` hiệu lực `kind=party` → nút `Party`; `kind=concept` → nút `ConceptInstance {concept_id, slots_<name>: value, slots_<name>_unit, quote (mask_text), op_id, found_by}`, cạnh `ABOUT` tới `nid[source_uid]` nếu có, cạnh `HOLDER` tới Party của `holder` (tra danh mục qua `load_catalog()`; không có Party đó thì bỏ cạnh). `concept_absent` không tạo nút.

- [ ] **Step 1: Viết test** dựng oplog có 1 op party NLD + 1 op concept `leave.annual` (`source_uid` là uid thật của trang mẫu) → có các nút và 3 loại cạnh, `validate(build) == []`; op concept `rejected` → không có nút; quote chứa tên người trong `mask_text` → thuộc tính đã che (problems không có "còn PII"); dựng hai lần → cùng `build_id`.
- [ ] **Step 2:** chạy → FAIL. **Step 3:** cài. **Step 4:** chạy `tests/test_contracts_graph_build.py tests/test_contracts_graph_service.py` → PASS.
- [ ] **Step 5: Commit** `feat(team-4.2): contract graph carries parties and concept instances from assertions`

### Task 10: Recheck và căn cứ luật

**Files:**
- Create: `src/rag/bridge/recheck.py`, `src/rag/bridge/basis.py`
- Test: `tests/test_bridge_recheck.py`, `tests/test_bridge_basis.py`

**Interfaces:**
- Consumes: `RuleResult`, `FactSet`, `catalog_payload` (lấy phần của một khái niệm), tagger's item checks (tách hàm kiểm item thành `check_item(contract, batch_uids, item, catalog) -> tuple[dict | None, str | None]` trong `tagger.py` và dùng lại).
- Produces:
  - `RECHECK_PROMPT_VERSION = "concept-recheck-1"`
  - `needs_recheck(results: list[RuleResult], factset: FactSet) -> list[str]` — concept_id có finding `missing_content` hoặc `hidden_right`, không thuộc `present` và không thuộc `absent_checked`
  - `recheck(llm, contract: Contract, catalog: Catalog, concept_ids: list[str], *, at: datetime, k: int = 5, model: str | None = None) -> list[GraphOperation]` — mỗi khái niệm: dựng `BM25Index(tokenizer=syllable_tokenize)` trên các đơn vị (`Chunk(chunk_id=uid, doc_id=contract_id, source="contract", page_start=None, page_end=None, section=label, text=text)`), truy vấn `label + " " + " ".join(phrasing)`, lấy `k` đơn vị; một lời gọi `ask_json`; tìm thấy → op `kind=concept`, `found_by="recheck"`; không → op `kind=concept_absent` với `searched_uids`
  - `class LawBasis(Protocol): def concept_basis(self, concept_id: str, day: date) -> dict`
  - `AnchorLawBasis(catalog: Catalog, graph: LegalGraph | None)` — trả `{"concept_id", "day", "anchors": [{"pid", "role", "provision": text_at(...) | None}], "problems": [...]}`; `graph is None` hoặc `GraphNotPublished` / lỗi kết nối → `provision=None`, `problems=["basis_unavailable"]`

- [ ] **Step 1: Viết test** recheck với `FakeLLM`: khái niệm tìm thấy → op `concept` `found_by=recheck`; không thấy → op `concept_absent`, `searched_uids` dài ≤ 5 và chứa uid có từ khóa; `needs_recheck` bỏ qua khái niệm đã `present`. Basis: graph giả trả `text_at` → có `provision`; graph ném `GraphNotPublished` → `problems == ["basis_unavailable"]`, không raise.
- [ ] **Step 2:** chạy → FAIL. **Step 3:** cài. **Step 4:** → PASS.
- [ ] **Step 5: Commit** `feat(team-4.2): recheck silent concepts before reporting; anchor-based law basis`

### Task 11: Điều phối, báo cáo, lệnh chạy

**Files:**
- Create: `src/rag/bridge/check.py`, `scripts/check_contract_concepts.py`
- Test: `tests/test_bridge_check.py`

**Interfaces:**
- Consumes: mọi thứ ở trên; `extract_facts` (`rag.contracts.facts`).
- Produces:
  - `@dataclass CheckReport(contract_id: str, day: date, catalog_version: str, results: list[RuleResult], basis: dict[str, dict], tag_rejected: list[dict], warnings: list[str], stats: dict)`
  - `check_contract(llm, contract: Contract, *, catalog: Catalog | None = None, basis: LawBasis | None = None, at: datetime, model: str | None = None) -> CheckReport` — trình tự: `extract_facts` nếu `contract.facts` rỗng → `party_ops` + `tag_contract` (thêm op vào `contract.oplog`) → `build_factset` → `evaluate` → `needs_recheck` → `recheck` → thêm op → `build_factset` + `evaluate` lại cho các khái niệm đó → `basis.concept_basis` cho mọi khái niệm có finding khác `ok` → `CheckReport`. `day` = `contract.sign_date` hoặc `catalog.law_values_valid_from` (kèm cảnh báo "không có ngày ký"). `stats`: số lời gọi LLM, số lô, số op mỗi loại, thời gian.
  - `report_json(r: CheckReport) -> dict`, `report_markdown(r: CheckReport, catalog: Catalog) -> str` — Markdown nhóm theo finding theo thứ tự `violation, missing_content, hidden_right, conflict, possible_right, needs_facts`; mỗi dòng: label khái niệm, trích dẫn hợp đồng (uid + quote), giá trị luật, nhãn neo; `ok` chỉ đếm.
  - Script: `uv run python scripts/check_contract_concepts.py <file> <out_dir>` — tạo hợp đồng qua `ui/contracts_api.create(data, name, persist=False)` (cách dựng giống `scripts/trace_contract_pipeline.py`), LLM `server.get_pipeline()[0].llm`, `AnchorLawBasis` với `LegalGraph` nếu `LEGAL_GRAPH=1`; ghi `report.json`, `report.md`, `oplog.json` vào `out_dir`.

- [ ] **Step 1: Viết test** `check_contract` trên `Contract` nhỏ với `FakeLLM` theo kịch bản (facts → tag → recheck): kết quả có `leave.annual` violation khi slot 8 day + `work_condition` thiếu → `needs_facts`; `content.raise_policy` im lặng, recheck không thấy → `missing_content` và oplog có `concept_absent`; mọi payload LLM ghi lại không chứa chuỗi `"pregnant"` hay giá trị dữ kiện `user`; `report_markdown` có tiêu đề nhóm "Vi phạm" và trích dẫn. Basis `None` → dùng `AnchorLawBasis(catalog, None)`.
- [ ] **Step 2:** chạy → FAIL. **Step 3:** cài. **Step 4:** chạy toàn bộ `uv run pytest tests -q -k "bridge or contracts"` → PASS.
- [ ] **Step 5: Commit** `feat(team-4.2): concept-based contract check with markdown/json report and CLI script`

### Task 12: Gán nhãn hợp đồng demo và chạy thật

**Files:**
- Create: `tests/fixtures/bridge/demo_gold.yaml`, `scripts/score_concept_check.py`, `docs/superpowers/notes/2026-11-14-concept-check-first-run.md`

**Interfaces:**
- `demo_gold.yaml`: `{concept_id: [{uid_label: "Điều 3", value: [8, day] | true | null}]}` cho mọi khái niệm có mặt trong `data/team-4.2/contracts_demo/hdld_tvpl_2025_filled.txt`, gán tay; khái niệm không có mặt không ghi.
- `scripts/score_concept_check.py <out_dir>/oplog.json <gold>` in: precision / recall gán khái niệm (theo cặp concept, nhãn đơn vị), độ đúng slot, số `hidden_right`/`missing_content` mà gold có khái niệm đó (báo nhầm), số lời gọi, thời gian.

- [ ] **Step 1:** đọc hợp đồng demo, viết `demo_gold.yaml`.
- [ ] **Step 2:** `uv run python scripts/check_contract_concepts.py ../../data/team-4.2/contracts_demo/hdld_tvpl_2025_filled.pdf <scratch>/run1` → có `report.md`.
- [ ] **Step 3:** `uv run python scripts/score_concept_check.py <scratch>/run1/oplog.json tests/fixtures/bridge/demo_gold.yaml` → in số đo.
- [ ] **Step 4:** ghi note: model, số đo, 5 lỗi đáng chú ý nhất kèm ví dụ, đề xuất sửa `describe`/`phrasing`. Không đặt ngưỡng.
- [ ] **Step 5: Commit** `docs(team-4.2): first concept-check run on demo labor contract`
