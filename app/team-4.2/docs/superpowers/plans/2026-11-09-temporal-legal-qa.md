# Hỏi đáp theo mốc thời gian — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mọi câu hỏi pháp lý trong chat được trả lời theo dòng thời gian pháp lý (nhiều mốc), dùng đúng phiên bản luật do backend chọn từ kho có phiên bản, kho cũ chỉ để tham khảo, có trạng thái hai tầng, quy định chuyển tiếp và giới hạn kết luận.

**Architecture:** Package mới `rag.temporal`: timeline (quy tắc → LLM khi cần → kiểm tra) → `VersionedIndex` (BM25 + dense trên chunk của `rag.legal`, lọc theo khoảng hiệu lực trước khi xếp hạng) + truy xuất kho cũ qua `RAGPipeline.retriever` → trạng thái văn bản/điều khoản → `transition_rules` → LLM trả JSON → backend hạ mức chắc chắn → log. `ui/server.py` gọi `TemporalQA` cho `/api/chat`.

**Tech Stack:** Python 3.12, sqlite3, các index/embedder/LLM sẵn có của `rag`, Starlette, pytest.

**Spec:** `app/team-4.2/docs/superpowers/specs/2026-11-09-temporal-legal-qa-design.md`

## Global Constraints

- Đường dẫn tương đối từ `app/team-4.2/`. Code `src/rag/temporal/`, test `tests/test_temporal_*.py`. Chạy `python -m pytest -q tests/test_temporal_<x>.py`; toàn bộ suite phải pass.
- Commit sau mỗi task (đã được phép commit trên nhánh `feat/team-4.2/w02-legal-version-builder`); không push khi chưa hỏi.
- Test không gọi mạng, không gọi LLM thật: dùng `FakeLLM` (trả chuỗi cố định theo prompt) và embedder giả `rag.index.embedder.make_embedder("hash", ...)` nếu có, không thì embedder giả trong test.
- Ngày theo `Asia/Ho_Chi_Minh`; khoảng mốc là đóng `[start, end]`; khoảng hiệu lực phiên bản vẫn nửa mở `[valid_from, valid_to)`.
- LLM không bao giờ chọn phiên bản; mốc thiếu `evidence` có thật trong câu hỏi bị loại.
- Câu hỏi đưa vào LLM và log luôn là bản đã che PII (`rag.quality.pii.mask_text` + `MaskState` như pipeline hiện tại).

## Review Focus

1. Câu hỏi không có mốc nào và không chọn ngày → mốc `evaluation = hôm nay`, cảnh báo luật hiện hành, vẫn trả lời (Task 2).
2. Mốc chỉ có năm 2024 với Luật Nhà ở (đổi 01/8/2024) → cả hai phiên bản vào ngữ cảnh, câu trả lời không `firm` (Task 4, Task 6).
3. LLM trả JSON hỏng / không phải JSON → vẫn trả lời dạng văn bản, certainty `qualified`, không crash (Task 6).
4. Kho mới trống (chưa build) → chat chạy như cũ trên kho cũ, mọi căn cứ `unversioned` (Task 7).
5. Ngày lịch không hợp lệ ("2023-02-30") từ API → 400, không crash (Task 9).

---

### Task 1: Mô hình + trích mốc bằng quy tắc

**Files:** Create `src/rag/temporal/__init__.py`, `src/rag/temporal/models.py`, `src/rag/temporal/rules.py`; Test `tests/test_temporal_rules.py`

**Interfaces — Produces:**
- `models.py`: `Role = Literal["signing","contract_effective","performance","discovery","dispute","evaluation","unspecified"]`; `Precision = Literal["day","month","year","range","relative_unresolved"]`; dataclass frozen `TimeAnchor(role, start: date|None, end: date|None, precision, source: Literal["calendar","question","default"], evidence: str|None, relative_expression: str|None, confidence: float)`; `LegalTimeline(anchors: tuple[TimeAnchor,...], primary: TimeAnchor, warnings: tuple[str,...], asked_at: datetime)`; `TransitionRule(rule_id, source_document_key, source_article, text, old_law_key, new_law_key, new_law_effective_from: date|None, related_roles: tuple[str,...])`.
- `rules.py`: `extract_rule_anchors(question: str, *, asked_at: datetime) -> list[TimeAnchor]` (source="question", evidence = đoạn khớp, role từ từ khoá trong cửa sổ ~40 ký tự trước mốc, không thấy → `unspecified`); `resolve_relative(expr: str, asked_at: datetime) -> tuple[date|None, date|None, Precision]`; `ROLE_KEYWORDS: dict[Role, tuple[str,...]]`.

Quy tắc khoảng: ngày → start=end; `tháng M/YYYY` / `tháng M năm YYYY` → cả tháng (precision month); `năm YYYY` / YYYY đứng sau "năm" → cả năm; `từ <mốc> đến <mốc>` → range; tương đối: `năm nay` (cả năm hiện tại), `năm ngoái`/`năm trước` (cả năm trước), `cuối năm ngoái` (01/10–31/12 năm trước, range), `đầu năm nay` (01/01–31/03, range), `tháng trước` (cả tháng trước), `hiện nay`/`bây giờ`/`hiện tại` (hôm nay, role evaluation); không quy được → `relative_unresolved`.

- [ ] Step 1: test `test_day_month_year_and_roles` — "Tôi ký hợp đồng ngày 15/06/2023, thực hiện trong năm 2024 và tranh chấp năm 2025" → 3 anchor: (signing, 2023-06-15..2023-06-15, day), (performance, 2024-01-01..2024-12-31, year), (dispute, 2025-01-01..2025-12-31, year), evidence là chuỗi con của câu.
- `test_relative_expressions` — asked_at 2026-11-09: "năm ngoái" → 2025-01-01..2025-12-31 year; "cuối năm ngoái" → 2025-10-01..2025-12-31 range; "bây giờ" → 2026-11-09 day role evaluation; "tháng 3/2023" → 2023-03-01..2023-03-31 month.
- `test_vietnamese_long_date_and_range` — "từ ngày 01 tháng 7 năm 2024 đến ngày 31/12/2024" → một anchor range 2024-07-01..2024-12-31.
- `test_invalid_date_skipped` — "ngày 30/02/2024" → không anchor.
- `test_no_dates` — "Điều khoản phạt vi phạm này có hợp pháp không?" → [].
- [ ] Step 2: FAIL → Step 3: viết → Step 4: PASS → Step 5: commit `feat(team-4.2): temporal anchors from rules`.

---

### Task 2: Dòng thời gian (LLM khi cần + kiểm tra + hợp nhất lịch)

**Files:** Create `src/rag/temporal/timeline.py`; Test `tests/test_temporal_timeline.py`

**Interfaces — Consumes:** Task 1. **Produces:**
- `needs_llm(question: str, anchors: Sequence[TimeAnchor]) -> bool` — True nếu có anchor role unspecified, hoặc relative_expression, hoặc ≥ 2 anchor.
- `parse_llm_events(raw: str, question: str, *, asked_at) -> tuple[list[TimeAnchor], list[str]]` — JSON `{"events":[{"role","date":{"start","end","precision"},"relative_expression","evidence","confidence"}]}`; event có evidence không là chuỗi con (NFC, gộp khoảng trắng, casefold) của câu hỏi → loại, warning `timeline.evidence_not_found`; role ngoài danh sách → `unspecified`; ngày hỏng → dùng `resolve_relative(relative_expression)` hoặc `relative_unresolved`.
- `build_timeline(question: str, *, asked_at: datetime, calendar_date: date|None = None, llm: LLM|None = None) -> LegalTimeline`
  Hợp nhất: anchor quy tắc là gốc; anchor LLM chỉ **gán/điều chỉnh role** cho anchor quy tắc có cùng evidence chồng lấn, hoặc thêm anchor mới có evidence hợp lệ; ngày của LLM khác ngày quy tắc trên cùng evidence → giữ ngày quy tắc. LLM lỗi/không JSON → warning `timeline.llm_failed`, dùng quy tắc. Lịch: thêm anchor source=calendar role unspecified làm `primary`; anchor câu hỏi không chứa ngày lịch → warning `timeline.calendar_conflict:<role>`. Không anchor → evaluation hôm nay source=default, warning `timeline.default_today`. `primary` khi không có lịch: anchor `evaluation` nếu có, không thì anchor đầu tiên. Anchor `relative_unresolved` → warning `timeline.relative_unresolved:<expr>`.
- Prompt LLM (hằng `TIMELINE_PROMPT`) yêu cầu đúng JSON, cấm tạo ngày không có trong câu.

- [ ] Step 1: tests — `test_no_anchor_defaults_to_today` (Review Focus 1); `test_calendar_wins_and_warns_on_conflict` (lịch 2023-06-15, câu "theo luật năm 2025" → primary calendar, warning bắt đầu `timeline.calendar_conflict`, anchor 2025 vẫn còn); `test_llm_assigns_roles_without_changing_dates` (FakeLLM trả role "discovery" cho evidence "cuối năm ngoái" và ngày 2025-12-31 → giữ khoảng 2025-10-01..2025-12-31, role discovery); `test_llm_invented_event_rejected` (evidence không có trong câu → loại + warning); `test_llm_not_called_for_single_clear_anchor` (FakeLLM đếm lần gọi = 0 với "ký ngày 15/06/2023"); `test_llm_garbage_falls_back` (FakeLLM trả "xin lỗi" → warning `timeline.llm_failed`).
- [ ] Step 2–5 như Task 1; commit `feat(team-4.2): legal timeline with evidence-checked LLM roles`.

---

### Task 3: Trạng thái văn bản, bảng kho cũ, văn bản chỉ để sửa đổi

**Files:** Create `src/rag/temporal/status.py`, `data/team-4.2/legal/legacy_map.yaml`; Test `tests/test_temporal_status.py`

**Interfaces — Produces:**
- `DocumentStatus = Literal["verified","partially_verified","unversioned","outdated","unknown"]`
- `LegacyLaw(source: str, doc_type: str, doc_number: str, issuer: str)`; `load_legacy_map(path) -> dict[str, LegacyLaw]` (key = tên file nguồn của chunk kho cũ).
- `legacy_duplicates(store: LegalStore, legacy: Mapping[str, LegacyLaw]) -> set[str]` — tên file kho cũ có cùng (loại casefold, số hiệu chuẩn hoá, cơ quan casefold) với một văn bản không phải VBHN trong kho mới.
- `legacy_status(store, law: LegacyLaw|None, *, start: date, end: date) -> DocumentStatus` — có văn bản cùng số hiệu trong kho mới và không có phiên bản giao `[start,end]` → `outdated`; kho mới có REPEAL áp dụng được với ngày ≤ start → `outdated`; không thì `unversioned`; `law is None` → `unknown`.
- `versioned_status(versions_at: Sequence[ProvisionVersion]) -> DocumentStatus` — rỗng → `outdated`; tất cả `verified` → `verified`; có `effectivity.unresolved` ở mọi phiên bản → `unknown`; còn lại `partially_verified`.
- `is_amendment_only(provisions: Sequence[Provision]) -> bool` — mọi Điều có tiêu đề hành động sửa đổi (dùng `rag.legal.directives._ACTION_START`/`_PASSIVE`) hoặc là Điều hiệu lực/chuyển tiếp (tiêu đề chứa "hiệu lực", "thi hành", "chuyển tiếp").
- `legacy_map.yaml`: 6 file `data/team-4.2/raw/` → Bộ luật Dân sự 91/2015/QH13, Hàng hải 95/2015/QH13, Hình sự 100/2015/QH13, Lao động 45/2019/QH14, Tố tụng dân sự 92/2015/QH13, Tố tụng hình sự 101/2015/QH13; issuer "Quốc hội".

- [ ] Step 1: tests — `test_legacy_map_loads_six_codes`; `test_duplicate_by_number_type_issuer` (store có `bo-luat:91/2015/QH13` → `bo_luat_dan_su_2015.txt` trùng; `nghi-quyet:91/2015/QH13` không trùng); `test_versioned_status_levels`; `test_is_amendment_only_real` (fixture 43/2024 → True, 59/2020 → False, 03/2022 → True); `test_legacy_outdated_when_newer_known` (dùng store test có văn bản cùng số hiệu đã hết hiệu lực tại mốc).
- [ ] Step 2–5; commit `feat(team-4.2): document-level status and legacy dedupe`.

---

### Task 4: VersionedIndex — truy xuất lọc theo thời gian

**Files:** Create `src/rag/temporal/index.py`; Test `tests/test_temporal_index.py`

**Interfaces — Consumes:** `rag.legal.chunks.export_chunks`, `VersionedChunk`, `BM25Index`, `VectorIndex` (in-memory store) + embedder truyền vào. **Produces:**
- `VersionedIndex(store: LegalStore, embedder|None)`; `.build() -> int` (bỏ văn bản `is_consolidated` và `is_amendment_only`; chunk → `rag.schema.Chunk(chunk_id, doc_id=document_key, source=title, page None, section, text)`; giữ map chunk_id → VersionedChunk; build_ids đã nạp để `.stale()` biết khi có build mới).
- `.stale() -> bool`.
- `.search(query: str, start: date, end: date, k: int) -> list[tuple[VersionedChunk, float]]` — tập ứng viên = chunk có `valid_from <= end` và (`valid_to is None` hoặc `valid_to > start`); BM25 chấm toàn bộ (`search(query, len(index))`) rồi lọc; dense (nếu có embedder) tương tự; gộp RRF (k=60); trả top-k. Tất định.
- `.versions_of(article_id: str, start: date, end: date) -> list[VersionedChunk]`.

- [ ] Step 1: tests dùng fixture realestate + `make_service` kiểu test_legal_realestate (build_all) và embedder=None (chỉ BM25): `test_filter_before_rank_returns_version_valid_at_date` (truy vấn "điều kiện chủ đầu tư dự án nhà ở" tại 2023-06-15 chỉ trả chunk của `luat:65/2014/QH13`; tại 2025-06-15 chỉ `luat:27/2023/QH15`); `test_year_range_returns_both_versions` (khoảng 2024-01-01..2024-12-31 trả chunk của cả 65/2014 và 27/2023 — Review Focus 2); `test_amendment_only_docs_not_indexed` (không chunk nào của `luat:43/2024/QH15`); `test_stale_after_new_build`.
- [ ] Step 2–5; commit `feat(team-4.2): time-filtered versioned index`.

---

### Task 5: Quy định chuyển tiếp

**Files:** Create `src/rag/temporal/transitions.py`; Test `tests/test_temporal_transitions.py`

**Interfaces — Consumes:** `LegalService` (provisions_for, store), `parse_effectivity`. **Produces:** `collect_transition_rules(service: LegalService, used: Sequence[VersionedChunk], timeline: LegalTimeline) -> list[TransitionRule]`:
- (i) mỗi note `note:transition:<doc>#dN` trên chunk dùng → rule từ Điều N của `<doc>` (text = text Điều đó từ `provisions_for(doc)`), new_law = doc đích của chunk.
- (ii) các luật cùng `law_family` có hiệu lực ở các mốc khác nhau trong timeline (theo `laws_in_force` tại start của từng anchor) → rule = Điều chuyển tiếp (`parse_effectivity(...).transition_article`) của luật mới hơn; old_law/new_law tương ứng; related_roles = vai trò các mốc nằm hai phía.
- (iii) anchor có start < ngày hiệu lực của luật đang hiệu lực tại mốc evaluation/primary trong cùng family → như (ii).
- Không trùng rule_id (`<doc>#d<N>`); thiếu Điều chuyển tiếp → bỏ qua.

- [ ] Step 1: tests với fixture realestate: `test_family_change_across_anchors_adds_transition_article` (anchors ký 2023-06-15 + đánh giá 2025-06-15 → rule từ Điều chuyển tiếp của `luat:27/2023/QH15`, old `luat:65/2014/QH13`, text chứa "chuyển tiếp" hoặc nội dung Điều đó); `test_no_rule_when_single_law_applies` (chỉ 2025-06-15 → []); `test_note_based_rule` (chunk giả có note `note:transition:luat:03/2022/QH15#d11` + service fixture 03/2022 → rule source_article "Điều 11").
- [ ] Step 2–5; commit `feat(team-4.2): transition rules for legal context`.

---

### Task 6: Hợp đồng với LLM, hạ mức chắc chắn

**Files:** Create `src/rag/temporal/answer.py`; Test `tests/test_temporal_answer.py`

**Interfaces — Produces:**
- `ContextItem(n: int, store: Literal["versioned","legacy"], document_key|None, title, article_id|None, section, text, valid_from|None, valid_to|None, document_status, provision_status|None, provenance: tuple[str,...], anchor_roles: tuple[str,...], chunk_id)`
- `build_messages(question: str, timeline: LegalTimeline, items: Sequence[ContextItem], rules: Sequence[TransitionRule]) -> tuple[str, str]` (system, user) — system nêu luật chơi (chỉ dùng ngữ cảnh, kho cũ chỉ tham khảo, trả đúng JSON schema mục 6 spec, không tự chọn phiên bản, thiếu dữ kiện thì hỏi lại).
- `TemporalAnswer(answer_markdown, issues: list[dict], transition_assessments: list[dict], follow_up_questions: list[str], certainty: Literal["firm","qualified","cannot_conclude"], downgrade_reasons: list[str], raw_ok: bool)`
- `parse_answer(raw: str) -> TemporalAnswer` — JSON trong khối ```json hoặc thô; không parse được → `answer_markdown=raw`, `issues=[]`, `certainty="qualified"`, `raw_ok=False` (Review Focus 3).
- `enforce(answer: TemporalAnswer, items, rules, timeline, *, year_change: bool) -> TemporalAnswer` — loại `[n]` không tồn tại; issue `firm` → `qualified` nếu citation của nó có `document_status != verified` hoặc `provision_status not in (None,"verified")` hoặc store legacy, hoặc có rule với assessment ∉ {not_applicable, applicable}, hoặc rule không được đánh giá, hoặc `year_change`; `certainty` tổng = thấp nhất các issue; không còn citation hợp lệ nào → `cannot_conclude`; ghi `downgrade_reasons` (mã cố định).

- [ ] Step 1: tests — `test_parse_json_block`; `test_garbage_is_qualified_text`; `test_firm_on_legacy_downgraded`; `test_firm_with_unresolved_transition_downgraded`; `test_year_change_downgrades`; `test_invalid_citation_removed_and_cannot_conclude_when_none_left`; `test_firm_kept_when_all_verified_and_no_rules`.
- [ ] Step 2–5; commit `feat(team-4.2): temporal answer contract and certainty enforcement`.

---

### Task 7: TemporalQA — điều phối + log

**Files:** Create `src/rag/temporal/qa.py`, `src/rag/temporal/log.py`; Test `tests/test_temporal_qa.py`

**Interfaces — Consumes:** Task 1–6, `RAGPipeline` (retriever kho cũ, mask). **Produces:**
- `QALog(path)`: `.record(entry: dict) -> str` (bảng `qa_log(id, asked_at, payload)`), `.get(id) -> dict`.
- `TemporalQA(service: LegalService, index: VersionedIndex, llm: LLM, *, legacy: RAGPipeline|None, legacy_map: Mapping[str, LegacyLaw], log: QALog|None, k_per_anchor: int = 6, k_legacy: int = 4, now: Callable[[], datetime])`
- `.ask(question: str, *, calendar_date: date|None = None, mask_state: MaskState|None = None) -> TemporalResult` — che PII câu hỏi; timeline; với mỗi anchor có start/end: `index.search(q, start, end, k)`; anchor `relative_unresolved` → không truy xuất kho mới cho nó; gộp item theo chunk_id (anchor_roles hợp nhất); status cấp văn bản = `versioned_status(versions_at)` trên các chunk của văn bản tại khoảng của anchor; provenance = `source_operations` → `source_document_key` của thao tác (qua `service.store.operation`); kho cũ: `legacy.retriever.retrieve(q, k_legacy)` + context như pipeline, bỏ chunk thuộc `legacy_duplicates`, status `legacy_status`; transition rules; `year_change` = có anchor precision year/month/range mà một article dùng có ≥ 2 phiên bản trong khoảng; LLM; `enforce`; mở che PII trong `answer_markdown`; log; trả `TemporalResult(timeline, items, rules, answer, log_id)`.
- Kho mới trống → chỉ kho cũ, mọi item `unversioned`/`outdated` (Review Focus 4). Không item nào → từ chối như pipeline (không gọi LLM).

- [ ] Step 1: tests (FakeLLM ghi prompt, trả JSON; service + index trên fixture realestate; legacy=None hoặc fake retriever): `test_ask_uses_version_at_anchor` (câu "ký hợp đồng mua nhà ngày 15/06/2023, điều kiện chủ đầu tư là gì" → mọi item versioned thuộc 65/2014; prompt chứa "2023-06-15"); `test_multi_anchor_adds_transition_and_qualifies` (ký 2023 + "bây giờ" → rules không rỗng, certainty ≠ firm khi FakeLLM không đánh giá rule); `test_empty_versioned_store_uses_legacy_only` (fake legacy trả 1 chunk → item store legacy, status unversioned); `test_no_context_refuses_without_llm`; `test_log_records_masked_question` (câu có SĐT → log không chứa số gốc).
- [ ] Step 2–5; commit `feat(team-4.2): temporal QA orchestration and log`.

---

### Task 8: API + giao diện chat

**Files:** Modify `ui/server.py` (khởi tạo lười `TemporalQA` dùng `get_pipeline()` + `get_legal_service()` + `VersionedIndex` với embedder của pipeline; rebuild index khi `stale()`), `ui/index.html`; Test `tests/test_temporal_api.py`

**Interfaces:** `POST /api/chat` body thêm `as_of` (YYYY-MM-DD, tuỳ chọn; sai định dạng/ngày → 400 — Review Focus 5). Response giữ trường cũ (`answer`, `citations`, `sources`, `trace`, `query_pii`) + `timeline` (anchors, primary, warnings), `issues`, `certainty`, `downgrade_reasons`, `transition_assessments`, `transition_rules`, `follow_up_questions`, `log_id`; mỗi citation/source thêm `store`, `document_status`, `provision_status`, `valid_from`, `valid_to`, `provenance`.
UI: ô `<input type="date">` cạnh ô hỏi (gửi `as_of`, nút xoá); trên câu trả lời một hàng thẻ "Mốc pháp lý đang sử dụng" (vai trò, ngày/khoảng, nguồn) + cảnh báo; nhãn trạng thái (biểu tượng + chữ) trên pill trích dẫn và trong popover (hiệu lực từ–đến, "do … sửa"); khối "Quy định chuyển tiếp" với trạng thái đánh giá; câu hỏi bổ sung dạng nút gợi ý; dòng mức chắc chắn khi không `firm`.

- [ ] Step 1: tests API (TestClient, monkeypatch `server.get_temporal_qa` trả fake trả `TemporalResult` dựng tay): `test_chat_returns_timeline_and_statuses`; `test_invalid_as_of_400`; `test_old_fields_still_present`. JS: `node --check` trên script trích từ index.html.
- [ ] Step 2–4; chụp headless Chromium 1366px và 390px (iframe) một câu trả lời giả lập (dùng route test tạm hoặc stub) kiểm tra không tràn; Step 5 commit `feat(team-4.2): temporal legal answers in chat`.

---

### Task 9: Bộ đánh giá theo mốc + chạy thật

**Files:** Create `evals/team-4.2/datasets/temporal_qa_realestate.jsonl` (≥ 15 câu), `evals/team-4.2/runners/run_temporal_eval.py`, `tests/test_temporal_eval.py`, `evals/team-4.2/results/w02-temporal-qa/README.md`

- Mỗi dòng: `question`, `as_of` (tuỳ chọn), `asked_at`, `expected_anchors` [{role, start, end}], `expected_documents` [document_key phải có trong top-k kho mới tại anchor tương ứng], `forbidden_documents`.
- Runner: chạy `build_timeline` (không LLM: `llm=None`) + `VersionedIndex.search` trên DATA_DIR được chỉ định; in độ đúng mốc (khớp role+khoảng), độ đúng phiên bản (expected ⊆ docs, forbidden ∩ docs = ∅). Tuỳ chọn `--llm` chạy `TemporalQA` thật và đo tỉ lệ `firm` dựa trên căn cứ không verified (phải 0).
- Test: chạy runner trên fixture realestate (không mạng) → độ đúng phiên bản = 100% với các câu của dataset dùng 4 luật trong fixture; độ đúng mốc ≥ 90%.
- Chạy thật trên `legal_run` + kho cũ, có LLM; ghi README kết quả, ví dụ câu trả lời, giới hạn.
- Commit `feat(team-4.2): temporal QA eval set and report`.
