# Phân công tuần 2 — Team 4.2

[Danh sách task](README.md) · Mỗi task chi tiết nằm trong file riêng cùng thư mục.

Chia thành 3 phần: **Tùng làm riêng** · **Nhóm 1 (Huy + Khánh)** · **Nhóm 2 (Tuấn + Tú)**.
Mỗi nhóm tự chia việc nội bộ, ghi tên người làm vào cột "Người làm" và báo lại trong tracker.

---

## Tùng — OCR + Agent multi-hop (làm riêng)

| Task | File | Ngày | Người làm |
|---|---|---|---|
| Interface `OCREngine` / `Block` (giao cho Nhóm 1 trước cuối ngày 2) | [W02-02c](W02-02c-ocr.md) A1 | 1–2 | Tùng |
| Engine Tesseract + Gemini (cache, đếm chi phí, dừng cứng 1.8 USD) | W02-02c A2–A3 | 1–2 | Tùng |
| Thử MinerU / PP-StructureV3, chọn 1 | W02-02c A4 | 2–3 | Tùng |
| Benchmark OCR tiếng Việt (nrl-ai + trang luật + trang bẫy) | W02-02c B0–B1 | 2–3 | Tùng |
| Benchmark cấu trúc (OmniDocBench) + kiểm tra chéo (MDPBench-VI) | W02-02c B2–B3 | 3–4 | Tùng |
| Bảng tổng hợp, chốt engine mặc định | W02-02c B4 | 4 | Tùng |
| Agent loop multi-hop (pilot): decompose → retrieve → kiểm tra đủ bằng chứng → retrieve tiếp (≤ N vòng); đo trên 27 câu `multi` (phần `test`) so với baseline: R@5, độ đúng, số vòng, latency, chi phí | W02-06 (tạo mới) | 4–5 | Tùng |
| Mục OCR + Agent trong report; ≥2 failure case OCR | W02-05 | 5 | Tùng |

Ghi chú:
- Agent loop là **pilot**, hoàn thiện ở tuần 3 (cập nhật dòng query decomposition trong [carryover-w01.md](carryover-w01.md)).
- Nếu thiếu thời gian: ưu tiên B1, cắt B3 trước.
- Ngân sách Gemini 2 USD dùng chung cho OCR và agent → giữ lại một phần cho agent.

---

## Nhóm 1 — Huy + Khánh: Ingestion & Index (phần khó)

Sửa pipeline lõi, schema dùng chung, versioning và dedup. Nhóm này giữ vai trò **tích hợp**.

| Task | File | Ngày | Người làm |
|---|---|---|---|
| Setup: merge tuần 1, tạo nhánh `feat/team-4.2/w02-ingestion`, chốt quyết định | [00-setup](00-setup.md) | 1 | |
| Schema `DocMeta` + provenance (**PR nháp sáng ngày 1, merge trước ngày 2**) | [W02-02a](W02-02a-schema.md) | 1–2 | |
| Văn bản + metadata + ingest lặp, nối các bước vào `RAGPipeline.ingest`, `demo_w02.py` | [W02-02d](W02-02d-text-meta-reingest.md) | 2–3 | |
| Nối OCR vào pipeline: Block → Page/Chunk, dò trang scan theo từng trang, `needs_review` khi confidence thấp | W02-02c A1 (phần pipeline) | 3 | |
| Version hiện hành / lịch sử, văn bản sửa đổi một phần, upload trùng số hiệu | [W02-02e](W02-02e-versioning.md) | 3 | |
| Near-dup, conflict, review queue | [W02-02g](W02-02g-dedup-review.md) | 3 | |
| Fixed vs structural chunking | [W02-04](W02-04-chunking.md) | 4 | |
| Demo: ingest → ingest lại → cập nhật version → review queue → hỏi hiện hành/lịch sử | W02-05 | 4–5 | |
| Report chính (ghép mục của mọi người), README bài nộp, tracker | W02-05 | 5 | |

---

## Nhóm 2 — Tuấn + Tú: Data Quality

> Quy tắc: **người cài lỗi (fixtures) không viết detector** (PII, validate). Nhóm tự chọn ai làm phần nào nhưng phải giữ quy tắc này.

| Task | File | Ngày | Người làm |
|---|---|---|---|
| 25 fixtures lỗi + `labels.jsonl` (**commit trước 17h ngày 1**) | [W02-01a](W02-01a-fixtures.md) | 1 | |
| Data inventory + lý do biểu diễn | [W02-01](W02-01-inventory.md) | 1 | |
| Bộ câu hỏi bảng / version / OCR | [W02-01b](W02-01b-questions.md) | 1 | |
| Nhóm bảng / CSV / XLSX | [W02-02b](W02-02b-tables.md) | 2 | |
| Mask PII trước embed/log | [W02-02f](W02-02f-pii.md) | 2–3 | |
| Kiểm tra số liệu (**API so sánh số đã chuẩn hoá giao cho Nhóm 1 trước ngày 3**) | [W02-02h](W02-02h-validate.md) | 3 | |
| Eval quality report: TP / FN / FP | [W02-03](W02-03-quality-report.md) | 4 | |
| Carryover: chấm tay `answers.csv`; tách dev/test `benchmark_doi_thuong`, thêm câu `out_of_scope` (**trước ngày 4**, agent loop cần) | [carryover-w01](carryover-w01.md) | 1–4 | |
| Failure cases (≥5), slides, README chạy lại | W02-05 | 4–5 | |

---


## Điểm bàn giao giữa các phần

| Khi nào | Từ | Đến | Nội dung |
|---|---|---|---|
| Sáng ngày 1 | Nhóm 1 | Mọi người | PR nháp schema `DocMeta` / `Chunk` |
| 17h ngày 1 | Nhóm 2 | Nhóm 1 | Fixtures + nhãn đã commit |
| Cuối ngày 2 | Tùng | Nhóm 1 | Interface `OCREngine` + `TesseractEngine` chạy được |
| Trước ngày 3 | Nhóm 2 | Nhóm 1 | Hàm chuẩn hoá / so sánh số (W02-02h) cho conflict detection |
| Trước ngày 4 | Nhóm 2 | Tùng | Bộ `benchmark_doi_thuong` đã tách dev/test |
| Ngày 4 | Tùng, Nhóm 2 | Nhóm 1 | Mục report + failure cases |

## Quy tắc chung

- Mọi số trong report phải có thư mục kết quả trong `evals/team-4.2/results/w02-*`.
- Dữ liệu tuần 2 ingest vào `DATA_DIR` riêng, không ghi đè snapshot 6 Bộ luật.
- Đổi `schema.py` phải báo cả nhóm.
