# Đồ thị corpus luật — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng đồ thị luật có phiên bản trong Neo4j từ snapshot kho luật, trả lời năm câu hỏi ở spec §1.

**Architecture:** Kho `rag.legal` (SQLite) là nguồn sự thật. Gói mới `rag.legal.graph` dựng nút / cạnh thuần Python
từ một snapshot (tất định), kiểm tra, rồi ghi Neo4j dưới `build_id` mới và đổi con trỏ `LGMeta`. Lớp đọc
`LegalGraph` chạy trên Neo4j. Vector / BM25 không đổi.

**Tech Stack:** Python 3.12, neo4j driver 5.28 (extra `graph`), pytest. Không LLM, không embedding.

**Spec:** `docs/superpowers/specs/2026-11-13-legal-corpus-graph-design.md`

## Global Constraints

- Không sửa `parse_structure` theo cách làm đổi lời văn điều khoản đã công bố.
- Đồ thị là dữ liệu dẫn xuất: không ghi ngược vào kho.
- Dẫn chiếu không giải được: không tạo cạnh, ghi `unresolved_refs` kèm lý do (`doc_not_in_store`,
  `provision_not_found`, `ambiguous_law`).
- Nhãn chung `LGNode`; nhãn và quan hệ hợp lệ chỉ lấy từ `src/rag/legal/graph/schema.json`.
- Khoảng hiệu lực nửa mở `[valid_from, valid_to)`.
- Bật bằng `LEGAL_GRAPH=1`; dùng lại `NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD / NEO4J_DATABASE`.
- Neo4j sập không được làm hỏng việc công bố snapshot kho luật.
- Chạy test: `uv run --no-sync python -m pytest <file> -q -p no:cacheprovider` từ `app/team-4.2`. Không commit `uv.lock`.

## Review Focus

- Văn bản hết hiệu lực toàn bộ nhưng không có văn bản thay thế trong kho: `text_at` phải trả "không có hiệu lực".
- Dẫn chiếu tên luật không số hiệu tới một họ có nhiều đời (BLLĐ 2012 / 2019): phải chọn theo ngày của phiên bản nguồn.
- Dẫn chiếu dạng danh sách ("khoản 1, 2 và 3 Điều 20", "Điều 21 và Điều 22"): mỗi đích một cạnh.
- Phụ lục biểu mẫu chứa "Điều 1." đánh số lại: không thành `Provision`.
- Công bố bị ngắt giữa chừng: người đọc vẫn thấy build cũ nguyên vẹn.

---

### Task 1: Kho — thay thế / bãi bỏ giữa văn bản dưới luật

**Files:** Modify `src/rag/legal/effectivity.py`, `src/rag/legal/discovery.py`; Test `tests/test_legal_effectivity.py`, `tests/test_legal_discovery.py`.

**Interfaces — Produces:** `parse_effectivity` nhận "Nghị định này / Thông tư này có hiệu lực …" và câu
"Nghị định số 74/2024/NĐ-CP … hết hiệu lực …" (`RepealStatement.target_name` bắt đầu bằng loại văn bản,
`target_number` có dấu gạch nối). `discover` tải văn bản bị thay thế theo đúng loại và thêm quan hệ `THAY_THE`.

- [ ] Test: Điều hiệu lực "Nghị định này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2026.\nNghị định số
  74/2024/NĐ-CP ngày 30 tháng 6 năm 2024 của Chính phủ quy định mức lương tối thiểu … hết hiệu lực kể từ ngày
  Nghị định này có hiệu lực thi hành." → `default_from == 2026-01-01`, một repeal `("Nghị định", "74/2024/NĐ-CP", 2026-01-01)`.
- [ ] Test: các ca Luật hiện có không đổi (chạy cả `tests/test_legal_effectivity.py`).
- [ ] Sửa regex loại văn bản và số hiệu; `discovery` lấy loại từ `rep.target_name`.
- [ ] Chạy toàn bộ test `legal`; commit.

**Ruling:** "nghị định sửa đổi nghị định" (chỉ dẫn sửa từng điều khoản) cần mở rộng `directives.py`, để lại sau
Task 8 nếu còn thời gian; ghi vào notes. Giá nếu sai: NĐ 145/2020 vẫn `needs_review` do hết hiệu lực một phần.

### Task 2: Kho — đóng phiên bản theo trạng thái vbpl

**Files:** Modify `src/rag/legal/service.py` (`_flag_known_gaps`); Test `tests/test_legal_service_gaps.py` (mới).

- [ ] Test: văn bản `eff_status="Hết hiệu lực toàn bộ"`, `vbpl_effective_to=D`, không có REPEAL áp dụng → mọi
  phiên bản mở được đóng tại `D`, `notes` chứa `note:closed_by_vbpl_status`; phiên bản bắt đầu từ `D` trở đi bị bỏ.
- [ ] Test: có REPEAL áp dụng → không đổi.
- [ ] Cài; chạy test `legal`; commit.

### Task 3: Dựng phần cấu trúc (thuần Python)

**Files:** Create `src/rag/legal/graph/__init__.py`, `schema.json`, `build.py`; Test `tests/test_legal_graph_build.py`.

**Interfaces — Produces:**
```python
GRAPH_VERSION = "1"
@dataclass(frozen=True) class Node: node_id: str; label: str; props: dict
@dataclass(frozen=True) class Edge: type: str; src: str; dst: str; props: dict
@dataclass(frozen=True) class LegalGraphBuild: build_id: str; snapshot_id: str; nodes: tuple; edges: tuple; report: dict
def build_legal_graph(store: LegalStore, snapshot_id: str, *, text_of: Callable[[LegalDocument], str]) -> LegalGraphBuild
def validate(build: LegalGraphBuild, store: LegalStore) -> list[str]
```
`node_id`: LawDoc = document_key; Provision = provision_id; ProvisionVersion = `pid@YYYY-MM-DD`; Appendix = `key#pl<n>`.
Chỉ `article / clause / point` thành `Provision`; `article_title` → `title`, `clause_lead_in` → `lead_in` trên
phiên bản cùng `valid_from` gần nhất của Điều / khoản. Ngày lưu dạng chuỗi ISO.

- [ ] Test trên kho tạm 2 văn bản (một luật có sửa đổi): số nút theo nhãn, `HAS_PROVISION / CHILD_OF /
  HAS_VERSION`, quan hệ văn bản (`AMENDS`…) từ `DocumentRelation` đã `confirmed`, `CHANGED_BY` từ `source_operations`.
- [ ] Test `validate`: trùng khóa, cạnh thiếu đầu, phiên bản chồng khoảng, nhãn ngoài schema → có lỗi.
- [ ] Test tất định: dựng hai lần → cùng `build_id`, cùng nút, cùng cạnh.
- [ ] Cài; commit.

### Task 4: `GUIDES` và `BASED_ON`

**Files:** Create `src/rag/legal/graph/relations.py`; Modify `build.py`; Test `tests/test_legal_graph_relations.py`.

**Interfaces — Produces:** `doc_relations(doc, text, documents) -> list[Edge]`.

- [ ] Test: tiêu đề "Nghị định … Quy định chi tiết và hướng dẫn thi hành một số điều của Bộ luật Lao động về …"
  → `GUIDES` tới BLLĐ hiệu lực tại ngày ban hành; dòng "Căn cứ Bộ luật Lao động ngày 20 tháng 11 năm 2019;" →
  `BASED_ON`; "Căn cứ Luật Tổ chức Chính phủ …" (không có trong kho) → không cạnh.
- [ ] Cài; commit.

### Task 5: Dẫn chiếu `REFERS_TO`

**Files:** Create `src/rag/legal/graph/refs.py`; Modify `build.py`; Test `tests/test_legal_graph_refs.py`.

**Interfaces — Produces:**
```python
@dataclass(frozen=True) class Ref: raw: str; offset: int; addresses: tuple[Address | None, ...]; doc_kind: str | None; doc_name: str | None; doc_number: str | None; self_ref: str | None
def find_refs(text: str) -> list[Ref]
def resolve(ref, *, source_doc, source_address, valid_from, documents, provision_ids, guided_key, in_scope_article) -> list[tuple[str | None, str | None]]   # (target node_id, lý do không giải được)
```
- [ ] Test `find_refs` cho: "điểm a khoản 1 Điều 35", "khoản 1, 2 và 3 Điều 20", "Điều 21 và Điều 22",
  "khoản 2 Điều này", "Điều 5 của Luật này", "khoản 1 Điều 21 của Bộ luật Lao động",
  "Nghị định số 122/2020/NĐ-CP", "điểm b khoản này".
- [ ] Test `resolve` theo năm quy tắc spec §5.2, gồm họ luật nhiều đời và ba lý do không giải được.
- [ ] Test: `raw` nằm đúng `offset` trong text nguồn; `kind=details` ở Điều phạm vi điều chỉnh của văn bản có một `GUIDES`.
- [ ] Cài; nối vào `build.py` (cạnh + `unresolved_refs` + thống kê trong `report`); commit.

### Task 6: Phụ lục

**Files:** Create `src/rag/legal/graph/appendix.py`; Modify `build.py`; Test `tests/test_legal_graph_appendix.py`.

**Interfaces — Produces:** `split_appendices(text: str) -> tuple[int | None, list[AppendixPart]]` (vị trí hết phần
thân; `AppendixPart(number, title, kind, text, span)`).

- [ ] Test: văn bản có khối chữ ký rồi "PHỤ LỤC\nDANH MỤC ĐỊA BÀN …" → một phụ lục `list`; "Mẫu số 01" chứa
  "Điều 1." → `form`; văn bản không phụ lục → `(None, [])`.
- [ ] Cài; `build.py` thêm nút `Appendix`, `HAS_APPENDIX`, `body_end_offset` trên phiên bản Điều cuối; commit.

### Task 7: Ghi Neo4j bằng con trỏ, service, CLI

**Files:** Create `src/rag/legal/graph/neo4j_store.py`, `service.py`; Modify `src/rag/legal/__main__.py`,
`.env.example`; Test `tests/test_legal_graph_neo4j.py` (bỏ qua khi thiếu `NEO4J_TEST_URI`).

**Interfaces — Produces:**
```python
def legal_graph_config_from_env(env=os.environ) -> GraphConfig | None      # None khi LEGAL_GRAPH != "1"
class LegalGraphStore: ensure_schema(); publish(build, batch=2000); current() -> dict | None; run(query, **params); close()
```
`publish`: ghi nút / cạnh mang `build_id` mới theo lô → `MERGE (m:LGMeta {id:'legal'}) SET m.current_build,
m.snapshot_id, m.published_at` → xóa `LGNode` có `build_id` khác theo lô. CLI: `python -m rag.legal graph build|check`.

- [ ] Test live: publish build A rồi B → chỉ còn nút của B, `current()` trỏ B; ngắt trước bước đổi con trỏ
  (ném lỗi sau khi ghi nút) → `current()` vẫn là A và truy vấn theo `current_build` chỉ thấy A.
- [ ] Cài; commit.

### Task 8: Lớp truy vấn và nghiệm thu

**Files:** Create `src/rag/legal/graph/query.py`; Test `tests/test_legal_graph_query.py` (live);
Create `docs/superpowers/notes/2026-11-13-legal-corpus-graph-check.md`.

**Interfaces — Produces:** `LegalGraph(store)` với `text_at(pid, day)`, `changes(pid, from_day, to_day)`,
`guidance(pid, day)`, `references(pid, day, direction="out")`, `applicable(document_key, day)`,
`appendices(document_key)`; mỗi kết quả kèm `citation` (số hiệu, nhãn điều khoản, khoảng hiệu lực, trạng thái).

- [ ] Test live trên đồ thị nhỏ dựng từ kho tạm: năm phương thức, gồm "không có hiệu lực" (chưa ban hành / đã bãi bỏ).
- [ ] Crawl lại, dựng đồ thị thật, chạy các ca nghiệm thu spec §8; ghi số đo (tỉ lệ giải dẫn chiếu theo lý do,
  văn bản ngoài kho bị dẫn chiếu nhiều nhất) vào notes. Mẫu 100 dẫn chiếu kiểm tay: xuất file cho người kiểm.
- [ ] Chạy toàn bộ test; commit.
