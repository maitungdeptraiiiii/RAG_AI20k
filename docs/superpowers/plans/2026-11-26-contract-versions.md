# Bổ sung văn bản vào hợp đồng (phiên bản + đối chiếu) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trên Contract Studio, bổ sung phụ lục hoặc hợp đồng khác vào hợp đồng đã phân tích, tạo phiên bản mới và đối chiếu với phiên bản trước.

**Architecture:** Mỗi phiên bản là một `Contract` riêng mang trường `lineage`. Phụ lục: sao chép bản cha, nối trang, LLM chỉ trích và gán khái niệm trên phần mới, rồi chạy `check_contract`. Hợp đồng khác: phân tích thường, rồi chạy rule liên văn bản bằng `Dossier` trong bộ nhớ trên dữ kiện đã lưu.

**Tech Stack:** Python 3.12, Starlette, pytest (LLM giả); React 19 + TypeScript + Vite.

**Spec:** `docs/superpowers/specs/2026-11-26-contract-versions-design.md`

Mọi đường dẫn dưới đây tính từ `app/team-4.2/` (trừ dòng **Spec**, tính từ gốc repo). Chạy test: `PYTHONPATH=src python -m pytest <file> -q`.

## Global Constraints

- Phiên bản cũ không bao giờ bị sửa (dữ kiện, nhật ký thao tác, kết quả đã lưu).
- Mục không liên quan văn bản mới không đổi kết quả do LLM đọc lại: phần cũ không được trích hay gán lại.
- Chỉ bổ sung vào phiên bản mới nhất và đã có `concept_check`; chỉ so với bản cha.
- Lỗi giữa chừng: không có phiên bản `ready` mới; bản nháp không được lưu đĩa.
- "Trước" và "sau" đánh giá cùng một ngày. Phụ lục: mặc định ngày hiệu lực của phụ lục, không có thì bắt buộc nhập. Hợp đồng khác: mặc định hôm nay. Sửa được. Không đổi `sign_date`.
- Hợp đồng lưu trước đây (không có `lineage`) = version 1.
- Test dùng LLM giả; không gọi mạng.
- Nhánh đang có thay đổi chưa commit của việc khác: chỉ `git add` đúng file của task; hỏi người dùng trước commit đầu tiên.

## Review Focus

1. Ngày đánh giá sớm hơn ngày hiệu lực phụ lục -> giá trị cũ vẫn áp dụng, kể cả slot khái niệm (Task 2).
2. Phụ lục đưa giá trị khác nhưng không có câu "sửa đổi" -> `CONFLICT`, hiện thành mục đổi, không tự chọn (Task 2).
3. Phụ lục lặp lại đúng giá trị cũ -> đối chiếu rỗng, không có `CONFLICT` (Task 4).
4. LLM lỗi khi chuẩn bị hoặc phân tích -> không có phiên bản mới, bản cha nguyên vẹn (Task 6).
5. Bấm bổ sung vào bản không phải mới nhất, hoặc `same_party=false` -> bị từ chối, không tạo gì (Task 6).

---

### Task 1: Lưu `lineage` và liệt kê họ phiên bản

**Files:** Modify `src/rag/contracts/models.py`, `src/rag/contracts/store.py`; Test `tests/test_contracts_versions_store.py`

**Interfaces — Produces:**
- `Contract.lineage: dict[str, Any]` (mặc định `{}`), khóa: `family_id, version, parent_id, status ("draft"|"ready"|"member"), linked: list[str], addition: dict, compare: dict`.
- `family_id(c: Contract) -> str` (`lineage["family_id"]` hoặc `contract_id`); `version_of(c) -> int` (mặc định 1) — đặt trong `models.py`.
- `ContractStore.family(fid: str) -> list[Contract]`: bản gốc và các bản `ready`, tăng dần theo version, gộp cả bộ nhớ và đĩa; không gồm `draft`, `member`.

- [ ] **Step 1: Test**
```python
def test_lineage_round_trip_and_family(tmp_path):
    s = ContractStore(tmp_path)
    root = _contract("a" * 24, persist=True)
    v2 = _contract("b" * 24, persist=True, lineage={"family_id": "a" * 24, "version": 2, "parent_id": "a" * 24, "status": "ready"})
    draft = _contract("c" * 24, persist=False, lineage={"family_id": "a" * 24, "version": 3, "status": "draft"})
    for c in (root, v2, draft):
        s.add(c, original=b"x", suffix=".txt")
    fresh = ContractStore(tmp_path)
    assert [c.contract_id for c in fresh.family("a" * 24)] == ["a" * 24, "b" * 24]
    assert fresh.get("b" * 24).lineage == v2.lineage
    assert version_of(fresh.get("a" * 24)) == 1
```
`_contract(cid, persist, lineage=None)` = `Contract(cid, "x.txt", persist, datetime.now(timezone.utc), "t", [], 0, lineage=lineage or {})`.
- [ ] **Step 2:** chạy, mong FAIL (`unexpected keyword argument 'lineage'`).
- [ ] **Step 3:** Thêm trường vào `Contract`, vào `_dump`/`_load`, viết `family`. File hỏng trong thư mục kho bị bỏ qua.
- [ ] **Step 4:** chạy test mới + `tests/test_contracts_parse_store.py`: PASS.
- [ ] **Step 5:** commit `feat(team-4.2): hợp đồng có lineage phiên bản`.

### Task 2: Slot khái niệm theo cùng quy tắc sửa đổi của phụ lục

Hiện `factset_from_graph` chỉ áp cạnh `AMENDS` + ngày hiệu lực cho nút `ContractFact`; slot khái niệm khác giá trị giữa hai phần thành `CONFLICT`.

**Files:** Modify `src/rag/bridge/graph_facts.py`; Test thêm vào `tests/test_bridge_graph_facts.py`

**Interfaces — Produces:** chữ ký `factset_from_graph` không đổi. Giá trị từ `ContractFact` và slot khái niệm gom chung theo tên rồi giải một lần bằng logic của `_contract_level` (tách thành `_resolve_group(name, group, amends, day, sign_date, warnings) -> Fact | _Conflict | None`).

- [ ] **Step 1: Test.** Dựng hợp đồng 2 phần theo kiểu helper sẵn có trong file: `p0` Điều 1 lương thử việc 80%; `p1` "Điều chỉnh Điều 1: ... 85% ... có hiệu lực từ ngày 01/06/2025"; thao tác ASSERT `concept` ở cả hai phần cùng tên slot `s`.
```python
assert factset(day=date(2025, 5, 1)).facts[s].value == 80      # chưa hiệu lực
f = factset(day=date(2025, 7, 1)).facts[s]
assert f.value == 85 and f.amended_from[0]["value"] == 80
assert factset_without_amend_wording(day=date(2025, 7, 1)).facts[s] is CONFLICT
```
- [ ] **Step 2:** chạy, mong FAIL (`CONFLICT` ở cả hai ngày).
- [ ] **Step 3:** Refactor như Interfaces. Slot không có `uid` coi như giá trị gốc.
- [ ] **Step 4:** chạy `test_bridge_graph_facts.py test_bridge_check.py test_bridge_check_graph_parity.py test_contracts_amendments.py`: PASS.
- [ ] **Step 5:** commit `fix(team-4.2): phụ lục sửa được giá trị slot khái niệm theo ngày hiệu lực`.

### Task 3: Chỉ đọc phần mới, và đánh giá theo ngày chỉ định

**Files:** Modify `src/rag/contracts/facts.py`, `src/rag/bridge/tagger.py`, `src/rag/bridge/check.py`; Test `tests/test_check_partial.py`

**Interfaces — Produces:**
- `extract_part_facts(llm, contract, part_id: str, *, extra_fields: Sequence[dict] = (), on_event=None) -> list[str]`: chỉ đọc đơn vị có `uid` bắt đầu `f"{part_id}."`; gộp ứng viên trường vào `facts["candidates"]`, gộp bên; **không** thêm ứng viên `type`, `sign_date`, `effective_date` và không đổi `contract.sign_date`; ghi chúng vào `facts["appendix_dates"][part_id] = {"sign_date", "effective_date"}`; trả các khóa trường có giá trị mới khác giá trị cũ. Không lô nào đọc được -> `ContractAIError`, không ghi gì.
- `tag_contract(..., units: Sequence[str] | None = None)`.
- `check_contract(..., only_units: Sequence[str] | None = None, day: date | None = None)`. `only_units`: gán khái niệm chỉ trên các đơn vị đó; `party_ops`/`fact_ops` chỉ nhận ứng viên có `unit` thuộc các đơn vị đó. `day`: thay ngày đánh giá (`sign_date` vẫn truyền vào `factset_from_graph`).

- [ ] **Step 1: Test** (dùng `ScriptLLM`, `PAGES` từ `tests/test_bridge_check.py`, thêm trang phụ lục):
```python
extract_part_facts(llm, c, "p1")
sent = [u["uid"] for _, p in llm.calls for u in p["units"]]
assert sent and all(u.startswith("p1.") for u in sent)
assert c.sign_date == date(2025, 1, 2) and c.facts["candidates"]["sign_date"] == before["sign_date"]

report = check_contract(llm2, c, ..., only_units=new_uids, day=date(2025, 7, 1))
assert report.day == date(2025, 7, 1)
assert all(u["uid"].startswith("p1.") for s, p in llm2.calls if s.startswith(TAG_PROMPT[:40]) for u in p["units"])
assert [o for o in old_ops if o not in c.oplog.all()] == []
```
- [ ] **Step 2:** chạy, mong FAIL.
- [ ] **Step 3:** Cài đặt; dùng `make_batches(contract, units=...)`.
- [ ] **Step 4:** chạy test mới + `test_contracts_facts.py test_bridge_tagger.py test_bridge_check.py test_bridge_recheck.py`: PASS.
- [ ] **Step 5:** commit `feat(team-4.2): trích và gán khái niệm chỉ trên phần mới, soát theo ngày chỉ định`.

### Task 4: Nghiệp vụ phiên bản phụ lục và đối chiếu

**Files:** Create `src/rag/contracts/versions.py`; Test `tests/test_contracts_versions.py`

**Interfaces — Consumes:** Task 1, 3. **Produces:**
- `copy_for_version(parent: Contract, new_id: str, at: datetime) -> Contract`: deepcopy; `lineage` `status="draft"`, `version = version_of(parent)+1`; `persist=False`; `oplog` giữ `op_id`, đổi `contract_id`; `concept_check=None`; `linked` chép từ cha.
- `append_appendix(c, texts: list[PageText], data: bytes, title: str, at: datetime) -> str`: nối trang (đánh số tiếp), thay `SET_LAYOUT` = bố cục hiệu lực + một `PartSpec(f"p{n}", "appendix", title, len(assemble(trang cũ).text) + 2, None)`, cập nhật `text, pages, file_checksum, doc, units, total_units`; trả `part_id`.
- `effective_date(c, part_id: str) -> date | None`: `valid_from` đầu tiên của `find_amendments(c.doc)` có nguồn thuộc phần đó; không có thì `appendix_dates[part_id]["effective_date"]`.
- `reopen_changed_fields(c, keys: list[str]) -> None`: dựng lại `oplog` bỏ thao tác người `SET_FIELD` đích `fact:<key>` (hoặc `<key>` nếu đích trực tiếp, trừ `party`, `sign_date`, `type`).
- `compare_results(before: list[dict], after: list[dict]) -> dict` = `{"changed": [{"key","before","after"}], "added": [dict], "removed": [dict], "unchanged": int}`; khóa `f"{concept_id}/{rule_id}@{object or ''}"`; "đổi" khi khác `status`, `finding`, `law_values` hoặc `facts_used` giá trị/đơn vị (khác trích đoạn không tính).

- [ ] **Step 1: Test**
```python
v = copy_for_version(parent, "v" * 24, NOW); pid = append_appendix(v, APPENDIX, b"pl", "PHỤ LỤC 01", NOW)
assert pid == "p1"
assert [(u.uid, u.text.strip()) for u in v.units if u.uid.startswith("p0.")] == [(u.uid, u.text.strip()) for u in parent.units]
assert any(u.uid.startswith("p1.") for u in v.units)
assert parent_snapshot_before == _dump(parent)
assert effective_date(v, "p1") == date(2025, 6, 1)

r = {"concept_id": "a", "rule_id": "r1", "object": None, "status": "FAIL", "finding": "violation", "law_values": {}, "facts_used": {}, "evidence": ()}
assert compare_results([r], [r | {"evidence": ({"uid": "p1.d1"},)}]) == {"changed": [], "added": [], "removed": [], "unchanged": 1}
assert compare_results([r], [r | {"status": "PASS", "finding": "ok"}])["changed"][0]["key"] == "a/r1@"
assert compare_results([r], [])["removed"] == [r]
```
Thêm: soát cha và bản mới (phụ lục chỉ lặp lại lương cũ) cùng `day` bằng LLM giả -> `changed == []` và không kết quả nào có `reasons` chứa conflict.
- [ ] **Step 2:** FAIL (module chưa có). **Step 3:** cài đặt. **Step 4:** PASS. **Step 5:** commit `feat(team-4.2): tạo phiên bản phụ lục và đối chiếu kết quả`.

### Task 5: Quy tắc liên hợp đồng cho phiên bản

**Files:** Create `src/rag/contracts/version_cross.py`; Test `tests/test_contracts_version_cross.py`

**Interfaces — Consumes:** `compare_results`. **Produces:**
- `version_dossier(contracts: list[Contract], *, day: date, continuous_employment: bool | None, user_facts: dict) -> tuple[Dossier, dict[str, dict]]`: mỗi hợp đồng = một `DossierDoc` chính (text phần `p0`, `kind = facts["document_kind"]`); mỗi phần phụ lục = `DossierDoc` loại `AMENDMENT` trỏ về nó; thiếu tiêu đề mà `detect_parts` nhận ra thì thêm dòng `PHỤ LỤC <n>` vào đầu text. Mọi `ref` của kiểu đối tượng (trừ `amends`) = `"party1"`; một `Party` với `role` = tên ref đầu tiên tra trong vai trò của gói (labor: `NLD`). `facts_by_contract` = dữ kiện đã lưu.
- `cross_check(before: list[Contract], after: list[Contract], *, day, continuous_employment, user_facts) -> dict` = `{"day", "supported": bool, "results": [...], "compare": {...}, "recomputed": int, "total": int, "note": str | None}`; chỉ lấy kết quả `object is not None`; "sau" = `session.update({}, objects=object_changes(...))`; `recomputed` lấy từ `session.stats` như `stats` trong `rag.rules.events.diff_event`. Gói không có `object_types`: `supported=False`, `note="Không có quy tắc liên văn bản cho loại hợp đồng này"`. Không gọi LLM.

- [ ] **Step 1: Test** với hồ sơ mẫu `tests/fixtures/rete/b4` (dựng `Contract` từ các file `.txt`, dữ kiện bằng `fake_facts` của `tests/test_dossier_objects.py`):
```python
out = cross_check([hd1, hd2], [hd1, hd2, hd_sot], day=date(2023, 6, 1), continuous_employment=True, user_facts=SPEC["user_facts"])
got = {c["key"]: (c["before"]["status"], c["after"]["status"]) for c in out["compare"]["changed"]}
assert got == {"content.term/r6@employee=party1": ("FAIL", "PASS"), "content.term/r5@employee=party1": ("PASS", "FAIL")}
assert out["recomputed"] == 3 and out["total"] == 55
```
Hai con số `3` và `55` là số đo của slide 12; nếu khác, đối chiếu với `run_scenario("b4")` rồi sửa nguyên nhân, không sửa số cho khớp mà không hiểu.
- [ ] **Step 2–4:** FAIL, cài đặt, PASS cùng `test_dossier_objects.py`. **Step 5:** commit `feat(team-4.2): đối chiếu quy tắc liên hợp đồng giữa hai phiên bản`.

### Task 6: API

**Files:** Create `ui/contract_versions.py`; Modify `ui/server.py` (thêm `*contract_versions.routes`), `ui/contracts_api.py` (`card`, `handle_list`, `handle_delete`); Test `tests/test_contract_versions_api.py`

**Interfaces — Produces:**
- `POST /api/contracts/{cid}/additions` (multipart `file`) -> `{"addition_id","filename","suggested_kind": "appendix"|"contract"|null,"excerpt","today"}`. Nháp giữ trong bộ nhớ. 409 khi bản không mới nhất hoặc chưa có `concept_check`.
- `POST /api/contracts/{cid}/additions/{aid}/prepare/stream` `{kind}` -> `done {"draft": snapshot, "other": snapshot|null, "review_date": str|null}`.
- `POST /api/contracts/{draft}/additions/analyze/stream` `{review_date, user_facts, same_party, continuous_employment}` -> `done {**snapshot(draft), "compare": {...}}`. Soát qua `verify.check_gate` cho bản nháp (và hợp đồng `other`). Xong mới đặt `status="ready"`, `persist` theo bản gốc, lưu; `other` đặt `status="member"`.
- `lineage["compare"] = {"day", "against": parent_id, "contract": compare_results|None, "before_differs_from_saved": bool, "cross": cross_check|None, "catalog_changed": bool}`. Phụ lục: `before` = `check_contract(None, deepcopy(parent), rules_only=True, day=day, graph=None, user_facts=...)`. `cross` tính khi họ có từ hai hợp đồng.
- `GET /api/contracts/{cid}/versions` -> `{"versions": [{"contract_id","version","filename","addition","latest"}]}`.
- `GET /api/contracts/{cid}/studio/compare` -> `lineage["compare"]`; 404 với version 1.
- `card` thêm `"lineage": {family_id, version, status}`. `handle_list` bỏ bản không phải mới nhất, `draft`, `member`. `handle_delete`: bản mới nhất -> xóa nó (và `member` nó thêm); bản gốc -> xóa cả họ; bản giữa -> 409.

- [ ] **Step 1: Test** (fixture `studio_client` như `test_contract_studio.py`, thêm routes mới; LLM giả = `ClassifyingScriptLLM` trả `amendment` cho file phụ lục):
  - `test_appendix_flow_creates_v2_and_keeps_v1`: upload, xác minh, phân tích; bổ sung; `suggested_kind == "appendix"`; prepare; xác minh trường mở lại; analyze `review_date="2025-07-01"`; `versions` có 2; bản cha `_dump` không đổi; `compare["day"] == "2025-07-01"`; mục `leave.annual` không nằm trong `changed`.
  - `test_missing_review_date_is_400`.
  - `test_llm_failure_leaves_no_version`: LLM ném lỗi ở prepare, rồi riêng ở analyze -> stream kết `error`, `versions` còn 1, cha không đổi.
  - `test_not_latest_is_409`, `test_same_party_false_is_400`.
  - `test_other_contract_flow_has_cross_section`, `test_list_shows_only_latest`, `test_delete_latest_restores_previous`.
- [ ] **Step 2–4:** FAIL, cài đặt (dùng `studio.stream_work(..., cid=parent_id)` để chặn chạy song song), PASS cùng `test_contracts_api.py test_contract_studio.py test_contract_dossier_api.py`.
- [ ] **Step 5:** commit `feat(team-4.2): API bổ sung văn bản và đối chiếu phiên bản`.

### Task 7: Giao diện

**Files:** Create `contract-studio/src/components/AddDocumentPanel.tsx`, `contract-studio/src/components/ComparePanel.tsx`, `contract-studio/src/live/versions.ts`, `contract-studio/src/live/versions.test.ts`; Modify `contract-studio/src/App.tsx`

**Interfaces — Consumes:** API Task 6. **Produces:** `compareRows(compare: any): { group: "changed"|"added"|"removed"; scope: "contract"|"cross"; key: string; before?: any; after?: any }[]`.

- [ ] **Step 1: Test** `compareRows`: thứ tự `changed`, `added`, `removed`; `contract` trước `cross`; `compare.contract === null` không lỗi; đầu vào rỗng -> `[]`.
- [ ] **Step 2:** `npm test` FAIL. **Step 3:** cài `versions.ts`.
- [ ] **Step 4:** UI: nút **"Bổ sung văn bản"** khi `card.last_check` và là bản mới nhất; panel: chọn file -> xác nhận loại (mặc định theo gợi ý, `null` thì bắt chọn) -> khối xác minh sẵn có cho bản nháp -> ngày đánh giá (bắt buộc; hợp đồng khác mặc định hôm nay, thêm "cùng người lao động" và "làm việc liên tục: có/không/không rõ") -> chạy; bộ chọn phiên bản v1, v2…; tab **"So với bản trước"** hiện ngày đang dùng, ghi chú khi `before_differs_from_saved`, mỗi dòng: tên mục, kết luận cũ -> mới, trích đoạn hai bên, phần không đổi thu gọn thành số đếm, mục liên hợp đồng kèm "tính lại X/Y quy tắc".
- [ ] **Step 5:** `npm test && npm run check && npm run build`: PASS. Commit `feat(team-4.2): Contract Studio bổ sung văn bản và so với bản trước` (gồm `dist` nếu repo đang theo dõi nó).

### Task 8: Chạy thật và ghi hạn chế

**Files:** Modify `docs/superpowers/notes/w04-rule-engine/han_che_va_loi_ton_dong.md` (tính từ `app/team-4.2/`)

- [ ] **Step 1:** chạy toàn bộ `PYTHONPATH=src python -m pytest tests -q`; so với kết quả trên `HEAD` trước khi làm, không có lỗi mới.
- [ ] **Step 2:** mở UI, chạy với LLM thật: (a) hợp đồng mẫu + phụ lục nâng lương; (b) `hd1_2022`, bổ sung `hd2_2023`, rồi `hd_sot_2023`. Ghi lại số mục đổi và mục đổi bất thường.
- [ ] **Step 3:** ghi hạn chế: phụ lục không có câu sửa đổi -> mâu thuẫn; liên hợp đồng không dùng câu trả lời ở bảng xác minh, chỉ dùng ứng viên đã trích; một `party` chung; không so bản bất kỳ; nháp mất khi khởi động lại; kết quả thực tế ở Step 2.
- [ ] **Step 4:** commit `docs(team-4.2): hạn chế của bổ sung văn bản`.
