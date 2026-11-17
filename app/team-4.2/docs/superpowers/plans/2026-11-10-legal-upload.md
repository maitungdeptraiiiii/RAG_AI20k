# Upload văn bản pháp luật (Phần 3/4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Người dùng upload một văn bản pháp luật (file hoặc URL vbpl) qua 3 bước có xác nhận, văn bản vào kho có phiên bản qua staging + công bố nguyên khối, chat chỉ đọc cặp (snapshot, chỉ mục) hoàn chỉnh.

**Architecture:** Thêm `rag.legal.snapshots` (snapshot kho bất biến: staging bằng bản sao sqlite → `build_all` → validate → đổi con trỏ `CURRENT` nguyên tử; mọi đường ghi — upload, duyệt, CLI — đi qua đây). Thêm gói `rag.legal.upload` (chuẩn hoá text, kiểm tra cấu trúc, đọc phần đầu văn bản + tra vbpl có nguồn từng trường, so sánh từng điều, bản nháp 3 bước, xem trước bằng bản sao tạm, ghi vào staging). Server giữ một `LegalRuntime` (snapshot + chỉ mục + TemporalQA) đổi bằng một phép gán sau khi chỉ mục của snapshot mới dựng xong; một luồng ghi duy nhất xử lý hàng đợi việc ghi.

**Tech Stack:** Python 3.12, sqlite3 (backup API), `filelock`, Starlette, vanilla JS + Tailwind CDN, pytest.

**Spec:** `app/team-4.2/docs/superpowers/specs/2026-11-10-legal-upload-design.md` (bản 2). Đọc spec trước khi làm bất kỳ task nào.

## Global Constraints

- Mọi lệnh chạy từ `app/team-4.2`: test `python -m pytest -q <files>`; cả bộ `python -m pytest -q` (≈3 phút).
- Không sửa quy tắc tự xác minh / `needs_review` của phần 1; chỉ **thêm** lý do mới `source.no_vbpl_metadata`, `source.inherited_metadata_conflict`.
- Chat **không bao giờ** đọc snapshot chưa `published`, và luôn đọc snapshot + chỉ mục của **cùng** `snapshot_id`.
- Text đi vào kho luật **không che PII**; không gọi `mask_pages` trên đường này.
- File text nguồn không bao giờ bị ghi đè: `raw/<slug(key)>/<sha256>.txt`.
- Chỉ nhận loại `Luật`, `Bộ luật`, `Nghị quyết`, và VBHN có số chứa `VBHN-VPQH`; thông báo loại khác đúng câu: "Kho luật chỉ nhận Luật / Bộ luật / Nghị quyết / VBHN của VPQH; hãy dùng 'Tài liệu thường'".
- Cảnh báo thiếu luật gốc đúng câu: "Văn bản này sửa {tên} {số hiệu}, nhưng kho chưa có luật này. Hãy upload luật gốc."
- Quy tắc thay thế: bản trong kho `text_source == "vbpl"` chỉ được thay bởi nguồn URL vbpl; bản `"file"` thay được bởi cả hai. Kiểm tra ở server.
- Giữ 3 snapshot `published` gần nhất (cộng snapshot đang được runtime / request dùng).
- Giao diện tiếng Việt, khung trang `/upload` hiện có, không cuộn ngang ở 390px.
- Commit sau mỗi task, message `feat(team-4.2): ...`, kết thúc bằng dòng `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Server khởi động lại giữa lúc đang dựng** → snapshot `building` phải thành `failed` lúc khởi động, khoá ghi được nhả, bản nháp `building` thành `failed` có "Thử lại"; chat dùng snapshot `published` mới nhất. (Test ở Task 2 và Task 7.)
2. **Kho cũ chưa có snapshot** (chỉ có `DATA_DIR/legal/catalog.sqlite` từ phần 1/2) → lần đầu mở tạo snapshot khởi đầu `published` từ bản sao của nó, không mất dữ liệu, không dựng lại. (Test ở Task 2.)
3. **Lệnh CLI `python -m rag.legal build` chạy trong khi server đang ghi** → khoá ghi liên tiến trình; lệnh thứ hai báo "đang có lần cập nhật khác" thay vì ghi chồng. (Test ở Task 2.)
4. **URL không phải trang chi tiết vbpl** (trang khác, vbpl.vn/van-ban/khac, id không tồn tại) → bước ① báo lỗi rõ, không tạo bản nháp hỏng. (Test ở Task 6.)
5. **PDF có tiêu đề / số trang lặp mỗi trang và dòng bị ngắt giữa câu** → chuẩn hoá không tạo Điều giả, không nuốt Điều thật. (Test ở Task 3.)

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `src/rag/legal/models.py` (sửa) | Thêm trường nguồn/xác minh vào `LegalDocument` |
| `src/rag/legal/rawfiles.py` (mới) | Đường dẫn text theo nội dung, ghi idempotent |
| `src/rag/legal/service.py` (sửa) | Lý do `source.*` khi dựng; `build_all(progress=...)` |
| `src/rag/legal/snapshots.py` (mới) | Snapshot, staging, khoá ghi, validate, công bố, dọn dẹp |
| `src/rag/legal/__main__.py` (sửa) | `crawl` / `build` đi qua `SnapshotManager.write` |
| `src/rag/legal/upload/__init__.py` (mới) | Xuất API gói |
| `src/rag/legal/upload/normalize.py` (mới) | Chuẩn hoá text PDF/DOCX, kiểm tra cấu trúc |
| `src/rag/legal/upload/metadata.py` (mới) | Đọc phần đầu văn bản, tra vbpl, gộp có nguồn, kiểm loại |
| `src/rag/legal/upload/diff.py` (mới) | So sánh từng điều, mức từ |
| `src/rag/legal/upload/drafts.py` (mới) | Bản nháp + lưu trữ + máy trạng thái |
| `src/rag/legal/upload/flow.py` (mới) | `UploadService`: bước ①②③, xem trước, ghi vào staging |
| `src/rag/temporal/index.py` (sửa) | `VersionedIndex(..., dense=...)` dùng chung vector store, ghi `snapshot_id` |
| `ui/legal_runtime.py` (mới) | `LegalRuntime`, `WriteWorker` (hàng đợi ghi, chuyển cặp, lease) |
| `ui/server.py` (sửa) | Dùng runtime; API upload pháp luật; duyệt qua hàng đợi |
| `ui/upload.html` (sửa) | Chế độ "Văn bản pháp luật", 3 bước, so sánh, tiến độ |
| `ui/review.html` (sửa) | Trạng thái "đang áp dụng quyết định" |
| `tests/test_legal_snapshots.py`, `tests/test_legal_upload_*.py`, `tests/test_legal_runtime.py`, `tests/test_legal_upload_api.py`, `tests/test_legal_upload_realestate.py` (mới) | Test |

---

### Task 1: Trường nguồn của văn bản, text theo nội dung, lý do `source.*`

**Files:**
- Modify: `src/rag/legal/models.py` (`LegalDocument`)
- Create: `src/rag/legal/rawfiles.py`
- Modify: `src/rag/legal/service.py` (`build_law`, `build_all`)
- Test: `tests/test_legal_source_fields.py`

**Interfaces:**
- Produces (thêm vào cuối `LegalDocument`, đều có mặc định để payload cũ vẫn đọc được):
  - `text_source: Literal["vbpl", "file"] = "vbpl"`
  - `content_verified: dict[str, str] | None = None` — `{"by": str, "at": iso}`; `None` với nguồn vbpl.
  - `source_verified: bool = True`
  - `source_checked_at: datetime | None = None`
  - `field_sources: dict[str, dict[str, str]] = field(default_factory=dict)` — tên trường → `{"source": "vbpl"|"text"|"user"|"inherited", "at": iso, "detail": str}`
  - `metadata_conflicts: tuple[str, ...] = ()` — mô tả tiếng Việt từng mâu thuẫn giữa giá trị kế thừa và text mới.
- Produces `rawfiles.content_path(raw_dir: Path, key: str, checksum: str) -> Path` = `raw_dir / slug(key) / f"{checksum}.txt"` (slug giống `crawl.raw_path_for`).
- Produces `rawfiles.write_text(raw_dir: Path, key: str, text: str) -> tuple[Path, str]` — sha256 của `text`; không ghi lại nếu file đã có; trả `(path, checksum)`.
- Produces `LegalService.build_all(self, progress: Callable[[str, int, int], None] | None = None) -> list[BuildRun]` — gọi `progress("plan", i, n)` / `progress("build", i, n)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_old_payload_without_new_fields_decodes_with_defaults(tmp_path):
    # payload phần 1 (không có text_source...) -> mặc định vbpl, source_verified True
    doc = decode(LegalDocument, OLD_PAYLOAD)
    assert doc.text_source == "vbpl" and doc.source_verified is True and doc.field_sources == {}

def test_content_path_is_immutable_per_checksum(tmp_path):
    p1, c1 = write_text(tmp_path, "luat:43/2024/QH15", "A\n")
    p2, c2 = write_text(tmp_path, "luat:43/2024/QH15", "B\n")
    assert p1 != p2 and p1.read_text(encoding="utf-8") == "A\n"
    assert write_text(tmp_path, "luat:43/2024/QH15", "A\n") == (p1, c1)

def test_unverified_source_flags_every_version(svc_with_doc):          # store có 1 luật nhỏ (fixture tạo text 3 Điều)
    svc = svc_with_doc(source_verified=False)
    svc.build_all()
    vs = svc.store.versions(KEY)
    assert vs and all("source.no_vbpl_metadata" in v.status_reasons for v in vs)
    assert all(v.verification_status == "needs_review" for v in vs)

def test_metadata_conflict_flags_every_version(svc_with_doc):
    svc = svc_with_doc(metadata_conflicts=("ngày hiệu lực kế thừa 01/01/2025 khác điều hiệu lực 01/8/2024",))
    svc.build_all()
    assert all("source.inherited_metadata_conflict" in v.status_reasons for v in svc.store.versions(KEY))

def test_verified_source_unchanged(svc_with_doc):
    svc = svc_with_doc()
    svc.build_all()
    assert not any(r.startswith("source.") for v in svc.store.versions(KEY) for r in v.status_reasons)

def test_build_all_reports_progress(svc_with_doc):
    seen = []
    svc_with_doc().build_all(progress=lambda stage, i, n: seen.append((stage, i, n)))
    assert ("plan", 1, 1) in seen and ("build", 1, 1) in seen
```

- [ ] **Step 2: Run** `python -m pytest -q tests/test_legal_source_fields.py` — Expected: FAIL (`write_text` / fields missing).
- [ ] **Step 3: Implement** fields, `rawfiles.py`, and in `LegalService.build_law` after `_flag_known_gaps`: `if not doc.source_verified: versions = _flag(versions, lambda pid: True, None, "source.no_vbpl_metadata")`; `if doc.metadata_conflicts: ... "source.inherited_metadata_conflict"`. `build_all` gains the `progress` kwarg.
- [ ] **Step 4: Run** the new test file plus `tests/test_legal_*.py` — Expected: all PASS.
- [ ] **Step 5: Commit** `feat(team-4.2): legal document source fields and content-addressed text`.

---

### Task 2: Snapshot kho — staging, khoá ghi, validate, công bố

**Files:**
- Create: `src/rag/legal/snapshots.py`
- Modify: `pyproject.toml` (thêm `"filelock"` vào dependencies)
- Test: `tests/test_legal_snapshots.py`

**Interfaces:**
- Consumes: `LegalStore`, `LegalService.build_all(progress=...)` (Task 1).
- Produces:

```python
SnapshotStatus = Literal["building", "validated", "published", "failed"]

@dataclass(frozen=True)
class Snapshot:
    snapshot_id: str            # "s" + yyyymmddHHMMSS + "-" + 6 hex
    parent_id: str | None
    status: SnapshotStatus
    reason: str                 # "bootstrap" | "upload:<upload_id>" | "review:<review_id>" | "cli:build" | "cli:crawl"
    actor: str
    created_at: datetime
    published_at: datetime | None
    error: str | None
    catalog_path: Path          # legal_dir/snapshots/<id>/catalog.sqlite

@dataclass(frozen=True)
class WriteResult(Generic[T]):
    snapshot: Snapshot
    value: T

class WriteLockedError(RuntimeError): ...          # "Đang có lần cập nhật kho khác"
class SnapshotValidationError(RuntimeError): ...   # .problems: list[str]

class SnapshotManager:
    def __init__(self, legal_dir: Path, *, now: Callable[[], datetime] = ...,
                 service_factory: Callable[[LegalStore], LegalService] = LegalService,
                 lock_timeout: float = 0.0) -> None
    legal_dir: Path                                             # thuộc tính; text nguồn ở legal_dir/"raw" (dùng chung mọi snapshot)
    def current(self) -> Snapshot                               # snapshot đang công bố (đọc file CURRENT)
    def get(self, snapshot_id: str) -> Snapshot
    def list(self) -> list[Snapshot]                            # mới trước
    def store(self, snapshot_id: str | None = None) -> LegalStore
    def service(self, snapshot_id: str | None = None) -> LegalService
    def write(self, reason: str, actor: str, fn: Callable[[LegalService], T], *,
              progress: Callable[[str, int, int], None] | None = None) -> WriteResult[T]
    @contextmanager
    def scratch(self) -> Iterator[LegalService]                 # bản sao tạm của snapshot hiện tại, xoá khi thoát
    def mark_interrupted(self) -> list[str]                     # building/validated -> failed ("bị dừng giữa chừng")
    def cleanup(self, keep: int = 3, in_use: Collection[str] = ()) -> list[str]
    def validate(self, service: LegalService) -> list[str]      # rỗng = hợp lệ
```

Quy tắc:
- Metadata snapshot ở `legal_dir/snapshots/index.sqlite` (bảng `snapshots`); con trỏ `legal_dir/CURRENT` (một dòng: `snapshot_id`), ghi bằng file tạm + `os.replace`.
- Khởi tạo: không có `CURRENT` → tạo snapshot `bootstrap` `published` bằng sqlite backup API từ `legal_dir/catalog.sqlite` nếu có, hoặc kho rỗng. Không chạy `build_all`.
- `write`: lấy `FileLock(legal_dir/"write.lock", timeout=lock_timeout)` (hết giờ → `WriteLockedError`) → sao chép snapshot hiện tại sang staging (`building`) → `fn(service)` → `service.build_all(progress)` → `validate` (`validated`) → ghi `CURRENT` (`published`, `published_at`). Lỗi ở bất kỳ đâu → `failed` + `error`, `CURRENT` không đổi, ném lại lỗi gốc. `fn` ném `ValueError`/`KeyError` (lỗi nghiệp vụ, ví dụ quyết định duyệt không hợp lệ) → xoá staging thay vì giữ `failed`.
- `validate` trả các vấn đề: văn bản không phải VBHN thiếu bản dựng mới nhất; `latest_build.inputs` ≠ inputs tính lại từ thao tác hiện tại (dùng cùng công thức `_sha1` trong `build_law`); file `raw_text_path` không tồn tại hoặc sha256 ≠ `raw_checksum`; thao tác `auto_accepted`/`approved` có `target_document_key` không có trong kho.
- `cleanup`: xoá thư mục snapshot `published` cũ hơn `keep` bản mới nhất và staging `failed` cũ hơn 7 ngày, trừ `current()` và `in_use`.

- [ ] **Step 1: Write the failing tests**

```python
def test_bootstrap_copies_legacy_catalog_without_rebuild(tmp_path, small_legacy_catalog):
    mgr = SnapshotManager(tmp_path)
    snap = mgr.current()
    assert snap.status == "published" and snap.reason == "bootstrap"
    assert [d.document_key for d in mgr.store().documents()] == [KEY]
    assert mgr.store().latest_build(KEY).build_id == LEGACY_BUILD_ID

def test_write_publishes_new_snapshot_and_keeps_parent(tmp_path, mgr_with_law):
    before = mgr_with_law.current()
    res = mgr_with_law.write("cli:build", "test", lambda svc: "ok")
    assert res.value == "ok" and res.snapshot.status == "published" and res.snapshot.parent_id == before.snapshot_id
    assert mgr_with_law.current().snapshot_id == res.snapshot.snapshot_id
    assert mgr_with_law.get(before.snapshot_id).catalog_path.exists()

def test_failure_during_build_keeps_current(tmp_path, mgr_with_law, monkeypatch):
    before = mgr_with_law.current()
    monkeypatch.setattr(LegalService, "build_law", boom_on_second_call)      # lỗi ở luật thứ 2
    with pytest.raises(RuntimeError):
        mgr_with_law.write("upload:u1", "test", add_second_law)
    assert mgr_with_law.current().snapshot_id == before.snapshot_id
    assert mgr_with_law.list()[0].status == "failed" and "boom" in mgr_with_law.list()[0].error

def test_validation_failure_is_not_published(tmp_path, mgr_with_law):
    before = mgr_with_law.current()
    with pytest.raises(SnapshotValidationError):
        mgr_with_law.write("upload:u1", "t", lambda svc: Path(svc.store.document(KEY).raw_text_path).write_text("x"))
    assert mgr_with_law.current().snapshot_id == before.snapshot_id

def test_business_error_discards_staging(tmp_path, mgr_with_law):
    n = len(mgr_with_law.list())
    with pytest.raises(ValueError):
        mgr_with_law.write("review:r1", "t", lambda svc: (_ for _ in ()).throw(ValueError("x")))
    assert len(mgr_with_law.list()) == n

def test_second_writer_gets_locked_error(tmp_path, mgr_with_law):
    other = FileLock(tmp_path / "write.lock"); other.acquire()
    try:
        with pytest.raises(WriteLockedError):
            SnapshotManager(tmp_path).write("cli:build", "t", lambda s: None)
    finally:
        other.release()

def test_mark_interrupted(tmp_path, mgr_with_law):
    mgr_with_law._insert_for_test(status="building")        # helper riêng của test: ghi dòng building
    assert mgr_with_law.mark_interrupted() and mgr_with_law.list()[0].status == "failed"

def test_cleanup_keeps_three_current_and_in_use(tmp_path, mgr_with_law):
    ids = [mgr_with_law.write("cli:build", "t", lambda s: None).snapshot.snapshot_id for _ in range(5)]
    removed = mgr_with_law.cleanup(keep=3, in_use={ids[0]})
    assert ids[0] not in removed and ids[1] in removed and all(i not in removed for i in ids[2:])

def test_scratch_does_not_touch_current(tmp_path, mgr_with_law):
    with mgr_with_law.scratch() as svc:
        svc.store.upsert_document(other_doc())
    assert other_doc().document_key not in {d.document_key for d in mgr_with_law.store().documents()}
```

(Thay `_insert_for_test` bằng thao tác sqlite trực tiếp trong test nếu không muốn thêm hàm; không thêm API công khai chỉ để test.)

- [ ] **Step 2: Run** `python -m pytest -q tests/test_legal_snapshots.py` — Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `snapshots.py` theo quy tắc trên; sao chép bằng `sqlite3.connect(src).backup(sqlite3.connect(dst))`.
- [ ] **Step 4: Run** test file — Expected: PASS.
- [ ] **Step 5: Commit** `feat(team-4.2): legal store snapshots with staging and atomic publish`.

---

### Task 3: Chuẩn hoá text PDF/DOCX và kiểm tra cấu trúc

**Files:**
- Create: `src/rag/legal/upload/__init__.py`, `src/rag/legal/upload/normalize.py`
- Test: `tests/test_legal_upload_normalize.py`

**Interfaces:**
- Produces `normalize_legal_text(pages: Sequence[str]) -> str` — ghép các trang; bỏ dòng lặp đầu/cuối trang (tiêu đề, "Trang N", số trang trơn) xuất hiện ở ≥ 50% trang; ghép dòng bị ngắt giữa câu; mỗi đơn vị một dòng: tách trước `Điều N.`, `Chương <La Mã|số>`, `Mục N`, `Phần thứ ...`, `N.` đầu khoản, `a)`/`đ)` đầu điểm — chỉ khi ở đầu dòng gốc hoặc ngay sau dấu kết câu; NFC; bỏ khoảng trắng thừa.
- Produces:

```python
@dataclass(frozen=True)
class StructureCheck:
    n_articles: int
    gaps: tuple[tuple[str, str], ...]      # (Điều trước, Điều sau) khi số nhảy, ví dụ ("12", "14"); bỏ qua 5a/5b
    has_effectivity_article: bool          # parse_effectivity(...).article is not None

def check_structure(text: str, key: str) -> StructureCheck
```

- [ ] **Step 1: Write the failing tests**

```python
REAL = (FIXTURES / "realestate" / <file của 43/2024 theo manifest>).read_text(encoding="utf-8")

def wrap_like_pdf(text, width=70, header="LUẬT SỬA ĐỔI ...", per_page=40):
    # ngắt dòng ở 70 ký tự, chèn header + "Trang N" mỗi 40 dòng
    ...

def test_pdf_wrapped_text_parses_to_same_articles_and_directives():
    norm = normalize_legal_text(pages_of(wrap_like_pdf(REAL)))
    assert [p.provision_id for p in parse_structure(norm, KEY) if p.kind == "article"] == \
           [p.provision_id for p in parse_structure(REAL, KEY) if p.kind == "article"]
    assert [(d.source_locator, d.operation_type) for d in parse_directives(parse_structure(norm, KEY))] == \
           [(d.source_locator, d.operation_type) for d in parse_directives(parse_structure(REAL, KEY))]

def test_repeated_headers_and_page_numbers_removed():
    norm = normalize_legal_text(["LUẬT X\nĐiều 1. A\n1", "LUẬT X\nĐiều 2. B\n2", "LUẬT X\nĐiều 3. C\n3"])
    assert "LUẬT X" not in norm and norm.splitlines() == ["Điều 1. A", "Điều 2. B", "Điều 3. C"]

def test_reference_to_article_mid_sentence_is_not_split():
    norm = normalize_legal_text(["1. Theo quy định tại\nĐiều 5 của Luật này thì ..."])
    assert norm == "1. Theo quy định tại Điều 5 của Luật này thì ..."

def test_structure_check_gap_and_effectivity():
    sc = check_structure("Điều 1. A\nĐiều 2. B\nĐiều 4. Hiệu lực thi hành\nLuật này có hiệu lực từ ngày 01 tháng 7 năm 2025.", "luat:1/2025/QH15")
    assert sc.n_articles == 3 and sc.gaps == (("2", "4"),) and sc.has_effectivity_article

def test_inserted_article_labels_are_not_gaps():
    assert check_structure("Điều 5. A\nĐiều 5a. B\nĐiều 6. C", "k").gaps == ()
```

- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — Expected: PASS. Nếu test văn bản thật không đạt chỉ vì một quy tắc tách, sửa quy tắc, không nới test.
- [ ] **Step 5: Commit** `feat(team-4.2): normalize uploaded legal text and structure check`.

---

### Task 4: Thông tin văn bản — đọc phần đầu, tra vbpl, gộp có nguồn

**Files:**
- Create: `src/rag/legal/upload/metadata.py`
- Test: `tests/test_legal_upload_metadata.py`

**Interfaces:**
- Consumes: `rag.ingest.vbpl.VbplClient` (`detail`, `search_by_number`), `metadata_from_detail`, `pick_detail`; `rag.legal.keys.document_key`, `normalize_number`; `parse_effectivity`, `parse_structure`; `parse_consolidation_header`.
- Produces:

```python
Source = Literal["vbpl", "text", "user", "inherited"]

@dataclass(frozen=True)
class FieldValue:
    value: Any                   # str | date | None
    source: Source
    at: datetime
    detail: str = ""             # bằng chứng: câu chữ, vbpl_id, tên người nhập, nguồn của bản trước

FIELDS = ("doc_type", "doc_number", "title", "issuer", "issued_on",
          "vbpl_id", "vbpl_effective_from", "vbpl_effective_to", "eff_status")

ACCEPTED_TYPES = ("Luật", "Bộ luật", "Nghị quyết")
REJECT_TYPE_MESSAGE = "Kho luật chỉ nhận Luật / Bộ luật / Nghị quyết / VBHN của VPQH; hãy dùng 'Tài liệu thường'"

def parse_vbpl_url(url: str) -> str | None                     # id từ https://vbpl.vn/van-ban/chi-tiet/{id}[?...]; khác -> None
def header_fields(text: str, now: datetime) -> dict[str, FieldValue]   # loại, số hiệu, tên, cơ quan, ngày ban hành từ phần đầu (source="text")
def vbpl_fields(detail: dict, now: datetime) -> dict[str, FieldValue]  # từ metadata_from_detail (source="vbpl")
def lookup_vbpl(client, doc_type: str, doc_number: str) -> dict | None # search_by_number + lọc loại + pick_detail; lỗi mạng -> None
def merge_fields(*layers: dict[str, FieldValue]) -> dict[str, FieldValue]   # lớp sau thắng nếu value không None
def inherit_fields(new: dict[str, FieldValue], old_doc: LegalDocument, now: datetime) -> dict[str, FieldValue]
    # điền trường vbpl còn trống từ old_doc với source="inherited", detail = "bản trước: <nguồn cũ> <thời điểm>"
def metadata_conflicts(fields: dict[str, FieldValue], text: str, key: str) -> tuple[str, ...]
    # trường "inherited" mâu thuẫn: vbpl_effective_from ≠ parse_effectivity(...).default_from; doc_number ≠ số đọc từ text
def type_problem(doc_type: str | None, doc_number: str | None) -> str | None   # REJECT_TYPE_MESSAGE hoặc None; VBHN hợp lệ khi số chứa "VBHN-VPQH"
def is_consolidated(doc_type: str | None, doc_number: str | None) -> bool
```

- [ ] **Step 1: Write the failing tests** — dùng `FakeVbplClient` (trả dict cố định / ném `VbplError`):

```python
def test_parse_vbpl_url():
    assert parse_vbpl_url("https://vbpl.vn/van-ban/chi-tiet/171234?x=1") == "171234"
    assert parse_vbpl_url("https://vbpl.vn/van-ban/khac/1") is None
    assert parse_vbpl_url("https://example.com/van-ban/chi-tiet/1") is None

def test_header_fields_from_real_amending_law():
    f = header_fields(REAL_43_2024, NOW)
    assert f["doc_type"].value == "Luật" and f["doc_number"].value == "43/2024/QH15"
    assert f["issued_on"].value == date(2024, 6, 29) and f["issued_on"].source == "text"

def test_vbpl_wins_over_text_and_keeps_source():
    m = merge_fields(header_fields(REAL_43_2024, NOW), vbpl_fields(DETAIL_43, NOW))
    assert m["vbpl_id"].source == "vbpl" and m["doc_number"].source == "vbpl"

def test_lookup_failure_returns_none():
    assert lookup_vbpl(FailingClient(), "Luật", "43/2024/QH15") is None

def test_inherited_fields_marked_and_conflict_detected():
    old = doc(vbpl_id="99", vbpl_effective_from=date(2025, 1, 1), eff_status="Còn hiệu lực")
    f = inherit_fields(header_fields(TEXT_EFFECTIVE_2024_08_01, NOW), old, NOW)
    assert f["vbpl_id"].source == "inherited" and f["vbpl_id"].value == "99"
    assert metadata_conflicts(f, TEXT_EFFECTIVE_2024_08_01, KEY) == (
        "Ngày hiệu lực kế thừa 01/01/2025 khác ngày đọc từ điều hiệu lực 01/08/2024",)

@pytest.mark.parametrize("t,n,ok", [("Luật", "43/2024/QH15", True), ("Nghị định", "10/2023/NĐ-CP", False),
                                    ("Văn bản hợp nhất", "01/VBHN-VPQH", True), ("Văn bản hợp nhất", "05/VBHN-BTP", False)])
def test_type_problem(t, n, ok):
    assert (type_problem(t, n) is None) == ok
    if not ok: assert type_problem(t, n) == REJECT_TYPE_MESSAGE
```

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `feat(team-4.2): uploaded legal document metadata with field provenance`.

---

### Task 5: So sánh từng điều

**Files:**
- Create: `src/rag/legal/upload/diff.py`
- Test: `tests/test_legal_upload_diff.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class ArticleChange:
    article: str                        # nhãn Điều, ví dụ "260"
    old_text: str
    new_text: str
    ops: tuple[tuple[str, str], ...]    # mức từ: ("equal"|"delete"|"insert", đoạn text) theo thứ tự

@dataclass(frozen=True)
class ArticleDiff:
    same: int
    changed: tuple[ArticleChange, ...]
    added: tuple[str, ...]              # nhãn Điều chỉ có ở bản mới
    removed: tuple[str, ...]

def diff_articles(old_text: str, new_text: str, key: str) -> ArticleDiff
```

So theo `parse_structure` (kind `article`, ghép cả cây con của Điều); so sánh trên text đã gộp khoảng trắng; mức từ bằng `difflib.SequenceMatcher` trên danh sách từ.

- [ ] **Step 1: Write the failing tests**

```python
def test_whitespace_only_differences_are_same():
    d = diff_articles("Điều 1. A  b\nĐiều 2. C", "Điều 1. A b\nĐiều 2.  C", "k")
    assert d.same == 2 and d.changed == ()

def test_changed_added_removed():
    d = diff_articles("Điều 1. A\nĐiều 2. B\nĐiều 3. C", "Điều 1. A\nĐiều 2. B sửa\nĐiều 4. D", "k")
    assert d.same == 1 and [c.article for c in d.changed] == ["2"] and d.added == ("4",) and d.removed == ("3",)
    assert ("insert", "sửa") in d.changed[0].ops
```

- [ ] **Step 2–4:** run (FAIL) → implement → run (PASS).
- [ ] **Step 5: Commit** `feat(team-4.2): article-level diff for duplicate legal uploads`.

---

### Task 6: Bản nháp và luồng 3 bước (`UploadService`)

**Files:**
- Create: `src/rag/legal/upload/drafts.py`, `src/rag/legal/upload/flow.py`
- Test: `tests/test_legal_upload_flow.py`

**Interfaces:**
- Consumes: Task 1 (`rawfiles`, fields), Task 2 (`SnapshotManager.current/store/scratch/write`), Task 3, 4, 5. Loader file: `rag.ingest.loaders.load_source(path, source=..., ocr=...)` — **không** qua `RAGPipeline.prepare` (che PII và bỏ qua theo `has_doc`). Báo cáo trang: `rag.ingest.page_report.page_details`.
- Produces:

```python
DraftState = Literal["step1", "step2", "step3", "queued", "building", "published",
                     "failed", "stale", "duplicate", "cancelled"]

@dataclass
class Draft:
    upload_id: str
    created_at: datetime
    state: DraftState
    origin: Literal["file", "url"]
    source_name: str                    # tên file hoặc URL
    text: str                           # đã chuẩn hoá, KHÔNG che PII
    checksum: str
    pages: list[dict]                   # page_details (file) | [] (url)
    structure: dict                     # encode(StructureCheck)
    fields: dict[str, dict]             # tên -> encode(FieldValue)
    source_verified: bool
    base_snapshot_id: str
    duplicate: dict | None              # {"document_key", "checksum", "text_source", "diff": encode(ArticleDiff), "replace_allowed": bool}
    replace: bool = False
    preview: dict | None = None         # encode(Preview), gán ở bước ②
    confirmations: dict[str, dict] = field(default_factory=dict)   # "step1"/"step2"/"step3" -> {"by","at","note"}
    snapshot_id: str | None = None
    error: str | None = None
    progress: dict | None = None        # {"stage", "done", "total"}

class DraftStore:                       # JSON: legal_dir/uploads/<upload_id>/draft.json (+ file gốc cạnh đó)
    def __init__(self, root: Path) -> None
    def save(self, draft: Draft) -> None          # ghi file tạm + os.replace
    def load(self, upload_id: str) -> Draft       # KeyError nếu không có
    def list(self) -> list[Draft]                 # mới trước
    def mark_interrupted(self) -> list[str]       # queued/building -> failed ("server khởi động lại giữa chừng")

class StepError(ValueError): ...                  # gọi sai bước / thiếu xác nhận; message tiếng Việt
class StaleDraftError(StepError): ...             # kho đã đổi từ lúc so sánh: "Kho đã thay đổi từ lúc bạn so sánh — hãy xem lại bước ①"

@dataclass(frozen=True)
class Preview:
    kind: Literal["base", "amending", "consolidated"]
    targets: tuple[dict, ...]           # {"document_key"|None, "name", "number", "in_store": bool, "warning": str|None}
    operations: tuple[dict, ...]        # {"operation_id","source_locator","description","effective_from","review_status","reasons_vi":[...],"excerpt"}
    repeals: tuple[dict, ...]
    waiting_for_this: int               # số thao tác của văn bản khác đang chờ văn bản này
    effectivity: dict                   # {"default_from","evidence","exceptions":[{"units","date","evidence"}],"conditional_units":[...],"flags_vi":[...]}
    replace_note: str | None

class UploadService:
    def __init__(self, snapshots: SnapshotManager, drafts: DraftStore, *, client_factory=VbplClient,
                 ocr=None, now=...) -> None
    def create_from_file(self, path: Path, source_name: str) -> Draft          # step1
    def create_from_url(self, url: str) -> Draft                               # step1; StepError nếu không phải URL vbpl / id không có
    def confirm_text(self, upload_id: str, by: str) -> Draft                   # step1 -> step2; StepError nếu duplicate giống hệt / không cho thay
    def choose_replace(self, upload_id: str, by: str) -> Draft                 # chỉ khi duplicate.replace_allowed
    def update_fields(self, upload_id: str, values: dict[str, str], by: str) -> Draft   # step2; source="user"; kiểm trùng lại nếu số hiệu đổi
    def relookup_vbpl(self, upload_id: str) -> Draft
    def preview(self, upload_id: str) -> Draft                                 # tính Preview bằng snapshots.scratch()
    def confirm_understanding(self, upload_id: str, by: str) -> Draft          # step2 -> step3; StepError nếu trường bắt buộc trống / type_problem / VBHN không rõ luật được hợp nhất
    def submit(self, upload_id: str, by: str, note: str = "") -> Draft         # step3 -> queued (không ghi kho; Task 7 làm)
    def apply_to(self, svc: LegalService, upload_id: str) -> None              # chạy trong SnapshotManager.write: kiểm stale, ghi text + văn bản + quan hệ
    def cancel(self, upload_id: str) -> Draft
```

Quy tắc trong `UploadService`:
- `create_*`: tính `checksum`, `structure`, `fields` (url: `vbpl_fields`; file: `header_fields` rồi `lookup_vbpl` → `vbpl_fields` nếu có), `source_verified = (nguồn url) or (tra được)`, `base_snapshot_id = snapshots.current().snapshot_id`, kiểm trùng với `snapshots.store()`: trùng + cùng checksum → `state="duplicate"`; trùng + khác → `duplicate` có `diff` và `replace_allowed = not (existing.text_source == "vbpl" and origin == "file")`.
- Mỗi phương thức kiểm `state` và ném `StepError` khi sai bước; server không có đường nào bỏ qua kiểm tra này.
- `preview`: trong `scratch()`, `upsert_document` bản nháp (text ghi vào thư mục tạm) rồi `plan_operations(key)`; cộng `plan_operations` cho văn bản có thao tác `operation.target_law_not_found` trỏ số hiệu này để đếm `waiting_for_this`. `reasons_vi` ánh xạ mã lý do → câu tiếng Việt (bảng hằng trong `flow.py`; mã chưa có bản dịch thì hiện nguyên mã). Cảnh báo thiếu luật gốc dùng đúng câu trong Global Constraints.
- `apply_to`: (1) nếu văn bản cùng `document_key` trong `svc.store` có checksum khác `draft.duplicate["checksum"]` (hoặc xuất hiện khi lúc tạo chưa có) → ném `StaleDraftError(StepError)`; (2) `rawfiles.write_text(legal_dir/"raw", key, text)`; (3) dựng `LegalDocument` từ `fields` (+ `inherit_fields` khi `replace`), `text_source`, `content_verified={"by","at"}` từ xác nhận step1 (nguồn file), `source_verified`, `source_checked_at`, `field_sources`, `metadata_conflicts`, `discovered_via=f"upload:{upload_id}"`; (4) `upsert_document`; (5) quan hệ `confirmed` với bằng chứng câu chữ: `SUA_DOI_BO_SUNG` tới mỗi luật đích có trong kho, `HOP_NHAT` tới luật được hợp nhất, `THAY_THE` tới luật bị bãi bỏ — thay thế giữ nguyên các quan hệ đã có.

- [ ] **Step 1: Write the failing tests** (`snapshots` dựng trên kho tạm có Luật Đất đai 31/2024 từ fixture realestate; `FakeVbplClient`):

```python
def test_url_flow_creates_step1_with_vbpl_fields(svc_env):
    d = svc_env.upload.create_from_url("https://vbpl.vn/van-ban/chi-tiet/171234")
    assert d.state == "step1" and d.fields["doc_number"]["source"] == "vbpl" and d.source_verified

def test_bad_url_raises_step_error(svc_env):
    with pytest.raises(StepError, match="vbpl"):
        svc_env.upload.create_from_url("https://vbpl.vn/van-ban/khac/1")

def test_steps_cannot_be_skipped(svc_env):
    d = svc_env.upload.create_from_file(TXT_43, "43.txt")
    with pytest.raises(StepError): svc_env.upload.confirm_understanding(d.upload_id, "An")
    with pytest.raises(StepError): svc_env.upload.submit(d.upload_id, "An")

def test_file_without_vbpl_match_is_unverified(svc_env_offline):
    d = svc_env_offline.upload.create_from_file(TXT_43, "43.txt")
    assert d.source_verified is False

def test_text_is_not_pii_masked(svc_env):
    d = svc_env.upload.create_from_file(TXT_WITH_PHONE_AND_NAME, "x.txt")
    assert "0912345678" in d.text

def test_identical_duplicate_stops(svc_env):
    d = svc_env.upload.create_from_file(TXT_31_SAME_AS_STORE, "31.txt")
    assert d.state == "duplicate" and d.duplicate["diff"] is None
    with pytest.raises(StepError): svc_env.upload.confirm_text(d.upload_id, "An")

def test_file_cannot_replace_vbpl_text(svc_env):
    d = svc_env.upload.create_from_file(TXT_31_EDITED, "31.txt")
    assert d.duplicate["replace_allowed"] is False and d.duplicate["diff"]["changed"]
    with pytest.raises(StepError): svc_env.upload.choose_replace(d.upload_id, "An")

def test_preview_warns_missing_base_law(svc_env_without_housing_law):
    d = walk_to_step2(svc_env_without_housing_law, TXT_43)
    d = svc_env_without_housing_law.upload.preview(d.upload_id)
    warn = [t["warning"] for t in d.preview["targets"] if not t["in_store"]]
    assert "Văn bản này sửa Luật Nhà ở 27/2023/QH15, nhưng kho chưa có luật này. Hãy upload luật gốc." in warn

def test_preview_shows_per_operation_dates(svc_env):
    d = svc_env.upload.preview(walk_to_step2(svc_env, TXT_43).upload_id)
    assert all("effective_from" in o for o in d.preview["operations"])
    assert d.preview["kind"] == "amending"

def test_reject_unsupported_type(svc_env):
    d = walk_to_step2(svc_env, TXT_DECREE)
    with pytest.raises(StepError, match="Kho luật chỉ nhận"):
        svc_env.upload.confirm_understanding(d.upload_id, "An")

def test_apply_is_stale_when_store_changed(svc_env):
    d = walk_to_step3(svc_env, TXT_UPLOADED_V2, replace=True)
    svc_env.snapshots.write("upload:other", "B", lambda s: replace_text_in_store(s, KEY_UPLOADED, "v3"))
    with pytest.raises(StaleDraftError):
        svc_env.snapshots.write(f"upload:{d.upload_id}", "An", lambda s: svc_env.upload.apply_to(s, d.upload_id))

def test_drafts_survive_restart(tmp_path, svc_env):
    d = svc_env.upload.create_from_file(TXT_43, "43.txt")
    assert DraftStore(svc_env.drafts_root).load(d.upload_id).text == d.text
```

- [ ] **Step 2: Run** `python -m pytest -q tests/test_legal_upload_flow.py` — FAIL.
- [ ] **Step 3: Implement** `drafts.py`, `flow.py`.
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `feat(team-4.2): three-step legal upload drafts and preview`.

---

### Task 7: Chỉ mục gắn snapshot, `LegalRuntime`, hàng đợi ghi

**Files:**
- Modify: `src/rag/temporal/index.py` (`VersionedIndex.__init__`, `build`)
- Create: `ui/legal_runtime.py`
- Test: `tests/test_legal_runtime.py`

**Interfaces:**
- Consumes: Task 2 `SnapshotManager`, Task 6 `UploadService.apply_to`, `DraftStore`.
- Produces in `index.py`: `VersionedIndex(store, embedder=None, *, retriever_factory=None, vector_dir=None, dense=None, snapshot_id: str | None = None)` — `dense` là `VectorIndex` dùng chung giữa các snapshot (vector store chỉ thêm theo `chunk_id`; mỗi `VersionedIndex` chỉ trả chunk trong `chunks` của chính nó, nên dùng chung an toàn); `build()` dùng `dense` được truyền thay vì tự mở; thuộc tính `snapshot_id`.
- Produces in `ui/legal_runtime.py`:

```python
@dataclass
class LegalRuntime:
    snapshot_id: str
    service: LegalService
    index: VersionedIndex
    qa: TemporalQA
    leases: int = 0

class RuntimeHolder:
    def __init__(self, snapshots: SnapshotManager, make_runtime: Callable[[str], LegalRuntime]) -> None
    def get(self) -> LegalRuntime | None
    @contextmanager
    def lease(self) -> Iterator[LegalRuntime | None]      # chat dùng một runtime trọn request
    def offer(self, rt: LegalRuntime) -> bool              # chỉ nhận nếu rt.snapshot_id mới hơn runtime hiện tại (theo published_at); không bao giờ lùi
    def in_use(self) -> set[str]                           # snapshot hiện tại + đang có lease

JobState = Literal["queued", "building", "validating", "publishing", "indexing", "done", "failed", "index_failed"]

@dataclass
class Job:
    job_id: str
    kind: Literal["upload", "review", "reindex"]
    ref: str                       # upload_id | review_id
    actor: str
    state: JobState
    progress: dict | None
    snapshot_id: str | None
    error: str | None
    result: dict | None            # kết quả cho UI (Task 8 định nghĩa nội dung)

class WriteWorker:                 # một luồng daemon, FIFO
    def __init__(self, snapshots: SnapshotManager, holder: RuntimeHolder, *,
                 make_runtime: Callable[[str], LegalRuntime], on_upload_done: Callable[[Job], None] | None = None) -> None
    def submit(self, kind: str, ref: str, actor: str, fn: Callable[[LegalService], Any]) -> Job
    def reindex(self) -> Job                                    # dựng chỉ mục cho snapshot published mới nhất
    def job(self, job_id: str) -> Job                           # KeyError
    def jobs(self) -> list[Job]
    def wait_idle(self, timeout: float) -> bool                 # cho test
```

Mỗi việc: `snapshots.write(reason, actor, fn, progress=...)` → `state` theo giai đoạn → nếu publish xong: `make_runtime(snapshot_id)` (dựng chỉ mục) → `holder.offer` → `done`; lỗi dựng chỉ mục → `index_failed`, holder giữ runtime cũ; sau đó `snapshots.cleanup(in_use=holder.in_use())`.

- [ ] **Step 1: Write the failing tests** (`make_runtime` giả: trả runtime có `index` giả, có thể cấu hình chậm / ném lỗi):

```python
def test_publish_then_switch_after_index(env):
    old = env.holder.get().snapshot_id
    job = env.worker.submit("upload", "u1", "An", add_law)
    assert env.worker.wait_idle(10)
    assert env.worker.job(job.job_id).state == "done" and env.holder.get().snapshot_id != old

def test_build_failure_keeps_runtime(env):
    old = env.holder.get()
    job = env.worker.submit("upload", "u1", "An", add_law_that_breaks_build)
    env.worker.wait_idle(10)
    assert env.worker.job(job.job_id).state == "failed" and env.holder.get() is old

def test_index_failure_keeps_pair(env):
    env.fail_next_index()
    old = env.holder.get()
    job = env.worker.submit("upload", "u1", "An", add_law)
    env.worker.wait_idle(10)
    j = env.worker.job(job.job_id)
    assert j.state == "index_failed" and env.snapshots.current().snapshot_id == j.snapshot_id
    assert env.holder.get() is old and old.index.snapshot_id == old.snapshot_id

def test_two_uploads_while_indexing_never_mix_or_go_back(env):
    env.slow_index(seconds=0.5)
    a = env.worker.submit("upload", "u1", "An", add_law_a)
    b = env.worker.submit("upload", "u2", "Bình", add_law_b)
    env.worker.wait_idle(20)
    rt = env.holder.get()
    assert rt.snapshot_id == env.worker.job(b.job_id).snapshot_id and rt.index.snapshot_id == rt.snapshot_id

def test_lease_survives_switch_and_cleanup(env):
    with env.holder.lease() as rt:
        for i in range(5):
            env.worker.submit("upload", f"u{i}", "An", add_law_n(i))
        env.worker.wait_idle(30)
        assert rt.snapshot_id in env.holder.in_use()
        assert rt.service.store.documents() is not None          # file snapshot còn đọc được

def test_restart_marks_interrupted(env_factory):
    env = env_factory(crash_during_build=True)
    env2 = env_factory(reuse=env)
    assert env2.snapshots.list()[0].status == "failed"
```

- [ ] **Step 2: Run** `python -m pytest -q tests/test_legal_runtime.py tests/test_temporal_index.py` — FAIL (new tests).
- [ ] **Step 3: Implement** index changes + `legal_runtime.py`.
- [ ] **Step 4: Run** — PASS, `tests/test_temporal_*.py` vẫn PASS.
- [ ] **Step 5: Commit** `feat(team-4.2): snapshot-bound legal index and single write queue`.

---

### Task 8: Server — runtime, duyệt qua hàng đợi, API upload pháp luật, CLI

**Files:**
- Modify: `ui/server.py`, `src/rag/legal/__main__.py`
- Test: `tests/test_legal_upload_api.py`; cập nhật `tests/test_legal_review_api.py`, `tests/test_temporal_api.py` nếu chúng phụ thuộc `get_legal_service` / `_temporal_qa` cũ

**Interfaces:**
- Consumes: Task 2, 6, 7.
- Server:
  - Khởi động (lazy, lần đầu cần): `SnapshotManager(DATA_DIR/legal)`; `mark_interrupted()` cho snapshot và `DraftStore`; `RuntimeHolder`; `WriteWorker`. `make_runtime(snapshot_id)` dựng `VersionedIndex` (BM25 + dense dùng chung một `VectorIndex` mở một lần từ `legal_vector_dir`, khi `LEGAL_DENSE != "0"`) + `TemporalQA` như `_build_temporal_qa` hiện tại.
  - `get_temporal_qa()` trả `holder.get().qa`; bỏ vòng kiểm tra `index.stale()` 30 giây. `handle_chat` bọc phần dùng QA trong `holder.lease()`. Giữ nguyên fallback "kho mới lỗi → pipeline cũ".
  - `get_legal_service()` → `snapshots.service()` (snapshot đang công bố) cho đọc ở `/review`.
  - `POST /api/legal/reviews/{id}/decision`: kiểm đồng bộ (body, mục tồn tại và `open` trên snapshot hiện tại) → `worker.submit("review", id, reviewer, lambda svc: svc.decide(decision))` → `202 {"job_id"}`. Lỗi nghiệp vụ của `decide` hiện ra ở job (`failed`, `error`).
  - API mới (JSON; lỗi `StepError` → 409 với `{"error": msg}`, không có → 404):

| Method | Path | Gọi |
|---|---|---|
| POST | `/api/legal/uploads` (multipart `file` hoặc form `url`) | `create_from_file` / `create_from_url` |
| GET | `/api/legal/uploads` | `drafts.list()` (không trả `text`) |
| GET | `/api/legal/uploads/{id}` | `drafts.load` + job hiện tại |
| POST | `/api/legal/uploads/{id}/confirm-text` `{by}` | `confirm_text` |
| POST | `/api/legal/uploads/{id}/replace` `{by}` | `choose_replace` |
| POST | `/api/legal/uploads/{id}/fields` `{values, by}` | `update_fields` rồi `preview` |
| POST | `/api/legal/uploads/{id}/relookup` | `relookup_vbpl` rồi `preview` |
| POST | `/api/legal/uploads/{id}/confirm-understanding` `{by}` | `confirm_understanding` |
| POST | `/api/legal/uploads/{id}/submit` `{by, note}` | `submit` → `worker.submit("upload", id, by, lambda svc: upload.apply_to(svc, id))` → `202 {"job_id"}` |
| POST | `/api/legal/uploads/{id}/retry` `{by}` | chỉ khi `failed` / `index_failed`: như submit |
| POST | `/api/legal/uploads/{id}/cancel` | `cancel` |
| GET | `/api/legal/jobs/{job_id}` | `worker.job` |
| POST | `/api/legal/reindex` | `worker.reindex()` |
| GET | `/api/legal/pending-base-laws` | thao tác `operation.target_law_not_found` trên snapshot hiện tại, nhóm theo `target_law_name` + số |
| GET | `/api/legal/uploads/{id}/page_image/{page}` | ảnh trang gốc (dùng lại cách `handle_page_image` render từ file trong `uploads/<id>/`) |

  - Khi job upload `done`: draft `published`, `snapshot_id`, `result = {"laws": [{"document_key","title","changed_provisions","new_review_items","review_url": "/review?document=<key>"}]}` — `changed_provisions` = số `provision_id` có tập (valid_from, valid_to, text) khác giữa snapshot cha và snapshot mới; `new_review_items` = mục `open` có trong snapshot mới mà không có trong snapshot cha. Job `failed` → draft `failed` + `error`; `StaleDraftError` → draft `stale`.
- CLI: `crawl` → `SnapshotManager.write("cli:crawl", getpass.getuser(), lambda svc: discover(client, svc.store, seeds, legal_dir/"raw", ...))`; `build` → `write("cli:build", user, lambda svc: None)`; `show`/`report` đọc `snapshots.store()`. `WriteLockedError` → in "Đang có lần cập nhật kho khác, thử lại sau" và thoát mã 2. Server đang chạy sẽ thấy snapshot CLI ở lần `reindex` hoặc lần ghi tiếp theo (ghi rõ trong docstring `__main__`).

- [ ] **Step 1: Write the failing tests** (Starlette `TestClient`, `DATA_DIR` tạm, `FakeVbplClient`, `make_runtime` thật trên BM25 không dense với `LEGAL_DENSE=0`):

```python
def test_full_upload_flow_over_http(client):
    r = client.post("/api/legal/uploads", files={"file": ("43.txt", TXT_43.encode())}); uid = r.json()["upload_id"]
    assert client.post(f"/api/legal/uploads/{uid}/submit", json={"by": "An"}).status_code == 409   # nhảy bước
    client.post(f"/api/legal/uploads/{uid}/confirm-text", json={"by": "An"})
    client.post(f"/api/legal/uploads/{uid}/confirm-understanding", json={"by": "An"})
    job = client.post(f"/api/legal/uploads/{uid}/submit", json={"by": "An"}).json()["job_id"]
    wait_job(client, job, "done")
    d = client.get(f"/api/legal/uploads/{uid}").json()
    assert d["state"] == "published" and d["result"]["laws"]

def test_chat_uses_old_pair_until_index_ready(client, slow_index):
    before = server.get_temporal_qa().index.snapshot_id
    job = submit_upload(client, TXT_43)
    assert server.get_temporal_qa().index.snapshot_id == before        # đang dựng chỉ mục
    wait_job(client, job, "done")
    assert server.get_temporal_qa().index.snapshot_id != before

def test_review_decision_is_queued(client_with_open_review):
    r = client_with_open_review.post(f"/api/legal/reviews/{RID}/decision",
                                     json={"action": "reject", "reviewer": "An", "note": "sai"})
    assert r.status_code == 202 and wait_job(client_with_open_review, r.json()["job_id"], "done")

def test_review_decision_during_upload_build_is_not_lost(client_with_open_review, slow_build):
    job_u = submit_upload(client_with_open_review, TXT_43)
    job_r = client_with_open_review.post(f"/api/legal/reviews/{RID}/decision",
                                         json={"action": "reject", "reviewer": "An", "note": "sai"}).json()["job_id"]
    wait_job(client_with_open_review, job_r, "done")
    assert server.get_legal_service().store.review_item(RID).status == "resolved"

def test_concurrent_same_number_only_one_recorded(client):
    a, b = upload_to_step3(client, TXT_UPLOADED_V2), upload_to_step3(client, TXT_UPLOADED_V3)   # cùng số hiệu, bản trong kho là file
    ja, jb = submit(client, a), submit(client, b)
    wait_idle(client)
    states = {client.get(f"/api/legal/uploads/{a}").json()["state"], client.get(f"/api/legal/uploads/{b}").json()["state"]}
    assert states == {"published", "stale"}

def test_cli_build_reports_lock(tmp_path, held_lock, capsys):
    assert main(["build"]) == 2 and "Đang có lần cập nhật kho khác" in capsys.readouterr().out
```

- [ ] **Step 2: Run** `python -m pytest -q tests/test_legal_upload_api.py tests/test_legal_review_api.py tests/test_temporal_api.py` — FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the three files — PASS.
- [ ] **Step 5: Commit** `feat(team-4.2): legal upload API, queued review decisions, CLI via snapshots`.

---

### Task 9: Giao diện — `/upload` chế độ văn bản pháp luật, `/review` chờ áp dụng

**Files:**
- Modify: `ui/upload.html`, `ui/review.html`
- Test: `tests/test_server_docs.py` (thêm kiểm tra trang có các phần tử chính) + kiểm tra tay ở 1366px / 390px

**Interfaces:**
- Consumes: API Task 8.
- Hành vi:
  - Cột trái: công tắc "Tài liệu thường" | "Văn bản pháp luật" (nhớ lựa chọn bằng `localStorage`, bọc try/catch). Chế độ pháp luật: dropzone + ô URL vbpl, nút "Tải lên"; lịch sử liệt kê bản nháp (`/api/legal/uploads`) với nhãn trạng thái; mục "Chỉ dẫn đang chờ luật gốc" (`/api/legal/pending-base-laws`).
  - Cột phải: thanh bước `① Text đúng chưa? → ② Hệ thống hiểu đúng chưa? → ③ Đưa vào kho`, bước chưa mở bị khoá.
  - ①: dùng lại bản đồ trang / bảng từng trang / ảnh cạnh text của trang hiện có (nguồn URL: text + link vbpl); hộp kiểm tra cấu trúc (số Điều, Điều nhảy số, có điều hiệu lực), cảnh báo nổi bật khi có vấn đề; trùng giống hệt → thông báo dừng; trùng khác → tóm tắt (giống/sửa/thêm/bỏ), danh sách điều sửa với hai cột cũ/mới tô `delete`/`insert`, nút "Thay bản trong kho" (ẩn và thay bằng giải thích "bản vbpl là text gốc" khi `replace_allowed=false`) và "Hủy"; nút "Text đúng, sang bước ②".
  - ②: form trường thông tin, mỗi trường có chip nguồn (`vbpl` / `từ văn bản` / `bạn nhập` / `kế thừa`) + tooltip thời điểm và bằng chứng; chỗ lệch vbpl ↔ text và mâu thuẫn kế thừa tô cảnh báo; khối hiệu lực (ngày chung + câu chữ, ngoại lệ, theo sự kiện, cờ); luật bị sửa với cảnh báo thiếu luật gốc; bảng chỉ dẫn (vị trí, thao tác, ngày hiệu lực, trạng thái, lý do) bấm để xem câu chữ; nút "Tra lại vbpl", "← Quay lại bước ①", "Hiểu đúng, sang bước ③".
  - ③: ô tên người thực hiện (bắt buộc) + ghi chú, tóm tắt, nút "Đưa vào kho luật"; sau khi gửi: các giai đoạn (chờ lượt → dựng (i/n) → kiểm tra → công bố → dựng chỉ mục → chat đã chuyển) cập nhật bằng polling `/api/legal/jobs/{id}` mỗi 1,5 giây; kết quả theo luật với link `/review`; `failed` → lỗi + "Thử lại"/"Huỷ"; `index_failed` → "kho đã cập nhật nhưng chỉ mục hỏi đáp lỗi, chat đang dùng dữ liệu trước đó" + "Dựng lại chỉ mục"; `stale` → "Kho đã thay đổi từ lúc bạn so sánh — hãy xem lại bước ①".
  - `/review`: sau khi gửi quyết định, hiện "Đang áp dụng quyết định…" và poll job; xong thì tải lại danh sách; `failed` hiện `error`. Hỗ trợ `?document=<key>` để lọc.
- [ ] **Step 1: Write the failing test** — `test_upload_page_has_legal_mode` (GET `/upload` chứa `id="mode-legal"`, `id="legal-steps"`), `test_review_page_polls_jobs` (review.html chứa `/api/legal/jobs/`).
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS.
- [ ] **Step 5: Kiểm tra tay**: chạy server, upload `tests/fixtures/legal/realestate` text 43/2024 qua chế độ pháp luật tới hết bước ③; chụp màn hình 1366px và 390px (headless như Task 14 phần 1), không cuộn ngang. Ghi kết quả vào commit message.
- [ ] **Step 6: Commit** `feat(team-4.2): legal upload UI with three steps and queued review`.

---

### Task 10: Tích hợp trên văn bản thật và các trường hợp biên còn lại

**Files:**
- Test: `tests/test_legal_upload_realestate.py`

**Interfaces:**
- Consumes: mọi task trước; fixture `tests/fixtures/legal/realestate` (manifest + text).

- [ ] **Step 1: Write the tests**

```python
def test_upload_equals_crawler(tmp_path):
    # A: manifest đầy đủ -> build_all. B: manifest bỏ 43/2024 -> snapshot -> upload 43/2024 qua URL (FakeVbplClient trả detail từ manifest) -> 3 bước -> write
    assert versions_signature(A, LAND) == versions_signature(B, LAND)      # (provision_id, valid_from, valid_to, text, verification_status)
    assert versions_signature(A, HOUSING) == versions_signature(B, HOUSING)

def test_pdf_like_file_gives_same_operations_as_vbpl(tmp_path):
    # file text = wrap_like_pdf(43/2024), FakeVbplClient tra được metadata -> preview operations == preview từ URL (so (source_locator, operation_type, effective_from))

def test_amending_before_base_applies_later(tmp_path):
    # kho thiếu Luật Nhà ở 27/2023: upload 43/2024 -> thao tác vào 27/2023 có operation.target_law_not_found; upload 27/2023 -> sau write, thao tác áp dụng, Điều hiệu lực 27/2023 có phiên bản từ 2024-08-01

def test_same_file_twice_no_new_snapshot(tmp_path):
    # upload 43/2024 hết 3 bước; upload lại cùng file -> state duplicate; số snapshot không đổi

def test_unverified_replace_does_not_inherit_verification(tmp_path):
    # bản trong kho từ file (source_verified=True nhờ tra vbpl); upload file sửa, tra vbpl lỗi -> phiên bản needs_review với source.no_vbpl_metadata dù field vbpl_id có source="inherited"

def test_replace_vbhn_keeps_links(tmp_path):
    # thay VBHN (nguồn URL) -> quan hệ HOP_NHAT tới luật được hợp nhất còn, _check_vbhn chạy với text mới

def test_multi_date_effectivity_preview(tmp_path):
    # upload Luật Đất đai 31/2024 -> preview.effectivity: exceptions chứa Điều 190, 248 ngày 2024-04-01; conditional_units chứa khoản 9 Điều 60

def test_build_failure_at_nth_law_chat_unchanged(tmp_path, monkeypatch):
    # holder có runtime; build_law ném ở luật thứ 3 -> job failed; holder.get().snapshot_id không đổi; TemporalQA.ask trên runtime cũ vẫn trả kết quả
```

- [ ] **Step 2: Run** `python -m pytest -q tests/test_legal_upload_realestate.py` — sửa lỗi lộ ra ở task sở hữu code (ghi lại trong commit), không nới test.
- [ ] **Step 3: Run cả bộ** `python -m pytest -q` — Expected: toàn bộ PASS (≥ 790 test cũ + test mới).
- [ ] **Step 4: Commit** `test(team-4.2): legal upload integration on real-estate corpus`.
