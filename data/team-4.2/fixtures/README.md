# Quality fixtures — Team 4.2

30 fixture nhỏ, hoàn toàn giả lập về **văn bản pháp luật Việt Nam**, tạo ở Week 2 nhưng dùng xuyên suốt các tuần sau để kiểm tra ingestion, data quality, versioning, retrieval và regression. Chúng là **ground truth cho evaluation**, không phải dữ liệu để detector đọc.

## Cách dùng

1. Ingest theo thứ tự trong bảng bên dưới, vào `DATA_DIR` riêng; không ghi đè corpus snapshot 6 Bộ luật.
2. Pipeline tự tạo `SourceRecord`, checksum và các ID. `manifest.jsonl` chỉ cung cấp metadata/hint đầu vào.
3. So `IngestReportV2`, `QualityIssue`, review queue và manifest truy vấn với `labels.jsonl`.
4. Đếm TP/FN/FP bằng script evaluation. Detector không được import hay đọc file labels.

Mọi email, điện thoại và mã định danh trong fixtures là dữ liệu giả lập (`example.test`, dải số minh hoạ), không phải PII thật. `raw/` là nguồn chưa mask; không đưa nó vào log, embedding hoặc dịch vụ bên ngoài.

## Thứ tự ingest

| Thứ tự | Fixture | Mục đích |
|---:|---|---|
| 1–3 | `w02-01`…`w02-03` | Negative controls hợp lệ |
| 4–5 | `w02-04`, `w02-05` | Exact duplicate và same-content candidate của `w02-01` |
| 6–8 | `w02-06`…`w02-08` | Near duplicate; cần review, không tự xoá/gộp |
| 9–13 | `w02-09`…`w02-13` | Chuẩn hoá đơn vị, conflict, khác kỳ và locale mơ hồ |
| 14–18 | `w02-14`…`w02-18` | Version toàn phần/một phần, future effective date và ambiguity |
| 19–22 | `w02-19`…`w02-22` | Bảng: header, tổng, đơn vị/kỳ, PII |
| 23 | `w02-23` | Flowchart thủ tục: OCR/structure quality trung bình-thấp |
| 24 | `w02-24` | Bảng pháp lý rõ: multi-header, đơn vị và ghi chú |
| 25 | `w02-25` | Văn bản pháp lý rõ: heading và paragraph |
| 26 | `w02-26` | Exact duplicate thứ 2 (bản sao bytes của `w02-14`) |
| 27 | `w02-27` | DOCX: PII giả trong đoạn văn + bảng; có mẫu âm (số hiệu, ngày, số tiền, Điều) |
| 28 | `w02-28` | XLSX: caption gộp ô, dòng đơn vị, sheet trống, cột SĐT giả |
| 29 | `w02-29` | PDF scan mờ/nghiêng/nhiễu (từ `w02-25`): OCR kém, không có text layer |
| 30 | `w02-30` | PNG bảng nghiêng −7°, nhiễu (từ `w02-24`): OCR kém |

`w02-26`…`w02-30` được sinh xác định bằng `evals/team-4.2/runners/build_w02_extra_fixtures.py`.

Ba PNG scan `w02-23`…`w02-25` là artifact raster để Tesseract/OCR adapter đọc trực tiếp. `w02-23`, `w02-29`, `w02-30` là failure case `ocr.low_confidence`; `w02-24` và `w02-25` là baseline để kiểm tra parser không báo nhầm. Kỳ vọng text/confidence chính xác phụ thuộc engine OCR; không chấm khớp từng ký tự OCR.

## Quy ước nhãn

- Mỗi nhãn có `split`: `dev` (13 fixture, để chỉnh ngưỡng) hoặc `test` (17 fixture, số báo cáo). Không chuyển fixture test sang dev sau khi đã xem kết quả.

- `expected.ingest_status` dùng đúng enum `IngestReportV2`.
- `dedup_action` dùng enum `DedupResult`.
- `issue_codes` dùng namespace `QualityIssue`.
- `numeric` chỉ nêu quan hệ expected của `NumericComparison`; `incomparable` không mặc định là conflict.
- `query_expectation` là kết quả resolver cần cho `current`/`as_of`, không phải detector.

`manifest.jsonl` là **FixtureManifest**: nó cung cấp file nguồn, metadata/hint và quan hệ test. Pipeline mới tạo `SourceRecord`, `DocumentRecord`, `VersionRecord`, checksum và UUID theo Contract v1. Fixture có `approval="pending"` là case review; dữ liệu pending không được vào answer manifest mặc định.

Fixture và nhãn được đóng băng trước khi implement/tune detector. Mọi sửa nhãn sau đó phải nêu lý do trong PR và được reviewer ngoài người viết fixtures kiểm tra.
