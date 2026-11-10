# Kho luật có phiên bản (Legal Version Builder) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng kho luật từ vbpl.vn trả lời được "tại ngày X, điều/khoản/điểm này của luật Y có nội dung gì và đã xác minh tới đâu", bằng cách tự áp dụng các thao tác sửa đổi theo ngày hiệu lực của từng thao tác.

**Architecture:** Package mới `rag.legal`. Văn bản thô (crawl) → cây Provision → thao tác sửa đổi (bất biến, là nguồn sự thật) → ProvisionVersion dẫn xuất, dựng lại được hoàn toàn → SQLite. Không LLM trong đường dựng. Trang `/review` trong app Starlette cho người duyệt.

**Tech Stack:** Python 3.12, sqlite3 (stdlib), pyyaml, requests + beautifulsoup4 (đã có), Starlette (UI hiện có), pytest.

**Spec:** `app/team-4.2/docs/superpowers/specs/2026-11-09-legal-version-builder-design.md`

## Global Constraints

- Mọi đường dẫn tương đối tính từ `app/team-4.2/`. Code ở `src/rag/legal/`, test ở `tests/test_legal_*.py`, fixture ở `tests/fixtures/legal/`.
- Chạy test: `python -m pytest -q tests/test_legal_<x>.py` từ `app/team-4.2/`. Cả bộ test cũ (522 test) phải vẫn pass.
- **Không commit, không push** khi chưa được người dùng cho phép. Bước "Checkpoint" ở cuối mỗi task = chạy toàn bộ test, không commit.
- Không dùng LLM trong parse/dựng phiên bản. Test không gọi mạng (dùng client giả).
- Chỉ dùng hai endpoint công khai đã có trong `src/rag/ingest/vbpl.py`: `POST {API_BASE}/all` và `GET {API_BASE}/{id}`. Không thử endpoint khác.
- Khoảng hiệu lực nửa mở `[valid_from, valid_to)`; `valid_to=None` = chưa kết thúc. `as_of(d)` chọn bản có `valid_from <= d < valid_to`.
- Text luôn NFC. Khoá văn bản = `<loại>:<số hiệu chuẩn hoá>` (`luat:59/2020/QH14`, `bo-luat:91/2015/QH13`, `nghi-quyet:...`, `vbhn:43/VBHN-VPQH`).
- Không tin `effFrom`/`effTo` của vbpl để dựng; chỉ dùng đối chiếu.
- Dữ liệu chạy thật dưới `DATA_DIR/legal/` (`catalog.sqlite`, `raw/`). Seed ở `data/team-4.2/legal/seeds.yaml` (được commit sau này).
- Trạng thái và lý do là chuỗi cố định có tiền tố (`effectivity.*`, `operation.*`, `vbhn.*`, `discovery.*`), không chép đoạn text dài vào lý do.

## Review Focus

1. Nội dung mới trong ngoặc kép kéo dài nhiều dòng, chứa cả khoản/điểm con, kết thúc bằng `".` hoặc `”;` → phải lấy trọn, không cắt ở dòng đầu (test ở Task 4).
2. Ngoặc kép thẳng `"` và cong `“ ”` đều xuất hiện trong văn bản vbpl → hai kiểu phải cho kết quả giống nhau (Task 4).
3. Số hiệu đơn vị có hậu tố: `Điều 33a`, `khoản 5a`, `điểm g1`, `điểm đ` → id và thứ tự đúng, `5a` đứng sau `5` (Task 2, Task 7).
4. "Điều N" xuất hiện giữa câu ("theo quy định tại Điều 5 của Luật này") hoặc trong đoạn trích dẫn của văn bản sửa đổi → không được mở Điều mới trong cây cấu trúc (Task 2).
5. Hai văn bản sửa đổi khác nhau cùng sửa một khoản, cùng ngày hiệu lực → `conflicted`, không lấy bừa một bản (Task 8).

---

### Task 1: Khung package, model, khoá, fixture thật

**Files:**
- Create: `src/rag/legal/__init__.py`, `src/rag/legal/models.py`, `src/rag/legal/keys.py`
- Create: `tests/fixtures/legal/luat_59_2020_QH14.txt`, `tests/fixtures/legal/luat_03_2022_QH15.txt` (chép từ text đã crawl qua `VbplClient` + `html_to_text`; script tạo: `python -m rag.legal fixture 59/2020/QH14 03/2022/QH15 --out tests/fixtures/legal` thêm ở Task 12, ở task này chép tay bằng một lệnh Python một dòng dùng `search_by_number`/`pick_detail`/`html_to_text`)
- Modify: `pyproject.toml` (thêm `"pyyaml"` vào `dependencies`)
- Test: `tests/test_legal_keys.py`

**Interfaces:**
- Produces (`models.py`, mọi dataclass `frozen=True`):
  - `OperationType` Literal: `REPLACE_ARTICLE, REPLACE_ARTICLE_TITLE, REPLACE_CLAUSE, REPLACE_CLAUSE_LEAD_IN, REPLACE_POINT, INSERT_ARTICLE, INSERT_CLAUSE, INSERT_POINT, DELETE_ARTICLE, DELETE_CLAUSE, DELETE_POINT, REPLACE_TEXT, AMEND_TEXT, REPEAL_DOCUMENT, UNSUPPORTED`
  - `ParseStatus = Literal["exact","partial","unsupported","failed"]`; `ReviewStatus = Literal["auto_accepted","pending","approved","rejected"]`; `VerificationStatus = Literal["verified","needs_review","conflicted"]`; `ProvisionKind = Literal["article","article_title","clause","clause_lead_in","point"]`
  - `Address(article: str, clause: str|None=None, point: str|None=None, part: Literal["whole","title","lead_in"]="whole")`
  - `LegalDocument(document_key, vbpl_id, title, doc_type, doc_number, issuer, issued_on: date|None, vbpl_effective_from: date|None, vbpl_effective_to: date|None, eff_status: str|None, is_consolidated: bool, raw_text_path: str, raw_checksum: str, fetched_at: datetime, discovered_via: str|None=None)`
  - `DocumentRelation(source_key, target_key, relation: str, evidence: str, status: Literal["detected","confirmed","rejected"])` — `relation` dùng mã vbpl (`SUA_DOI_BO_SUNG`, `THAY_THE`, `HOP_NHAT`, `BAI_BO`).
  - `Provision(provision_id, document_key, kind: ProvisionKind, address: Address, parent_id: str|None, order: int, heading_path: tuple[str,...], text: str, span: tuple[int,int])`
  - `AmendmentOperation(operation_id, source_document_key, source_issued_on: date|None, source_locator: str, source_address: Address|None, source_span: tuple[int,int], sequence: int, target_document_key: str|None, target_law_name: str|None, operation_type: OperationType, target: Address|None, anchor: Address|None, new_text: str|None, old_phrase: str|None, effective_from: date|None, parse_status: ParseStatus, review_status: ReviewStatus, status_reasons: tuple[str,...]=(), old_text: str|None=None, reviewer: str|None=None, reviewed_at: datetime|None=None, review_note: str|None=None, supersedes_operation_id: str|None=None)`
  - `ProvisionVersion(provision_id, document_key, kind: ProvisionKind, text: str, valid_from: date, valid_to: date|None, verification_status: VerificationStatus, status_reasons: tuple[str,...], notes: tuple[str,...], source_operations: tuple[str,...], build_id: str)`
  - `BuildRun(build_id, document_key, operation_ids: tuple[str,...], inputs_checksum: str, built_at: datetime, code_version: str)`
  - `ReviewItem(review_id, kind: Literal["operation","vbhn_mismatch","discovery"], document_key: str, operation_id: str|None, provision_id: str|None, reasons: tuple[str,...], status: Literal["open","resolved"], created_at: datetime, payload: dict)`
  - `ReviewDecision(review_id, action: Literal["approve","reject","correct"], reviewer: str, note: str, corrected_fields: dict, decided_at: datetime)`
- Produces (`keys.py`):
  - `document_key(doc_type: str, doc_number: str) -> str` — map loại: `Luật→luat`, `Bộ luật→bo-luat`, `Nghị quyết→nghi-quyet`, `Văn bản hợp nhất`/số chứa `VBHN`→`vbhn`, khác → slug ASCII; số hiệu bỏ khoảng trắng, viết hoa.
  - `provision_id(document_key: str, address: Address, kind: ProvisionKind) -> str` — `#d60`, `#d49.title`, `#d60.k2`, `#d49.k1.lead`, `#d60.k2.e`.
  - `parse_provision_id(pid: str) -> tuple[str, Address, ProvisionKind]`
  - `unit_sort_key(label: str) -> tuple` — `"5" < "5a" < "6"`; điểm theo bảng chữ cái tiếng Việt `a, b, c, d, đ, e, g, h, i, k, l, m, n, o, p, q, r, s, t, u, v, x, y`; `g1` ngay sau `g`.

- [ ] **Step 1: Viết test** `tests/test_legal_keys.py`:
  `test_document_key_prefixes_type` — `document_key("Luật","59/2020/QH14")=="luat:59/2020/QH14"`, `document_key("Bộ luật","91/2015/QH13")=="bo-luat:91/2015/QH13"`, `document_key("Nghị quyết","91/2015/QH13")=="nghi-quyet:91/2015/QH13"`, `document_key("Văn bản hợp nhất","43/VBHN-VPQH")=="vbhn:43/VBHN-VPQH"`, `document_key("Luật"," 59 / 2020 / qh14 ")=="luat:59/2020/QH14"`.
  `test_provision_id_roundtrip` — với 5 dạng ở trên, `parse_provision_id(provision_id(k,a,kind)) == (k,a,kind)`.
  `test_unit_sort_key_vietnamese_order` — `sorted(["e","đ","d","g1","g","a"], key=unit_sort_key)==["a","d","đ","e","g","g1"]`; `sorted(["5a","6","5","10"], key=unit_sort_key)==["5","5a","6","10"]`.
  `test_fixtures_present` — hai file fixture tồn tại, file 59/2020 có đúng 218 dòng khớp `^Điều \d+[a-zđ]?\. `, file 03/2022 chứa dòng `Điều 7. Sửa đổi, bổ sung một số điều của Luật Doanh nghiệp`.
- [ ] **Step 2: Chạy test, xác nhận FAIL** (`ModuleNotFoundError: rag.legal`).
- [ ] **Step 3: Viết `models.py`, `keys.py`, tạo fixture, thêm `pyyaml` vào `pyproject.toml`.**
- [ ] **Step 4: Chạy `python -m pytest -q tests/test_legal_keys.py` → PASS.**
- [ ] **Step 5: Checkpoint:** `python -m pytest -q` → toàn bộ pass.

---

### Task 2: Parser cấu trúc văn bản → cây Provision

**Files:**
- Create: `src/rag/legal/structure.py`
- Test: `tests/test_legal_structure.py`

**Interfaces:**
- Consumes: `Provision`, `Address`, `provision_id`, `unit_sort_key` (Task 1).
- Produces: `parse_structure(text: str, document_key: str) -> list[Provision]` — thứ tự đọc; `index_provisions(provisions) -> dict[str, Provision]` (theo `provision_id`).

Quy tắc (chỉ những gì test chưa tự quyết định):
- Dòng Điều: `^Điều\s+(\d+[a-zđ]?)\s*[.:]\s*(.*)$` ở **đầu dòng**, dòng đó không nằm trong đoạn trích dẫn.
- Khoản: `^(\d+[a-zđ]?)\.\s+` ; Điểm: `^([a-zđ]\d*)\)\s+` — chỉ khi đang ở trong một Điều (điểm phải ở trong khoản).
- Heading `^(Phần|Chương|Mục|Tiểu mục)\b` → cập nhật `heading_path` (tiêu đề heading là dòng ngay sau nếu dòng heading chỉ có số).
- **Đoạn trích dẫn:** dòng bắt đầu bằng `"` hoặc `“` mở chế độ trích dẫn; chế độ kết thúc ở dòng có dấu đóng `"`/`”` ở cuối (cho phép theo sau bởi `.`, `;`, `,`). Dòng trong trích dẫn được nối vào text của provision hiện tại, không bao giờ tạo Điều/Khoản/Điểm.
- `article` text = toàn bộ Điều (dòng tiêu đề + thân). `article_title` text = phần sau "Điều N." trên dòng tiêu đề. `clause` text = toàn bộ khoản kể cả các điểm. `clause_lead_in` chỉ tạo khi khoản có điểm: text từ đầu khoản tới trước điểm đầu tiên. Dòng thân Điều trước khoản đầu tiên (Điều không chia khoản) thuộc text `article`, không tạo provision riêng.
- `span` = offset `[start, end)` trong `text` đầu vào (sau NFC).

- [ ] **Step 1: Viết test:**
  `test_real_law_has_218_articles` — fixture 59/2020: số provision `kind=="article"` == 218; `Điều 60` có `article_title` text `"Biên bản họp Hội đồng thành viên"`.
  `test_clause_points_and_lead_in` — 59/2020: các điểm của `#d60.k2` theo thứ tự là `["a","b","c","d","đ","e","g"]`; `#d60.k2.lead` tồn tại và text bắt đầu bằng `"2. Biên bản họp Hội đồng thành viên phải thông qua"`; `#d60.k3` text bắt đầu bằng `"3. Trường hợp chủ tọa"`.
  `test_heading_path` — `#d1` có `heading_path[0].startswith("Chương I")`.
  `test_suffix_units` — text giả `"Điều 33a. Tên\n1. A\n5a. B\nb1) C"`: id có `#d33a`, `#d33a.k5a`, và `b1` là điểm của `k5a`.
  `test_inline_article_reference_not_heading` — `"Điều 5. X\n1. Theo quy định tại Điều 7 của Luật này.\nĐiều 6. Y"` → đúng 2 article (`5`, `6`).
  `test_quoted_block_is_not_structure` — fixture 03/2022: số article == 11 (Điều 1–11); `#d7.k3` (của văn bản sửa đổi) text chứa `"3. Trường hợp chủ tọa"` ở trong trích dẫn và không tạo `#d7.k3.b`-con nào từ dòng trích dẫn; dòng trích dẫn `"Điều 10a. Khen thưởng..."` giả lập trong một khoản không tạo article `10a`.
  `test_spans_cover_text` — với mọi provision của 59/2020, `text_in[p.span[0]:p.span[1]].strip() == p.text.strip()`.
- [ ] **Step 2: Chạy, xác nhận FAIL.**
- [ ] **Step 3: Viết `parse_structure` (máy trạng thái theo dòng) và `index_provisions`.**
- [ ] **Step 4: Chạy `tests/test_legal_structure.py` → PASS.**
- [ ] **Step 5: Checkpoint toàn bộ test.**

---

### Task 3: Điều hiệu lực, thay thế, chuyển tiếp

**Files:**
- Create: `src/rag/legal/effectivity.py`
- Modify: `src/rag/versioning/effectivity_guard.py` — tách thân của `unsupported_effectivity_reasons` thành `effectivity_reasons_for_text(text: str, *, effective_from: date|None) -> tuple[str,...]`; hàm cũ gọi hàm mới (hành vi giữ nguyên, test cũ phải pass).
- Test: `tests/test_legal_effectivity.py`

**Interfaces:**
- Consumes: `Provision`, `Address` (Task 1), `parse_structure` (Task 2).
- Produces:
  - `parse_vn_date(s: str) -> date|None` — `"ngày 01 tháng 3 năm 2022"`, `"01/03/2022"`, `"2022-03-01"`; ngày không hợp lệ → `None`.
  - `RepealStatement(target_name: str, target_number: str|None, effective: date|None, has_exception: bool, span: tuple[int,int])`
  - `EffectivityInfo(article: str|None, default_from: date|None, exceptions: tuple[tuple[Address, date], ...], repeals: tuple[RepealStatement, ...], transition_article: str|None, flags: tuple[str, ...])`
  - `parse_effectivity(provisions: Sequence[Provision]) -> EffectivityInfo`
  - `effective_date_for(info: EffectivityInfo, address: Address|None) -> date|None` — ngoại lệ khớp chính xác nhất (điểm > khoản > Điều) thắng; không có thì `default_from`.

Quy tắc: Điều hiệu lực = Điều có `article_title` khớp `hiệu lực thi hành|hiệu lực` (casefold); Điều chuyển tiếp = tiêu đề chứa `chuyển tiếp`. Ngày chung = ngày đầu tiên sau mỏ neo "có hiệu lực (thi hành) (kể) từ". Ngoại lệ: câu `(Khoản|Điểm|Điều) ... (của Luật này)? có hiệu lực (thi hành)? (kể)? từ ngày D` → `Address` trong chính văn bản này. Thay thế: câu `<Luật|Bộ luật> <tên> (số <số hiệu>)? hết hiệu lực (thi hành)? kể từ (ngày Luật này có hiệu lực thi hành|ngày D)` → `RepealStatement` (effective = `default_from` cho mẫu đầu); `has_exception` khi cùng câu có `trừ|ngoại trừ|trường hợp quy định tại`. `flags` = `effectivity_reasons_for_text(text Điều hiệu lực, effective_from=default_from)` trừ lý do `transition` (chuyển tiếp đã có trường riêng).

- [ ] **Step 1: Viết test:**
  `test_real_amending_law_single_date` — 03/2022: `default_from == date(2022,3,1)`, `article=="10"`, `transition_article=="11"`, `exceptions==()`.
  `test_unit_exception` — text giả: `"Điều 3. Hiệu lực thi hành\n1. Luật này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2026.\n2. Khoản 3 Điều 1 của Luật này có hiệu lực từ ngày 01 tháng 01 năm 2027."` → `default_from==date(2026,7,1)`, `exceptions==((Address("1","3"), date(2027,1,1)),)`; `effective_date_for(info, Address("1","3","a"))==date(2027,1,1)`, `effective_date_for(info, Address("1","2"))==date(2026,7,1)`.
  `test_repeal_statement` — `"...2. Luật Nhà ở số 65/2014/QH13 hết hiệu lực kể từ ngày Luật này có hiệu lực thi hành."` với default 2024-08-01 → `repeals[0].target_number=="65/2014/QH13"`, `target_name=="Luật Nhà ở"`, `effective==date(2024,8,1)`, `has_exception is False`.
  `test_relative_date_flag` — `"Luật này có hiệu lực sau 45 ngày kể từ ngày ký."` → `default_from is None`, có flag bắt đầu `effectivity.relative_date`.
  `test_invalid_date` — `"... từ ngày 31 tháng 02 năm 2026"` → `default_from is None`, flag `effectivity.invalid_date`.
  `test_old_guard_unchanged` — chạy `python -m pytest -q tests/test_effectivity_guard.py` vẫn pass (không phải test mới, là bước verify ở Step 4).
- [ ] **Step 2: Chạy, FAIL.**
- [ ] **Step 3: Viết `effectivity.py`; refactor `effectivity_guard.py`.**
- [ ] **Step 4: Chạy `tests/test_legal_effectivity.py tests/test_effectivity_guard.py` → PASS.**
- [ ] **Step 5: Checkpoint.**

---

### Task 4: Parser chỉ dẫn sửa đổi

**Files:**
- Create: `src/rag/legal/directives.py`
- Test: `tests/test_legal_directives.py`

**Interfaces:**
- Consumes: `parse_structure` (Task 2), `Address`, `OperationType`, `ParseStatus` (Task 1).
- Produces:
  - `ParsedDirective(source_locator: str, source_address: Address, source_span: tuple[int,int], sequence: int, target_law_name: str|None, target_law_number: str|None, operation_type: OperationType, target: Address|None, anchor: Address|None, new_text: str|None, old_phrase: str|None, parse_status: ParseStatus, reasons: tuple[str,...])`
  - `parse_directives(provisions: Sequence[Provision]) -> list[ParsedDirective]` — `sequence` tăng dần theo thứ tự đọc.
  - `strip_quotes(text: str) -> str` — bỏ dấu ngoặc mở/đóng của đoạn trích dẫn và dấu `.`/`;` ngay sau dấu đóng.

Cách duyệt (không do test quyết định): mỗi Điều của văn bản sửa đổi xác định **luật đích** từ tiêu đề Điều (`... của <Luật|Bộ luật> <tên>( số <số hiệu>)?`). Tiêu đề Điều có thể **tự là chỉ dẫn** (`Điều 4. Sửa đổi, bổ sung khoản 1 Điều 23 của Luật Nhà ở`). Trong Điều: mỗi khoản là một chỉ dẫn; nếu khoản có địa chỉ chỉ tới Điều (`một số điểm, khoản của Điều 17 như sau:`) thì các điểm `a)`, `b)` là chỉ dẫn con kế thừa Điều đó. Hành động: `sửa đổi(, bổ sung)?` → REPLACE_*; `bổ sung <đơn vị> X vào sau <đơn vị> Y` → INSERT_* với `anchor`; `bãi bỏ` → DELETE_*; `sửa đổi(, bổ sung)? tên (điều|Điều N)` → REPLACE_ARTICLE_TITLE; `đoạn mở đầu khoản N` → REPLACE_CLAUSE_LEAD_IN; `thay (cụm )?từ "X" bằng (cụm từ )?"Y"` → REPLACE_TEXT (`old_phrase`=X, `new_text`=Y); `Phụ lục|Biểu|bảng|số thứ tự` trong địa chỉ → UNSUPPORTED. Một chỉ dẫn nêu nhiều đích (`điểm b và điểm c khoản 4`, `khoản 1 và khoản 2 Điều 148`, `tên điều và đoạn mở đầu khoản 1 Điều 49`, `điểm g và bổ sung điểm g1 vào sau điểm g khoản 1 Điều 31`) tách thành nhiều `ParsedDirective`; nội dung trích dẫn chia theo dòng mở đầu đơn vị (`Điều N.`, `N.`, `x)`) khớp với từng đích — không chia được thì mọi directive con là `partial` với lý do `operation.cannot_split_content`. REPLACE_TEXT có cụm `tại một số điều|trong toàn bộ|tại các điều` mà không liệt kê đơn vị → `partial`, lý do `operation.bulk_text_scope`.

- [ ] **Step 1: Viết test.** Hàm trợ giúp `ops(directives)` = list `(operation_type, target, anchor)`.
  `test_real_enterprise_law_article_7` — 03/2022, lọc `target_law_name=="Luật Doanh nghiệp"`: đúng 10 directive, theo thứ tự:
  `REPLACE_ARTICLE_TITLE d49`, `REPLACE_CLAUSE_LEAD_IN d49.k1`, `REPLACE_ARTICLE_TITLE d50`, `REPLACE_POINT d60.k2.e`, `REPLACE_CLAUSE d60.k3`, `REPLACE_POINT d109.k1.d`, `REPLACE_CLAUSE d148.k1`, `REPLACE_CLAUSE d148.k2`, `REPLACE_CLAUSE d158.k2`, `REPLACE_CLAUSE d217.k5`; tất cả `parse_status=="exact"`; `source_locator` của cái thứ 5 là `"Điều 7 > 3 > b"`; `new_text` của `d60.k3` bắt đầu `"3. Trường hợp chủ tọa, người ghi biên bản từ chối ký"` và kết thúc `"pháp luật có liên quan."` (không còn dấu ngoặc).
  `test_real_public_investment_nested` — 03/2022 Điều 1 (Luật Đầu tư công), directive từ khoản 1: `REPLACE_POINT d17.k4.b`, `REPLACE_POINT d17.k4.c`, `DELETE_POINT d17.k4.d`, `INSERT_CLAUSE d17.k5a anchor d17.k5`.
  `test_real_insert_point_after` — Điều 3 khoản 1: `REPLACE_POINT d31.k1.g` và `INSERT_POINT d31.k1.g1 anchor d31.k1.g`.
  `test_real_unsupported_appendix` — Điều 3 khoản 5 (Phụ lục IV) và Điều 8 (Biểu thuế) → `UNSUPPORTED`, `parse_status=="unsupported"`.
  `test_title_is_directive` — Điều 4 (`Sửa đổi, bổ sung khoản 1 Điều 23 của Luật Nhà ở`) → một `REPLACE_CLAUSE d23.k1`, `target_law_name=="Luật Nhà ở"`.
  `test_replace_whole_article` — Điều 9 khoản 1 → `REPLACE_ARTICLE d55`, `new_text` bắt đầu `"Điều 55."`.
  `test_multiline_quoted_clause_with_points` — 03/2022 Điều 7 khoản 5: `new_text` của `d148.k1` chứa các dòng `b) Thay đổi ngành, nghề và lĩnh vực kinh doanh;` và `c) Thay đổi cơ cấu tổ chức quản lý công ty;` (Review Focus 1).
  `test_curly_and_straight_quotes_equal` — cùng một Điều giả lập dùng `"..."` và `“...”` → `new_text` giống hệt (Review Focus 2).
  `test_bulk_replace_text_is_partial` — `"Thay cụm từ “Bộ Kế hoạch và Đầu tư” bằng cụm từ “Bộ Tài chính” tại một số điều của Luật Doanh nghiệp."` → `REPLACE_TEXT`, `partial`, `old_phrase=="Bộ Kế hoạch và Đầu tư"`, lý do chứa `operation.bulk_text_scope`.
  `test_scoped_replace_text_is_exact` — `"Thay cụm từ “X” bằng cụm từ “Y” tại khoản 2 Điều 10."` → `exact`, `target==Address("10","2")`.
  `test_no_directive_text_returns_empty` — văn bản gốc 59/2020 → `[]`.
- [ ] **Step 2: Chạy, FAIL.**
- [ ] **Step 3: Viết `directives.py`.**
- [ ] **Step 4: Chạy `tests/test_legal_directives.py` → PASS.**
- [ ] **Step 5: Checkpoint.**

---

### Task 5: Phân giải luật đích và định vị đơn vị

**Files:**
- Create: `src/rag/legal/targets.py`
- Test: `tests/test_legal_targets.py`

**Interfaces:**
- Consumes: `LegalDocument`, `Address`, `Provision`, `provision_id` (Task 1).
- Produces:
  - `law_name(title: str) -> str` — `"Luật Doanh nghiệp số 59/2020/QH14" → "luật doanh nghiệp"` (casefold, NFC, bỏ phần từ `" số "`, bỏ năm `" 2020"` ở cuối).
  - `resolve_target_law(name: str|None, number: str|None, *, before: date|None, documents: Sequence[LegalDocument]) -> tuple[str|None, tuple[str,...]]` — có `number` → khớp số hiệu (bất kể loại nếu chỉ một ứng viên Luật/Bộ luật); không có → các văn bản không phải VBHN cùng `law_name`, `issued_on < before`, lấy bản `issued_on` lớn nhất; 0 ứng viên → `(None, ("operation.target_law_not_found",))`; số hiệu và tên mâu thuẫn → `(None, ("operation.target_law_mismatch",))`.
  - `locate(index: Mapping[str, Provision], document_key: str, address: Address) -> Provision|None` — `part="title"` → provision `article_title`, `part="lead_in"` → `clause_lead_in`.

- [ ] **Step 1: Viết test:**
  `test_law_name_normalizes` — `law_name("Luật Doanh nghiệp số 59/2020/QH14")=="luật doanh nghiệp"`; `law_name("Luật Nhà ở 2014")=="luật nhà ở"`.
  `test_resolve_latest_before_amendment` — documents: Luật Doanh nghiệp 68/2014 (2014-11-26) và 59/2020 (2020-06-17); `resolve_target_law("Luật Doanh nghiệp", None, before=date(2022,1,11), ...)` → `("luat:59/2020/QH14", ())`; `before=date(2018,1,1)` → `luat:68/2014/QH13`.
  `test_resolve_by_number_ignores_resolution_collision` — documents chứa `nghi-quyet:91/2015/QH13` và `bo-luat:91/2015/QH13`; `resolve_target_law("Bộ luật Dân sự","91/2015/QH13",...)` → `bo-luat:91/2015/QH13`.
  `test_resolve_missing` — tên không có → `(None, ("operation.target_law_not_found",))`.
  `test_locate_parts` — trên index 59/2020: `locate(.., Address("49",part="title"))` là `article_title` của Điều 49; `Address("49","1",part="lead_in")` → `None` nếu khoản 1 Điều 49 không có điểm, ngược lại là `clause_lead_in` (khẳng định theo fixture thật).
- [ ] **Step 2–4:** FAIL → viết `targets.py` → PASS.
- [ ] **Step 5: Checkpoint.**

---

### Task 6: Lắp ráp AmendmentOperation và quy tắc tự xác minh

**Files:**
- Create: `src/rag/legal/operations.py`
- Test: `tests/test_legal_operations.py`

**Interfaces:**
- Consumes: `ParsedDirective`, `parse_directives` (Task 4); `EffectivityInfo`, `effective_date_for`, `RepealStatement` (Task 3); `resolve_target_law`, `locate` (Task 5).
- Produces:
  - `operation_id_for(source_key: str, sequence: int, operation_type: str, target: Address|None) -> str` — sha1 16 ký tự hex, tất định.
  - `build_operations(source: LegalDocument, directives: Sequence[ParsedDirective], effectivity: EffectivityInfo, *, documents: Sequence[LegalDocument], indexes: Mapping[str, Mapping[str, Provision]]) -> list[AmendmentOperation]` — `indexes`: document_key → index provision của luật đích (luật đích chưa có trong kho → không có key).
  - `repeal_operations(source: LegalDocument, effectivity: EffectivityInfo, *, documents) -> list[AmendmentOperation]` — một `REPEAL_DOCUMENT` cho mỗi `RepealStatement`, `target=None`.
  - `AUTO_ACCEPT_RULES` docstring liệt kê đúng 5 điều kiện dưới.

Tự xác minh (`review_status="auto_accepted"`) khi **đủ cả**: `parse_status=="exact"`; `effective_from` khác None; luật đích phân giải được; đơn vị đích tồn tại (`REPLACE_*`, `DELETE_*`, `REPLACE_TEXT`) hoặc `anchor` tồn tại và đơn vị mới chưa tồn tại (`INSERT_*`); với `REPLACE_CLAUSE`/`REPLACE_POINT`/`REPLACE_ARTICLE`/`INSERT_*` thì `new_text` bắt đầu bằng đúng nhãn đơn vị (`"3. "`, `"e) "`, `"Điều 55."`) và với `REPLACE_TEXT` thì `old_phrase` xuất hiện **đúng một lần** trong text đơn vị đích. Không đủ → `pending`, `status_reasons` ghi điều kiện hỏng (`operation.no_effective_date`, `operation.target_missing`, `operation.label_mismatch`, `operation.phrase_not_unique`, cộng lý do từ parser). `effective_from = effective_date_for(effectivity, directive.source_address)`; nếu `effectivity.flags` khác rỗng → mọi thao tác `pending` kèm các flag. `UNSUPPORTED`, `partial`, `failed` luôn `pending`. Nếu `effectivity.transition_article` khác None, mọi thao tác của văn bản nguồn thêm reason `note:transition:<source_key>#d<N>` (builder chuyển thành `notes`, phần 2 dùng để nhắc kiểm tra chuyển tiếp). `REPEAL_DOCUMENT` tự xác minh khi phân giải được đích, có `effective`, và `has_exception=False`; có ngoại lệ → vẫn auto_accepted nhưng thêm reason `note:transition_exception` (builder chuyển thành `notes`).

- [ ] **Step 1: Viết test:**
  `test_real_enterprise_ops_auto_accepted` — dùng fixture 59/2020 + 03/2022 (documents có 59/2020 issued 2020-06-17, 03/2022 issued 2022-01-11): 10 thao tác cho `luat:59/2020/QH14`, tất cả `auto_accepted`, `effective_from==date(2022,3,1)`.
  `test_unknown_target_law_pending` — các thao tác cho Luật Đầu tư công (không có trong documents) → `pending`, reason chứa `operation.target_law_not_found`.
  `test_label_mismatch_pending` — sửa `new_text` của thao tác `d60.k3` thành bắt đầu `"4. "` (dựng ParsedDirective giả) → `pending`, `operation.label_mismatch`.
  `test_flags_make_everything_pending` — EffectivityInfo có `flags=("effectivity.relative_date: ...",)` → mọi thao tác `pending`.
  `test_operation_id_deterministic` — chạy `build_operations` hai lần → cùng danh sách id.
  `test_transition_note_attached` — 03/2022 (có Điều 11 chuyển tiếp) → mọi thao tác có reason `note:transition:luat:03/2022/QH15#d11`.
  `test_repeal_operation` — RepealStatement Luật Nhà ở 65/2014, documents có `luat:65/2014/QH13` → một `REPEAL_DOCUMENT`, `target_document_key=="luat:65/2014/QH13"`, `auto_accepted`.
- [ ] **Step 2–4:** FAIL → viết → PASS.
- [ ] **Step 5: Checkpoint.**

---

### Task 7: Version builder — áp dụng thao tác theo thời gian

**Files:**
- Create: `src/rag/legal/builder.py`
- Test: `tests/test_legal_builder.py`

**Interfaces:**
- Consumes: `Provision`, `AmendmentOperation`, `ProvisionVersion` (Task 1); `EffectivityInfo`, `effective_date_for` (Task 3); `unit_sort_key`.
- Produces:
  - `build_versions(document: LegalDocument, provisions: Sequence[Provision], effectivity: EffectivityInfo, operations: Sequence[AmendmentOperation], *, build_id: str) -> list[ProvisionVersion]`
  - `applicable(op: AmendmentOperation) -> bool` — `review_status in {"auto_accepted","approved"}` và `effective_from is not None`.

Thuật toán (không do test quyết định hết):
- Trạng thái là cây lá: mỗi Điều có `title`, `intro` (thân trước khoản đầu), danh sách khoản; mỗi khoản có `lead_in` (hoặc toàn văn nếu không có điểm) và danh sách điểm. Text của `article`/`clause` luôn **render lại từ lá** (dòng `Điều N. <title>`, rồi intro, rồi các khoản theo `unit_sort_key`; khoản = lead_in + các điểm).
- Phiên bản đầu: mỗi provision `valid_from = effective_date_for(effectivity, address)`; nếu `None` thì dùng `document.vbpl_effective_from` và thêm reason `effectivity.unresolved` (Task 8 biến thành `needs_review`).
- Thao tác áp dụng sắp theo `(effective_from, source_issued_on or date.min, source_document_key, sequence)`. Gom theo `effective_from`: áp mọi thao tác cùng ngày, render lại, so text từng provision với trạng thái trước → provision đổi text: đóng bản cũ `valid_to=ngày`, mở bản mới với `source_operations` = các thao tác chạm vào nó (gồm thao tác trên con của nó). Provision bị xoá: đóng, không mở. Provision mới (INSERT): mở bản mới. Điều đổi tên/đoạn mở đầu: chỉ lá tương ứng đổi.
- `REPLACE_ARTICLE` thay toàn bộ cây con của Điều bằng cây parse từ `new_text` (dùng `parse_structure` trên `new_text`, ánh xạ về document_key đích). `REPLACE_CLAUSE` tương tự cho khoản (parse điểm con). Ghi `old_text` không cần trong builder (store điền khi lưu, Task 9).
- **Sau khi dựng**: nếu Điều hiệu lực của chính văn bản (`effectivity.article`) có phiên bản mới do thao tác áp dụng, parse lại `EffectivityInfo` từ text mới nhất của Điều đó; nếu `default_from`/`exceptions` khác → dựng lại một lần với effectivity mới; vẫn khác sau lần hai → thêm reason `effectivity.unstable` cho mọi phiên bản.
- Kết quả sắp theo `(provision_id, valid_from)`; tất định.

- [ ] **Step 1: Viết test:**
  `test_real_clause_changes_on_effective_date` — 59/2020 + 10 thao tác Task 6: bản của `luat:59/2020/QH14#d60.k3` có đúng 2 phiên bản: `[2021-01-01, 2022-03-01)` với text gốc, `[2022-03-01, None)` với text mới (bắt đầu `"3. Trường hợp chủ tọa, người ghi biên bản từ chối ký"`); bản `#d60` (article) cũng tách tại 2022-03-01; `#d61` chỉ có 1 phiên bản `[2021-01-01, None)`.
  `test_title_change_only_title_leaf` — `#d50.title` có 2 phiên bản, các khoản của Điều 50 chỉ 1.
  `test_insert_clause_order` — văn bản giả có Điều 17 khoản 4, 5, 6; INSERT_CLAUSE `5a` anchor `5` hiệu lực 2023-01-01 → text Điều 17 từ 2023-01-01 có khoản thứ tự `4, 5, 5a, 6` (Review Focus 3); `#d17.k5a` có 1 phiên bản bắt đầu 2023-01-01.
  `test_delete_point_closes_version` — DELETE_POINT `d17.k4.d` 2023-01-01 → `#d17.k4.d` có `valid_to==date(2023,1,1)` và không có phiên bản sau.
  `test_non_applicable_ops_ignored` — thao tác `pending` không đổi nội dung (Task 8 lo trạng thái).
  `test_no_overlapping_intervals` — với mọi provision của kết quả real: các khoảng không chồng nhau và liên tiếp (`valid_to` của bản trước == `valid_from` bản sau).
  `test_deterministic` — dựng hai lần (đảo thứ tự list thao tác đầu vào) → kết quả bằng nhau.
  `test_effectivity_article_amended_rebuilds` — luật giả hiệu lực 2025-01-01 ở Điều 9; thao tác REPLACE_ARTICLE Điều 9 (hiệu lực 2024-08-01, nội dung mới: "Luật này có hiệu lực thi hành từ ngày 01 tháng 8 năm 2024.") → mọi provision có `valid_from==date(2024,8,1)`.
- [ ] **Step 2–4:** FAIL → viết `builder.py` → PASS.
- [ ] **Step 5: Checkpoint.**

---

### Task 8: Trạng thái xác minh, thay thế luật, sửa đổi chồng

**Files:**
- Modify: `src/rag/legal/builder.py` (thêm bước gắn trạng thái sau khi dựng nội dung)
- Create: `src/rag/legal/status.py`
- Test: `tests/test_legal_status.py`

**Interfaces:**
- Consumes: kết quả `build_versions` nội bộ, `AmendmentOperation`.
- Produces:
  - `apply_statuses(versions: list[ProvisionVersion], operations: Sequence[AmendmentOperation], *, default_dates: Mapping[str, date], document: LegalDocument, effectivity_amended: bool) -> list[ProvisionVersion]` — `default_dates`: source_document_key → ngày hiệu lực chung, dùng làm ngày dự kiến cho thao tác chờ không có `effective_from`. `build_versions` gọi hàm này ở cuối (nhận thêm tham số `default_dates: Mapping[str, date] = {}`).
  - `apply_repeals(versions, operations) -> list[ProvisionVersion]` — áp `REPEAL_DOCUMENT` áp dụng được lên `document_key` của văn bản đang dựng.
  - `demote_amended_directives(operations: Sequence[AmendmentOperation], *, directive_articles: Mapping[str, set[str]]) -> list[AmendmentOperation]` — `directive_articles`: source_document_key → tập số Điều của văn bản đó **chứa chỉ dẫn sửa đổi**. Nếu một thao tác áp dụng được nhắm vào `target_document_key=A` và `target.article ∈ directive_articles[A]`, mọi thao tác có `source_document_key==A` và `source_address.article==target.article` chuyển `pending` với reason `operation.source_amended:<id thao tác B>`.

Quy tắc (theo spec 5.6):
- Thao tác **không áp dụng được** (pending/partial/unsupported/failed, không bị rejected) chạm provision P với ngày dự kiến E (`effective_from` hoặc `default_dates[source]`; không có cả hai → ngày `valid_from` sớm nhất của P): tách phiên bản của P tại E (cùng text), từ E trở đi `needs_review` với reason `operation.pending:<id>`. "Chạm" = P là đích, là con cháu của đích, hoặc là tổ tiên của đích (article/clause chứa nó). Anh em không bị gắn.
- `REPLACE_TEXT` partial có `old_phrase`: mọi provision lá của luật đích chứa `old_phrase` (casefold) từ E được gắn như trên, cùng tổ tiên của chúng.
- Hai thao tác **áp dụng được** từ **hai văn bản nguồn khác nhau**, cùng `effective_from`, cùng đích (hoặc một là tổ tiên của đích kia) → phiên bản từ ngày đó `conflicted`, reason `operation.conflict:<id1>,<id2>`.
- `effectivity.unresolved`, `effectivity.unstable` → `needs_review`.
- Ngày bắt đầu sớm nhất của văn bản khác `document.vbpl_effective_from` **và** Điều hiệu lực của văn bản không bị thao tác áp dụng nào sửa → mọi phiên bản đầu tiên thêm reason `effectivity.vbpl_mismatch` → `needs_review` (`build_versions` truyền cờ `effectivity_amended: bool` vào `apply_statuses`). Lệch nhưng Điều hiệu lực đã bị sửa (như 43/2024) → chỉ thêm `note:vbpl_effective_from_outdated`.
- Reason dạng `note:*` → chuyển sang `notes`, không đổi trạng thái.
- Còn lại `verified`. `conflicted` thắng `needs_review` thắng `verified`.
- Repeal: mọi phiên bản của văn bản có `valid_from >= D` bị bỏ, phiên bản đang mở tại D đóng ở D; `note:transition_exception` → thêm vào `notes` của phiên bản cuối mỗi provision.

- [ ] **Step 1: Viết test:**
  `test_pending_point_flags_ancestors_not_siblings` — thao tác pending trên `d60.k2.e` hiệu lực 2022-03-01: `#d60.k2.e`, `#d60.k2`, `#d60` có phiên bản từ 2022-03-01 `needs_review` với reason `operation.pending:<id>`; `#d60.k2.d` và `#d60.k3` vẫn 1 phiên bản `verified`.
  `test_pending_without_date_uses_source_default` — pending không có `effective_from`, `default_dates={"luat:03/2022/QH15": date(2022,3,1)}` → tách tại 2022-03-01.
  `test_bulk_phrase_flags_all_occurrences` — luật giả có cụm "Bộ Kế hoạch và Đầu tư" ở `d5.k1` và `d9.k2.a`; REPLACE_TEXT partial → hai lá đó và tổ tiên `needs_review`, `d5.k2` không.
  `test_same_day_conflict` — hai văn bản nguồn khác nhau cùng REPLACE_CLAUSE `d10.k2` hiệu lực 2025-07-01 → `#d10.k2` từ 2025-07-01 `conflicted` (Review Focus 5).
  `test_repeal_closes_document` — luật cũ, REPEAL_DOCUMENT hiệu lực 2024-08-01 → mọi provision `valid_to==date(2024,8,1)`, không có phiên bản bắt đầu sau đó.
  `test_repeal_with_exception_note` — như trên, có `note:transition_exception` → phiên bản cuối có `"note:transition_exception"` trong `notes`, `verified`.
  `test_vbpl_mismatch_flags_when_unexplained` — luật giả có Điều hiệu lực ghi 2025-01-01, `vbpl_effective_from=2025-07-01`, không có thao tác → phiên bản đầu `needs_review` với `effectivity.vbpl_mismatch`; cùng luật nhưng có thao tác áp dụng sửa Điều hiệu lực → `verified` với note `note:vbpl_effective_from_outdated`.
  `test_amended_amending_law_demotes` — A (`luat:03/2022/QH15`) có thao tác từ Điều 7 lên Luật Doanh nghiệp; B áp dụng REPLACE_CLAUSE `luat:03/2022/QH15#d7.k3` → các thao tác của A có `source_address.article=="7"` thành `pending` với reason bắt đầu `operation.source_amended:`; thao tác của A từ Điều 9 không đổi.
- [ ] **Step 2–4:** FAIL → viết `status.py` + nối vào `build_versions` → PASS; chạy lại `tests/test_legal_builder.py` (vẫn PASS).
- [ ] **Step 5: Checkpoint.**

---

### Task 9: Kho SQLite và API truy vấn

**Files:**
- Create: `src/rag/legal/store.py`
- Test: `tests/test_legal_store.py`

**Interfaces:**
- Consumes: mọi model Task 1.
- Produces `LegalStore(path: Path)`:
  - `upsert_document(doc: LegalDocument) -> None`; `document(key) -> LegalDocument|None`; `documents() -> list[LegalDocument]`
  - `add_relation(rel: DocumentRelation) -> None` (khoá `(source_key,target_key,relation)`, ghi đè `status/evidence`); `relations(key: str) -> list[DocumentRelation]` (cả hai chiều)
  - `add_operations(ops: Sequence[AmendmentOperation]) -> int` — bỏ qua id đã có; trả số bản ghi mới.
  - `operations(*, target_key: str|None=None, source_key: str|None=None, include_rejected: bool=False) -> list[AmendmentOperation]`
  - `set_review(op_id: str, status: ReviewStatus, reviewer: str, note: str, at: datetime) -> None` — chỉ đổi các trường review; nội dung bất biến.
  - `supersede_operation(old_id: str, new_op: AmendmentOperation, reviewer: str, note: str, at: datetime) -> None` — bản cũ `rejected`, bản mới có `supersedes_operation_id=old_id`, cùng transaction.
  - `save_build(run: BuildRun, versions: Sequence[ProvisionVersion]) -> None`; `latest_build(key) -> BuildRun|None`; `builds(key) -> list[BuildRun]`
  - `provisions_as_of(key: str, day: date, *, build_id: str|None=None) -> list[ProvisionVersion]` (mặc định build mới nhất)
  - `provision_history(provision_id: str, *, build_id: str|None=None) -> list[ProvisionVersion]`
  - `laws_in_force(day: date) -> list[LegalDocument]` — văn bản không phải VBHN có ít nhất một phiên bản hợp lệ tại `day` trong build mới nhất.
  - `law_family(name: str) -> list[LegalDocument]` — mọi văn bản cùng `law_name` (Task 5), sắp theo `issued_on`.
  - `add_review_item(item: ReviewItem) -> None` (bỏ qua nếu đã có mục mở cùng `(kind, operation_id, provision_id)`); `review_items(status: str|None="open") -> list[ReviewItem]`; `review_item(id) -> ReviewItem|None`; `resolve_review(decision: ReviewDecision) -> None` (lưu quyết định, đóng mục).
  - Mỗi ghi là một transaction; `PRAGMA foreign_keys=ON`; schema tạo khi khởi tạo.

- [ ] **Step 1: Viết test** (dùng `tmp_path`):
  `test_operations_immutable_and_superseded` — add → supersede → `operations()` không có bản cũ, `operations(include_rejected=True)` có cả hai, bản mới có `supersedes_operation_id`.
  `test_add_operations_idempotent` — add hai lần cùng list → lần hai trả 0.
  `test_as_of_half_open` — lưu 2 phiên bản `[2021-01-01,2022-03-01)`, `[2022-03-01,None)`; `as_of(2022-02-28)` ra bản 1, `as_of(2022-03-01)` ra bản 2.
  `test_latest_build_wins_old_kept` — 2 build → `provisions_as_of` dùng build 2; `build_id=` build 1 vẫn truy được.
  `test_laws_in_force_and_family` — Luật Nhà ở 65/2014 (đóng 2024-08-01) và 27/2023 (mở 2024-08-01): `laws_in_force(2023-06-15)` có 65/2014 không có 27/2023; `law_family("luật nhà ở")` trả cả hai theo thứ tự năm.
  `test_review_item_dedup_and_resolve` — thêm 2 lần cùng mục → 1 mục mở; resolve → `review_items("open")==[]`.
  `test_persists_across_instances` — mở lại `LegalStore` cùng path → dữ liệu còn.
- [ ] **Step 2–4:** FAIL → viết `store.py` → PASS.
- [ ] **Step 5: Checkpoint.**

---

### Task 10: Đối chiếu VBHN

**Files:**
- Create: `src/rag/legal/vbhn.py`
- Test: `tests/test_legal_vbhn.py`

**Interfaces:**
- Consumes: `parse_structure` (Task 2), `parse_vn_date` (Task 3), `ProvisionVersion`.
- Produces:
  - `ConsolidationInfo(target_name: str|None, target_number: str|None, included: tuple[tuple[str, date|None], ...], cutoff: date|None)` — `included` = (số hiệu văn bản sửa đổi, ngày hiệu lực ghi trong VBHN).
  - `parse_consolidation_header(text: str) -> ConsolidationInfo` — đọc phần trước `Điều 1.`: luật được hợp nhất (`<Luật|Bộ luật> <tên> số <số hiệu>`), và các mục `Luật số <số hiệu> ... có hiệu lực (thi hành)? kể từ ngày D`; `cutoff = max` các D (None nếu không đọc được ngày nào).
  - `normalize_for_compare(text: str) -> str` — NFC, casefold, gộp khoảng trắng, đổi `“”` thành `"`, bỏ `\[\d+\]`, bỏ dòng chú thích bắt đầu bằng `[\d+]`.
  - `VbhnMismatch(article: str, reason: str, built_excerpt: str, vbhn_excerpt: str)` — excerpt ≤ 200 ký tự quanh chỗ khác đầu tiên.
  - `compare_with_vbhn(built_as_of: Sequence[ProvisionVersion], vbhn_text: str) -> list[VbhnMismatch]` — so từng `article`; Điều có trong VBHN mà không có trong bản dựng → reason `vbhn.missing_in_build`; ngược lại `vbhn.missing_in_vbhn`; khác text → `vbhn.text_differs`.

- [ ] **Step 1: Viết test** (fixture giả lập `tests/fixtures/legal/vbhn_sample.txt`, 2 Điều, header nêu `Luật Doanh nghiệp số 59/2020/QH14` và `Luật số 03/2022/QH15 ... có hiệu lực kể từ ngày 01 tháng 3 năm 2022`, có chú thích `[1]`):
  `test_header_cutoff` — `cutoff==date(2022,3,1)`, `target_number=="59/2020/QH14"`, `included==(("03/2022/QH15", date(2022,3,1)),)`.
  `test_footnotes_ignored_equal` — bản dựng khớp nội dung (không có `[1]`) → `[]`.
  `test_text_differs_reported` — đổi một chữ → 1 mismatch `vbhn.text_differs`, article đúng.
  `test_missing_article` — thiếu một Điều trong bản dựng → `vbhn.missing_in_build`.
- [ ] **Step 2–4:** FAIL → viết → PASS.
- [ ] **Step 5: Checkpoint.**

---

### Task 11: Crawl và tự tìm văn bản liên quan

**Files:**
- Create: `src/rag/legal/crawl.py`, `src/rag/legal/discovery.py`, `data/team-4.2/legal/seeds.yaml`
- Modify: `.gitignore` (repo root) — thêm `data/team-*/legal/raw/` và `data/team-*/legal/*.sqlite`
- Test: `tests/test_legal_discovery.py`

**Interfaces:**
- Consumes: `VbplClient`, `metadata_from_detail`, `html_to_text`, `_norm_number` (đã có, `src/rag/ingest/vbpl.py`); `document_key` (Task 1); `parse_structure`, `parse_effectivity`, `parse_directives`, `law_name`, `parse_consolidation_header`; `LegalStore`.
- Produces:
  - `crawl.fetch_document(client: VbplClient, doc_type: str, doc_number: str, raw_dir: Path, *, now) -> tuple[LegalDocument, str] | None` — `search_by_number` rồi **lọc theo `docType.name == doc_type`** (Review: số hiệu trùng); lấy chi tiết bằng `pick_detail`; ghi `raw_dir/<document_key thay / bằng _>.txt`; `None` nếu không có.
  - `crawl.document_from_detail(detail: dict, raw_path: Path, text: str, *, now) -> LegalDocument`
  - `Seed(doc_type: str, doc_number: str)`; `load_seeds(path: Path) -> list[Seed]` — YAML: `laws: [{type: "Luật", number: "31/2024/QH15"}, ...]`
  - `DiscoveryReport(added: list[tuple[str,str,str]], rejected: list[tuple[str,str]], suspicious: list[str])` — added = (document_key, relation, evidence); rejected = (tiêu đề ứng viên, lý do); suspicious = document_key có `eff_status` chứa "một phần" mà không có văn bản sửa đổi nào được thêm.
  - `discover(client, store: LegalStore, seeds: Sequence[Seed], raw_dir: Path, *, max_depth: int = 2, max_pages: int = 3, now=...) -> DiscoveryReport`

Thuật toán discovery: hàng đợi `(document_key, depth)` từ seed (depth 0). Với mỗi văn bản X: `keyword = law_name gốc có chữ hoa (tiêu đề cắt trước " số ")`, gọi `client.iter_list(keyword=..)` tối đa `max_pages` trang; với mỗi ứng viên ban hành sau X, chưa có trong store: phân loại theo tiêu đề (`sửa đổi` → sửa đổi; cùng `law_name`, không phải VBHN → thay thế; `isConsolidatedDocument` + cùng tên → VBHN; còn lại bỏ). **Xác nhận bằng nội dung** sau khi tải: sửa đổi → `parse_directives` có directive `target_law_name` khớp `law_name(X)` (và số hiệu nếu directive có); thay thế → `parse_effectivity(...).repeals` có mục khớp số hiệu X; VBHN → `parse_consolidation_header` khớp số hiệu X. Xác nhận được → `upsert_document` (với `discovered_via="<X> | keyword=<k> | <evidence>"`), `add_relation(status="confirmed")`, đưa vào hàng đợi (sửa đổi: depth+1 nếu < max_depth; thay thế: depth 0; VBHN: không lan). Không xác nhận → `rejected`. Ứng viên VBHN không lan. Ngoài ra luật cũ bị thay thế cũng cần: với seed X, đọc `parse_effectivity(X).repeals` → `fetch_document` từng luật bị thay thế (theo số hiệu, loại `Luật`/`Bộ luật`), thêm với relation `THAY_THE` (X → luật cũ), depth 0.

- [ ] **Step 1: Viết test** với `FakeClient` (lớp trong test, có `iter_list(keyword, ...)`, `search_by_number`, `detail`) trả dữ liệu dựng tay; `raw_dir=tmp_path`:
  `test_number_collision_filtered_by_type` — `search_by_number("91/2015/QH13")` trả Nghị quyết trước, Bộ luật sau → `fetch_document(client,"Bộ luật","91/2015/QH13",...)` trả `bo-luat:91/2015/QH13`.
  `test_amendment_confirmed_by_content` — seed Luật Doanh nghiệp 59/2020; danh sách có (a) 03/2022 với text fixture thật, (b) một luật tiêu đề có "sửa đổi ... Luật Doanh nghiệp" nhưng nội dung không có chỉ dẫn cho Luật Doanh nghiệp → (a) trong `added` relation `SUA_DOI_BO_SUNG`, (b) trong `rejected` lý do `discovery.not_confirmed_by_content`.
  `test_replacement_found_from_repeal_clause` — seed Luật Nhà ở 27/2023 với Điều hiệu lực chứa câu hết hiệu lực 65/2014 → 65/2014 được fetch, relation `THAY_THE` `("luat:27/2023/QH15" → "luat:65/2014/QH13")`.
  `test_depth_limit` — chuỗi sửa đổi A←B←C←D; `max_depth=2` → B, C thêm; D không.
  `test_suspicious_partial_status` — seed có `eff_status="Hết hiệu lực một phần"`, không tìm được sửa đổi → `suspicious==[key seed]`.
  `test_seeds_file_valid` — `load_seeds(Path("../../data/team-4.2/legal/seeds.yaml"))` (đường dẫn từ `app/team-4.2`) == 4 seed: Luật 31/2024/QH15, Luật 27/2023/QH15, Luật 29/2023/QH15, Bộ luật 91/2015/QH13.
- [ ] **Step 2–4:** FAIL → viết → PASS.
- [ ] **Step 5: Checkpoint.**

---

### Task 12: Điều phối dựng, quyết định duyệt, CLI

**Files:**
- Create: `src/rag/legal/service.py`, `src/rag/legal/__main__.py`
- Test: `tests/test_legal_service.py`

**Interfaces:**
- Consumes: mọi thứ Task 2–11.
- Produces `LegalService(store: LegalStore, *, now: Callable[[], datetime] = ..., code_version: str = "legal-v1")`:
  - `provisions_for(key: str) -> list[Provision]` — parse từ raw text (cache trong bộ nhớ theo checksum).
  - `plan_operations(source_key: str) -> list[AmendmentOperation]` — directive + effectivity + repeal của văn bản nguồn → `store.add_operations`; mỗi thao tác không `auto_accepted` → một `ReviewItem(kind="operation")` với `payload` = các trường thao tác + `source_excerpt` (text trong `source_span`, ≤ 1500 ký tự).
  - `build_law(key: str) -> BuildRun` — thao tác đích là `key` (không rejected) + `demote_amended_directives` + `default_dates` + `build_versions`; nếu có VBHN liên quan (relation `HOP_NHAT` tới `key`) và `cutoff`: `compare_with_vbhn(store.provisions_as_of(...cutoff) của bản vừa dựng, text VBHN)`; mỗi mismatch → các phiên bản của Điều đó từ `cutoff` thành `conflicted` (reason `vbhn.*`) + `ReviewItem(kind="vbhn_mismatch")`; không có `cutoff` → reason `note:vbhn_cutoff_unknown`. `build_id = sha1(key + inputs_checksum)[:16]`; `inputs_checksum` = sha1 của raw checksum + id/review_status mọi thao tác dùng. Lưu bằng `save_build`.
  - `build_all() -> list[BuildRun]` — `plan_operations` cho mọi văn bản có directive hoặc repeal, rồi `build_law` cho mọi văn bản không phải VBHN.
  - `decide(decision: ReviewDecision) -> BuildRun|None` — `approve` → `set_review(approved)`; `reject` → `set_review(rejected)`; `correct` → tạo thao tác mới (copy + `corrected_fields`, chỉ các trường `operation_type, target, anchor, new_text, old_phrase, effective_from, target_document_key`; trường khác → `ValueError`), `review_status="approved"`, `supersede_operation`. Sau đó `resolve_review` và `build_law(target)` → trả BuildRun. Ghi chú (`note`) bắt buộc khác rỗng.
  - `report() -> dict` — đếm thao tác theo `(parse_status, review_status)`, phiên bản theo `verification_status` của build mới nhất mỗi luật, số mục review mở.
- CLI `python -m rag.legal <cmd>`: `crawl [--seeds PATH]` (gọi `discover`, in report), `build`, `show KEY --as-of YYYY-MM-DD [--provision dN.kM...]`, `report`, `fixture NUMBER... --out DIR`. Đường dẫn dữ liệu = `Settings.load().data_dir / "legal"`.

- [ ] **Step 1: Viết test** (store tmp, documents 59/2020 + 03/2022 từ fixture, không mạng):
  `test_build_all_real_enterprise` — sau `build_all()`: `as_of(luat:59/2020/QH14, 2022-02-28)` Điều 60 khoản 3 là text gốc, `as_of(..., 2022-03-01)` là text mới; mọi phiên bản `#d60.*` `verified`; có ReviewItem mở cho các thao tác Luật Đầu tư công (luật đích chưa có).
  `test_build_idempotent` — `build_all()` hai lần → `build_id` giống, không có ReviewItem trùng.
  `test_reject_then_rebuild` — reject thao tác `d60.k3` → build mới: `#d60.k3` chỉ còn 1 phiên bản (text gốc), build cũ vẫn truy được qua `build_id`.
  `test_correct_creates_superseding_op` — correct thao tác `d60.k3` với `effective_from=2022-07-01` → thao tác cũ rejected, mới approved có `supersedes_operation_id`; `#d60.k3` đổi tại 2022-07-01.
  `test_correct_rejects_unknown_field` — `corrected_fields={"source_document_key": "x"}` → `ValueError`.
  `test_empty_note_rejected` — `note=""` → `ValueError`.
  `test_cli_show` — `python -m rag.legal show luat:59/2020/QH14 --as-of 2022-03-01 --provision d60.k3` với `DATA_DIR=tmp` đã build → exit 0, stdout chứa `"verified"` và `"2022-03-01"`.
- [ ] **Step 2–4:** FAIL → viết → PASS.
- [ ] **Step 5: Checkpoint.**

---

### Task 13: Xuất chunk có phiên bản cho phần 2

**Files:**
- Create: `src/rag/legal/chunks.py`
- Test: `tests/test_legal_chunks.py`

**Interfaces:**
- Consumes: `LegalStore` (Task 9).
- Produces:
  - `VersionedChunk(chunk_id: str, document_key: str, article_id: str, section: str, text: str, valid_from: date, valid_to: date|None, verification_status: VerificationStatus, status_reasons: tuple[str,...], notes: tuple[str,...], source_operations: tuple[str,...], build_id: str)`
  - `export_chunks(store: LegalStore, document_key: str, *, build_id: str|None = None, max_syllables: int = 300) -> list[VersionedChunk]` — một nhóm chunk cho mỗi phiên bản `article`; text dài hơn `max_syllables` (đếm theo khoảng trắng) tách tại ranh giới dòng, dòng `Điều N. ...` lặp ở đầu mỗi mảnh; `section` = `" > ".join(heading_path + ("Điều N. tên",))`; `chunk_id = f"{build_id}:{article_id}:{valid_from.isoformat()}:{i}"`.

- [ ] **Step 1: Viết test:**
  `test_one_group_per_article_version` — sau build thật: chunk của `#d60` có đúng 2 `valid_from` khác nhau (2021-01-01, 2022-03-01), tất cả `verified`.
  `test_long_article_split_keeps_heading` — mọi chunk có `len(text.split()) <= 300 + len(dòng tiêu đề)` và bắt đầu bằng `"Điều "`.
  `test_metadata_carried` — chunk của Điều có phiên bản `needs_review` mang đúng `status_reasons`.
- [ ] **Step 2–4:** FAIL → viết → PASS.
- [ ] **Step 5: Checkpoint.**

---

### Task 14: Trang duyệt `/review`

**Files:**
- Create: `ui/review.html`
- Modify: `ui/server.py` — routes `GET /review`, `GET /api/legal/reviews?status=open|resolved|all`, `GET /api/legal/reviews/{review_id}`, `POST /api/legal/reviews/{review_id}/decision`; `get_legal_service()` lười tạo `LegalService(LegalStore(settings.data_dir/"legal"/"catalog.sqlite"))`; link "Duyệt kho luật" trong `ui/index.html` sidebar.
- Test: `tests/test_legal_review_api.py`

**Interfaces:**
- Consumes: `LegalService.decide`, `LegalStore.review_items/review_item/operations`.
- Produces API:
  - list → `{"items": [{review_id, kind, document_key, operation_id, provision_id, reasons, status, created_at, title}]}` (`title` = locator + loại thao tác).
  - detail → item + `operation` (mọi trường, ngày dạng ISO) + `source_excerpt` + `target_before` (text đích ở `as_of(effective_from - 1 ngày)` nếu có) + `target_after` (`new_text`) + `vbhn` (mismatch excerpt nếu `kind=="vbhn_mismatch"`).
  - decision body `{action, reviewer, note, corrected_fields}` → 200 `{"build_id": ...}`; thiếu `reviewer`/`note` → 400; `ValueError` → 400 với message; review đã đóng → 409.
- Trang: danh sách mục mở (lọc theo luật, theo tiền tố lý do), khung chi tiết hiện đoạn chỉ dẫn gốc, bảng trường thao tác, trước/sau, ba nút approve / reject / correct (correct mở form các trường cho phép), ô người duyệt (nhớ trong `localStorage`, bọc try/catch), ghi chú bắt buộc. Dùng Tailwind CDN + Inter như `ui/upload.html`.

- [ ] **Step 1: Viết test** (Starlette `TestClient`, monkeypatch `server.get_legal_service` trả service trên store tmp đã `build_all()` từ fixture):
  `test_list_open_reviews` — có ít nhất một mục, mọi mục `status=="open"`.
  `test_detail_has_source_excerpt` — `source_excerpt` chứa `"Luật Đầu tư công"` hoặc text của chỉ dẫn.
  `test_decision_requires_note` — POST không có `note` → 400.
  `test_approve_closes_and_rebuilds` — POST approve hợp lệ → 200, mục đó không còn trong `status=open`.
  `test_decision_on_closed_returns_409`.
  `test_review_page_served` — `GET /review` → 200, có `<title>`.
- [ ] **Step 2–4:** FAIL → viết → PASS. Mở `/review` bằng headless Chromium (như đã làm với `/upload`) ở 1366px và 390px (iframe), kiểm tra không tràn ngang.
- [ ] **Step 5: Checkpoint.**

---

### Task 15: Chạy thật với seed bất động sản và chốt kỳ vọng

**Files:**
- Create: `tests/fixtures/legal/realestate/` (text thô các văn bản discovery tìm được: tối thiểu 31/2024, 27/2023, 29/2023, 43/2024, 65/2014, 66/2014, 45/2013 + mọi VBHN tìm thấy), `tests/test_legal_realestate.py`
- Modify: không sửa code trừ khi chạy thật lộ lỗi — mỗi lỗi sửa kèm một test tái hiện trong file test của task sở hữu code đó.

- [ ] **Step 1: Chạy thật** `DATA_DIR=<scratch>/legal_run python -m rag.legal crawl` rồi `build`, rồi `report`. Ghi lại: văn bản đã thêm, ứng viên bị loại, suspicious, số thao tác theo trạng thái.
- [ ] **Step 2: Đọc văn bản 43/2024/QH15** (Điều về Luật Đất đai/Nhà ở/KDBĐS và Điều hiệu lực) và Điều hiệu lực của 31/2024, 27/2023, 29/2023, 65/2014, 66/2014; viết kỳ vọng cụ thể vào test (dùng fixture đã lưu, không mạng):
  `test_housing_law_as_of_2023` — `laws_in_force(2023-06-15)` chứa `luat:65/2014/QH13`, không chứa `luat:27/2023/QH15`.
  `test_housing_law_as_of_2025` — `laws_in_force(2025-06-15)` chứa `luat:27/2023/QH15`, không chứa `luat:65/2014/QH13`.
  `test_land_law_start_date_from_text` — ngày `valid_from` sớm nhất của `luat:31/2024/QH15` bằng ngày đọc từ văn bản sau khi áp 43/2024 (ghi giá trị cụ thể sau Step 2), và khác `vbpl_effective_from` (2025-01-01) nếu văn bản xác nhận như vậy.
  `test_43_2024_relations` — relation `SUA_DOI_BO_SUNG` từ `luat:43/2024/QH15` tới cả ba luật BĐS.
  `test_no_verified_version_from_unsupported` — không phiên bản `verified` nào có `source_operations` chứa thao tác `UNSUPPORTED`.
- [ ] **Step 3: Chạy `tests/test_legal_realestate.py` → PASS** (sau các sửa ở Step 1 nếu có).
- [ ] **Step 4: Viết báo cáo ngắn** vào `evals/team-4.2/results/w02-legal-builder/README.md`: lệnh chạy, số văn bản, số thao tác theo trạng thái, các mục review mở tiêu biểu, giới hạn đã biết.
- [ ] **Step 5: Checkpoint cuối:** `python -m pytest -q` toàn bộ pass; báo người dùng kết quả và hỏi có commit không.
