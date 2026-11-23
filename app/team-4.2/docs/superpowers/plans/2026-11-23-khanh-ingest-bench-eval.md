# Phần của Khánh (K1–K3): báo cáo nạp luật · harness eval theo gói · benchmark engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Làm K1, K2, K3 trong `docs/phan_cong_w04/khanh.md` (K4 router chat KHÔNG nằm trong kế hoạch này): báo cáo kho luật
`legal_ingest.md`, harness eval chạy gold của mọi hồ sơ mẫu trên 3 engine, benchmark 6 kịch bản × 2 trục cho `reference` và `network`.

**Architecture:** Mọi mã mới của eval/bench nằm trong `src/rag/rules/bench/` (thư mục Khánh được sửa) và hai script mỏng
trong `scripts/`. Engine chỉ được gọi qua `rag.rules.evaluator` (`evaluator_for`, `Session.results/update/fork`), `next_questions`,
`explain`, và `rag.bridge.engine.evaluate` cho engine cũ. Gói tổng hợp của benchmark được GHI ra YAML rồi nạp bằng
`rag.rules.loader.load_packs(..., root=<thư mục tạm>)`, không dựng `Rule` bằng tay. Báo cáo K1 đọc kho luật có phiên bản
qua `SnapshotManager(...).store()`.

**Tech Stack:** Python 3 (`.venv`), pytest, PyYAML, `tracemalloc`, matplotlib (thêm làm phụ thuộc tùy chọn nhóm `bench`).

**Spec:** `docs/phan_cong_w04/khanh.md` (§1 K1–K3, §3 Không được làm, §4 Nghiệm thu) + `docs/superpowers/specs/2026-11-22-rete-rule-engine-design.md`
§7 Interface, §9 Benchmark, §10 Kiểm thử. Cách gọi engine: `app/team-4.2/docs/superpowers/notes/w04-rule-engine/engine_interface.md` (gốc repo).

## Global Constraints

- Đường dẫn `src/ tests/ scripts/ docs/` tính từ `app/team-4.2/`; `reports/ data/` tính từ gốc repo.
- Không sửa `src/rag/rules/**` ngoài `src/rag/rules/bench/`, không sửa `src/rag/bridge/engine.py`, không sửa pack YAML, không sửa fixture/gold.
- Không thêm regex hay heuristic đoán chữ (memory `prefer-generalizable-over-regex`); loại hợp đồng lấy từ fixture hoặc `classify_contract`.
- Benchmark: trung vị + p95, ≥20 lần lặp, bỏ lần khởi động; bộ nhớ đỉnh bằng `tracemalloc`; số node tính lại lấy từ `session.stats` (chỉ network).
- Mỗi lần chạy kiểm `reference` và `network` ra kết quả bằng nhau: so `json.dumps(dataclasses.asdict(x), default=str, sort_keys=True)`
  của `results()` và của `Diff`; lệch → in seed + dữ kiện, script thoát mã ≠ 0. Không có cờ bỏ qua.
- Bảng kết quả luôn đủ 6 kịch bản × 2 trục; không chỉnh tham số cho mạng "đẹp hơn".
- `summary.md` của benchmark ghi cấu hình máy (CPU, số lõi, RAM, phiên bản Python, hệ điều hành).
- Eval: miền chưa có gold phải có dòng trong `summary.md`; mỗi ca sai dẫn tới thư mục hồ sơ + rule.
- Nhận diện loại hợp đồng dùng LLM thật (`classify_contract`; Tùng đồng ý 23/11 vì rẻ: chỉ gửi ≤8 đơn vị đầu × ≤800 ký tự, ~40 hợp đồng chính).
  Kết quả lưu đệm theo sha256(văn bản) + model ở `evals/team-4.2/results/w04-rule-engine/eval/classify_cache.json`: chạy lại không gọi LLM. `--no-classify` để bỏ.
- Mỗi task cập nhật `app/team-4.2/docs/superpowers/notes/w04-rule-engine/han_che_va_loi_ton_dong.md` (mục mới "Q. Đo và eval (phần Khánh)") với hạn chế phát hiện được.
- Commit kết thúc bằng `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; không push, không merge.

## Review Focus

1. Hồ sơ nhiều văn bản có gold theo nhiều kỳ: eval phải soát ở mọi `from` VÀ ngày trước `from` kế tiếp (như `_gold_days` của `tests/test_rete_dossiers.py`), không chỉ kỳ đầu.
2. Gold của bộ hợp đồng đơn lẻ ghi `object: <doc_id>` trong khi `RuleResult.object` là `None`: khớp theo hợp đồng, không theo trường object.
3. Engine cũ không nhận đối tượng: rule xuyên đối tượng thiếu kết quả phải đếm là "MISSING", không làm script hỏng.
4. Gói tổng hợp mà mọi rule ra UNKNOWN thì benchmark vô nghĩa: test bộ sinh đòi có cả PASS và FAIL khi đủ dữ kiện.
5. `--seed 0` chạy hai lần phải ra cùng bảng (trừ cột thời gian/bộ nhớ): bộ sinh không được dùng `random` toàn cục hay thứ tự `set`.

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `src/rag/legal/ingest_report.py` | K1: đọc kho luật, đối chiếu danh sách văn bản mục tiêu, dựng bảng + markdown |
| `scripts/legal_ingest_report.py` | K1: chạy trên snapshot hiện tại, ghi `evals/team-4.2/results/w04-rule-engine/legal_ingest.md` |
| `src/rag/rules/bench/__init__.py` | gói rỗng |
| `src/rag/rules/bench/cases.py` | K3: đọc `tests/fixtures/rete/*` (hai dạng) thành `Case` |
| `src/rag/rules/bench/evalrun.py` | K3: chạy 3 engine, chấm theo gold, bảng chọn gói, markdown |
| `scripts/eval_rule_engine.py` | K3: CLI, ghi `evals/team-4.2/results/w04-rule-engine/eval/summary.md` |
| `src/rag/rules/bench/synth.py` | K2: sinh gói YAML tổng hợp (trục 1, trục 2), dữ kiện, đối tượng, chuỗi cập nhật |
| `src/rag/rules/bench/runner.py` | K2: đo thời gian/bộ nhớ, 6 kịch bản, so hai evaluator |
| `scripts/bench_rule_engine.py` | K2: CLI, ghi `<timestamp>.json`, `summary.md`, `axis1.png`, `axis2.png` |
| `tests/test_legal_ingest_report.py`, `tests/test_bench_cases.py`, `tests/test_bench_evalrun.py`, `tests/test_bench_synth.py`, `tests/test_bench_runner.py` | test |

---

### Task 1: K1 — báo cáo kho luật `legal_ingest.md`

**Files:**
- Create: `src/rag/legal/ingest_report.py`, `scripts/legal_ingest_report.py`, `tests/test_legal_ingest_report.py`
- Output: `evals/team-4.2/results/w04-rule-engine/legal_ingest.md`

**Interfaces:**
- Consumes: `rag.legal.store.LegalStore` (`document(key)`, `relations(key)`, `operations(target_key=...)`, `latest_build(key)`, `provisions_as_of(key, day)`), `rag.legal.snapshots.SnapshotManager(path).current()/.store()`.
- Produces: `TARGETS: tuple[Target, ...]`; `Target(key: str, name: str, expected_from: date | None)`;
  `IngestRow(key, name, present: bool, title, effective_from, expected_from, date_ok: bool | None, articles: int, amended_by: list[str], built: bool)`;
  `ingest_rows(store, targets, *, day: date) -> list[IngestRow]`; `render_markdown(rows, *, snapshot_id: str, day: date) -> str`.

`TARGETS` (khóa theo dạng `document_key` của kho, vd. `bo-luat:91/2015/QH13`; ngày hiệu lực kỳ vọng ghi tay từ văn bản):
BLDS 91/2015/QH13 (2017-01-01), LTM 36/2005/QH11 (2006-01-01), BVQLNTD 19/2023/QH15 (2024-07-01), Nhà ở 27/2023/QH15 (2024-08-01,
theo Luật 43/2024/QH15), và các văn bản hướng dẫn đã nạp ở snapshot `s20261123071410-54f166`: NĐ 55/2024, QĐ 07/2024, Luật 54/2010,
NQ 01/2014, Luật 05/2017, NĐ 95/2024, NĐ 96/2024 (`expected_from=None` nếu chưa tra văn bản; bảng ghi "chưa đối chiếu").
Khóa nào không chắc thì mở `store.documents()` để lấy đúng khóa, không đoán.

- [ ] **Step 1: Viết test hỏng** — dựng `LegalStore(tmp_path / "x.sqlite")`, `upsert_document` một `LegalDocument` khóa `luat:19/2023/QH15`, `vbpl_effective_from=date(2024,7,1)`.

```python
def test_present_document_with_matching_date():
    rows = ingest_rows(store, [Target("luat:19/2023/QH15", "BVQLNTD", date(2024, 7, 1))], day=date(2026, 11, 23))
    assert rows[0].present and rows[0].date_ok is True

def test_missing_target_is_reported_not_dropped():
    rows = ingest_rows(store, [Target("luat:99/2099/QH99", "X", None)], day=date(2026, 11, 23))
    assert rows[0].present is False and rows[0].date_ok is None

def test_wrong_date_flagged():
    rows = ingest_rows(store, [Target("luat:19/2023/QH15", "BVQLNTD", date(2025, 1, 1))], day=date(2026, 11, 23))
    assert rows[0].date_ok is False

def test_markdown_names_snapshot_and_every_row():
    md = render_markdown(rows, snapshot_id="s1", day=date(2026, 11, 23))
    assert "s1" in md and "BVQLNTD" in md and "X" in md and "THIẾU" in md
```

- [ ] **Step 2:** `.venv/Scripts/python.exe -m pytest -q tests/test_legal_ingest_report.py` → FAIL (`ModuleNotFoundError: rag.legal.ingest_report`).
- [ ] **Step 3: Cài đặt** `ingest_rows`, `render_markdown`. `effective_from` = `store.first_valid_from(key)` nếu có bản dựng, không thì `doc.vbpl_effective_from`;
  `articles` = số `Điều` trong `provisions_as_of(key, day)` (đếm theo trường cấp Điều của `ProvisionVersion`, không đếm theo chữ);
  `amended_by` = khóa nguồn của `operations(target_key=key)` (duy nhất, sắp xếp). Markdown: bảng một dòng mỗi văn bản + mục "Ghi chú" cho dòng thiếu/lệch ngày.
- [ ] **Step 4:** chạy lại test → PASS.
- [ ] **Step 5: Script** `scripts/legal_ingest_report.py [--out PATH] [--day YYYY-MM-DD]`: lấy kho như `rag.legal.__main__._snapshots()`, in `snapshot_id`, ghi markdown.
  Chạy: `.venv/Scripts/python.exe scripts/legal_ingest_report.py` → có file `evals/team-4.2/results/w04-rule-engine/legal_ingest.md`. Đọc bảng; dòng nào thiếu/lệch ngày → ghi vào mục Q của file hạn chế (không tự tải thêm luật).
  Nếu `CURRENT` của kho không phải snapshot 23/11 → báo trong mục Q và trong câu trả lời, không đổi `CURRENT`.
- [ ] **Step 6: Commit** `feat(team-4.2): báo cáo kho luật cho các luật hợp đồng mới (K1)`.

---

### Task 2: K3 — đọc hồ sơ mẫu thành `Case`

**Files:**
- Create: `src/rag/rules/bench/__init__.py`, `src/rag/rules/bench/cases.py`, `tests/test_bench_cases.py`

**Interfaces:**
- Consumes: định dạng `tests/fixtures/rete/README.md`; bộ đọc của luồng thật `rag.bridge.facts_map.contract_facts`, `normalize_slot`, `rag.bridge.check.user_fact_set`; `rag.rules.loader.load_packs`, `packs_for_kind`; `rag.rules.objects.WorkingObject`; `rag.rules.semantics.Fact`.
- Produces:
  - `Expect(rule: str, object: str | None, status: str)` — `rule` dạng `concept/rule`.
  - `Case(suite: str, case_id: str, path: Path, packs: tuple[str, ...], document_kind: str, day: date, facts: dict, present: frozenset[str], objects: tuple[WorkingObject, ...], expected: tuple[Expect, ...])`.
  - `load_cases(root: Path = FIXTURES) -> tuple[list[Case], list[str]]` — danh sách ca + danh sách thư mục không có `gold.yaml`.
  - `FLAT_SUITES: dict[str, tuple[str, str]]` = `{"loan": ("civil_loan", "loan_contract"), "lease": ("civil_lease", "lease_contract"), "consumer": ("consumer", "consumer_contract"), "commercial": ("commercial", "commercial_sale_contract")}`.
  - `result_key(r: RuleResult) -> str` = `concept/rule` + `@object` nếu có.

Quy tắc dựng (chép đúng logic các test, không sáng tác):
- Hồ sơ (có `dossier.yaml`): mỗi nhãn gold sinh một `Case` cho mỗi ngày của `_gold_days` (mọi `from` + ngày trước `from` kế tiếp); `facts` như `facts_at`, `objects` như `objects_of`, `present=∅` (`tests/test_rete_dossiers.py:62-93`). Gộp các nhãn trùng ngày vào cùng một `Case` (`case_id = f"{did}@{day}"`). `document_kind` = kind của văn bản đầu tiên không phải `amendment`.
- Bộ đơn lẻ: mỗi hợp đồng trong `facts.yaml` một `Case` ở `sign_date`, facts như `_session` của `tests/test_rete_pack_fixtures.py:86-99`; `Expect.object=None` (gold ghi `object: <doc>` để chọn hợp đồng, Review Focus 2).

- [ ] **Step 1: Viết test hỏng**

```python
def test_every_fixture_dir_is_loaded_or_reported():
    cases, no_gold = load_cases()
    seen = {c.suite for c in cases} | set(no_gold)
    assert {"a1", "b1", "b2", "b3", "b4", "b5", "r1", "loan", "lease", "consumer", "commercial"} <= seen

def test_dossier_cases_cover_every_period_boundary():
    a1 = sorted(c.day.isoformat() for c in load_cases()[0] if c.suite == "a1")
    assert {"2024-06-30", "2024-07-01", "2024-08-31", "2024-09-01", "2026-01-01"} <= set(a1)

def test_flat_cases_match_existing_fixture_test_on_network():
    """Bộ đọc dựng đúng đầu vào: network trên Case cho đúng trạng thái gold như tests/test_rete_*_fixtures.py."""
    from rag.rules.evaluator import evaluator_for
    for c in [c for c in load_cases()[0] if c.suite in FLAT_SUITES]:
        got = {result_key(r): r.status for r in evaluator_for(load_packs(list(c.packs)), "network")
               .session(day=c.day, facts=c.facts, present=set(c.present), evidence={}).results()}
        assert all(got[e.rule] == e.status for e in c.expected), c.case_id
```

- [ ] **Step 2:** `pytest -q tests/test_bench_cases.py` → FAIL (module chưa có).
- [ ] **Step 3:** cài đặt `cases.py`. `load_packs` bọc `functools.lru_cache` theo tuple gói.
- [ ] **Step 4:** chạy lại → PASS. Nếu test 3 lệch với gold mà test fixture gốc vẫn xanh → bộ đọc sai, sửa bộ đọc (không sửa gold).
- [ ] **Step 5: Commit** `feat(team-4.2): đọc hồ sơ mẫu rete thành ca eval (K3)`.

---

### Task 3: K3 — chấm 3 engine, bảng chọn gói, `eval/summary.md`

**Files:**
- Create: `src/rag/rules/bench/evalrun.py`, `scripts/eval_rule_engine.py`, `tests/test_bench_evalrun.py`
- Output: `evals/team-4.2/results/w04-rule-engine/eval/summary.md`

**Interfaces:**
- Consumes: Task 2 (`Case`, `Expect`, `load_cases`, `result_key`); `rag.bridge.engine.evaluate(catalog, facts, present, evidence, day)`; `rag.rules.evaluator.evaluator_for`; `rag.rules.explain.explain(catalog, session, concept_id, rule_id, obj)`; `rag.contracts.classify.classify_contract(llm, contract)`.
- Produces:
  - `ENGINES = ("legacy", "reference", "network")`.
  - `run_case(case: Case, engine: str) -> dict[str, RuleResult]` — `legacy` gọi `engine.evaluate` không đối tượng.
  - `Miss(suite, case_id, path, rule, object, want, got, explain_md: str | None)`.
  - `Score(engine, by_pack: dict[str, Counter], by_kind: dict[str, Counter], confusion: dict[tuple[str, str], int], misses: list[Miss])` — nhãn đếm `right/wrong/unknown/missing`; ma trận gold × got trên `PASS FAIL UNKNOWN NOT_APPLICABLE MISSING`; "kind" = `catalog.concepts[cid].kind`.
  - `score(cases: list[Case], engine: str) -> Score`.
  - `PackRow(suite, case_id, fixture_kind, classified_kind: str | None, packs_run: tuple, wrong_domain: bool | None)`; `pack_choice(cases, classify=None) -> list[PackRow]` — `classify(case) -> str` (kind); `wrong_domain = packs_for_kind(classified) != packs_for_kind(fixture_kind)`, `None` khi không phân loại.
  - `render_summary(scores: list[Score], packs: list[PackRow], no_gold: list[str], *, classified: bool) -> str`.

- [ ] **Step 1: Viết test hỏng**

```python
def test_new_engines_match_all_gold():
    cases, _ = load_cases()
    for eng in ("reference", "network"):
        s = score(cases, eng)
        assert s.misses == [], [(m.case_id, m.rule, m.want, m.got) for m in s.misses[:5]]

def test_legacy_counts_cross_object_rules_as_missing_not_crash():
    s = score([c for c in load_cases()[0] if c.suite == "b1"], "legacy")
    assert any(m.got == "MISSING" for m in s.misses)

def test_confusion_totals_equal_number_of_labels():
    cases, _ = load_cases()
    s = score(cases, "reference")
    assert sum(s.confusion.values()) == sum(len(c.expected) for c in cases)

def test_pack_choice_flags_wrong_domain():
    c = next(c for c in load_cases()[0] if c.suite == "lease")
    row = pack_choice([c], classify=lambda _c: "labor_contract")[0]
    assert row.wrong_domain is True and pack_choice([c])[0].wrong_domain is None

def test_summary_lists_missing_gold_and_every_engine():
    md = render_summary([score([], e) for e in ENGINES], [], ["x_dir"], classified=False)
    assert "x_dir" in md and all(e in md for e in ENGINES) and "classify" in md
```

- [ ] **Step 2:** `pytest -q tests/test_bench_evalrun.py` → FAIL.
- [ ] **Step 3:** cài đặt `evalrun.py`. `explain_md` chỉ cho `reference`/`network` (dựng lại phiên của ca), `None` cho `legacy`.
  Markdown có: bảng theo gói × engine, theo kind × engine, 3 ma trận nhầm, bảng chọn gói (cột "classify: chưa chạy" khi `--no-classify`), danh sách ca sai (đường dẫn `tests/fixtures/rete/<suite>` + rule + ngày + `explain`), dòng "chưa có gold" cho mỗi thư mục trong `no_gold`, ghi chú "gold chờ Tùng duyệt" cho suite có `labeled_by` chứa "CHỜ".
- [ ] **Step 4:** chạy lại → PASS.
- [ ] **Step 5: Bộ phân loại có đệm** — `cached_classifier(llm, cache_path: Path, model: str) -> Callable[[Case], str]` trong `evalrun.py`:
  văn bản = hợp đồng chính của ca (không gồm phụ lục), đọc bằng `parse_contract([PageText(1, text)])`; khóa đệm `sha256(text)+":"+model`;
  có khóa thì trả ngay, không thì gọi `classify_contract` rồi ghi file. Mỗi văn bản chỉ phân loại một lần dù nhiều ca (hồ sơ nhiều kỳ).
  Test (LLM giả đếm số lần gọi): hai ca cùng văn bản → 1 lần gọi; chạy lại với cùng file đệm → 0 lần gọi; LLM lỗi → kind `unknown`, `wrong_domain=True`.
- [ ] **Step 6: Script** `scripts/eval_rule_engine.py [--out DIR] [--no-classify]`; LLM tạo như `scripts/bench_contract_agent.py:_nocache_llm`.
  Chạy `.venv/Scripts/python.exe scripts/eval_rule_engine.py` → ghi `evals/team-4.2/results/w04-rule-engine/eval/summary.md` + `classify_cache.json`;
  in số lần gọi LLM. Mong đợi reference/network 0 ca sai, legacy có MISSING ở rule xuyên đối tượng; ca phân loại sai → nêu trong summary và mục Q (không sửa prompt trong kế hoạch này).
- [ ] **Step 7: Commit** `feat(team-4.2): harness eval rule engine theo gói, 3 engine, nhận diện loại bằng LLM có đệm (K3)`.

---

### Task 4: K2 — bộ sinh gói tổng hợp, trục 1 (số rule)

**Files:**
- Create: `src/rag/rules/bench/synth.py`, `tests/test_bench_synth.py`

**Interfaces:**
- Consumes: định dạng `pack.yaml` / `concepts.yaml` (`src/rag/rules/packs/README.md`, ví dụ `civil_loan`); `load_packs(ids, root=)`; `packs/kinds.yaml` (chép vào thư mục tạm vì loader đọc kind chung từ `root`).
- Produces:
  - `RuleSpec(n_rules: int, shared_ratio: float, depth: int, n_facts: int, seed: int)`.
  - `write_rule_pack(spec: RuleSpec, root: Path) -> str` (trả id gói `synth_r{n}_s{shared}_d{depth}`).
  - `load_rule_pack(spec, root) -> Catalog`.
  - `random_facts(catalog, spec, rng: random.Random, *, missing: float) -> dict[str, Fact]`.
  - `update_batches(catalog, spec, rng, size: int, count: int) -> list[dict[str, Fact | None]]` (có cả xóa dữ kiện = `None`).
  - `REAL_AXIS1 = {"labor": ["labor"], "ba_mien": ["labor", "civil_loan", "civil_lease"]}`; `AXIS1_SIZES = (500, 2000, 10000)`.

Hình dạng gói (để benchmark đo đúng thứ spec §9 nói): `n_facts` dữ kiện số `f0..f{n-1}` (khai trong `user_facts`, đơn vị `null`);
mỗi rule một khái niệm `kind: count_limit`, `check: {fact: f_k, op: lte, value: v}`; một tỉ lệ `shared_ratio` rule dùng
`applicability` lấy từ một nhóm nhỏ điều kiện chung (≈ `n_rules*(1-shared_ratio)/10` điều kiện), còn lại điều kiện riêng;
`depth>0`: chuỗi dữ kiện suy ra `d1..d{depth}` qua `derived` (d1 từ `f0`, d{i+1} `when: {fact: d{i}, op: eq, value: true}`), và các rule dùng chung đọc `d{depth}`.
Mọi ngẫu nhiên đi qua `random.Random(seed)` riêng; ghi YAML với thứ tự cố định.

- [ ] **Step 1: Viết test hỏng**

```python
SPEC = RuleSpec(n_rules=50, shared_ratio=0.5, depth=3, n_facts=50, seed=0)

def test_synth_pack_loads_with_real_loader(tmp_path):
    cat = load_rule_pack(SPEC, tmp_path)
    assert sum(len(c.rules) for c in cat.concepts.values()) == 50

def test_same_seed_same_yaml(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write_rule_pack(SPEC, a); write_rule_pack(SPEC, b)
    pid = write_rule_pack(SPEC, a)
    assert (a / pid / "concepts.yaml").read_bytes() == (b / pid / "concepts.yaml").read_bytes()

def test_full_facts_give_both_pass_and_fail(tmp_path):
    cat = load_rule_pack(SPEC, tmp_path)
    facts = random_facts(cat, SPEC, random.Random(0), missing=0.0)
    st = {r.status for r in evaluator_for(cat, "reference").session(day=date(2025, 1, 1), facts=facts, present=set(), evidence={}).results()}
    assert {"PASS", "FAIL"} <= st

def test_missing_facts_give_unknown(tmp_path):
    cat = load_rule_pack(SPEC, tmp_path)
    facts = random_facts(cat, SPEC, random.Random(0), missing=0.5)
    st = [r.status for r in evaluator_for(cat, "reference").session(day=date(2025, 1, 1), facts=facts, present=set(), evidence={}).results()]
    assert "UNKNOWN" in st

def test_depth_zero_has_no_derived(tmp_path):
    pid = write_rule_pack(RuleSpec(20, 0.2, 0, 50, 1), tmp_path)
    assert not yaml.safe_load((tmp_path / pid / "pack.yaml").read_text(encoding="utf-8")).get("derived")
```

- [ ] **Step 2:** `pytest -q tests/test_bench_synth.py` → FAIL.
- [ ] **Step 3:** cài đặt. Nếu loader từ chối dạng nào (vd. bắt buộc `law`, `anchors`, `holder`) → thêm trường tối thiểu loader đòi, ghi lý do bằng một dòng chú thích; không sửa loader.
- [ ] **Step 4:** chạy lại → PASS; thêm `RuleSpec(10000, 0.5, 3, 500, 0)` nạp được trong < 60 s (đo tay một lần, ghi số vào mục Q).
- [ ] **Step 5: Commit** `feat(team-4.2): sinh gói rule tổng hợp nạp bằng loader thật (K2 trục 1)`.

---

### Task 5: K2 — bộ sinh trục 2 (số đối tượng mỗi hồ sơ)

**Files:**
- Modify: `src/rag/rules/bench/synth.py`; Test: `tests/test_bench_synth.py`

**Interfaces:**
- Consumes: Task 4 (`write_rule_pack` dùng lại phần ghi YAML); dạng `object_types` và rule xuyên đối tượng của `packs/labor` (`over`, `group_by` một khóa và hai khóa, `check: {count: ...}` / `{not_exists: ...}`), `WorkingObject`, `ObjectChanges`.
- Produces:
  - `ObjSpec(n_objects: int, n_cross_rules: int, seed: int)`; `AXIS2_SIZES = (1, 5, 20, 100)`; `AXIS2_RULES = (5, 50)`.
  - `write_object_pack(spec, root) -> str`; `load_object_pack(spec, root) -> Catalog`.
  - `random_objects(spec, rng) -> list[WorkingObject]` — kiểu `Contract` (attrs `kind`, `job`, `has_probation`, `amount`; ~20% thuộc tính vắng = chưa biết) và `Amendment` (`refs.contract`), cùng một `employee`, khoảng hiệu lực nối tiếp.
  - `object_changes(objects, rng, kind: Literal["add", "remove", "modify"]) -> ObjectChanges`.

Rule xuyên đối tượng chia đều ba dạng spec §5.6: đếm (`count`, `group_by: {employee}`), ghép cặp (`group_by: {employee, job}`), phủ định (`not_exists` trên `Amendment`).

- [ ] **Step 1: Viết test hỏng**

```python
def test_object_pack_has_three_cross_rule_shapes(tmp_path):
    cat = load_object_pack(ObjSpec(20, 6, 0), tmp_path)
    rules = [r for c in cat.concepts.values() for r in c.rules if r.over is not None]
    assert len(rules) == 6 and any(len(r.group_by) == 2 for r in rules)

def test_objects_evaluate_and_agree(tmp_path):
    spec = ObjSpec(20, 6, 0); cat = load_object_pack(spec, tmp_path)
    objs = random_objects(spec, random.Random(0))
    out = [json.dumps([dataclasses.asdict(r) for r in evaluator_for(cat, k).session(
        day=date(2025, 1, 1), facts={}, present=set(), evidence={}, objects=objs).results()], default=str, sort_keys=True)
        for k in ("reference", "network")]
    assert out[0] == out[1] and '"object": "employee=' in out[0]

def test_object_changes_cover_add_remove_modify():
    objs = random_objects(ObjSpec(5, 5, 0), random.Random(0))
    assert object_changes(objs, random.Random(1), "add").added and object_changes(objs, random.Random(1), "remove").removed
```

(Tên trường `r.group_by`, `ObjectChanges.added/removed` theo model thật; đọc `rag/rules/model.py`, `rag/rules/objects.py` trước khi viết test.)

- [ ] **Step 2:** chạy → FAIL. **Step 3:** cài đặt. **Step 4:** chạy → PASS.
- [ ] **Step 5: Commit** `feat(team-4.2): sinh hồ sơ nhiều đối tượng cho benchmark (K2 trục 2)`.

---

### Task 6: K2 — bộ đo và 6 kịch bản

**Files:**
- Create: `src/rag/rules/bench/runner.py`, `tests/test_bench_runner.py`

**Interfaces:**
- Consumes: Task 4–5; `evaluator_for`; `rag.rules.questions.next_questions(catalog, session)`; `session.stats` (network: `nodes_recomputed`, `rules_recomputed`, `objects_recomputed`).
- Produces:
  - `Timing(median_ms: float, p95_ms: float, runs: int)`; `measure(fn, *, repeats: int = 20, warmup: int = 1) -> Timing`; `peak_kb(fn) -> float` (`tracemalloc`).
  - `Row(scenario: int, axis: int, size: str, evaluator: str, median_ms, p95_ms, peak_kb, recomputed: int | None, digest: str)` — `digest` = sha256 của kết quả đã chuẩn hóa (để so lần chạy và so hai evaluator).
  - `Mismatch(scenario, size, seed, detail: str)`; `class EvaluatorMismatch(Exception)`.
  - `run_axis1(spec: RuleSpec | list[str], *, seed, repeats, root) -> list[Row]` (kịch bản 1, 2, 3 với 1/5/20 dữ kiện, 4 với 100 hồ sơ chung mạng, 5 `next_questions` trên `missing=0.7`).
  - `run_axis2(spec: ObjSpec, *, seed, repeats, root) -> list[Row]` (kịch bản 2 và 6: thêm/xóa/đổi một đối tượng).
  - Mỗi hàm so `reference` với `network` trên cùng đầu vào (results và Diff); lệch → raise `EvaluatorMismatch` kèm seed + dữ kiện.

Kịch bản 1 đo `evaluator_for(cat, kind)`; nếu network dựng mạng lười ở `session()` thì ghi điều đó trong chú thích hàm và cột ghi chú của summary (không dời phép đo cho đẹp).

- [ ] **Step 1: Viết test hỏng**

```python
def test_measure_drops_warmup_and_reports_p95():
    calls = []
    t = measure(lambda: calls.append(1), repeats=20, warmup=1)
    assert len(calls) == 21 and t.runs == 20 and t.p95_ms >= t.median_ms

def test_axis1_small_has_all_scenarios_both_evaluators(tmp_path):
    rows = run_axis1(RuleSpec(30, 0.5, 3, 50, 0), seed=0, repeats=3, root=tmp_path)
    assert {(r.scenario, r.evaluator) for r in rows} >= {(s, e) for s in (1, 2, 3, 4, 5) for e in ("reference", "network")}
    assert any(r.recomputed is not None for r in rows if r.evaluator == "network")

def test_axis2_has_scenario_6(tmp_path):
    rows = run_axis2(ObjSpec(5, 5, 0), seed=0, repeats=3, root=tmp_path)
    assert {r.scenario for r in rows} == {2, 6}

def test_digest_same_for_both_evaluators(tmp_path):
    rows = run_axis1(RuleSpec(30, 0.5, 0, 50, 0), seed=0, repeats=3, root=tmp_path)
    by = {}
    for r in rows: by.setdefault((r.scenario, r.size), set()).add(r.digest)
    assert all(len(v) == 1 for k, v in by.items() if k[0] != 1)

def test_mismatch_raises(monkeypatch, tmp_path):
    import rag.rules.bench.runner as R
    monkeypatch.setattr(R, "_canon", lambda results, kind="x": kind)   # ép hai bên khác nhau
    with pytest.raises(R.EvaluatorMismatch):
        run_axis1(RuleSpec(10, 0.5, 0, 50, 0), seed=0, repeats=1, root=tmp_path)
```

(`_canon(results, kind)` là hàm chuẩn hóa nội bộ duy nhất mà mọi phép so đi qua; test cuối thay nó để kiểm đường báo lỗi.)

- [ ] **Step 2:** chạy → FAIL. **Step 3:** cài đặt. **Step 4:** chạy → PASS.
- [ ] **Step 5: Commit** `feat(team-4.2): đo 6 kịch bản benchmark, so hai evaluator mỗi lần chạy (K2)`.

---

### Task 7: K2 — script, báo cáo, biểu đồ, lần chạy thật

**Files:**
- Create: `scripts/bench_rule_engine.py`; Modify: `pyproject.toml` (nhóm tùy chọn `bench = ["matplotlib"]`), `tests/test_bench_runner.py`
- Output: `evals/team-4.2/results/w04-rule-engine/bench/<YYYYmmdd-HHMMSS>.json`, `summary.md`, `axis1.png`, `axis2.png`

**Interfaces:**
- Consumes: Task 6 (`run_axis1`, `run_axis2`, `Row`, `EvaluatorMismatch`), Task 4–5 (`REAL_AXIS1`, `AXIS1_SIZES`, `AXIS2_SIZES`, `AXIS2_RULES`).
- Produces: `main(argv) -> int`; `render_summary(rows, machine: dict, params: dict) -> str`; `plot(rows, out_dir) -> list[Path]` (bỏ qua và in cảnh báo nếu không có matplotlib — summary vẫn ghi).
  Cờ: `--seed 0`, `--repeats 20`, `--quick` (trục 1: 44-rule thật + 500; trục 2: 1 và 5 đối tượng; repeats 3 — cho test), `--out`.
  Trục 1 đủ: `labor`, `ba_mien` + 500/2.000/10.000 × shared {0.2, 0.5} × depth {0, 3}, `n_facts` 50 (500 cho 10.000). Trục 2: 1/5/20/100 × {5, 50} rule.

- [ ] **Step 1: Viết test hỏng**

```python
def test_quick_run_twice_same_table_except_timing(tmp_path):
    spec = importlib.util.spec_from_file_location("bench_rule_engine", ROOT / "scripts" / "bench_rule_engine.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); main = mod.main
    assert main(["--quick", "--seed", "0", "--out", str(tmp_path / "a")]) == 0
    assert main(["--quick", "--seed", "0", "--out", str(tmp_path / "b")]) == 0
    strip = lambda p: [{k: v for k, v in r.items() if k not in ("median_ms", "p95_ms", "peak_kb")}
                       for r in json.loads(next(p.glob("*.json")).read_text())["rows"]]
    assert strip(tmp_path / "a") == strip(tmp_path / "b")

def test_summary_has_machine_and_six_scenarios_two_axes(tmp_path):
    main(["--quick", "--seed", "0", "--out", str(tmp_path)])
    md = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "Python" in md and "CPU" in md and all(f"Kịch bản {i}" in md for i in range(1, 7)) and "Trục 2" in md
```

- [ ] **Step 2:** chạy → FAIL. **Step 3:** cài đặt; `uv add --optional bench matplotlib` (hoặc sửa tay `pyproject.toml` nếu uv không dùng được; ghi vào ledger). **Step 4:** chạy → PASS.
- [ ] **Step 5: Chạy thật** (đóng các việc nặng khác): `.venv/Scripts/python.exe scripts/bench_rule_engine.py --seed 0` (chạy nền, có thể lâu với 10.000 rule).
  Mong đợi: thoát 0, có JSON + `summary.md` + 2 PNG. Có `EvaluatorMismatch` → dừng, ghi ca vào mục Q, báo Tùng; không sửa engine.
  Đọc bảng: ghi vào `summary.md` (đoạn "Nhận xét") đúng như số — kịch bản 2 mạng có thể chậm hơn reference.
- [ ] **Step 6: Commit** `feat(team-4.2): script benchmark rule engine, báo cáo và biểu đồ hai trục (K2)` (kèm file báo cáo của lần chạy thật).

---

### Sau cùng

- Thêm 5 file test mới vào lệnh gate (ghi trong mục Q). Chạy gate:
  `.venv/Scripts/python.exe -m pytest -q tests/test_rules_*.py tests/test_bridge_*.py tests/test_contract_graph_tools.py tests/test_ask_contract_graph.py tests/test_contract_graph_agent.py tests/test_contracts_api.py tests/test_three_domains.py tests/test_kinds.py tests/test_prompts_cover_packs.py tests/test_rete_pack_fixtures.py tests/test_rule_inventory_examples.py tests/test_rule_inventory.py tests/test_legal_ingest_report.py tests/test_bench_*.py`
  Mong đợi: 1313 passed cũ + test mới, không fail mới.
- Cập nhật `docs/phan_cong_w04/khanh.md` §6: ghi K1–K3 do Claude làm theo yêu cầu Tùng, K4 chưa làm.
