# Schema và interface tuần 2 — Contract v1.2

[Workflow](WORKFLOW_WEEK_2.md) · [Phân công](../src/rag/PHAN-CONG.md) · [Yêu cầu tuần 2](../../../weeks/week-02/README.md)

Tài liệu này chốt thiết kế để Khánh triển khai phần versioning/dedup/review trước, sau đó Huy tích hợp vào pipeline. Đây là contract triển khai được đề xuất trong phiên làm việc với Khánh; chưa xác nhận các thành viên khác đã duyệt. Không thay thế `schema.py` hoặc interface đang chạy cho đến khi có adapter và migration tương ứng.

## 1. Quyết định thiết kế

- Giữ API tuần 1 hoạt động. Đặt model trong `rag/models/` và contract theo chức năng trong `ingest/`, `quality/`, `versioning/`, `retrieve/`; dùng adapter để nối sang `Page`, `Chunk`, `Hit` hiện có. Xem [cấu trúc code và import mới](CODE_LAYOUT.md).
- Dữ liệu trao đổi dùng Python dataclass; danh sách bất biến dùng `tuple`. Ngày hiệu lực dùng `date`; thời điểm thu thập/xử lý dùng `datetime` có timezone, serialize UTC ISO-8601. Enum serialize thành chuỗi; `Decimal` serialize thành chuỗi thập phân, không chuyển qua float.
- Lưu metadata, phiên bản, review, findings và manifest trong SQLite ở `DATA_DIR` tuần 2. Ảnh/file nguồn và artifact lớn lưu ngoài SQLite, tham chiếu bằng đường dẫn tương đối dưới `DATA_DIR`.
- Document/version/source là ba định danh riêng. Phiên bản và nội dung đã phát hành là bất biến; thay đổi extraction/masking/chunking tạo processing revision hoặc chunk set mới.
- Detector chỉ trả findings/proposals. Chỉ coordinator/repository được ghi thay đổi trạng thái. Không tự xóa near-duplicate hoặc tự chọn nguồn đúng khi conflict.
- Tuần 2 ưu tiên khả năng chạy lại và đúng dữ liệu. Chưa cần microservice, message broker hay distributed transaction.

## 2. Quy ước chung và ID

| Tên | Quy tắc |
|---|---|
| `document_id` | UUID do repository cấp; định danh tài liệu logic, giữ qua các phiên bản |
| `version_id` | UUID do repository cấp; một lần phát hành nội dung nguồn, không suy ra chỉ từ text OCR |
| `source_id` | UUID do repository cấp; một lần thu thập file/URL, kể cả lần upload trùng |
| `processing_id` | SHA-256 của version + source + parser/OCR/config + checksum đầu ra nguồn chuẩn hóa |
| `unit_id` | ID ổn định trong document cho một đơn vị thay thế được; UUID hoặc key do người dùng xác nhận |
| `unit_revision_id` | SHA-256 của unit + version + processing + phạm vi block; biểu diễn nội dung cụ thể |
| `chunk_set_id` | SHA-256 của processing + unit revisions + chunking/masking/enrichment config và đầu ra đã an toàn |
| `chunk_id` | `<chunk_set_id>:<index>`; ổn định khi cùng đầu vào/config, index từ 0 |
| `raw_checksum` | SHA-256 bytes chính xác của artifact thu thập |
| `content_checksum` | SHA-256 nội dung nguồn chuẩn hóa có cấu trúc; trước masking/enrichment |

Hash dùng JSON canonical: UTF-8, NFC cho text, key sắp xếp, không whitespace thừa; giữ thứ tự blocks/rows/cells. Không bỏ dấu, đổi chữ hoa/thường hoặc xóa dấu câu khi tính exact content checksum. Chuẩn hóa phục vụ near-dup phải là một hàm khác, có version config riêng.

Checksum là tín hiệu trùng, không phải định danh pháp lý. Cùng bytes nhưng metadata hiệu lực khác nhau vẫn phải kiểm tra. File khác bytes nhưng text giống nhau chỉ là `same_content_candidate`; không tự gộp khi có ảnh/bảng chưa được biểu diễn đầy đủ. URL trỏ tới bytes đã tải ở thời điểm thu thập, không hash nội dung URL tương lai.

Mọi record lưu bền có `schema_version: Literal["w02.v1"]`. Số trang/slide bắt đầu từ 1; chỉ số hàng/cột bắt đầu từ 0. `None` là chưa biết hoặc không áp dụng; không thay bằng chuỗi rỗng, ngày upload hoặc số 0.

## 3. Nguồn, tài liệu và phiên bản

### `SourceRecord`

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `source_id` | `str` | ID lần thu thập |
| `source_uri` | `str` | Đường dẫn/URL gốc, không chứa credential |
| `display_name` | `str` | Tên hiển thị |
| `media_type` | `str` | MIME type |
| `raw_artifact` | `str` | Đường dẫn bản nguồn được giữ lại |
| `raw_checksum` | `str` | Hash bytes |
| `collected_at` | `datetime` | Thời điểm thu thập |
| `document_id`, `version_id` | `str | None` | Được điền sau khi resolution/commit |

`source_id` mới không có nghĩa phải tạo version/chunk mới. Có thể ghi nhận lần thu thập trùng rồi liên kết về version cũ.

### `DocumentRecord`

`document_id: str`, `title: str`, `document_type: str`, `language: str`, `external_key: str | None`, `issuer: str | None`, `created_at: datetime`.

`external_key` như số hiệu phải đi với issuer/loại tài liệu khi đối chiếu; không coi riêng số hiệu hoặc tên file là unique key. Language dùng tag như `vi`, `en`, `und`.

### `VersionRecord`

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `version_id`, `document_id` | `str` | ID phiên bản và tài liệu |
| `label` | `str | None` | Nhãn do nguồn cung cấp hoặc tên hiển thị |
| `published_at` | `date | None` | Ngày xuất bản |
| `declared_effective_from` | `date | None` | Ngày hiệu lực ghi trên nguồn |
| `change_kind` | `Literal["initial", "full", "partial"]` | Bản đầu, thay toàn bộ, sửa một phần |
| `supersedes_version_ids` | `tuple[str, ...]` | Quan hệ thay thế; không tự đồng nghĩa thay toàn bộ |
| `approval` | `Literal["pending", "approved", "rejected"]` | Đã xác nhận quan hệ/nội dung hay chưa |
| `created_at` | `datetime` | Thời điểm hệ thống tạo record |

Không lưu `is_current` như nguồn sự thật. Hiện hành là kết quả tính theo ngày, approval và hiệu lực của các unit. Bản chưa có ngày hiệu lực không tự xuất hiện trong truy vấn hiện hành.

### `ProcessingRecord`

`processing_id`, `version_id`, `source_id`, `parser_name`, `parser_version`, `ocr_engine: str | None`, `ocr_config_id: str | None`, `normalization_config_id`, `content_checksum`, `coverage: Literal["complete", "incomplete", "unknown"]`, `created_at`.

Đổi engine OCR không tự tạo phiên bản pháp lý mới. Tạo processing mới và đánh giá/review lại. Chỉ một processing đã duyệt của mỗi unit revision được chọn trong manifest phục vụ truy vấn để tránh nhân đôi kết quả.

## 4. Đầu ra parser/OCR

### `Locator`

`source_id: str`, `page: int | None`, `slide: int | None`, `sheet: str | None`, `table_id: str | None`, `row_start/row_end: int | None`, `column_start/column_end: int | None`, `heading_path: tuple[str, ...]`, `bbox: tuple[float, float, float, float] | None`.

Row/column range là `[start, end)`; `bbox=(x0,y0,x1,y1)` chuẩn hóa 0–1, gốc trên trái sau khi xoay trang về hướng đọc. Phải giữ thông tin kích thước/rotation ảnh trong artifact để truy ngược. Các trường không áp dụng để `None`.

### `TableData`

- `headers: tuple[tuple[str, ...], ...]`: các hàng header, hỗ trợ nhiều tầng.
- `rows: tuple[tuple[str, ...], ...]`: giữ chuỗi nguồn, không ép float.
- `column_units: tuple[str | None, ...]`: cùng số cột; không biết để `None`.
- `caption: str | None`, `notes: tuple[str, ...]`, `period: str | None`.
- `merged_cells: tuple[CellSpan, ...]`: mỗi span có row/column range và chỉ rõ vùng `headers` hoặc `rows`.

Giữ hàng/cột rỗng có ý nghĩa. Nếu flatten ô merge hoặc parser không xác định được header/đơn vị, ghi finding về mất cấu trúc.

### `Block`

| Trường | Kiểu |
|---|---|
| `block_id` | `str` — `<processing_id>:<order>` |
| `processing_id`, `version_id` | `str` |
| `order` | `int` — thứ tự đọc từ 0 |
| `kind` | `Literal["heading", "paragraph", "table", "image", "list", "flow"]` |
| `text` | `str` — nội dung nguồn trích xuất, có thể rỗng với ảnh |
| `origin` | `Literal["native", "ocr"]` |
| `locator` | `Locator` |
| `table` | `TableData | None` |
| `image_artifact` | `str | None` |
| `ocr_confidence` | `float | None` |
| `relations` | `tuple[BlockRelation, ...]` |

`BlockRelation` gồm `target_block_id`, `relation: Literal["next", "contains", "branch"]`, `condition: str | None`; dùng khi xử lý flowchart để giữ thứ tự/điều kiện. Bảng bắt buộc có `table`; ảnh/biểu đồ cần giữ artifact gốc. Mô tả ảnh do LLM sinh phải nằm trong enrichment riêng, không gán vào text nguồn với nhãn `native`.

OCR confidence nếu có phải trong `[0,1]`, kèm cách tính trong config engine; không mặc định so sánh trực tiếp confidence của hai engine. `None` không phải chất lượng hoàn hảo.

### `ParseResult` và `OCRResult`

- `ParseResult(processing: ProcessingRecord, blocks: tuple[Block, ...], findings: tuple[QualityIssue, ...])`.
- `OCRPageInput(source_id, page, image_artifact, width, height, rotation)`.
- `OCRResult(regions: tuple[OCRRegion, ...], engine_name, engine_version, cost_usd: Decimal, elapsed_ms: int, findings)`.
- `OCRRegion(text, bbox, order, confidence, kind)`; parser adapter gán ID và chuyển thành `Block`.

OCR engine không tự cấp document/version ID, không lưu index, không quyết định phiên bản. Phân công gọi đầu ra OCR là `Block`; khi tích hợp có thể dùng `OCRRegion` hoặc alias riêng, nhưng phải phân biệt với `rag.models.Block` đã có provenance đầy đủ.

## 5. Chất lượng, PII và số liệu

### `TargetRef` và `QualityIssue`

`TargetRef` có `source_id`, `version_id`, `block_id`, `unit_revision_id`, `chunk_id` đều optional nhưng ít nhất một trường phải có; kèm `locator: Locator | None`. Không dùng một chuỗi ID mơ hồ không có loại đối tượng.

`QualityIssue` gồm:

- `issue_id: str`: hash detector/config + code + target refs + chứng cứ chuẩn hóa; ổn định khi chạy lại.
- `code: str`: namespace như `ocr.low_confidence`, `pii.detected`, `numeric.sum_mismatch`, `dedup.near`, `version.ambiguous`.
- `severity: Literal["info", "warning", "error"]`.
- `targets: tuple[TargetRef, ...]`: có thể gồm hai nguồn đối với conflict.
- `message: str`, `safe_evidence: dict[str, JSONValue]`: chỉ chứng cứ đã mask.
- `detector_name`, `detector_version`, `config_id`, `created_at`.

Không đưa PII gốc vào issue message, exception, trace hoặc report.

### Masking

`SafeBlock` có cùng cấu trúc cần thiết như `Block` nhưng mọi text/caption/notes/table cell/condition đã qua masking; giữ nguyên ID và locator. Đầu vào chưa mask không được dùng cho embedder, contextual LLM, reranker dịch vụ ngoài hoặc log nội dung.

`MaskResult(blocks: tuple[SafeBlock, ...], findings: tuple[QualityIssue, ...], masking_config_id: str)`.

Artifact nguồn và extraction gốc chỉ nằm ở khu lưu nguồn; bản phục vụ retrieval/citation là bản đã mask. Không lưu mapping đảo ngược PII trong log. Nếu cần mapping nội bộ thì lưu riêng, không cho answer path truy cập.

### Validation số liệu

`NumericContext(metric_key, unit, currency, period_start, period_end, dimensions)`; trường chưa biết là `None`, dimensions là mapping đã chuẩn hóa như vùng/đối tượng.

`NumericFact(fact_id, target: TargetRef, raw_value: str, value: Decimal | None, context: NumericContext, verified: bool)`.

`NumericComparison(relation: Literal["equal", "different", "incomparable", "invalid"], left_value: Decimal | None, right_value: Decimal | None, canonical_unit: str | None, reason: str)`.

Chỉ trả `equal/different` khi metric, kỳ, dimensions và đơn vị tương thích; thiếu ngữ cảnh trả `incomparable`. Dấu chấm/phẩy phải được giải theo locale/config; chuỗi mơ hồ trả `invalid` hoặc finding, không đoán âm thầm. Tolerance là `Decimal` có trong config, mặc định 0. `verified` đòi hỏi bước xác minh riêng; tổng số học khớp không tự đặt `verified=True`. Số OCR/LLM chưa xác minh không dùng làm cơ sở tính toán.

### `QualityAssessment`

`assessment_id`, `target`, `issue_ids`, `status: Literal["pending", "passed", "needs_review", "rejected"]`, `policy_id`, `assessed_at`.

Đây là kết quả áp dụng policy lên findings và quyết định review. Một `warning` không tự chặn mọi dữ liệu; policy phải nêu code nào chặn. `pending`, `needs_review`, `rejected` không được chọn vào answer manifest mặc định. Approval phiên bản và quality status được kiểm tra riêng.

## 6. Dedup và nhận diện tài liệu

`IdentityHint(document_id: str | None, external_key: str | None, issuer: str | None, title: str | None)` do caller cung cấp. Nếu không biết ID và không có ứng viên mơ hồ, repository tạo document mới; nếu có nghi vấn thì review.

`DedupMatch(candidate_version_id, kind: Literal["exact_artifact", "same_content_candidate", "near_duplicate"], similarity: float | None, targets, explanation)`.

`DedupResult(matches: tuple[DedupMatch, ...], action: Literal["link_existing", "continue", "review"], existing_version_id: str | None, findings)`.

- `link_existing` chỉ khi xác nhận nguồn/nội dung trùng và metadata nhận diện/hiệu lực không mâu thuẫn; ghi thêm SourceRecord, không tạo lại chunk.
- Cùng nội dung nhưng khác hiệu lực/quan hệ tài liệu không tự bỏ qua.
- Near-dup/conflict không tự xóa hoặc gộp. Thuật toán, threshold, score và config phải có trong kết quả chạy.
- Không import nhãn chuẩn fixtures vào detector.

## 7. Sửa đổi toàn bộ và một phần

### `ContentUnit` / `UnitRevision`

- `ContentUnit(unit_id, document_id, unit_key, title)`: đơn vị thay thế được, như toàn tài liệu hoặc một Điều. `unit_key` do mapping xác nhận, không sinh từ thứ tự chunk.
- `UnitRevision(unit_revision_id, unit_id, version_id, processing_id, block_ids: tuple[str, ...])`: nội dung trích xuất bất biến của đơn vị đó.
- `ApplicabilityRecord(applicability_id, unit_revision_id, effective_from: date | None, effective_to: date | None, approval, replaces: tuple[str, ...], decision_id: str | None)`.

Khoảng hiệu lực là `[effective_from, effective_to)`. `effective_to=None` nghĩa là chưa có mốc kết thúc được biết, không chứng minh mãi mãi còn hiệu lực. `effective_from=None` không đủ điều kiện truy vấn theo thời gian cho tới khi review bổ sung. Mọi điều chỉnh khoảng hiệu lực phải lưu audit; không sửa text của UnitRevision.

### `VersionPlan`

`plan_id`, `base_catalog_revision: int`, `document_id`, `candidate_version`, `candidate_units`, `candidate_unit_revisions`, `applicability_changes`, `required_review_ids`, `action: Literal["link_existing", "create", "review"]`.

`applicability_changes` ghi đầy đủ bản applicability cũ và bản dự kiến mới, cùng lý do. Đây là đề xuất, chưa được dùng cho truy vấn cho đến commit/activation.

- Bản đầu: tạo unit và khoảng hiệu lực.
- Thay toàn bộ: chấm dứt các unit đang có hiệu lực thuộc phạm vi thay thế tại ngày bản mới có hiệu lực; tạo unit revisions mới. Kiểm tra cả bản tương lai đã lên lịch để tránh interval chồng nhau.
- Sửa một phần: chỉ kết thúc/thay revision của các unit được nêu rõ; giữ các unit còn lại. `ChangeRequest` bắt buộc có mapping cũ→mới và ngày hiệu lực; không suy ra việc thay thế chỉ vì near-dup cao.
- Chỉ sửa một đoạn trong Điều: dựng revision đầy đủ của Điều sau sửa, có refs về cả phần kế thừa và phần sửa. Nếu chưa dựng được, giữ pending review; không ghép ngầm trong answer LLM.
- Hai revision cùng unit chồng hiệu lực mà chưa xác nhận quan hệ: đánh dấu mơ hồ và review, không chọn bản upload gần nhất.

Để xử lý partial update, tài liệu phải được phân unit ổn định ngay từ lần ingest đầu (ví dụ theo Điều). Tài liệu không có cấu trúc có thể có một unit toàn văn; nếu sau này cần sửa một phần, phải có migration phân unit được review.

## 8. Review và audit

`ReviewItem(review_id, issue_ids, targets, status: Literal["open", "resolved"], created_at, resolved_at: datetime | None)`.

`ReviewDecision(decision_id, review_id, action: Literal["accept", "reject", "keep_both", "link_existing", "confirm_replacement", "request_correction"], reviewer, reason, payload, created_at)`.

Payload được validate theo action: `confirm_replacement` phải có mapping unit revisions và ngày hiệu lực; `link_existing` phải có version đích. `keep_both` không tự chọn một bản cho current query. `request_correction` đóng yêu cầu hiện tại nhưng không cho phép dữ liệu lỗi vào manifest; bản sửa tạo assessment/review mới khi cần.

Resolve phải kiểm tra trạng thái/revision để chống hai người ghi đè. Quyết định được append vào audit, không xóa findings cũ. Detector chạy lại cùng issue không mở lại review đã giải quyết, trừ khi evidence/config thay đổi tạo issue mới.

Bổ sung API v1.2: `ReviewService.get(review_id)` trả `ReviewDetails(item, revision, issues, decision, application)`; `list_items(status="open", limit=100, offset=0)` phân trang theo trạng thái; `enqueue_version(plan, parsed, source, hint=..., change=..., dedup=...)` giữ input pending cho bước tái lập kế hoạch. `resolve(..., expected_revision=...)` luôn kiểm tra phiên bản queue và replan trên catalog mới nhất trước khi áp dụng version. Với thay toàn bộ, payload `confirm_replacement` có `effective_from` và `supersedes_version_ids`; với sửa một phần, có mapping revision cũ → unit key mới. Không bắt buộc mapping từng Điều đối với thay toàn bộ. Record lưu vẫn dùng `w02.v1`; các bảng queue được tạo thêm, không sửa cấu trúc record cũ.

## 9. Chunk, enrichment và phạm vi truy vấn

### `ChunkV2`

Giữ các trường tương thích `Chunk` hiện có: `chunk_id`, `doc_id`, `source`, `page_start`, `page_end`, `section`, `text`, `context`.

Bổ sung `document_id`, `version_id`, `processing_id`, `unit_revision_id`, `chunk_set_id`, `block_ids`, `locators: tuple[Locator, ...]`, `language`, `kind`, `masking_config_id`, `quality_assessment_id`, `generated_context: GeneratedContext | None`.

- `doc_id` legacy ánh xạ **chunk_set_id**, vì `ChunkStore` hiện dedup theo doc_id; không ánh xạ document_id khiến bản mới bị bỏ qua. Dùng adapter rõ ràng và không trộn dữ liệu tuần 1.
- Một chunk chỉ thuộc một unit revision. Không overlap qua ranh giới unit/version hoặc qua nội dung bị chặn chất lượng.
- `text` là bản nguồn đã mask, không phải câu do LLM viết lại. `context` là chuỗi enrichment được render từ `generated_context` hoặc header, không được ghi đè text.
- `GeneratedContext(text, origin: Literal["header", "llm"], model_id: str | None, prompt_config_id: str | None, input_checksum)` tách biệt khỏi bằng chứng.
- Chunk bảng lặp lại header/đơn vị/chú thích cần thiết; không cắt giữa một hàng nếu chưa có cách tái lập rõ ràng.
- Citation dùng locators và version, không chỉ dùng page_start. Các block kế thừa sau partial update có thể đến từ nhiều nguồn.

### `QueryScope` / `ResolvedScope`

`QueryScope(mode: Literal["current", "as_of", "all_versions"], as_of: date | None, document_ids: tuple[str, ...] = (), version_ids: tuple[str, ...] = ())`.

- `current`: lấy ngày hiện tại theo timezone cấu hình ứng dụng; ghi ngày đã resolve vào trace.
- `as_of`: bắt buộc có ngày, kiểm tra khoảng hiệu lực của unit.
- `all_versions`: lịch sử đã duyệt, cho phép nội dung ngoài khoảng hiện hành; vẫn loại dữ liệu pending/rejected.
- `version_ids` nếu có là điều kiện bổ sung, không được bỏ qua quality/approval. Danh sách filter rỗng nghĩa là không hạn chế theo filter đó.
- Không có flag cho user bình thường bật pending review. Giao diện review đọc dữ liệu riêng ngoài answer path.

`ResolvedScope(generation_id, catalog_revision, resolved_date: date | None, eligible_chunk_ids: frozenset[str], ambiguous_unit_ids: tuple[str, ...], findings)`.

Resolver phải trả đủ điều kiện theo version, unit applicability, quality và chunk set đang được chọn. Không chỉ lọc `version_id`: partial update có thể dùng units từ nhiều phiên bản nguồn. Unit mơ hồ bị loại; trace/câu trả lời phải cảnh báo thiếu bằng chứng phù hợp, không trình bày kết quả như đã đầy đủ.

Mọi retrieval arm chỉ tìm trong eligible chunks. BM25 có thể dựng corpus đã lọc và cache theo generation/scope; vector backend dùng filter hoặc tìm đầy đủ ứng viên hợp lệ trước khi lấy top-k. Không lấy global top-k rồi loại bản cũ ở cuối. Khi merge theo Điều phải có khóa document + unit revision; không gộp hai phiên bản khác nhau do section giống nhau. Hit.merged, neighbors và context expansion đều phải nằm trong ResolvedScope.

Citation tuần 2 bổ sung document_id, version_id, unit_revision_id và locators; giữ các trường citation tuần 1 để tương thích. Nếu so sánh nhiều phiên bản, gắn rõ nguồn và ngày hiệu lực từng bằng chứng.

## 10. Interface Python cần cung cấp

Các tên kiểu dưới đây trỏ tới models trong tài liệu này. Method đồng bộ cho phạm vi tuần 2; không âm thầm thực hiện ghi/index trong parser hoặc detector.

```python
class SourceReaderV2(Protocol):
    def read(self, value: str | Path, *, display_name: str | None = None) -> RawSourceV2: ...

# RawSourceV2: source: SourceRecord, content: bytes
# Reader lưu artifact thô trước, không log bytes/text nguồn.

class DocumentParserV2(Protocol):
    def parse(self, raw: RawSourceV2, *, candidate_version_id: str,
              config: ParseConfig, ocr: OCREngine | None = None) -> ParseResult: ...

class OCREngine(Protocol):
    def extract(self, page: OCRPageInput, *, config: OCRConfig,
                budget: BudgetLedger) -> OCRResult: ...

class PIIMasker(Protocol):
    def mask(self, blocks: Sequence[Block], *, config: MaskConfig) -> MaskResult: ...

class QualityValidator(Protocol):
    def validate(self, blocks: Sequence[SafeBlock], *, config: ValidationConfig) -> tuple[QualityIssue, ...]: ...

class NumericNormalizer(Protocol):
    def extract(self, blocks: Sequence[SafeBlock], *, config: NumericConfig) -> tuple[NumericFact, ...]: ...
    def compare(self, left: NumericFact, right: NumericFact,
                *, config: NumericConfig) -> NumericComparison: ...

class DedupDetector(Protocol):
    def detect(self, source: SourceRecord, parsed: ParseResult, *, hint: IdentityHint,
               catalog: CatalogView, config: DedupConfig) -> DedupResult: ...

class ConflictDetector(Protocol):
    def detect(self, candidate: Sequence[NumericFact], existing: Sequence[NumericFact],
               *, numeric: NumericNormalizer, config: ConflictConfig) -> tuple[QualityIssue, ...]: ...

class VersionResolver(Protocol):
    def propose(self, parsed: ParseResult, *, hint: IdentityHint, dedup: DedupResult,
                change: ChangeRequest, catalog: CatalogView) -> VersionPlan: ...

class ReviewService(Protocol):
    def enqueue(self, issues: Sequence[QualityIssue]) -> tuple[ReviewItem, ...]: ...
    def resolve(self, review_id: str, decision: ReviewDecision,
                *, expected_revision: int) -> ReviewItem: ...

class ChunkerV2(Protocol):
    def chunk(self, blocks: Sequence[SafeBlock], *, units: Sequence[UnitRevision],
              assessments: Sequence[QualityAssessment], config: ChunkingConfig) -> tuple[ChunkV2, ...]: ...

class ScopeResolver(Protocol):
    def resolve(self, scope: QueryScope, *, snapshot: CatalogSnapshot,
                clock: Clock) -> ResolvedScope: ...

class ScopedRetriever(Protocol):
    def retrieve(self, query: str, *, scope: ResolvedScope,
                 k: int = 5, mode: str = "hybrid", rerank: bool = True) -> RetrievalResultV2: ...

class IngestionCoordinator(Protocol):
    def ingest(self, value: str | Path, *, hint: IdentityHint,
               change: ChangeRequest, config: IngestConfig) -> IngestReportV2: ...
```

`CatalogView` là snapshot read-only có revision, tài liệu, nguồn/checksum, versions, applicability và fingerprints phục vụ detector; đọc extraction chưa mask chỉ trong nội bộ, không đưa ra log/dịch vụ ngoài. `CatalogSnapshot` là snapshot đã activate có generation/index tương ứng. `Clock.today(timezone)` được inject để kiểm thử không phụ thuộc ngày máy chạy.

`ChangeRequest(kind, effective_from, supersedes_version_ids, unit_mapping, unit_assignments=())` mô tả thay đổi do caller/nguồn xác nhận. `kind="partial"` bắt buộc mapping; chưa đủ thông tin trả plan review, không đoán.

Bổ sung tương thích v1.1: `UnitAssignment(unit_key, title, block_ids, complete=False)` chỉ định block thuộc đơn vị nào. Phải xác nhận `complete=True` khi có toàn văn đơn vị sau sửa; câu lệnh sửa đổi chưa được hợp nhất không đủ điều kiện. `unit_mapping` là tuple `(old_unit_revision_id, new_unit_key)`; với partial phải ánh xạ một-một, đúng revision đang hiệu lực, cùng document/unit. `supersedes_version_ids` chứa phiên bản nguồn của các Điều bị tác động, không bắt buộc là phiên bản mới nhất của toàn tài liệu. Trường `unit_assignments` mặc định rỗng giữ tương thích cách gọi cũ; record lưu SQLite không đổi cấu trúc nên vẫn dùng `schema_version="w02.v1"`, không cần migration database cho trường request này.

`RetrievalResultV2` giữ các trường result hiện tại và thêm resolved scope, warnings; answer adapter giữ citation/version metadata xuyên suốt.

`IngestReportV2` có `run_id`, `source_id`, `document_id: str | None`, `version_id: str | None`, `processing_id: str | None`, `status: Literal["duplicate", "needs_review", "activated", "failed"]`, `new_chunk_count`, `issue_ids`, `review_ids`, `generation_id: str | None`, `safe_errors`. Không báo `activated` nếu chỉ có metadata mà chưa có index sẵn sàng.

### Config bắt buộc

Config là dataclass có validate và `config_id` hash canonical; không dùng dict tự do cho contract chính.

| Config | Trường tối thiểu |
|---|---|
| `ParseConfig` | parser/version, normalization version, ngôn ngữ, tiêu chí chọn trang OCR |
| `OCRConfig` | engine/model/version, ngôn ngữ, confidence policy, timeout, cache config |
| `MaskConfig` | detector/version, loại PII, placeholder policy |
| `ValidationConfig` | rules/version, quality policy |
| `NumericConfig` | locale, unit conversion version, tolerance Decimal |
| `DedupConfig` | thuật toán/version, threshold, fingerprint config |
| `ConflictConfig` | metric mapping/version, NumericConfig ID |
| `ChunkingConfig` | strategy fixed/structural, size, overlap, tokenizer/word-count version, table policy |
| `IngestConfig` | các config trên, enrichment config nếu bật, DATA_DIR, budget policy |

Không hardcode threshold vào schema. Threshold được chốt trong config trước khi đánh giá test set.

## 11. Persistence, index và lỗi chạy giữa chừng

Repository cần các thao tác:

```python
catalog.snapshot() -> CatalogView
catalog.record_source(source) -> None
catalog.stage(plan, processing, blocks, findings, chunks,
              *, expected_revision) -> StagedGeneration
indexes.build_generation(staged) -> IndexReceipt
catalog.activate(generation_id, receipt, *, expected_revision) -> CatalogSnapshot
catalog.abort(generation_id, safe_error) -> None
```

Các contract hỗ trợ:

- `StagedGeneration(generation_id, base_catalog_revision, selected_chunk_ids, index_signature, manifest_checksum)` chứa toàn bộ corpus đã duyệt cần có cho snapshot mới; không chỉ chunks vừa thêm.
- `IndexReceipt(generation_id, index_signature, manifest_checksum, completed_backends, ready_at)` xác nhận BM25/vector và mọi retrieval arm đang bật đã build đủ.
- `BudgetLedger.reserve(max_cost_usd) -> reservation_id`; `settle(reservation_id, actual_cost_usd)`; `release(reservation_id)`; lưu bền và tính cả reservation đang chạy để không vượt ngân sách khi gọi song song.
- Cache OCR dùng checksum ảnh + engine/model/config; cache hit không phát sinh chi phí API mới. Ngân sách OCR/agent dùng ledger chung, có khoản giữ lại cho agent theo cấu hình; không coi mỗi engine có riêng 2 USD.

Stage chưa thay đổi snapshot đang phục vụ. Build index trong generation mới, sau đó activate bằng một transaction metadata/pointer khi receipt khớp. Query giữ cố định snapshot từ đầu đến cuối. Không cập nhật live index từng phần rồi mới đánh dấu hoàn tất.

Nếu catalog revision đổi khi đang build, activation trả `ConcurrentUpdateError`; replan/rebuild trên snapshot mới. Khi restart, generation chưa activate không được phục vụ; có thể retry idempotent hoặc abort. Giữ generation cũ trong thời gian query đang dùng; việc dọn artifact là thao tác riêng.

Với 25 fixtures, rebuild toàn bộ generation được chọn để giảm rủi ro đồng bộ. Đây là phần Huy tích hợp; Khánh có thể cung cấp fake index receipt trong kiểm thử repository, nhưng demo thật phải có receipt từ backend thật.

Các lỗi lập trình/config/input không hợp lệ raise exception có mã: `UnsupportedSourceError`, `SchemaValidationError`, `ParseError`, `BudgetExceededError`, `ConcurrentUpdateError`, `IndexBuildError`. Dữ liệu có vấn đề chất lượng trả findings/review, không giả thành lỗi hệ thống. Không nhúng text chứa PII vào exception.

## 12. Thứ tự chạy chuẩn

1. Thu thập nguồn, lưu checksum và source record; kiểm tra bản trùng bytes cùng identity/metadata để có thể bỏ qua parsing sớm.
2. Parse/OCR và tạo processing/blocks. Chưa xác định identity thì candidate version ID chỉ là ID dự kiến, chưa được approve.
3. Tính fingerprint nội bộ; mask PII; chạy quality/numeric validation trên SafeBlocks. Detector cần nguồn gốc chỉ đọc nội bộ và trả chứng cứ đã mask.
4. Chạy dedup, conflict, identity/version resolution; tạo review items nếu thiếu dữ kiện. Không thay catalog hiện hành chỉ vì có proposal.
5. Sau quyết định review cần thiết, tạo unit revisions/applicability và assessment đủ điều kiện.
6. Chunk SafeBlocks theo unit; enrichment nếu bật; lưu metadata/artifact staging.
7. Build generation index, verify receipt, activate snapshot. Trả report và kết quả có thể chạy lại.
8. Khi ask: resolve scope trên snapshot, retrieve trong eligible IDs, rerank/select context cùng phạm vi, generate và cite bản nguồn đã mask.

## 13. Khánh bàn giao gì, Huy follow gì?

Đây là đề xuất chia nội bộ; `PHAN-CONG.md` hiện chưa gán riêng task cho Huy/Khánh.

| Khánh làm trước | Huy tích hợp sau |
|---|---|
| `models/` và các interface theo chức năng trong contract này | Adapter Reader/Parser/Page/Chunk tuần 1 sang tuần 2 |
| VersionResolver, unit applicability, ScopeResolver | Kết nối ingest/ask và ScopedRetriever |
| Dedup/conflict orchestration, review/audit repository | Nhận parser bảng, OCR, PII và numeric API từ các thành viên |
| Dữ liệu mẫu, contract checks, hướng dẫn gọi | Generation index, activation và demo xuyên pipeline |

NumericNormalizer và PIIMasker thuộc Nhóm 2; Khánh dùng fake implementation có cùng interface để làm trước. OCR thuộc Tùng. Không viết lại các phần của thành viên khác chỉ để bắt đầu versioning.

Trình tự triển khai của Khánh: models/contracts → repository + full version → review + scope → partial version → near-dup/conflict adapter. Khi thay contract, tăng version và ghi migration; thông báo nhóm trước khi merge.

## 14. Các tình huống phải kiểm chứng trước bàn giao

| Tình huống | Kết quả bắt buộc |
|---|---|
| Upload lại cùng nguồn, identity và metadata | Ghi nhận lần thu thập; không tăng version/chunk/index |
| Cùng tên/số hiệu nhưng khác nội dung không rõ quan hệ | Review; không overwrite/gộp ngầm |
| File khác bytes, extraction giống nhưng còn ảnh chưa đọc | Candidate duplicate; không tự bỏ bản khác |
| Thay toàn bộ v1 bằng v2 ngày D | Trước D lấy v1; từ D lấy v2; lịch sử còn cả hai |
| V2 hiệu lực trong tương lai | Current không lấy sớm; as_of tương lai chọn đúng |
| V2 chỉ sửa Điều 3 | Điều 1/2 v1 vẫn dùng; Điều 3 mới thay đúng ngày |
| Bản cũ upload sau bản mới | Không thay hiện hành chỉ vì collected_at mới hơn |
| Hai revision chồng hiệu lực chưa phân xử | Review và cảnh báo; không chọn tùy ý |
| PII trong text, bảng, context hoặc chứng cứ lỗi | Không xuất hiện nguyên bản trong embedding/log/answer path |
| Khác đơn vị nhưng tương đương | Không báo conflict sau chuẩn hóa |
| Khác kỳ hoặc thiếu metric | Trả incomparable, không kết luận conflict số liệu |
| Chờ review/rejected | Không lọt vào retrieve, merge, neighbors hoặc citations |
| Đổi OCR hoặc chunking config | Không sửa chunk set cũ; không tạo giả phiên bản nguồn |
| Index lỗi hoặc restart trước activate | Snapshot cũ vẫn dùng được; bản dở dang không được query |
| Hai ingest cùng cập nhật catalog | Một commit theo revision; lượt còn lại replan, không mất update |

Kết quả test, config và chất lượng được lưu trong `evals/team-4.2/results/w02-*`; nhãn fixtures và câu hỏi đánh giá phải tách khỏi logic detector. Với gold retrieval, tiếp tục dùng nguồn + vị trí/section và bổ sung phạm vi phiên bản khi cần, không khóa gold vào chunk_id của một chiến lược.
