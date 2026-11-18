# Đồ thị hợp đồng làm nguồn thao tác chính: lớp đọc, bộ công cụ, agent chỉ đọc

Ngày: 2026-11-16 · Phạm vi: phần A của lộ trình trong deck "Pipeline hỏi đáp hợp đồng" (slide Rào chắn): bước 1–3.

## 1. Mục đích

Hôm nay đồ thị hợp đồng chỉ được **ghi ra** (Neo4j), còn mọi thao tác đọc đi đường khác: bộ kiểm luật
(`bridge/check.py`) dựng bảng dữ kiện từ `contract.facts` và oplog; Think hợp đồng tìm từ khóa trên văn bản.
Mục tiêu: mọi thao tác đọc phía hợp đồng đi qua đồ thị, để agent trả lời bằng cách **đi theo quan hệ** và trả
**đường đi** làm lời giải thích.

Thành công = câu demo "Lúc thử việc tôi được trả bao nhiêu?" trên `hdld_tvpl_2025_filled` được agent trả lời
12.750.000 đồng/tháng kèm đường đi Điều 6 → Điều 2 → (Phụ lục 2 sửa Điều 2 từ 01/07/2025, không áp dụng cho
thử việc) → căn cứ BLLĐ 2019 Điều 26 tại 02/01/2025; và bộ kiểm luật cho cùng kết quả như hôm nay khi đọc từ đồ thị.

## 2. Mục tiêu, ngoài mục tiêu, phản mục tiêu

Mục tiêu:
- G1. Giao diện đọc `ContractGraphView`, hai bản chạy: bộ nhớ (từ `GraphBuild`) và Neo4j. Cùng bộ test cho cả hai.
- G2. Đồ thị mang đủ dữ kiện để kiểm luật: nút `ContractFact`, cạnh `AMENDS` (phụ lục sửa điều khoản).
- G3. Bộ kiểm luật dựng bảng dữ kiện **chỉ từ `ContractGraphView`**.
- G4. Bộ công cụ có kiểu, chỉ đọc, luôn giới hạn trong một hợp đồng.
- G5. Agent chỉ đọc: vòng lặp gọi công cụ, tối đa N bước, ghi vết, trả lời kèm đường đi.

Ngoài mục tiêu (đợt sau): đề xuất cạnh và hàng chờ duyệt (bước 4); bộ đo so với truy vấn viết sẵn (bước 5);
lớp `Concept`/`ANCHORED_IN` bên luật (Huy); giao diện web cho agent; thay Think hợp đồng hiện có.

Phản mục tiêu (làm thì coi như hỏng dù chạy được):
- Agent ghi bất cứ gì vào đồ thị / oplog, hoặc chạy Cypher không qua rào chắn §5.8 (sửa 2026-11-16: trước đây
  cấm hẳn việc agent tự viết Cypher; người dùng quyết định thêm Text2Cypher có rào chắn).
- Neo4j trở thành bắt buộc: không có Neo4j thì kiểm luật và agent phải chạy y như cũ trên bản bộ nhớ.
- Ghép thực thể bằng LLM; cạnh `AMENDS` sinh bằng LLM.
- Kết luận đúng/sai luật do agent tự suy ra thay vì lấy từ bộ kiểm luật.
- Hai bản chạy cho kết quả khác nhau trên cùng bản dựng.

## 3. Ràng buộc có sẵn

- Oplog là nguồn sự thật; đồ thị dựng lại tất định từ file + oplog (`build_graph`), Neo4j chỉ giữ bản công bố.
- Lược đồ kiểm bởi `validate()` (miền/đích cạnh, PII, int64). Văn bản trên đồ thị đã che PII (`MaskState("HD_")`).
- `CONTRACT_GRAPH=1` mới bật Neo4j; công bố lỗi không làm hỏng API (`ContractGraphService`).
- LLM của app chỉ có `complete(system, user) -> str` (không có tool-calling gốc) → agent dùng JSON từng bước.
- Phía luật đọc qua `LegalGraph` (text_at, changes, guidance, references, applicable) và `AnchorLawBasis`.

## 4. Các cách đã cân nhắc

1. **Một giao diện, hai bản chạy (bộ nhớ + Neo4j)** — đã chọn. Test nhanh không cần Neo4j, demo sống khi Neo4j sập,
   giữ `CONTRACT_GRAPH` là tùy chọn. Giá: mỗi hàm viết hai lần (khoảng 6 hàm nhỏ); bù bằng bộ test chung.
2. Chỉ Neo4j: gọn, nhưng kiểm luật/test đều phụ thuộc Neo4j. Loại.
3. networkx từ bản dựng: thêm một đồ thị song song dễ lệch, bỏ phí Neo4j. Loại.

Người dùng chọn cách 1 (2026-11-16).

## 5. Thiết kế

### 5.1 Lược đồ v3 (`contracts/graph/schema.json`)

Thêm:

| Thành phần | Mô tả |
|---|---|
| Nút `ContractFact` | `node_id = {cid}:fact:{op_id}`; `name` (khóa `_CONTRACT_MAP`, vd. `base_salary_vnd`), `value`, `unit`, `quote` (đã che), `op_id`, `source = "contract"` |
| `HAS_FACT` | Contract → ContractFact |
| `EVIDENCE` | ContractFact → Unit (đơn vị chứa câu trích) |
| `AMENDS` | Unit → Unit; `valid_from` (ISO hoặc null), `raw` (câu sửa đổi), `kind` (`modify` / `supplement`) |

`schema_version` lên "3" → `build_id` đổi, lần công bố kế tiếp thay toàn bộ (đúng cơ chế hiện có).

### 5.2 Dữ kiện cấp hợp đồng vào oplog

Sau `extract_facts`, mỗi ứng viên chuẩn hóa được qua `_CONTRACT_MAP` sinh một `machine_op` ASSERT
`{"kind": "fact", "name", "value", "unit"}`, `source_uid` = uid câu trích, `quote` = câu trích, origin `llm`,
status `auto_accepted` (câu trích đã qua `quote_ok`). Mã op là băm nội dung nên chạy lại không nhân bản.
`build_graph` dựng `ContractFact` + `HAS_FACT` + `EVIDENCE` từ các op này (cạnh với `_concept_layer`).
`sign_date` vẫn là `SET_FIELD` trên nút Contract như hiện tại.

### 5.3 Cạnh `AMENDS` bằng quy tắc (module mới `contracts/amendments.py`, hàm thuần trên `ContractDoc`)

Với mỗi đơn vị thuộc phần không phải hợp đồng chính (`part_id != "p0"`):
- văn bản riêng có động từ sửa đổi (`sửa đổi|điều chỉnh|thay đổi|thay thế|bổ sung` — dùng chung mẫu với
  `facts_map._AMEND`, chuyển mẫu về một chỗ) **và**
- có `CrossRef` kind `internal` trỏ vào `p0` (xrefs đã phân giải "Điều 2 Hợp đồng lao động" về `p0.d2`)
→ cạnh `AMENDS(đơn vị phụ lục → đích)`. `kind = supplement` nếu động từ là "bổ sung", còn lại `modify`.

`valid_from`: ngày đầu tiên khớp `hiệu lực (kể )?từ ngày <ngày>` trong **cùng phần** (demo: khoản "2. Thời gian
thực hiện" → 2025-07-01); không thấy → null và ghi một vấn đề mềm vào `build.record()["notes"]` (không chặn công bố).
Mục 2 của phụ lục demo ("Bổ sung phụ cấp… Các nội dung khác của Điều 2 giữ nguyên") cũng thành `AMENDS` kind
`supplement` vì có "Điều 2".

### 5.4 `ContractGraphView` (module mới `contracts/graph/view.py`)

```python
class ContractGraphView(Protocol):
    contract_id: str
    def node(self, node_id: str) -> dict | None            # {"node_id", "label", **props}
    def find(self, label: str, **props) -> list[dict]      # khớp bằng nhau trên props; label trong SCHEMA
    def search_units(self, text: str, limit: int = 8) -> list[dict]  # chứa chuỗi (casefold, bỏ dấu cách thừa)
    def neighbors(self, node_id: str, *, rel_types: Sequence[str] | None = None,
                  direction: Literal["out", "in", "both"] = "both") -> list[Hop]
    def path(self, src: str, dst: str, *, rel_types=None, max_hops: int = 4) -> list[Hop] | None  # ngắn nhất
    def subgraph(self, node_id: str, *, hops: int = 1, rel_types=None, limit: int = 60) -> Subgraph
```

`Hop = {"rel": type, "dir": "out"|"in", "props": {...}, "node": {...}}`; `Subgraph = {"nodes": [...], "edges": [...]}`.

- `MemoryGraphView(build: GraphBuild)`: chỉ mục kề dựng một lần; `path` = BFS, thứ tự duyệt ổn định theo
  (rel, node_id) để kết quả tất định.
- `Neo4jGraphView(store: ContractGraphStore, contract_id)`: mọi truy vấn qua `store.run` (đọc), luôn có
  `contract_id: $cid`; `rel_types` kiểm theo `SCHEMA["relations"]` rồi mới nối vào chuỗi Cypher; `path` dùng
  `shortestPath` với `max_hops` là số nguyên đã kiểm (1..6). Khi nhiều đường ngắn nhất bằng nhau, chọn theo cùng
  quy tắc thứ tự như bản bộ nhớ (so sánh sau khi lấy `allShortestPaths`).
- Nút trả về bỏ thuộc tính `contract_id`, `build_id`; `text` cắt 600 ký tự kèm `"truncated": true`.
- `view_for(contract, service) -> ContractGraphView`: Neo4j khi `service.store` có và `current_build_id` khớp
  `build_id` vừa dựng; ngược lại bộ nhớ từ bản dựng vừa dựng. Trả kèm `backend` để ghi vào vết/báo cáo.

Bộ test chung (`tests/test_contract_graph_view.py`) chạy với fixture tham số hóa `[memory, neo4j]`; neo4j tự skip
khi không có `NEO4J_PASSWORD`/không kết nối được.

### 5.5 Kiểm luật đọc từ đồ thị (`bridge/graph_facts.py` thay chỗ dùng `contract_facts` + `build_factset`)

`factset_from_graph(view, *, day) -> FactSet`:
- `ContractFact` → dữ kiện cấp hợp đồng; nhiều giá trị khác nhau cho một tên được phân xử bằng `AMENDS`:
  giá trị B thay giá trị A khi đơn vị chứng cứ của B có cạnh `AMENDS` tới đơn vị chứng cứ của A (hoặc tới tổ tiên
  của nó). Không có cạnh → `CONFLICT` (giữ nguyên tinh thần `_resolve`, nhưng bằng cấu trúc thay vì vị trí phần).
- Ngữ nghĩa theo ngày: giá trị đang hiệu lực tại `day` (§7).
- `ConceptInstance` (+ cạnh `ABOUT`) → `present`, `evidence`, slot như `build_factset` hôm nay.
- `concept_absent`: hiện không lên đồ thị; thêm thuộc tính `absent_checked` (danh sách concept_id) trên nút Contract
  từ các ASSERT `concept_absent` để `needs_recheck` vẫn đọc được.

`check_contract` giữ nguyên trình tự, chỉ đổi chỗ đọc: sau mỗi lượt thêm op → `build_graph` (bộ nhớ, luôn) →
công bố qua `ContractGraphService` nếu bật → `view_for` → `factset_from_graph`. `report_json` thêm
`stats.graph_backend` và `stats.build_id`. `contract_facts`/`build_factset` cũ giữ lại một đợt để test so sánh
(test: trên hợp đồng demo, kết quả `evaluate` từ hai đường giống nhau, trừ chỗ §7 cố ý đổi), rồi xóa.

### 5.6 Bộ công cụ (module mới `contracts/graph/tools.py`)

Mỗi công cụ: tên, mô tả một dòng, lược đồ tham số (dict đơn giản: tên → kiểu/enums), hàm chạy. Tham số sai →
trả `{"error": "..."}` cho agent, không ném. Kết quả luôn là JSON nhỏ (≤ ~3.000 ký tự, cắt danh sách kèm `more`).

| Công cụ | Tham số | Nguồn |
|---|---|---|
| `find_units` | `text` hoặc `label` ("Điều 6", "Phụ lục 2") | view.search_units / find |
| `find_concept` | `concept_id` | view.find("ConceptInstance") + nhãn từ catalog |
| `expand` | `node_id`, `rel_types?`, `direction?` | view.neighbors |
| `find_path` | `src`, `dst`, `rel_types?`, `max_hops?` (≤6) | view.path |
| `subgraph` | `node_id`, `hops?` (≤2) | view.subgraph |
| `contract_facts` | `name?` | ContractFact + AMENDS (giá trị, chứng cứ, sửa đổi kèm `valid_from`) |
| `law_text_at` | `pid`, `day?` (mặc định ngày ký) | LegalGraph.text_at |
| `law_changes` / `law_guidance` / `law_references` | `pid`, ngày | LegalGraph |
| `concept_basis` | `concept_id`, `day?` | AnchorLawBasis |
| `check_concept` | `concept_id` | `evaluate` trên `factset_from_graph` cho một khái niệm → RuleResult |

Công cụ luật trả `{"error": "legal_graph_unavailable"}` khi không có đồ thị luật; agent vẫn trả lời được phần hợp
đồng và nói rõ thiếu căn cứ. `check_concept` không gọi LLM (không gán lại khái niệm); dùng op đã có trong oplog.

### 5.7 Agent (module mới `contracts/graph/agent.py`)

`GraphAgent(llm, tools, *, max_steps=8).ask(question) -> GraphAnswer`.

- Ngữ cảnh đầu: câu hỏi (đã che PII bằng cùng cách che của bản dựng), ngày ký, danh sách phần và nhãn Điều,
  danh sách khái niệm đã gán (concept_id, nhãn, Điều), mô tả công cụ.
- Mỗi bước LLM trả đúng một JSON: `{"thought": str, "tool": str, "args": {...}}` hoặc
  `{"final": {"answer": str, "path": [node_id, ...], "law": [pid, ...], "confidence": "answer"|"partial"|"cannot"}}`.
  Parse lỗi → nhắc lại một lần kèm lỗi; lỗi lần hai → dừng `cannot`.
- Hậu kiểm `final`: mọi `node_id` trong `path` phải đã xuất hiện trong kết quả công cụ của lượt này; liên tiếp
  trong `path` phải có cạnh (kiểm bằng `view.path(a, b, max_hops=1)`). Sai → hạ `partial` + cảnh báo, không tự sửa.
  Câu trả lời có kết luận pháp lý mà không có lần gọi `check_concept` → hạ `partial` + cảnh báo.
- Hết `max_steps` chưa có `final` → một lượt ép trả lời từ vết hiện có, đánh `partial`.
- `GraphAnswer`: answer (đã mở che), path (kèm nhãn từng nút để hiển thị), law, confidence, warnings,
  trace (mỗi bước: thought, tool, args, tóm tắt kết quả, ms), stats (bước, lời gọi LLM, backend).
- Mở che: dựng lại `MaskState("HD_")` bằng cách che lại tiêu đề phần và văn bản đơn vị theo đúng thứ tự `build_graph`
  (tách hàm `graph_mask_state(doc)` dùng chung để hai chỗ không lệch).

Chạy: `scripts/ask_contract_graph.py <contract_id|file> "<câu hỏi>" [--trace]` in câu trả lời, đường đi, vết.
Model: LLM của app (biến `CONTRACT_AGENT_MODEL` tùy chọn, cùng cơ chế OpenRouter như `concept_tag_llm`).

### 5.8 Text2Cypher có rào chắn (thêm 2026-11-16, theo yêu cầu người dùng)

Lý do: câu đếm / liệt kê / tổng hợp mà 12 công cụ có kiểu phải gọi nhiều bước (hoặc không làm được). Theo cách Neo4j
làm agent cho hợp đồng: phần lớn qua công cụ có kiểu, một phần nhỏ cho LLM viết Cypher, rào chắn nằm ngoài model.

- Công cụ `cypher_query(query)` chỉ có khi view là Neo4j (bản bộ nhớ không có Cypher; agent không thấy công cụ).
- `rag.contracts.graph.cypher.check_cypher` kiểm tĩnh trước khi chạy: chỉ đọc (cấm CREATE/MERGE/SET/DELETE/REMOVE/
  DROP/CALL/LOAD/USE/FOREACH…), chỉ nhãn / loại cạnh trong `schema.json` (không đọc đồ thị luật), mỗi MATCH neo
  `{contract_id: $cid}` ngay trong mẫu và là một đường liền (không dấu phẩy, không EXISTS{}/COUNT{}/mẫu trong biểu
  thức); MATCH bắt đầu bằng biến đã neo chỉ được khi chưa có WITH; `contract_id` chỉ so với `$cid`.
- Chạy qua `ContractGraphStore.run_read`: giao dịch đọc, thời hạn 5 s, tối đa 50 dòng (`truncated`).
- `clean_rows`: dict mang `contract_id` khác -> từ chối; bỏ `contract_id` / `build_id`.
- Từ chối / lỗi cú pháp trả `{"error"}` kèm lý do để agent sửa câu và thử lại.
- Giới hạn đã biết: giá trị vô hướng không kiểm lại được sau khi chạy (lớp chặn chính là kiểm tĩnh); `ContractFact` chứa
  mọi giá trị kể cả giá trị đã bị sửa, nên câu "giá trị tại ngày" phải qua `contract_facts` (mô tả công cụ nói rõ).
  Câu truy vấn trên nhiều hợp đồng: ngoài phạm vi.

## 6. Nghiệm thu

1. Bộ test view chung xanh trên bộ nhớ; xanh trên Neo4j khi có Neo4j.
2. `build_graph` trên hợp đồng demo: có `AMENDS(p2 khoản sửa lương → p0.d2)` với `valid_from = 2025-07-01`;
   các `ContractFact` lương 15.000.000 (Điều 2) và 17.000.000 (Phụ lục 2), % thử việc 85; `validate()` sạch.
3. `check_contract` đọc từ đồ thị cho cùng kết quả như hôm nay trên `tests/fixtures/bridge` và hợp đồng demo,
   trừ khác biệt cố ý theo §7 (ghi rõ trong test).
4. Agent với LLM giả kịch bản (test): đi `find_concept(probation.pay)` → `expand` → `find_path(Điều 6, Điều 2)`
   → `contract_facts(base_salary_vnd)` → `check_concept` → `final`; hậu kiểm đường đi đúng; đường đi bịa → `partial`.
5. Một lần chạy thật câu demo, ghi vào `docs/superpowers/notes/2026-11-1x-contract-graph-agent-first-run.md`
   (câu trả lời, đường đi, số bước, backend).
6. Không có chuỗi Cypher nào ghép từ dữ liệu agent (review + test: `rel_types` lạ → lỗi trước khi chạm Neo4j).

## 7. Quyết định về dữ kiện có sửa đổi (Q1)

Hôm nay `_resolve` lấy giá trị phụ lục bất kể ngày (lương = 17 triệu khi soát tại ngày ký). Hai cách đã cân nhắc:
(a) giá trị **đang hiệu lực tại ngày soát**; (b) giữ như hôm nay, lấy giá trị mới nhất.

**Người dùng chọn (a) (2026-11-16).** Cụ thể:
- `factset_from_graph(view, day)`: B thay A chỉ khi có `AMENDS` (§5.5) **và** `valid_from` của cạnh ≤ `day`.
  `valid_from` null → coi như hiệu lực từ ngày ký (cảnh báo trong báo cáo: "không rõ ngày hiệu lực của sửa đổi").
- Sửa đổi có `valid_from > day` không thay giá trị, mà được gắn vào `Fact` dưới dạng `later_amendments`
  (`({value, unit, uid, valid_from}, …)`, trường mới của `Fact`, mặc định rỗng); `report_markdown` in thêm dòng
  "từ <ngày>: <giá trị> [uid]". `amended_from` giữ nghĩa cũ (giá trị cũ đã bị thay tại `day`).
- Ngày soát mặc định = ngày ký, như hôm nay. Soát lại tại từng mốc sửa đổi (vd. lương tối thiểu từ 01/07/2025):
  đợt sau.
- Test so sánh §6-3: khác biệt cố ý duy nhất là các dữ kiện có sửa đổi sau ngày ký (demo: `base_salary_vnd`
  15.000.000 thay vì 17.000.000, kéo theo kết quả rule dùng nó).

## 8. Để người làm tự quyết

Tên hàm/biến nội bộ; định dạng tóm tắt kết quả công cụ trong vết; cách viết prompt agent; ngưỡng cắt văn bản;
có tách `Neo4jGraphView` thành file riêng hay không.

## 9. Thứ tự làm

1. Lược đồ v3 + `amendments.py` + `ContractFact` từ oplog (G2), test dựng trên demo.
2. `ContractGraphView` hai bản + bộ test chung (G1).
3. `factset_from_graph` + nối vào `check_contract`, test so sánh (G3).
4. Bộ công cụ (G4). 5. Agent + script + lần chạy thật (G5).
