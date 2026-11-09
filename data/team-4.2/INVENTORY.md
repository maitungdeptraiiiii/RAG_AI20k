# Data inventory — Week 2, Team 4.2

## Phạm vi và nguyên tắc

Team 4.2 xây Legal RAG cho văn bản pháp luật tiếng Việt. Inventory này mô tả **dữ liệu fixture giả lập** để kiểm tra pipeline Week 2; nó không thay thế manifest production hoặc corpus snapshot 6 Bộ luật.

- Raw artifact nằm trong `data/team-4.2/fixtures/raw/`; chỉ dùng `DATA_DIR` Week 2 riêng khi ingest.
- `fixtures/manifest.jsonl` là FixtureManifest: input metadata/hint cho ingest. Repository mới tạo `SourceRecord`, `DocumentRecord`, `VersionRecord`, checksum và UUID.
- `fixtures/labels.jsonl` là ground truth evaluation; detector, parser và chunker không được đọc file này.
- Content gốc, output OCR và mô tả LLM/enrichment là ba lớp riêng. Text trong `Block` là bằng chứng nguồn; `GeneratedContext` không được ghi đè nó.
- PII trong fixture là giả lập. Raw PII không được đi tới embedder, contextual LLM, reranker dịch vụ ngoài, log, exception, issue evidence hay answer path.

## Tóm tắt inventory

| Nhóm | Artifact hiện có | Fixture | Rủi ro chính | Biểu diễn chính |
|---|---:|---|---|---|
| Văn bản native | TXT, Markdown | `w02-01`–`w02-08`, `w02-14`–`w02-18` | mất heading/Điều, dedup sai, lẫn version | `Block(kind="heading"|"paragraph")`, `Locator.heading_path`, `ContentUnit` theo Điều |
| Bảng native | CSV | `w02-03`, `w02-09`–`w02-13`, `w02-19`–`w02-22` | mất header/đơn vị/kỳ, ép float, sai tổng, PII | `Block(kind="table")` + `TableData` |
| Ảnh scan | PNG | `w02-23`–`w02-25` | OCR sai, mất bố cục bảng/flow, provenance không đủ | `OCRPageInput` → `OCRResult` → `Block(origin="ocr")` + `image_artifact` |
| HTML web | Chưa có fixture | khảo sát parser URL | menu/footer lẫn content, URL đổi nội dung | Raw HTML/artifact; block theo heading/paragraph; URL + collected time |
| PDF có text layer | Chưa có fixture | khảo sát parser PDF | mất page/heading/footnote | page-level `Block`, `Locator.page`; giữ PDF gốc |
| PDF scan | Chưa có fixture riêng | cùng policy với PNG scan | OCR confidence/rotation/region | ảnh từng trang + bbox chuẩn hoá + OCR provenance |
| Slide, org chart, biểu đồ | Chưa có fixture | ngoài ba nhóm bắt buộc | plain text làm mất quan hệ/ảnh | slide/page `Locator`; `image_artifact`; relation/entity chỉ khi triển khai bonus |

HTML, PDF, slide, org chart và biểu đồ phải được khảo sát trong report/data inventory theo yêu cầu Week 2; ba nhóm bắt buộc để chạy end-to-end là văn bản, bảng/CSV và scan/OCR.

## Inventory fixture và cách biểu diễn

| Fixture | Loại nguồn | Mục đích chất lượng | Dữ liệu/metadata cần giữ | Kỳ vọng sau parse |
|---|---|---|---|---|
| `w02-01`, `w02-04` | TXT | exact duplicate | artifact bytes, checksum, source URI, identity hint, version/effective date | Hai `SourceRecord`; cùng version/chunk set sau `link_existing`; không nhân index |
| `w02-05` | Markdown | near duplicate khác cấu trúc | heading/paragraph source, parser version, content checksum | Review `dedup.near`; không tự gộp/xóa |
| `w02-06`–`w02-08` | TXT | near duplicate/identity mơ hồ | issuer, title, source, fingerprint/config | Candidate + review queue; giữ cả bản khác biệt |
| `w02-02` | Markdown | thông báo pháp lý hợp lệ | heading, effective date, language | Heading/paragraph native blocks |
| `w02-03` | CSV | bảng báo cáo hợp lệ | headers, rows, period, notes | `TableData`; giữ chuỗi nguồn, không ép số |
| `w02-09`, `w02-10` | CSV | cùng mức phạt khác đơn vị | metric, raw value, `VND`/`triệu VND`, period, region | `NumericFact`; compare `equal` với canonical `VND` |
| `w02-11` | CSV | conflict số liệu | cùng metric/kỳ/dimensions, giá trị khác | `numeric.conflict` + review; dedup vẫn `continue` |
| `w02-12` | CSV | khác kỳ | metric, period khác | `NumericComparison.incomparable`, không gọi là conflict |
| `w02-13` | CSV | chuỗi số mơ hồ | raw string và NumericConfig locale | `invalid` khi locale `und`; không đoán âm thầm |
| `w02-14`–`w02-16` | TXT | v1, full update tương lai, partial Điều 3 | external key + issuer, published/effective date, `change_kind`, unit mapping | `ContentUnit` ổn định theo Điều; `UnitRevision` và applicability theo thời gian |
| `w02-17`, `w02-18` | TXT | bản cũ upload muộn, version mơ hồ | collected/published/effective date, approval | Review; không chọn upload mới nhất làm current |
| `w02-19` | CSV | multi-header/đơn vị/note | nhiều hàng header, unit, note, period | `TableData.headers`, `column_units`, `notes`, `period` |
| `w02-20` | CSV | tổng sai | row values + total row + unit/period | `numeric.sum_mismatch`; policy quyết định review |
| `w02-21` | CSV | thiếu đơn vị/kỳ | `None` thay vì chuỗi rỗng/số 0 | finding `table.missing_unit` / `table.missing_period`; không compare số |
| `w02-22` | CSV | PII giả lập | field/locator/Pii type, evidence đã mask | `SafeBlock`; `pii.detected` chỉ chứa placeholder/metadata an toàn |
| `w02-23` | PNG flowchart | OCR/structure medium-low | original image, page=1, bbox, order, relation/condition | OCR blocks + `next`/`branch` nếu đủ tin cậy; nếu không `ocr.low_confidence`/review |
| `w02-24` | PNG bảng pháp lý | baseline bảng ảnh | image, bbox, header levels, unit, note | OCR/table blocks; không báo false positive chỉ vì là ảnh |
| `w02-25` | PNG văn bản pháp lý | baseline OCR text | image, heading path, page/bbox | OCR heading/paragraph blocks và provenance ảnh |

## Contract mapping

| Contract v1 | Nguồn trong fixture | Trách nhiệm pipeline |
|---|---|---|
| `SourceRecord` | `source_path`, `source_uri`, `display_name`, `media_type`, `collected_at` | Lưu raw artifact, cấp `source_id`, tính `raw_checksum` |
| `DocumentRecord` | `identity_hint` và `document` | Resolve document bằng issuer + external key + type, không dùng filename đơn lẻ |
| `VersionRecord` | `version.label`, dates, `change_kind`, `approval` | Cấp version ID; không dùng `is_current` làm source of truth |
| `ProcessingRecord` | parser/OCR/config được chọn khi chạy | Ghi parser/OCR/config/checksum/coverage; đổi OCR không tạo legal version mới |
| `Locator` | page scan, heading, sheet/table/range khi parser có | Giữ page từ 1; row/column `[start,end)`; bbox chuẩn hoá 0–1 |
| `Block` / `TableData` | raw text, CSV, scan | Text nguồn riêng; bảng phải giữ header/unit/note; ảnh giữ `image_artifact` |
| `SafeBlock` / `MaskResult` | PII fake tại `w02-22` | Mask trước mọi embedding/log/remote service |
| `NumericFact` / `NumericComparison` | `w02-09`–`w02-13`, `w02-20`–`w02-21` | `Decimal`, context đầy đủ mới equal/different; khớp tổng không tự `verified` |
| `QualityIssue` / review | labels chỉ để eval | Detector tạo finding có safe evidence; coordinator/repository quyết định review |
| `ContentUnit` / `ApplicabilityRecord` | Điều 1–3 trong `w02-14`–`w02-18` | Partial update thay đúng Điều; current/as_of lọc approval + interval + quality |

## Rủi ro và policy bắt buộc

| Rủi ro | Policy/điều kiện chấp nhận |
|---|---|
| Ingest lại cùng bytes | Thêm source collection nếu cần, không tạo version/chunk/index mới |
| Near duplicate hoặc conflict | Tạo finding/review; không tự chọn bản đúng hoặc xóa bản kia |
| Version chưa đủ chứng cứ | `approval="pending"`; không vào answer manifest mặc định |
| OCR confidence thấp | Không coi `None` là hoàn hảo; ghi engine/config/cách tính; policy đưa `needs_review` |
| Bảng bị flatten | Giữ artifact; finding structure loss nếu mất header/merged cell/unit/note |
| Số có locale/đơn vị/kỳ khác | Trả `invalid` hoặc `incomparable`; không so sánh/convert âm thầm |
| PII | Raw chỉ ở source store; `SafeBlock` cho retrieval; evidence/log đã mask |
| LLM mô tả hình/flow | Lưu enrichment riêng với origin/config; không đặt vào `Block.text` nguồn |

## Bàn giao và bằng chứng

- Nhóm 1 nhận `fixtures/` cùng FixtureManifest/labels để test repository, dedup, version resolver và review queue.
- Tùng dùng `w02-23`–`w02-25` làm sample pháp luật cho OCR; benchmark chính vẫn dùng dataset riêng theo phân công.
- Nhóm 2 dùng labels sau khi detector chạy để lập TP/FN/FP trong `evals/team-4.2/results/w02-*`.
- Câu hỏi evaluation ở task `W02-01b` sẽ tham chiếu `source_uri` + page/heading/section + version scope, không hard-code `chunk_id`.
- Trước demo, xác nhận URL nguồn ảnh scan vẫn truy cập được và ghi parser/OCR/numeric/chunking config vào kết quả.
