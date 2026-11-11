# Đính kèm hợp đồng trong chat (Phần 4/4, demo) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (người dùng chọn: Claude làm trực tiếp, một lượt review cuối). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Người dùng đính kèm hợp đồng vào chat, chọn bên, chạy 6 thao tác (tóm tắt, soát toàn bộ, soát một phần, đối chiếu thay đổi của luật, đề xuất sửa, hỏi về hợp đồng — kể cả Think), tải báo cáo Word/PDF; mọi kết luận pháp lý có căn cứ kho luật tại ngày ký hoặc bị từ chối.

**Architecture:** Gói mới `rag.contracts` (mô hình, tách đơn vị, kho phiên/lưu, trích thông tin nền, tra căn cứ theo mốc, các thao tác soát, xuất file, nguồn cho agent) + `ui/contracts_api.py` (HTTP) + nối `/api/chat` (`contract_id`) + UI trong `ui/index.html`. Căn cứ luật lấy từ `LegalRuntime` (lease, lọc hiệu lực tại ngày ký) và kho cũ. Think với hợp đồng dùng `AgentPipeline` không đổi vòng lặp, chạy trên một "baseline view" có `ContractAgentRetriever` gộp 3 nguồn.

**Tech Stack:** Python 3.11, Starlette, OpenAI-compatible `llm.complete(system, user)`, python-docx, PyMuPDF (`fitz.Story`), vanilla JS + Tailwind.

**Spec:** `app/team-4.2/docs/superpowers/specs/2026-11-11-contract-review-design.md` (§0 phạm vi demo thắng khi mâu thuẫn).

## Global Constraints

- Lệnh chạy từ `app/team-4.2`; test `python -m pytest -q <files>`. Baseline lỗi trước phần 4: demo scripts ×3, pii ×1 (docx ×4 hết lỗi sau khi cài python-docx).
- Kết luận pháp lý chỉ khi có căn cứ kho **đã qua bước kiểm chứng** (một lượt LLM cho cả báo cáo); không có → "Chưa thể kết luận" với câu: `Kho chưa có {luật} — chưa thể kết luận điều khoản này có hợp pháp không. Có thể upload luật ở trang Nạp văn bản pháp luật (/upload).` (`{luật}` = tên luật nếu xác định được, không thì "luật điều chỉnh vấn đề này").
- Căn cứ chỉ từ kho cũ → tối đa "có điều kiện", ghi "Kho cũ — chưa xác định phiên bản".
- Mốc = ngày ký; thiếu → chặn phần pháp lý, không dùng "hôm nay" ngầm.
- Trích dẫn điều khoản hợp đồng phải là chuỗi con của text hợp đồng (so sau gộp khoảng trắng); không khớp → bỏ trích dẫn, mục thành "cần kiểm tra".
- Mọi text gửi LLM che PII bằng `mask_text(..., state=contract.mask_state)`; output hiển thị / tải về mở che.
- Hợp đồng không bao giờ đi `/api/ingest` hay vào kho tra cứu.
- Demo: tối đa 30 đơn vị / 20 trang được soát; dư → "Bản demo chỉ soát N/M điều khoản". Upload ≤ 50 MB.
- Mỗi request làm việc trên hợp đồng giữ một `LegalRuntime` (`legal_api` lease) suốt request.
- Nhận xét không pháp lý gắn nhãn `Nhận xét về câu chữ / thương mại — không phải kết luận pháp lý`.
- Commit mỗi task: `feat(team-4.2): ...` + `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **LLM trả JSON hỏng / thiếu trường** → thao tác báo lỗi rõ ("AI trả kết quả không hợp lệ, thử lại"), không 500, không báo cáo rỗng như thể "không có vấn đề". (Test ở Task 5.)
2. **Hợp đồng không đánh số Điều** (chỉ đoạn văn) → tách theo đoạn, vẫn soát được. (Task 2.)
3. **Kho luật trống** (máy chưa nạp luật) → mọi mục pháp lý "Chưa thể kết luận", tóm tắt vẫn chạy. (Task 5.)
4. **Server khởi động lại** → thẻ hợp đồng "Chỉ trong phiên" báo hết phiên, không lỗi JS. (Task 9.)
5. **Think với hợp đồng khi agent trả abstain/error** → hiện trạng thái agent như chế độ Think hiện có, không mất PII mask. (Task 8.)

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `src/rag/contracts/__init__.py` | Xuất API |
| `src/rag/contracts/models.py` | `Contract`, `ContractUnit`, `Finding`, `Evidence`, `Report` |
| `src/rag/contracts/parse.py` | text → đơn vị (Điều / mục / đoạn), giới hạn demo |
| `src/rag/contracts/store.py` | `ContractStore`: bộ nhớ + lưu `DATA_DIR/contracts/<id>/` |
| `src/rag/contracts/llm_json.py` | gọi LLM trả JSON có che/mở PII, lỗi → `ContractAIError` |
| `src/rag/contracts/facts.py` | trích thông tin nền (loại, các bên, ngày, giá trị) + kiểm trích dẫn |
| `src/rag/contracts/evidence.py` | tra căn cứ tại mốc (kho có phiên bản + kho cũ), so phiên bản ký ↔ hiện hành |
| `src/rag/contracts/review.py` | 6 thao tác + quy tắc từ chối / kiểm chứng |
| `src/rag/contracts/export.py` | DOCX (python-docx), PDF (fitz.Story + font hệ thống có dấu) |
| `src/rag/contracts/agent_view.py` | `ContractAgentRetriever` + baseline view cho `AgentPipeline` |
| `ui/contracts_api.py` | routes `/api/contracts/...`, nối chat |
| `ui/server.py` (sửa) | đăng ký routes, `/api/chat` nhận `contract_id` |
| `ui/index.html` (sửa) | menu "+", thẻ hợp đồng, công tắc chế độ, hiển thị báo cáo, tải về, danh sách đã lưu |
| `scripts/team-4.2/seed_legal_demo.py` | nạp fixture bất động sản vào kho qua `SnapshotManager.write` |
| `data/team-4.2/contracts_demo/hop_dong_thue_nha_2023.txt` (+ `.docx`) | hợp đồng mẫu có lỗi cài sẵn |
| `tests/test_contracts_*.py` | test |

---

### Task 1: Dữ liệu demo — kho luật bất động sản + hợp đồng mẫu

**Files:** Create `scripts/team-4.2/seed_legal_demo.py`, `data/team-4.2/contracts_demo/hop_dong_thue_nha_2023.txt`, `.docx`; Test `tests/test_contracts_demo_data.py`

- [ ] `pip install python-docx` (đã là dependency trong pyproject; môi trường thiếu).
- [ ] Script: `seed(legal_dir: Path, fixtures: Path, actor="demo-seed") -> str` — `SnapshotManager(legal_dir).write("cli:seed-demo", actor, fn)`; `fn` đọc `tests/fixtures/legal/realestate/manifest.json`, ghi text qua `rawfiles.write_text(legal_dir/"raw", key, text)`, `upsert_document` với `raw_text_path`/`raw_checksum` mới. Idempotent (văn bản đã có cùng checksum thì bỏ qua). CLI: `python scripts/team-4.2/seed_legal_demo.py` dùng `Settings.load().data_dir/"legal"`.
- [ ] Hợp đồng mẫu: "HỢP ĐỒNG THUÊ NHÀ Ở", ký 15/03/2023 tại Hà Nội, Bên A (cho thuê) – Bên B (thuê), 12 Điều; lỗi cài sẵn: (a) Điều phạt vi phạm 20% giá trị nghĩa vụ (vượt mức 8% theo Luật Thương mại / gợi kiểm tra BLDS); (b) thiếu điều khoản quyền và nghĩa vụ bên thuê về sửa chữa (nội dung bắt buộc theo Luật Nhà ở 2014 Điều 121); (c) Bên A được đơn phương chấm dứt "bất cứ lúc nào" không báo trước — bất lợi bên thuê, liên quan Luật Nhà ở 2014 Điều 132; (d) điều khoản thanh toán mơ hồ ("thanh toán đúng hạn" không nêu hạn); có SĐT, CCCD, số tài khoản giả để thấy che PII; Điều 9 dẫn chiếu "theo Điều 4 của hợp đồng này".
- [ ] Test: seed vào tmp → snapshot published có `luat:65/2014/QH13`, `luat:27/2023/QH15`; chạy lần 2 không tạo snapshot mới. Hợp đồng mẫu đọc được bằng `load_source`.
- [ ] Chạy seed thật vào `data/team-4.2/legal` (kho hiện trống) để demo; commit script + dữ liệu.

### Task 2: Mô hình, tách đơn vị, kho

**Files:** `models.py`, `parse.py`, `store.py`; Test `tests/test_contracts_parse_store.py`

- [ ] `ContractUnit(uid: str, label: str, text: str, page: int|None)` — uid `u1..`, label "Điều 5" / "Mục II" / "Đoạn 3".
- [ ] `Contract(contract_id, filename, persist: bool, created_at, text, units, total_units, pages: list[dict], facts: dict, party: str|None ("neutral" | tên vai trò), sign_date: date|None, sign_date_source: "text"|"user"|None, reports: dict[str, dict], mask_state: MaskState)`; `contract_id = secrets.token_urlsafe(18)`.
- [ ] `split_units(text) -> list[ContractUnit]`: tách tại dòng bắt đầu `Điều \d+`, `Mục [IVX\d]+`, `\d+\.\s` cấp đầu khi không có "Điều"; không có tiêu đề nào → theo đoạn (dòng trống). Phần trước Điều đầu tiên = đơn vị "Phần mở đầu".
- [ ] `limit_units(units, n=30) -> (kept, total)`.
- [ ] `ContractStore(saved_dir)`: `add(contract)`, `get(id)` (bộ nhớ → đĩa), `save(id)` (ghi `contract.json` + `original<ext>`; `persist=True`), `delete(id)`, `list_saved(ids)`. Đọc đĩa dựng lại `mask_state` mới (placeholder có thể khác — chấp nhận ở demo).
- [ ] Tests: hợp đồng mẫu → 12 Điều + mở đầu; text không tiêu đề → đoạn; 40 Điều → kept 30 total 40; store: phiên không ghi đĩa, save ghi đĩa, delete xoá thư mục, id không hợp lệ (`../x`) → KeyError.

### Task 3: Gọi LLM JSON + thông tin nền

**Files:** `llm_json.py`, `facts.py`; Test `tests/test_contracts_facts.py`

- [ ] `ask_json(llm, system: str, payload: dict, mask_state) -> dict`: che mọi chuỗi trong payload (`mask_text`), gọi `llm.complete(system, json.dumps(...))`, bóc JSON (chấp nhận ```json fences), mở che mọi chuỗi trong kết quả; lỗi parse → `ContractAIError("AI trả kết quả không hợp lệ, hãy thử lại")`.
- [ ] `quote_ok(contract_text, quote) -> bool` (gộp khoảng trắng, NFC).
- [ ] `extract_facts(llm, contract) -> dict`: `{type, parties:[{name, role, unit, quote}], sign_date:{value, unit, quote}|None, effective_date, value, term, other_dates:[...]}`; giá trị nào có quote không khớp → bỏ (None). `sign_date` hợp lệ → `contract.sign_date`, source "text".
- [ ] Tests (FakeLLM): trích đúng; quote bịa → trường None; JSON hỏng → ContractAIError; payload gửi LLM không chứa số CCCD/SĐT mẫu.

### Task 4: Căn cứ luật tại mốc

**Files:** `evidence.py`; Test `tests/test_contracts_evidence.py`

- [ ] `LawEvidence(eid, store: "versioned"|"legacy", source_title, section, text, valid_from, valid_to, status, document_key, article_id)`.
- [ ] `find_evidence(runtime, legacy_search, query, anchor: date, k=4) -> list[LawEvidence]`: `runtime.index.search(query, anchor, anchor, k)` (nếu runtime có) + `legacy_search(query, k)`; tiêu đề từ `runtime.service.store.document(key).title`.
- [ ] `law_changes(runtime, evidence: list[LawEvidence], today: date) -> list[dict]`: với căn cứ versioned: phiên bản hiện hành của `article_id` (`store.provision_history`) — `unchanged` / `changed` (text khác) / `repealed` (luật hết hiệu lực: `laws_in_force(today)` không chứa) + luật thay thế (quan hệ `THAY_THE`/repeal ops) + điều chuyển tiếp (dùng `rag.temporal.transitions` nếu có hàm tiện, không thì tìm điều có "chuyển tiếp" trong luật mới); legacy → `untracked`.
- [ ] Tests trên kho seed (fixture): mốc 2023-03-15 tìm "chấm dứt hợp đồng thuê nhà" → có căn cứ `luat:65/2014/QH13`; `law_changes` hôm nay → `repealed`, thay bởi `luat:27/2023/QH15`.

### Task 5: Sáu thao tác + quy tắc

**Files:** `review.py`; Test `tests/test_contracts_review.py`

- [ ] `ReviewContext(llm, runtime, legacy_search, today)`.
- [ ] `summarize(ctx, contract) -> dict` (mục cố định, mỗi ý có `unit`).
- [ ] `review(ctx, contract, *, unit_ids=None, topics=None) -> Report`:
  1. phạm vi: tất cả / unit_ids / topics → LLM chọn unit (một lượt) và hiển thị phạm vi;
  2. một lượt "find issues" trên các đơn vị (≤30): `[{unit, quote, group: illegal|missing_required|unfavorable|ambiguous, severity, disadvantaged, explanation, legal_question|None, suggestion}]`;
  3. quote kiểm `quote_ok`, sai → `needs_check`;
  4. mục có `legal_question` (và nhóm missing_required luôn hỏi "nội dung bắt buộc của hợp đồng {type}") → `find_evidence` tại `sign_date`;
  5. một lượt "verify" cho mọi mục pháp lý: `[{finding, evidence_ids_supporting:[...]}]`;
  6. gán `legal_status`: có versioned hỗ trợ → `concluded`; chỉ legacy → `conditional`; không → `cannot_conclude` + câu từ chối; thiếu `sign_date` → `blocked_no_date`;
  7. nhóm `unfavorable`/`ambiguous` không có căn cứ → nhãn nhận xét thương mại;
  8. sắp: bất lợi cho `contract.party` lên đầu; `coverage = {"reviewed": kept, "total": total}`.
- [ ] `law_changes_report(ctx, contract) -> Report` (dùng căn cứ của lần soát gần nhất, chưa có thì chạy `review` trước).
- [ ] `redline(ctx, contract) -> Report` (bản cũ / đề xuất / lý do; mục cannot_conclude ghi "chưa kiểm tra pháp lý").
- [ ] `answer(ctx, contract, question, history) -> dict` (không Think): chọn đơn vị liên quan (LLM) + căn cứ → trả lời có trích dẫn; cùng quy tắc.
- [ ] Tests (FakeLLM + kho seed + kho trống): kho trống → mọi mục pháp lý cannot_conclude với đúng câu; chỉ legacy → conditional; quote bịa → needs_check; thiếu ngày ký → blocked_no_date nhưng summary chạy; JSON hỏng → ContractAIError; >30 đơn vị → coverage 30/40.

### Task 6: Xuất Word / PDF

**Files:** `export.py`; Test `tests/test_contracts_export.py`

- [ ] `report_docx(contract, report) -> bytes`, `report_pdf(contract, report) -> bytes`: tiêu đề, file, bên đã chọn, mốc, ngày tạo, "Đã soát N/M", từng mục (nhóm, mức, đơn vị + trích, bất lợi cho, giải thích, căn cứ + hiệu lực/trạng thái, gợi ý), mục từ chối, chú thích "Không thay thế tư vấn pháp lý"; redline: bảng cũ/đề xuất (gạch bỏ / gạch chân).
- [ ] PDF: `fitz.Story` + CSS `@font-face` từ font hệ thống có dấu (tìm lần lượt `C:/Windows/Fonts/arial.ttf`, `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`, `/System/Library/Fonts/Supplemental/Arial.ttf`); không tìm thấy → font mặc định + log cảnh báo. (Ruling: thay cho việc đóng gói font — không commit file font.)
- [ ] Tests: docx mở lại bằng python-docx chứa "Đã soát", tên luật, câu từ chối; pdf mở bằng fitz, text trích có "Điều" có dấu đúng.

### Task 7: API + chat (không Think)

**Files:** `ui/contracts_api.py`, `ui/server.py`; Test `tests/test_contracts_api.py`

- [ ] Routes: `POST /api/contracts` (multipart `file`, `persist`) → đọc (`load_source`, file tạm xoá ngay nếu không persist), tách, thông tin nền → JSON thẻ; `GET /api/contracts/{id}`; `POST /api/contracts/{id}/party` `{party}`; `POST /api/contracts/{id}/sign-date` `{date}` (source user); `POST /api/contracts/{id}/save`; `DELETE /api/contracts/{id}`; `POST /api/contracts/{id}/run` `{op: summary|review|partial|law_changes|redline, unit_ids?, topics?}` → report JSON (lease runtime); `GET /api/contracts/{id}/reports/{rid}.{docx|pdf}`; `GET /api/contracts?ids=a,b` (danh sách đã lưu theo id trình duyệt giữ).
- [ ] `/api/chat`: body có `contract_id` → không Think: `review.answer` (JSON và SSE một sự kiện `done`); không tìm thấy hợp đồng → 404 `{"error": "Hợp đồng này đã hết phiên — hãy đính kèm lại"}`.
- [ ] Lỗi: `ContractAIError` → 502 thông báo; file > 50 MB → 413; định dạng lạ → 400.
- [ ] Tests (TestClient, FakeLLM, kho seed tmp): upload mẫu → thẻ có các bên, ngày ký 2023-03-15; run review → có mục cannot_conclude hoặc concluded hợp lệ; tải docx/pdf 200; chat có contract_id đi đường hợp đồng; chat thường không đổi; contract_id lạ → 404.

### Task 8: Think với hợp đồng

**Files:** `agent_view.py`, `ui/contracts_api.py`; Test `tests/test_contracts_agent.py`

- [ ] `ContractAgentRetriever(contract, runtime, legacy_retriever, anchor)`: chunks = đơn vị hợp đồng **đã che** (doc_id `contract:<id>`, source `Hợp đồng: <file>`, section = label) + chunk kho có phiên bản hiệu lực tại mốc (source `Luật có phiên bản: <title> (hiệu lực từ … đến …)`) + chunk kho cũ (source giữ nguyên, section thêm "[Kho cũ — chưa xác định phiên bản]"); `capture_snapshot()` → `(revision, chunks)`; `search_candidates(query, k, *, revision, chunks, mode, dense, reranker)` → BM25 trên hợp đồng (in-memory `BM25Index`) + `runtime.index.search` + `legacy_retriever.search_candidates` hoặc `retrieve`, xen kẽ hạng; `arms = {"bm25": ..., "dense": _NullDense()}`, `reranker`, `rerank_n`.
- [ ] `AgentBaselineView(retriever, llm, condenser, context_config, top_k)` — đúng các thuộc tính `AgentPipeline` dùng.
- [ ] Chạy: che câu hỏi + lịch sử bằng `contract.mask_state` → `AgentPipeline(view, config).ask_stream/ask_debug` → mở che `answer`, `citations[*].quote/text`, `sources[*].text`.
- [ ] Hậu kiểm pháp lý: nếu không có citation từ nguồn "Luật có phiên bản" → thêm cảnh báo `Chưa có căn cứ luật có phiên bản tại ngày ký — các kết luận pháp lý (nếu có) chưa thể khẳng định. Có thể upload luật ở /upload.` và hạ `status` `answer` → `partial`.
- [ ] `/api/chat` `contract_id` + `think=true` → đường này (JSON + SSE).
- [ ] Tests: retriever gộp 3 nguồn; agent (FixtureLLM kiểu test_agent) đi theo dẫn chiếu "Điều 4 của hợp đồng này"; LLM không bao giờ nhận số CCCD mẫu; chỉ nguồn hợp đồng/kho cũ → partial + cảnh báo; `tests/test_agent.py` vẫn 37/37.

### Task 9: Giao diện

**Files:** `ui/index.html`; Test `tests/test_server_docs.py` (id có mặt)

- [ ] Nút "+": menu "Nạp tài liệu vào kho" (cũ) / "Đính kèm hợp đồng để soát" (mới, hộp chọn file + "Chỉ trong phiên này"/"Lưu lại").
- [ ] Thẻ hợp đồng trong luồng chat: tên file, số trang / chất lượng, các bên → chip "Tôi là …" + "Trung lập", ngày ký (sửa được, nhãn nguồn), 6 nút, "Lưu hợp đồng này", "Gỡ".
- [ ] Công tắc chế độ trên ô nhập: "Hỏi tự do" / "Hỏi với hợp đồng: <file>"; nhãn chế độ trên tin nhắn người dùng; nút 6 chuyển chế độ.
- [ ] Hiển thị báo cáo: "Đã soát N/M", nhóm theo mức, mỗi mục: đơn vị + trích, bất lợi cho, giải thích, căn cứ (hiệu lực + trạng thái) / câu từ chối + link /upload, nhãn nhận xét thương mại, gợi ý; "Đối chiếu thay đổi": bảng luật tại ngày ký → hiện hành; redline: cũ / đề xuất tô khác biệt; nút "Tải Word" / "Tải PDF"; đang chạy → spinner "AI đang soát…".
- [ ] Ngăn "Hợp đồng đã lưu" (ids trong localStorage, try/catch); thẻ trỏ hợp đồng đã mất → "Hợp đồng này đã hết phiên — hãy đính kèm lại", khoá nút.
- [ ] Escape mọi chuỗi server; 390px không cuộn ngang.

### Task 10: Chạy demo thật + review cuối

- [ ] Khởi động server với `.env` thật, đính kèm hợp đồng mẫu, chọn "bên thuê", chạy cả 6 thao tác + một câu Think ("Nếu bên thuê chậm trả tiền 2 tháng thì bên cho thuê được làm gì?"), tải Word/PDF; ghi lại kết quả và lỗi gặp phải (sửa trong task sở hữu).
- [ ] Toàn bộ test suite: không lỗi mới so với baseline.
- [ ] Một lượt review toàn phần 4 (subagent, model mạnh nhất) → sửa một đợt → báo người dùng.
