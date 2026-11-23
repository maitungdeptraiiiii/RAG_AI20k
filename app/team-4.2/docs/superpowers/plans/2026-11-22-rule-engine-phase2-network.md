# Rule engine v2 — Giai đoạn 2 (mạng điều kiện tăng dần) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm `NetworkEvaluator`: mạng điều kiện mệnh đề ba trị, chia sẻ node, cập nhật tăng dần, cho kết quả **giống hệt** `ReferenceEvaluator`; nối vào `check_contract` và `tools.check_concept`.

**Architecture:** `semantics.py` tách `evaluate_rule` thành "tính các đầu vào của rule" + `decide_rule` (bảng trạng thái), để mạng và Reference dùng chung một bảng quyết định (giống hệt theo cấu trúc). Mạng gồm node điều kiện dùng chung theo khóa cấu trúc (lá + `all` / `any` / `not` có bộ đếm T/F/U) cho `applicability` và `cases[*].when`; phần còn lại của rule (giá trị luật, `check`, kết quả) tính lại theo từng rule khi dữ kiện nó tham chiếu đổi.

**Tech Stack:** Python ≥ 3.12, pytest. Chạy từ `app/team-4.2/` bằng `.venv/Scripts/python.exe -m pytest`.

**Spec:** `app/team-4.2/docs/superpowers/specs/2026-11-22-rete-rule-engine-design.md` — giai đoạn 2 = §6.1 phần 1, §6.2 (không gồm node đối tượng), §6.3 (không gồm `objects`), §11 mục 2. Checklist: `docs/phan_cong_w04/tung_viec_can_lam.md` D8–D12, E1, E2. Kế hoạch giai đoạn 1 (đã xong): `2026-11-22-rule-engine-phase1.md`.

## Global Constraints

- Mọi kết quả của `NetworkEvaluator` bằng `ReferenceEvaluator` trên mọi đầu vào, kể cả sau chuỗi `update` (spec §2 phản mục tiêu).
- Thiếu dữ kiện không bao giờ thành vi phạm (spec §2).
- `Evaluator` / `Session` / `Diff` / `RuleChange` giữ nguyên chữ ký đã công bố; `objects` khác rỗng vẫn `NotImplementedError("objects: giai đoạn 7")` (spec §7).
- Mạng bất biến, dùng chung cho mọi phiên; ngày soát là đầu vào của phiên, không nằm trong mạng (spec §6.2).
- Mỗi node tính lại tối đa một lần trong một lần `update`; kết quả không phụ thuộc thứ tự `changes` (spec §6.3).
- Không thêm dependency. Chú thích tiếng Việt, định danh tiếng Anh. Commit `feat(team-4.2): ...` kèm dòng attribution của phiên.
- **Gate**: `.venv/Scripts/python.exe -m pytest tests/test_rules_*.py tests/test_bridge_*.py tests/test_contract_graph_tools.py tests/test_ask_contract_graph.py tests/test_contract_graph_agent.py tests/test_contracts_api.py -q` — baseline sau giai đoạn 1: toàn bộ passed (ghi số ở Task 1), 1 skipped, 1 xfailed.

## Review Focus

1. Dữ kiện `CONFLICT` / `UNKNOWN` / bị xóa (`None`) đổi qua lại trong cùng một lần `update`: mạng và Reference vẫn bằng nhau (Task 3).
2. Hai rule dùng chung một điều kiện con (node chia sẻ): đổi dữ kiện của điều kiện đó cập nhật **cả hai** rule, không chỉ rule đầu tiên (Task 2, 3).
3. `update` chỉ đổi `present` hoặc `evidence` của một khái niệm: chỉ rule của khái niệm đó tính lại, kết quả vẫn đúng (Task 3).
4. `fork()` rồi `update` trên bản sao: bản gốc không đổi, kể cả bộ đếm trong node (Task 3).
5. Bỏ một dữ kiện khiến một rule chuyển thành `violation` (bất biến "thiếu dữ kiện không thành vi phạm") (Task 3).

## File Structure

| File | Trách nhiệm |
|---|---|
| `src/rag/rules/semantics.py` | Thêm `RuleInputs`, `rule_inputs`, `decide_rule`, `resolve_law_with`; `evaluate_rule` = `decide_rule(rule_inputs(...))` |
| `src/rag/rules/network/__init__.py` | Docstring |
| `src/rag/rules/network/nodes.py` | Node điều kiện: lá, `all`, `any`, `not`, bộ đếm, khóa chia sẻ |
| `src/rag/rules/network/network.py` | `Network.compile(catalog)`: node dùng chung, chỉ mục dữ kiện → node / rule, rank |
| `src/rag/rules/network/session.py` | `NetworkSession`: `results`, `update`, `fork`, thống kê |
| `src/rag/rules/evaluator.py` | `evaluator_for(..., "network")`, `default_kind()` đọc `RAG_RULE_EVALUATOR` |
| `src/rag/bridge/check.py`, `src/rag/contracts/graph/tools.py` | Dùng phiên của evaluator |
| `tests/test_rules_network_*.py` | Test mới |

**Đơn giản hóa so với spec §6.2 (người viết kế hoạch quyết, Tùng xem lại):** `LawNode`, `LawLeafNode`, `PresenceNode` và phần `check` không thành node riêng; chúng nằm trong tính toán của `RuleNode`, vì giá trị luật và lá `law:` phụ thuộc từng rule nên không chia sẻ được. Chia sẻ node chỉ áp cho điều kiện trên dữ kiện (`applicability`, `cases[*].when`).

---

### Task 1: Tách `evaluate_rule` thành đầu vào + bảng quyết định

**Files:**
- Modify: `src/rag/rules/semantics.py`
- Test: `tests/test_rules_semantics.py` (thêm), `tests/test_rules_golden.py` (giữ nguyên, phải xanh)

**Interfaces:**
- Produces (Task 2, 3 dùng):

```python
@dataclass(frozen=True)
class RuleInputs:
    app: Tri                              # eval_cond(applicability)
    law: dict | None; law_st: Tri; law_reasons: tuple[str, ...]    # kết quả resolve_law
    check_st: Tri | None                  # check_cond(check, facts, law or {}) ; None khi rule.check is None

def resolve_law_with(rule: Rule, whens: Sequence[Tri], facts: Facts, day: date) -> tuple[dict | None, Tri, tuple[str, ...]]
    # như resolve_law nhưng nhận sẵn trị của rule.cases[i].when; resolve_law gọi hàm này
def rule_inputs(rule: Rule, facts: Facts, day: date, ctx: Context) -> RuleInputs
def decide_rule(concept_id: str, rule: Rule, facts: Facts, present: bool, evidence, inputs: RuleInputs, ctx: Context) -> RuleResult
    # đúng bảng trạng thái hiện tại của evaluate_rule, nhận đầu vào đã tính
def evaluate_rule(...)   # chữ ký cũ, = decide_rule(..., rule_inputs(...))
```

- [ ] **Step 1: Viết test thất bại** — `test_decide_rule_matches_evaluate_rule_on_golden_inputs`: với mọi ca golden (dùng `golden_cases` / `facts_from_spec(..., semantics.Fact, semantics.CONFLICT)`), `decide_rule(..., rule_inputs(...))` bằng `evaluate_rule(...)`; và `test_resolve_law_with_equals_resolve_law`: với `whens = [eval_cond(c.get("when"), facts, ctx) for c in rule.cases]` kết quả bằng `resolve_law` trên các rule có `cases` của catalog labor.
- [ ] **Step 2: Chạy, xác nhận fail** — `pytest tests/test_rules_semantics.py -q` → ImportError.
- [ ] **Step 3: Cài đặt** như chữ ký trên, chuyển thân hàm có sẵn (không viết lại bảng trạng thái). `rule_inputs` tính đủ mọi thành phần kể cả khi `app == "F"` (thuần, không tác dụng phụ).
- [ ] **Step 4: Chạy** `pytest tests/test_rules_semantics.py tests/test_rules_golden.py -q` rồi Gate → xanh, ghi số passed của Gate vào sổ.
- [ ] **Step 5: Commit** — `refactor(team-4.2): rules - tách evaluate_rule thành đầu vào và bảng quyết định`.

---

### Task 2: Node điều kiện có bộ đếm, chia sẻ theo khóa cấu trúc (D8)

**Files:**
- Create: `src/rag/rules/network/__init__.py`, `src/rag/rules/network/nodes.py`
- Test: `tests/test_rules_network_nodes.py`

**Interfaces:**
- Consumes: `eval_cond`, `Context`, `Tri` (semantics).
- Produces (Task 3 dùng):

```python
def cond_key(cond: dict) -> str                      # json.dumps(cond, sort_keys=True, ensure_ascii=False)
@dataclass class CondGraph:                          # đồ thị node điều kiện dùng chung, bất biến sau build
    def add(self, cond: dict | None) -> int | None   # trả chỉ số node gốc của cond (None nếu cond is None); trùng khóa thì dùng lại
    kinds: list[str]                                 # "leaf" | "all" | "any" | "not"
    conds: list[dict]; children: list[tuple[int, ...]]; parents: list[tuple[int, ...]]; rank: list[int]
    leaves_by_fact: dict[str, list[int]]             # tên dữ kiện -> chỉ số lá
class CondState:                                     # trạng thái theo phiên
    def __init__(self, graph: CondGraph, facts: Facts, ctx: Context)      # tính mọi node theo rank
    values: list[Tri]; counts: list[list[int]]       # đếm [T, F, U] của con cho all/any/not
    def update(self, changed_facts: set[str], facts: Facts, ctx: Context) -> set[int]
        # tính lại lá phụ thuộc dữ kiện đổi; lan lên cha theo rank, cập nhật bộ đếm O(1); trả tập node có giá trị đổi
    def copy(self) -> "CondState"
```

- [ ] **Step 1: Viết test thất bại**

```python
def test_shared_subexpression_is_one_node():          # hai cond cùng chứa {"fact":"a","op":"eq","value":1} -> graph.add cho cùng chỉ số lá; số node < tổng số biểu thức
def test_state_values_equal_eval_cond_after_random_updates():
    # seed cố định; 200 biểu thức ngẫu nhiên (all/any/not lồng ≤ 3 tầng, lá eq/lt/in/present/absent trên 6 dữ kiện),
    # 100 bước đổi ngẫu nhiên (đặt Fact, CONFLICT, UNKNOWN, hoặc xóa); sau mỗi bước values[root] == eval_cond(cond, facts, ctx)
def test_update_returns_only_changed_nodes_and_touches_only_dependents():
    # đổi dữ kiện "z" không nằm trong biểu thức nào -> update trả set() ; đổi "a" trả đúng các node có giá trị đổi
def test_copy_is_independent():                        # sửa bản sao không đổi values / counts của bản gốc
```

- [ ] **Step 2: Chạy, xác nhận fail.**
- [ ] **Step 3: Cài đặt** `nodes.py`. Giá trị: `all` = `F` nếu có con `F`, ngược lại `U` nếu có con `U`, ngược lại `T`; `any` = `T` nếu có con `T`, ngược lại `U` nếu có con `U`, ngược lại `F`; `not` đảo `T`/`F`, giữ `U`; lá = `eval_cond(leaf, facts, ctx)`. Rank của lá = 0, của node ghép = 1 + max rank con; `update` xử lý hàng đợi theo rank, mỗi node tối đa một lần.
- [ ] **Step 4: Chạy** `pytest tests/test_rules_network_nodes.py -q` → passed.
- [ ] **Step 5: Commit** — `feat(team-4.2): rules - node điều kiện ba trị có bộ đếm, chia sẻ theo khóa`.

---

### Task 3: `Network`, `NetworkSession`, đối chiếu với Reference (D9–D12)

**Files:**
- Create: `src/rag/rules/network/network.py`, `src/rag/rules/network/session.py`
- Modify: `src/rag/rules/evaluator.py` (`evaluator_for(catalog, "network")` trả `NetworkEvaluator`; `make_evaluator(..., "network")` dùng được; `default_kind()`)
- Test: `tests/test_rules_network.py`, sửa `tests/test_rules_evaluator.py` (bỏ hai chỗ kỳ vọng `NotImplementedError` cho `network`)

**Interfaces:**
- Consumes: `CondGraph`, `CondState` (Task 2); `rule_inputs`, `decide_rule`, `resolve_law_with`, `check_cond`, `referenced` (Task 1, semantics); `Session`, `Diff`, `RuleChange` (evaluator).
- Produces:

```python
class Network:
    @staticmethod
    def compile(catalog: Catalog) -> "Network"       # CondGraph cho applicability và cases[*].when của mọi rule; chỉ mục: dữ kiện -> rule (theo referenced), khái niệm -> rule
class NetworkEvaluator:                               # implements Evaluator
    def __init__(self, catalog: Catalog)              # biên dịch một lần
    def session(self, *, day, facts, present, evidence, objects=()) -> NetworkSession
class NetworkSession:                                 # implements Session
    stats: dict[str, int]                             # sau mỗi update: {"nodes_recomputed", "rules_recomputed"}; sau khởi tạo: tổng
def default_kind() -> EvaluatorKind                   # os.environ.get("RAG_RULE_EVALUATOR", "reference") — đổi mặc định sang "network" ở Task 5
```
Rule tính lại khi: dữ kiện nó tham chiếu (`referenced`) đổi; một node điều kiện gốc của nó (applicability hoặc `cases[i].when`) đổi giá trị; `present` hoặc `evidence` của khái niệm của nó đổi. Tính lại rule = `rule_inputs`-tương-đương lấy `app` / `whens` từ `CondState`, `resolve_law_with`, `check_cond`, rồi `decide_rule`. `update`: `None` xóa dữ kiện; `present` / `evidence` truyền thì thay hẳn; `Diff` theo thứ tự catalog, chỉ rule có `before != after`; `objects` khác rỗng → `NotImplementedError("objects: giai đoạn 7")`.

- [ ] **Step 1: Viết test thất bại**

```python
def test_network_session_results_equal_reference_on_golden():
    # với mỗi ca golden (facts_from_spec(..., semantics.Fact, semantics.CONFLICT)): phiên network(day, facts, present={concept} nếu present else set())
    # -> kết quả của rule đó == kết quả golden (asdict)
@pytest.mark.parametrize("seed", range(20))
def test_random_update_sequences_equal_reference(seed):
    # vũ trụ dữ kiện + giá trị ứng viên lấy từ rules_golden_cases._candidates trên mọi rule của catalog labor;
    # 150 bước ngẫu nhiên: đặt dữ kiện (Fact / CONFLICT / UNKNOWN), xóa dữ kiện, đổi present, đổi evidence, hoặc cả bốn trong một update;
    # sau mỗi bước: network.results() == reference.results() và Diff (before/after theo (concept_id, rule_id)) bằng nhau
def test_shared_condition_updates_all_rules():
    # chọn hai rule cùng chứa một điều kiện lá (catalog labor có ví dụ: contract_kind = xac_dinh_thoi_han ở 5 rule) ; đổi contract_kind -> Diff chứa mọi rule phụ thuộc
def test_present_or_evidence_change_recomputes_only_that_concept():
    # update({}, present=...) chỉ đổi present của một khái niệm: stats["rules_recomputed"] == số rule của khái niệm đó; kết quả == reference
def test_update_recomputes_fewer_rules_than_total():
    # đổi một dữ kiện chỉ 1–2 rule tham chiếu (vd. annual_leave): stats["rules_recomputed"] < tổng số rule
def test_fork_is_independent_including_counters():
    # fork, update bản sao, bản gốc results() không đổi và vẫn bằng reference; update tiếp bản gốc vẫn bằng reference
def test_removing_a_fact_never_creates_a_violation():
    # trên chuỗi ngẫu nhiên: sau khi xóa một dữ kiện, không rule nào chuyển từ finding != "violation" sang "violation"
def test_objects_not_supported_yet(): # update(objects=[x]) và session(objects=[x]) -> NotImplementedError
def test_make_evaluator_network_runs(): # make_evaluator(["labor"], "network").session(...).results() == reference
```

- [ ] **Step 2: Chạy, xác nhận fail** — `pytest tests/test_rules_network.py -q` → ImportError / NotImplementedError.
- [ ] **Step 3: Cài đặt** `network.py`, `session.py`, và sửa `evaluator.py`. Nếu `test_removing_a_fact_never_creates_a_violation` hoặc `test_random_update_sequences_equal_reference` fail, tìm nguyên nhân (systematic-debugging); nếu phát hiện Reference có hành vi khác spec thì ghi vào sổ làm `Ruling` thay vì sửa kỳ vọng cho vừa.
- [ ] **Step 4: Chạy** `pytest tests/test_rules_network.py tests/test_rules_evaluator.py -q` → passed; chạy Gate.
- [ ] **Step 5: Commit** — `feat(team-4.2): rules - NetworkEvaluator: mạng điều kiện tăng dần, khớp Reference`.

---

### Task 4: Nối vào `check_contract` và `tools.check_concept` (E1, E2)

**Files:**
- Modify: `src/rag/bridge/check.py` (`check_contract`: tham số `evaluator: str | None = None`; `read_graph` dùng phiên), `src/rag/contracts/graph/tools.py` (`check_concept` dùng `evaluator_for(catalog, default_kind())`)
- Test: `tests/test_rules_integration.py`

**Interfaces:**
- Consumes: `evaluator_for`, `default_kind` (Task 3).
- Produces: `check_contract(..., evaluator: str | None = None)` — `None` → `default_kind()`; lần `read_graph` đầu tạo phiên, lần sau (sau recheck) gọi `session.update(changes, present=..., evidence=...)` với `changes = {tên: facts_mới.get(tên) for tên trong hợp hai bảng nếu giá trị khác}`; `check_concept` tạo phiên cho mỗi lần gọi.

- [ ] **Step 1: Viết test thất bại** — dùng `ScriptLLM`, `PAGES`, `UNITS` kiểu `tests/test_bridge_check.py` (chép phần dựng hợp đồng, không import chéo):

```python
def test_check_contract_same_report_for_both_evaluators():
    # chạy hai lần (evaluator="reference" và "network") trên cùng hợp đồng và ScriptLLM; report_json bằng nhau sau khi bỏ stats["seconds"]
def test_check_contract_recheck_path_uses_update_and_matches():
    # hợp đồng có khái niệm "im lặng" buộc recheck (ScriptLLM trả items rỗng cho recheck): báo cáo cuối của hai evaluator bằng nhau
def test_check_concept_tool_equal_for_both_kinds(monkeypatch):   # RAG_RULE_EVALUATOR=reference rồi =network: kết quả tool bằng nhau
def test_unknown_evaluator_name_rejected():                      # evaluator="khong_co" -> ValueError
```

- [ ] **Step 2: Chạy, xác nhận fail.** **Step 3: Cài đặt.** **Step 4: Chạy** `pytest tests/test_rules_integration.py -q` rồi Gate → xanh với `RAG_RULE_EVALUATOR` chưa đặt (mặc định `reference`).
- [ ] **Step 5: Commit** — `feat(team-4.2): nối evaluator vào check_contract và check_concept`.

---

### Task 5: Mặc định `network`, nghiệm thu giai đoạn 2

**Files:**
- Modify: `src/rag/rules/evaluator.py` (`default_kind` mặc định `"network"`), `docs/phan_cong_w04/tung_viec_can_lam.md` (đánh dấu D8–D12, E1, E2)
- Test: `tests/test_rules_integration.py` (thêm)

- [ ] **Step 1: Viết test thất bại** — `test_default_evaluator_is_network`: không đặt biến môi trường → `default_kind() == "network"`; đặt `RAG_RULE_EVALUATOR=reference` → `"reference"`; giá trị lạ → `ValueError`.
- [ ] **Step 2–4:** fail → đổi mặc định → `pytest tests/test_rules_*.py -q` + Gate với mặc định `network`; chạy bộ test Gate thêm một lần với `RAG_RULE_EVALUATOR=reference` → hai lần đều xanh, số passed bằng nhau.
- [ ] **Step 5: Chạy toàn bộ suite** `pytest -q --ignore=tests/test_agent_partial_review.py -rf` → đúng 35 test fail như baseline (`app/team-4.2/docs/superpowers/notes/w04-rule-engine/phase1_baseline.md`), test mới đều passed. Commit — `feat(team-4.2): evaluator mặc định là network; giai đoạn 2 hoàn tất`.

---

## Self-Review

**Spec coverage:** §6.1 phần 1 (node alpha chia sẻ, bộ đếm, lan truyền theo rank, không bộ nhớ beta) → Task 2, 3; §6.2 (FactNode / Alpha / And / Or / Not / RuleNode) → Task 2, 3 (LawNode, LawLeafNode, PresenceNode gộp vào RuleNode: ghi ở "Đơn giản hóa"); §6.3 (`update`, `fork`, diff, mỗi node tính ≤ 1 lần, không phụ thuộc thứ tự) → Task 2, 3; §10 (đối chiếu ngẫu nhiên, bất biến thiếu dữ kiện) → Task 3; §11 mục 2 (nối `check_contract` / `check_concept`, test cũ xanh với `network`) → Task 4, 5. Hoãn: dữ kiện suy ra / ngoại lệ (giai đoạn 3), `objects` (giai đoạn 7), `explain` / `next_questions` (giai đoạn 4).

**Type consistency:** `CondGraph` / `CondState` (Task 2) dùng nguyên tên ở Task 3; `RuleInputs` / `rule_inputs` / `decide_rule` / `resolve_law_with` (Task 1) dùng ở Task 3; `default_kind` (Task 3) dùng ở Task 4, 5.

**Review Focus:** mục 1, 5 → Task 3; mục 2 → Task 2, 3; mục 3 → Task 3; mục 4 → Task 3.
