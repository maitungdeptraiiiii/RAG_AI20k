# Đồ thị hợp đồng làm nguồn thao tác chính — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kiểm luật và một agent chỉ đọc thao tác trên đồ thị hợp đồng (bộ nhớ hoặc Neo4j) qua một giao diện đọc chung, trả lời kèm đường đi.

**Architecture:** Lược đồ v3 thêm `ContractFact` và cạnh `AMENDS` (dựng bằng quy tắc). `ContractGraphView` có hai bản chạy (`MemoryGraphView` trên `GraphBuild`, `Neo4jGraphView` trên `ContractGraphStore`) dùng chung một bộ test. Bộ kiểm luật dựng `FactSet` từ view theo ngày; bộ công cụ có kiểu bọc view + `LegalGraph` + engine; `GraphAgent` gọi công cụ bằng JSON từng bước.

**Tech Stack:** Python 3.11+, pytest, neo4j driver 5.x (extra `[graph]`), LLM `complete(system, user) -> str`.

**Spec:** `app/team-4.2/docs/superpowers/specs/2026-11-16-contract-graph-agent-design.md`

Mọi lệnh chạy từ `app/team-4.2`. Đường dẫn dưới đây tương đối với `app/team-4.2`.

## Global Constraints

- Oplog là nguồn sự thật; `build_graph` tất định (cùng đầu vào → cùng nút, cạnh, `build_id`).
- `schema.json` `"version": "3"`; mọi nhãn/loại cạnh mới phải có trong `SCHEMA` và qua `validate()`.
- Văn bản/câu trích trên đồ thị đã che PII bằng `MaskState(prefix="HD_")`; `validate()` không được báo PII.
- Neo4j tùy chọn (`CONTRACT_GRAPH=1`); không có Neo4j thì kiểm luật và agent chạy trên `MemoryGraphView`.
- Không chuỗi Cypher nào ghép từ dữ liệu ngoài; `rel_types`/nhãn kiểm theo `SCHEMA` trước khi nối chuỗi; giá trị luôn là tham số; mọi truy vấn có `contract_id: $cid`.
- Agent không ghi đồ thị/oplog; kết luận pháp lý chỉ từ `check_concept` (engine).
- Ngày (Q1 = a): dữ kiện là giá trị **đang hiệu lực tại ngày soát**; `AMENDS.valid_from` null → coi như hiệu lực từ ngày ký + cảnh báo `"không rõ ngày hiệu lực của sửa đổi"`.
- Test Neo4j thật chỉ chạy khi có `NEO4J_TEST_URI` (mẫu `tests/test_contracts_neo4j.py:20`).

## Review Focus

1. Phụ lục sửa một điều khoản nhưng không ghi ngày hiệu lực → vẫn thay giá trị, kèm cảnh báo (Task 4 test `test_amend_without_date_applies_with_warning`).
2. Hai phụ lục cùng sửa một dữ kiện, ngày khác nhau → lấy sửa đổi mới nhất có `valid_from ≤ day`, sửa đổi sau đưa vào `later_amendments` (Task 4 test `test_two_amendments_pick_latest_in_force`).
3. Agent trả `path` có nút không gặp trong lượt hoặc hai nút liền kề không có cạnh → `partial` + cảnh báo, không ném (Task 7 test `test_invented_path_downgrades`).
4. Agent truyền `rel_types=["DELETE"]` hoặc `node_id` của hợp đồng khác → công cụ trả `{"error": ...}`, không chạm store (Task 6 test `test_tools_reject_bad_args`).
5. Hợp đồng không có phụ lục / không có dữ kiện → view, factset, công cụ trả rỗng, không lỗi (Task 3 test `test_empty_contract_view`, Task 4 test `test_no_facts`).

---

### Task 1: Lược đồ v3 và cạnh `AMENDS` bằng quy tắc

**Files:**
- Create: `src/rag/contracts/amendments.py`
- Modify: `src/rag/contracts/graph/schema.json`, `src/rag/contracts/graph/build.py` (sau dòng 101), `src/rag/bridge/facts_map.py:83` (dùng mẫu chung)
- Test: `tests/test_contracts_amendments.py`

**Interfaces:**
- Produces: `AMEND_RE: re.Pattern` (trong `amendments.py`, `facts_map._AMEND` import lại từ đây; thêm "bổ sung"); `@dataclass(frozen=True) class Amendment: src_uid: str; dst_uid: str; kind: Literal["modify","supplement"]; valid_from: date | None; raw: str`; `find_amendments(doc: ContractDoc) -> list[Amendment]`. Cạnh đồ thị `AMENDS(nid[src] → nid[dst], {"kind", "valid_from": iso|None, "raw"})`. `GraphBuild.record()["notes"]: list[str]` (thêm trường `notes: tuple[str,...] = ()` cho `GraphBuild`).

- [ ] **Step 1: Write the failing tests**

```python
DEMO = Path(__file__).resolve().parents[3] / "data/team-4.2/contracts_demo/hdld_tvpl_2025_filled.txt"

def demo_pages():
    return [PageText(1, DEMO.read_text(encoding="utf-8"))]

def test_demo_appendix2_amends_article2():
    b, doc = build_graph("c1", demo_pages(), OperationLog("c1"), file_checksum="x", built_at=T)
    am = [e for e in b.edges if e.type == "AMENDS"]
    mod = [e for e in am if e.props["kind"] == "modify"]
    assert len(mod) == 1 and mod[0].dst == "c1:p0.d2@1" and mod[0].props["valid_from"] == "2025-07-01"
    assert any(e.props["kind"] == "supplement" and e.dst == "c1:p0.d2@1" for e in am)
    assert validate(b) == []

def test_appendix_without_effective_date_gives_null_and_note():
    pages = [PageText(1, "Điều 1. Lương\nLương 10.000.000 đồng.\nPHỤ LỤC 1\nSửa đổi Điều 1 Hợp đồng lao động: lương lên 12.000.000 đồng.")]
    b, _ = build_graph("c1", pages, OperationLog("c1"), file_checksum="x", built_at=T)
    e = next(e for e in b.edges if e.type == "AMENDS")
    assert e.props["valid_from"] is None and b.record()["notes"]

def test_reference_without_amend_verb_is_not_amends():
    pages = [PageText(1, "Điều 1. Lương\nLương 10 triệu.\nPHỤ LỤC 1\nCăn cứ Điều 1 Hợp đồng lao động, hai bên cam kết.")]
    b, _ = build_graph("c1", pages, OperationLog("c1"), file_checksum="x", built_at=T)
    assert not [e for e in b.edges if e.type == "AMENDS"]
```

(Nếu nhãn phần/uid của hai trang tổng hợp khác `p0.d1`/`p1…`, chỉnh khẳng định theo `doc.units` thực tế — điều kiện cần giữ là "có/không có AMENDS" và `valid_from`.)

- [ ] **Step 2:** `uv run pytest tests/test_contracts_amendments.py -q` → FAIL (`AMENDS` không có).
- [ ] **Step 3: Implement**
  - `schema.json`: `"version": "3"`, thêm `"AMENDS": [["Unit"], ["Unit"]]` (nút/cạnh `ContractFact` thêm ở Task 2).
  - `find_amendments`: với mỗi `CrossRef` `kind == "internal"`, `to_uid` bắt đầu `"p0."`, đơn vị nguồn có `part_id != "p0"` và văn bản riêng (`own_texts`) khớp `AMEND_RE` → một `Amendment`; `kind="supplement"` nếu động từ đầu tiên khớp là "bổ sung". `valid_from` = ngày đầu tiên khớp `r"hiệu lực\s+(?:kể\s+)?từ\s+ngày\s+(\d{1,2})(?:/|\s+tháng\s+)(\d{1,2})(?:/|\s+năm\s+)(\d{4})"` trong văn bản mọi đơn vị cùng `part_id`. Trùng (src, dst) bỏ.
  - `build_graph`: thêm cạnh `AMENDS`; đơn vị có `valid_from is None` → note `f"sửa đổi {src} -> {dst}: không rõ ngày hiệu lực"`.
- [ ] **Step 4:** `uv run pytest tests/test_contracts_amendments.py tests/test_contracts_graph_build.py tests/test_bridge_facts_map.py -q` → PASS.
- [ ] **Step 5: Commit** `feat(team-4.2): AMENDS edges from appendix amendment clauses, schema v3`

### Task 2: Dữ kiện cấp hợp đồng → oplog → nút `ContractFact`

**Files:**
- Modify: `src/rag/bridge/facts_map.py` (thêm `fact_ops`), `src/rag/contracts/graph/build.py` (`_concept_layer`), `schema.json`
- Test: `tests/test_bridge_facts_map.py`, `tests/test_contracts_graph_build.py`

**Interfaces:**
- Consumes: `_CONTRACT_MAP` (facts_map.py:109).
- Produces: `fact_ops(facts: dict, contract_id: str, *, at: datetime) -> list[GraphOperation]` — một `machine_op(cid, "ASSERT", f"fact:{name}", {"kind": "fact", "name", "value", "unit"}, "llm", "auto_accepted", source_uid=c["unit"], quote=(c["quote"],), at=at)` cho mỗi ứng viên chuẩn hóa được (bỏ ứng viên không có `unit`). Nút `ContractFact` id `f"{cid}:fact:{op_id}"`, props `{name, value, unit, quote(che), op_id, source: "contract"}`; cạnh `HAS_FACT(Contract→ContractFact)`, `EVIDENCE(ContractFact→Unit)`. Nút Contract thêm `absent_checked: list[str]` (concept_id từ ASSERT `concept_absent`, sắp xếp). Schema: nút `ContractFact`; `HAS_FACT: [["Contract"],["ContractFact"]]`, `EVIDENCE: [["ContractFact"],["Unit"]]`.

- [ ] **Step 1: Failing tests**

```python
def test_fact_ops_one_per_normalized_candidate():
    facts = {"candidates": {"salary": [{"value": "15.000.000 đồng/tháng", "unit": "p0.d2", "quote": "15.000.000 đồng/tháng"}],
                            "probation_salary": [{"value": "85%", "unit": "p0.d6", "quote": "hưởng 85%"}],
                            "term": [{"value": "không rõ", "unit": "p0.d1", "quote": "x"}]}}
    ops = fact_ops(facts, "c1", at=AT)
    got = {(o.content["name"], o.content["value"], o.content["unit"], o.source_uid) for o in ops}
    assert got == {("base_salary_vnd", 15000000, "vnd", "p0.d2"), ("probation_pay_pct", 85.0, "percent", "p0.d6")}
    assert fact_ops(facts, "c1", at=AT)[0].op_id == ops[0].op_id      # chạy lại không nhân bản

def test_contract_fact_nodes_and_absent_checked():   # trong test_contracts_graph_build.py
    log = OperationLog("c1")
    for o in fact_ops({"candidates": {"salary": [{"value": "30 triệu đồng", "unit": "p0.d1.k1", "quote": "Giá 30 triệu đồng"}]}}, "c1", at=T):
        log.add(o)
    log.add(machine_op("c1", "ASSERT", "absent:x", {"kind": "concept_absent", "concept_id": "content.raise_policy"}, "llm", "auto_accepted", at=T))
    b, _ = build_graph("c1", PAGES, log, file_checksum="x", built_at=T)
    f = next(n for n in b.nodes if n.label == "ContractFact")
    assert f.props["name"] == "base_salary_vnd" and f.props["value"] == 30000000
    assert any(e.type == "EVIDENCE" and e.src == f.node_id and e.dst == "c1:p0.d1.k1@1" for e in b.edges)
    assert next(n for n in b.nodes if n.label == "Contract").props["absent_checked"] == ["content.raise_policy"]
    assert validate(b) == []
```

- [ ] **Step 2:** chạy hai test → FAIL.
- [ ] **Step 3:** cài `fact_ops` (dùng lại các hàm chuẩn hóa trong `_CONTRACT_MAP`; tên dữ kiện là khóa của `_CONTRACT_MAP`, một ứng viên có thể sinh nhiều tên, vd. `probation_period` → `has_probation` và `probation_length`); mở rộng `_concept_layer` (bỏ điều kiện `if not asserts: return` sớm cho phần fact/absent, hoặc tách hàm `_fact_layer`).
- [ ] **Step 4:** `uv run pytest tests/test_bridge_facts_map.py tests/test_contracts_graph_build.py -q` → PASS.
- [ ] **Step 5: Commit** `feat(team-4.2): contract-level facts as ASSERT ops and ContractFact nodes`

### Task 3: `ContractGraphView` — bộ nhớ và Neo4j, một bộ test

**Files:**
- Create: `src/rag/contracts/graph/view.py`
- Modify: `src/rag/contracts/graph/service.py` (thêm `build_and_publish`)
- Test: `tests/test_contract_graph_view.py`

**Interfaces:**
- Produces (trong `view.py`):
  - `Hop = TypedDict("Hop", {"rel": str, "dir": Literal["out","in"], "props": dict, "node": dict})`
  - `class ContractGraphView(Protocol)` với `contract_id: str`, `backend: Literal["memory","neo4j"]`, và:
    `node(node_id: str) -> dict | None`; `find(label: str, **props) -> list[dict]`; `search_units(text: str, limit: int = 8) -> list[dict]`;
    `neighbors(node_id: str, *, rel_types: Sequence[str] | None = None, direction: Literal["out","in","both"] = "both") -> list[Hop]`;
    `path(src: str, dst: str, *, rel_types: Sequence[str] | None = None, max_hops: int = 4) -> list[Hop] | None`;
    `subgraph(node_id: str, *, hops: int = 1, rel_types: Sequence[str] | None = None, limit: int = 60) -> dict` (`{"nodes": [...], "edges": [{"type","src","dst","props"}]}`).
  - Nút trả về: `{"node_id", "label", **props}` bỏ `contract_id`, `build_id`; `text` > 600 ký tự → cắt + `"truncated": True`.
  - `MemoryGraphView(build: GraphBuild)`, `Neo4jGraphView(store: ContractGraphStore, contract_id: str)`.
  - `check_rel_types(rel_types) -> list[str] | None` ném `ValueError` khi loại lạ; `max_hops` ngoài 1..6 → `ValueError`.
  - Thứ tự tất định: `neighbors` sắp theo `(rel, dir, node_id)`; `path` khi nhiều đường ngắn nhất chọn đường có dãy `(rel, node_id)` nhỏ nhất theo thứ tự từ điển (cả hai bản).
  - `search_units`: Unit có `text` hoặc `label` chứa chuỗi (so sánh `casefold`, gộp khoảng trắng), sắp theo `node_id`.
- Produces (service.py): `ContractGraphService.build_and_publish(contract_id, pages, oplog, *, file_checksum, now) -> tuple[GraphBuild, ContractDoc, dict]` (thân hiện tại của `rebuild`; `rebuild` gọi nó và bỏ phần tử đầu). `status["published"]` như cũ.
- Produces: `open_view(build: GraphBuild, status: dict, store: ContractGraphStore | None) -> ContractGraphView` — Neo4j khi `status["published"]` và `store` có; ngược lại bộ nhớ.

- [ ] **Step 1: Failing tests** — fixture `view` tham số hóa `["memory", "neo4j"]`; nhánh neo4j `pytest.skip` khi thiếu `NEO4J_TEST_URI`, ngược lại `store.ensure_schema(); store.publish(build)` rồi `Neo4jGraphView(store, "c1")`. Đầu vào: trang demo + oplog có `fact_ops` lương 15tr ở `p0.d2` (Task 2).

```python
def test_neighbors_of_article6_include_refers_to_article2(view):
    hops = view.neighbors("c1:p0.d6@1", rel_types=["REFERS_TO"], direction="out")   # hoặc đơn vị con chứa câu thử việc
    assert any(h["node"]["node_id"].startswith("c1:p0.d2") for h in hops)

def test_path_article6_to_article2_and_amendment(view):
    src = view.search_units("thử việc")[0]["node_id"]
    p = view.path(src, "c1:p0.d2@1", max_hops=3)
    assert p and p[-1]["node"]["node_id"] == "c1:p0.d2@1"
    assert any(h["rel"] == "AMENDS" and h["dir"] == "in" for h in view.neighbors("c1:p0.d2@1"))

def test_same_answers_on_both_backends(view, memory_view):
    for args in [("c1:p0.d2@1",), ("c1",)]:
        assert view.neighbors(*args) == memory_view.neighbors(*args)
    assert view.subgraph("c1:p0.d2@1", hops=1) == memory_view.subgraph("c1:p0.d2@1", hops=1)

def test_bad_rel_type_and_hops_raise(view):
    with pytest.raises(ValueError): view.neighbors("c1", rel_types=["DELETE"])
    with pytest.raises(ValueError): view.path("c1", "c1:p0", max_hops=9)

def test_foreign_and_missing_nodes(view):
    assert view.node("c2:p0.d1@1") is None and view.neighbors("c2:p0.d1@1") == []

def test_empty_contract_view():
    b, _ = build_graph("c9", [PageText(1, "")], OperationLog("c9"), file_checksum="x", built_at=T)
    v = MemoryGraphView(b)
    assert v.search_units("lương") == [] and v.path("c9", "c9", max_hops=1) == []
```

(Uid đích của câu thử việc: lấy từ `doc.units` khi viết test; đừng đoán.)

- [ ] **Step 2:** `uv run pytest tests/test_contract_graph_view.py -q` → FAIL (import).
- [ ] **Step 3:** cài `view.py`. Bản Neo4j: `neighbors` = `MATCH (a:CGNode {node_id:$id, contract_id:$cid})-[r]-(b:CGNode {contract_id:$cid}) WHERE type(r) IN $types ...` (lọc loại bằng tham số `$types` đã kiểm, chiều bằng `startNode(r) = a`); `path` = `MATCH p = allShortestPaths((a)-[*..N]-(b))` với `N` là số nguyên đã kiểm nối vào chuỗi, `WHERE all(r IN relationships(p) WHERE type(r) IN $types)`, rồi chọn theo quy tắc thứ tự ở Python. Sửa `service.py` như Interfaces.
- [ ] **Step 4:** `uv run pytest tests/test_contract_graph_view.py tests/test_contracts_graph_service.py -q` → PASS (neo4j skip nếu không có).
- [ ] **Step 5: Commit** `feat(team-4.2): ContractGraphView with in-memory and Neo4j backends`

### Task 4: `factset_from_graph` theo ngày

**Files:**
- Create: `src/rag/bridge/graph_facts.py`
- Modify: `src/rag/bridge/engine.py:17-23` (thêm `later_amendments`), `engine.py:206` (đưa `later_amendments` vào `facts_used`), `src/rag/bridge/check.py:145-148` (in dòng "từ <ngày>: …")
- Test: `tests/test_bridge_graph_facts.py`

**Interfaces:**
- Consumes: `ContractGraphView` (Task 3), `FactSet` (facts_map.py:160).
- Produces: `Fact.later_amendments: tuple[dict, ...] = ()` — `({"value","unit","uid","valid_from"}, …)`. `factset_from_graph(view: ContractGraphView, *, day: date, sign_date: date | None) -> tuple[FactSet, list[str]]` (warnings).

Quy tắc (spec §5.5, §7): gom `ContractFact` theo `name`; mỗi giá trị có `uid` = uid nút EVIDENCE, `top` = tổ tiên cấp cao nhất (theo `CHILD_OF`). Giá trị B **sửa** A khi có cạnh `AMENDS x→y` với `top(x) == top(B)` và `top(y) == top(A)`; ngày hiệu lực của B = `valid_from` cạnh đó (null → `sign_date`, + cảnh báo `"không rõ ngày hiệu lực của sửa đổi"`). Giá trị tại `day` = giá trị gốc (không bị cái gì sửa) được thay lần lượt bởi các sửa đổi có ngày ≤ `day` (mới nhất thắng; `amended_from` = các giá trị bị thay); sửa đổi có ngày > `day` → `later_amendments`. Hai giá trị khác nhau không có quan hệ sửa → `CONFLICT`. `ConceptInstance` → `present`, `evidence` (`{"uid", "quote", "op_id"}`), slot (`slot_<name>` / `slot_<name>_unit`) merge như `_merge`. `absent_checked` từ props nút Contract trừ `present`. `sign_date` → `Fact(sign_date)` như `contract_facts`.

- [ ] **Step 1: Failing tests** (đồ thị dựng từ trang demo + `fact_ops` với lương 15tr ở `p0.d2`, 17tr ở đơn vị phụ lục chứa câu "Sửa đổi Điều 2")

```python
def test_salary_at_sign_date_is_original_with_later_amendment(): # day 2025-01-02
    fs, warn = factset_from_graph(view, day=date(2025, 1, 2), sign_date=date(2025, 1, 2))
    f = fs.facts["base_salary_vnd"]
    assert f.value == 15000000 and f.later_amendments[0]["value"] == 17000000
    assert f.later_amendments[0]["valid_from"] == "2025-07-01" and not f.amended_from

def test_salary_after_effective_date_is_amended():               # day 2025-08-01
    f = factset_from_graph(view, day=date(2025, 8, 1), sign_date=date(2025, 1, 2))[0].facts["base_salary_vnd"]
    assert f.value == 17000000 and f.amended_from[0]["value"] == 15000000

def test_unrelated_different_values_conflict(): ...   # hai giá trị ở p0.d1 và p0.d2, không AMENDS -> CONFLICT
def test_amend_without_date_applies_with_warning(): ...  # trang tổng hợp Task 1 -> giá trị mới tại sign_date + warning
def test_two_amendments_pick_latest_in_force(): ...     # hai phụ lục 01/03 và 01/09; day 01/05 -> giá trị 01/03, later có 01/09
def test_no_facts(): ...                                # đồ thị không có ContractFact -> facts chỉ có sign_date, present rỗng
def test_concept_instances_feed_present_and_slots(): ... # ConceptInstance leave.annual slot annual_leave=8 day
```

- [ ] **Step 2:** `uv run pytest tests/test_bridge_graph_facts.py -q` → FAIL.
- [ ] **Step 3:** cài theo quy tắc trên; `report_markdown` in `f"  - {name}: từ {a['valid_from']}: {a['value']} {a.get('unit') or ''} [{a['uid']}]"` cho mỗi `later_amendments` trong `facts_used`.
- [ ] **Step 4:** `uv run pytest tests/test_bridge_graph_facts.py tests/test_bridge_engine*.py -q` → PASS.
- [ ] **Step 5: Commit** `feat(team-4.2): fact set read from contract graph, values in force at check day`

### Task 5: `check_contract` đọc từ đồ thị

**Files:**
- Modify: `src/rag/bridge/check.py:66-110`, `scripts/check_contract_concepts.py:80-84`
- Test: `tests/test_bridge_check.py` (đổi fixture), thêm `tests/test_bridge_check_graph_parity.py`

**Interfaces:**
- Consumes: `fact_ops` (T2), `ContractGraphService.build_and_publish`, `open_view` (T3), `factset_from_graph` (T4).
- Produces: `check_contract(..., graph: ContractGraphService | None = None)`; luồng: facts → `_add_ops(party_ops + fact_ops)` → tag → `_add_ops` → `view = _view(contract, graph, at)` → `factset_from_graph(view, day=day, sign_date=contract.sign_date)` → evaluate → recheck (nếu có) → dựng lại view → evaluate. `_view`: `graph.build_and_publish(...)` nếu `graph` khác None, ngược lại `build_graph(...)` thuần; `file_checksum=contract.file_checksum or ""`, `pages=contract.page_texts`. `build.problems` khác rỗng → vẫn dùng `MemoryGraphView(build)` và thêm cảnh báo `"đồ thị có lỗi lược đồ: …"`. `CheckReport.stats` thêm `graph_backend`, `build_id`; `warnings` thêm cảnh báo của factset. `contract_facts` + `build_factset` không còn được gọi trong `check.py`.
- Script: truyền `graph=api._graph()` và bỏ khối `_rebuild` thừa ở dòng 83-84 (giữ cập nhật `contract.doc/units/graph` bằng `api._rebuild` sau check nếu UI cần — giữ nguyên dòng đó, chỉ thêm tham số).

- [ ] **Step 1:** đổi fixture `contract()` trong `tests/test_bridge_check.py` sang trang thật: `PAGES = [PageText(1, "Bên A: Công ty TNHH Minh An, là Người sử dụng lao động. ...\nĐiều 1. Loại hợp đồng ...\nĐiều 2. Người lao động được nghỉ phép 08 ngày/năm.")]`, `doc = parse_contract(PAGES)`, `Contract(..., to_contract_units(doc), len(doc.top_units()), doc=doc, page_texts=PAGES, file_checksum="x")` (mẫu `tests/test_contracts_verify.py:32`); `ScriptLLM` dùng uid thật (`p0.d1`, `p0.d2`, đơn vị mở đầu) thay `u1..u3`. Các khẳng định cũ giữ nguyên; thêm `assert r.stats["graph_backend"] == "memory" and r.stats["build_id"].startswith("b")`.
- [ ] **Step 2:** test so sánh mới: cùng hợp đồng, so `evaluate` trên `build_factset(contract_facts(...), oplog)` (đường cũ) với `factset_from_graph` → bằng nhau theo `(concept_id, rule_id, finding)`; một test thứ hai trên trang demo có phụ lục: khác biệt duy nhất là các rule dùng `base_salary_vnd` (ghi rõ trong docstring "khác biệt cố ý spec §7").
- [ ] **Step 3:** `uv run pytest tests/test_bridge_check.py tests/test_bridge_check_graph_parity.py -q` → FAIL.
- [ ] **Step 4:** sửa `check.py` như Interfaces.
- [ ] **Step 5:** `uv run pytest tests -q -k "bridge or contracts"` → PASS.
- [ ] **Step 6: Commit** `feat(team-4.2): concept check reads facts from the contract graph`

### Task 6: Bộ công cụ có kiểu

**Files:**
- Create: `src/rag/contracts/graph/tools.py`
- Test: `tests/test_contract_graph_tools.py`

**Interfaces:**
- Consumes: `ContractGraphView`, `factset_from_graph`, `evaluate_concept` (engine.py:257), `AnchorLawBasis`, `LegalGraph | None`, `Catalog`.
- Produces:
  - `@dataclass(frozen=True) class Tool: name: str; doc: str; params: dict[str, dict]; run: Callable[[dict], dict]` — `params` dạng `{"node_id": {"type": "str", "required": True}, "direction": {"type": "str", "enum": ["out","in","both"]}, ...}`.
  - `make_tools(view: ContractGraphView, *, catalog: Catalog, day: date, sign_date: date | None, legal: LegalGraph | None) -> dict[str, Tool]` với tên: `find_units, find_concept, expand, find_path, subgraph, contract_facts, law_text_at, law_changes, law_guidance, law_references, concept_basis, check_concept`.
  - `call_tool(tools: dict[str, Tool], name: str, args: dict) -> dict`: tên lạ / tham số thiếu, sai kiểu, ngoài enum / `ValueError` từ view → `{"error": "<mô tả>"}`; kết quả JSON > 3000 ký tự → cắt danh sách dài nhất, thêm `"more": <số bị cắt>`.
  - `check_concept` trả `{"concept_id", "results": [{"rule_id","finding","status","law_values","facts_used","missing_facts","evidence"}]}` từ `evaluate_concept(catalog.concepts[cid], fs.facts, present=cid in fs.present, evidence=fs.evidence.get(cid, ()), day=day)`.
  - `contract_facts(name?)` trả mỗi dữ kiện `{name, value, unit, uid, quote, amended_from, later_amendments}`.
  - Công cụ luật khi `legal is None` hoặc ném lỗi → `{"error": "legal_graph_unavailable"}`; `day` tham số ISO, mặc định `day`.

- [ ] **Step 1: Failing tests**

```python
def test_tools_reject_bad_args(tools):
    assert "error" in call_tool(tools, "expand", {"node_id": "c1", "rel_types": ["DELETE"]})
    assert "error" in call_tool(tools, "find_path", {"src": "c1"})               # thiếu dst
    assert "error" in call_tool(tools, "nope", {})
    assert call_tool(tools, "expand", {"node_id": "c2:p0.d1@1"}) == {"hops": []}

def test_contract_facts_shows_later_amendment(tools):
    f = call_tool(tools, "contract_facts", {"name": "base_salary_vnd"})["facts"][0]
    assert f["value"] == 15000000 and f["later_amendments"][0]["valid_from"] == "2025-07-01"

def test_check_concept_runs_engine_without_llm(tools): ...   # probation.pay -> results có rule_id, finding
def test_law_tools_without_legal_graph(tools):
    assert call_tool(tools, "law_text_at", {"pid": "bllđ-2019#d26"}) == {"error": "legal_graph_unavailable"}
def test_output_is_capped(tools):
    out = call_tool(tools, "subgraph", {"node_id": "c1", "hops": 2})
    assert len(json.dumps(out, ensure_ascii=False)) <= 3200 and out.get("more", 0) >= 0
```

- [ ] **Step 2:** chạy → FAIL. **Step 3:** cài. **Step 4:** chạy → PASS.
- [ ] **Step 5: Commit** `feat(team-4.2): typed read-only tools over contract and legal graphs`

### Task 7: `GraphAgent`

**Files:**
- Create: `src/rag/contracts/graph/agent.py`
- Modify: `src/rag/contracts/graph/build.py` (tách `graph_mask_state(doc: ContractDoc) -> MaskState`, `build_graph` dùng nó)
- Test: `tests/test_contract_graph_agent.py`

**Interfaces:**
- Consumes: `make_tools`, `call_tool` (T6), view (T3), `catalog`.
- Produces:
  - `AGENT_PROMPT: str` (hằng; test nhận diện bằng `system.startswith(AGENT_PROMPT[:40])`).
  - `@dataclass class GraphAnswer: answer: str; path: list[dict]; law: list[str]; confidence: Literal["answer","partial","cannot"]; warnings: list[str]; trace: list[dict]; stats: dict`.
  - `GraphAgent(llm, tools: dict[str, Tool], view: ContractGraphView, *, mask: MaskState, context: dict, max_steps: int = 8)`; `.ask(question: str) -> GraphAnswer`.
  - Payload mỗi lượt (JSON trong `user`): `{"question" (đã che bằng `mask`), "context": {"sign_date", "parts": [...], "articles": [{node_id,label}], "concepts": [{concept_id,label,node_id,about}]}, "tools": [{name,doc,params}], "steps": [{tool,args,result}]}`.
  - Một bước LLM: `{"thought","tool","args"}` hoặc `{"final": {"answer","path","law","confidence"}}`. JSON hỏng → nhắc lại 1 lần (`steps` thêm `{"error": "..."}`), hỏng lần 2 → `cannot`.
  - Hậu kiểm: node trong `path` phải xuất hiện trong kết quả công cụ đã gọi; mỗi cặp liền kề `view.path(a, b, max_hops=1)` khác None → nếu sai: `partial` + `"đường đi có nút/cạnh không có trong đồ thị"`. `confidence == "answer"` mà không có bước `check_concept` và câu trả lời nói đúng/sai luật (từ khóa `đúng luật|trái luật|vi phạm|hợp pháp`) → `partial` + `"kết luận pháp lý chưa qua bộ kiểm luật"`. Hết `max_steps` → một lượt với `"force_final": true`, kết quả đánh `partial`.
  - `answer` mở che bằng `unmask_payload` với `mask`; `path` mỗi phần tử `{"node_id","label","text"[:160]}`; `stats = {"steps","llm_calls","backend": view.backend}`.

- [ ] **Step 1: Failing tests** — `ScriptAgentLLM` trả lần lượt: `find_concept(probation.pay)` → `find_path(<đơn vị thử việc>, c1:p0.d2@1)` → `contract_facts(base_salary_vnd)` → `check_concept(probation.pay)` → `final` với `path=[<đơn vị thử việc>, "c1:p0.d2@1"]`, answer "12.750.000 đồng/tháng".

```python
def test_demo_question_answers_with_path(): 
    a = agent.ask("Lúc thử việc tôi được trả bao nhiêu?")
    assert a.confidence == "answer" and "12.750.000" in a.answer
    assert [p["node_id"] for p in a.path][-1] == "c1:p0.d2@1" and len(a.trace) == 4

def test_invented_path_downgrades(): ...      # final.path chứa "c1:p0.d99@1" -> partial + warning
def test_legal_claim_without_check_downgrades(): ...  # final "đúng luật" không gọi check_concept -> partial
def test_bad_json_twice_gives_cannot(): ...
def test_step_limit_forces_final_partial(): ... # max_steps=2, LLM chỉ gọi tool -> lượt force_final -> partial
def test_pii_masked_in_payload_and_unmasked_in_answer(): ... # câu hỏi chứa tên người lao động -> payload có "[HD_", answer có lại tên
```

- [ ] **Step 2:** chạy → FAIL. **Step 3:** cài. **Step 4:** `uv run pytest tests/test_contract_graph_agent.py tests/test_contracts_graph_build.py -q` → PASS.
- [ ] **Step 5: Commit** `feat(team-4.2): read-only graph agent answering with a traversal path`

### Task 8: Script và lần chạy thật

**Files:**
- Create: `scripts/ask_contract_graph.py`, `docs/superpowers/notes/2026-11-16-contract-graph-agent-first-run.md`
- Modify: `src/rag/config.py` + `.env.example` (`CONTRACT_AGENT_MODEL`, mặc định rỗng = LLM của app), `src/rag/bridge/llm.py` (thêm `contract_agent_llm(settings, cache)` cùng mẫu `concept_tag_llm`)

**Interfaces:**
- Consumes: mọi thứ ở trên; dựng hợp đồng như `scripts/check_contract_concepts.py:69-79`.
- Produces: `uv run python scripts/ask_contract_graph.py <file hợp đồng> "<câu hỏi>" [--trace] [--max-steps 8]` — chạy `check_contract` (để có oplog khái niệm + dữ kiện), mở view qua `api._graph()`, dựng tools + agent, in JSON `{answer, confidence, path, law, warnings, stats}` và vết khi `--trace`.

- [ ] **Step 1:** test khói `tests/test_ask_contract_graph_script.py`: gọi `main()` với LLM giả (monkeypatch `server.get_pipeline`) trên trang demo → đầu ra có khóa `answer`, `path`, `stats.backend`.
- [ ] **Step 2:** cài script + config; test PASS.
- [ ] **Step 3:** chạy thật: `uv run python scripts/ask_contract_graph.py ../../data/team-4.2/contracts_demo/hdld_tvpl_2025_filled.txt "Lúc thử việc tôi được trả bao nhiêu?" --trace` (một lần với Neo4j nếu có, một lần `CONTRACT_GRAPH=0`).
- [ ] **Step 4:** ghi note: câu trả lời, đường đi, số bước, backend, chỗ agent đi sai (nếu có), so với kịch bản slide.
- [ ] **Step 5:** `uv run pytest tests -q` → toàn bộ PASS (ghi số test skip).
- [ ] **Step 6: Commit** `feat(team-4.2): ask_contract_graph script and first real run`
