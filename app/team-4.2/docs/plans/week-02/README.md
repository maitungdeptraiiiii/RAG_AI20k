# Kế hoạch tuần 2 — Ingestion & Data Quality (Team 4.2)

[Yêu cầu tuần 2](../../../../../weeks/week-02/README.md) · [Tracker](../../../../../weeks/week-02/team-4.2-TRACKER.md) · [Bài nộp](../../../../../reports/week-02/team-4.2/README.md)

Mỗi task một file. Làm xong bước nào thì đổi `- [ ]` thành `- [x]` trong file đó; xong cả task thì tick ở bảng dưới
và cập nhật tracker (Status + link PR/bằng chứng).

Ký hiệu: **A** Tùng (tích hợp) · **B** Khánh · **C** Huy · **D** Tuấn · **E** Tú

## Danh sách task

| Xong | File | Task | Owner | Reviewer | Ngày |
|---|---|---|---|---|---|
| [ ] | [00-setup.md](00-setup.md) | Merge tuần 1, tạo nhánh, chốt quyết định | A | Cả nhóm | 1 |
| [ ] | [W02-01-inventory.md](W02-01-inventory.md) | Data inventory + lý do biểu diễn | C | A | 1 |
| [ ] | [W02-01a-fixtures.md](W02-01a-fixtures.md) | 25 tài liệu lỗi cài sẵn + nhãn | B | E | 1 |
| [ ] | [W02-01b-questions.md](W02-01b-questions.md) | Bộ câu hỏi bảng/version/OCR | E | C | 1 |
| [ ] | [W02-02a-schema.md](W02-02a-schema.md) | Schema DocMeta + provenance | D | A | 1–2 |
| [ ] | [W02-02b-tables.md](W02-02b-tables.md) | Nhóm bảng/CSV | B | C | 2 |
| [ ] | [W02-02c-ocr.md](W02-02c-ocr.md) | Nhóm khó: PDF scan + OCR + benchmark OCR (2 bộ + kiểm tra chéo) | C | B | 2–4 |
| [ ] | [W02-02d-text-meta-reingest.md](W02-02d-text-meta-reingest.md) | Nhóm văn bản + metadata + ingest lặp | A | D | 2–3 |
| [ ] | [W02-02e-versioning.md](W02-02e-versioning.md) | Version hiện hành / lịch sử | D | A | 3 |
| [ ] | [W02-02f-pii.md](W02-02f-pii.md) | Mask PII trước embed/log | E | D | 2–3 |
| [ ] | [W02-02g-dedup-review.md](W02-02g-dedup-review.md) | Near-dup, conflict, review queue | A | B | 3 |
| [ ] | [W02-02h-validate.md](W02-02h-validate.md) | Kiểm tra số liệu | B | E | 3 |
| [ ] | [W02-03-quality-report.md](W02-03-quality-report.md) | Đo detector: phát hiện/bỏ sót/báo nhầm | E (+B) | A | 4 |
| [ ] | [W02-04-chunking.md](W02-04-chunking.md) | Fixed vs structural chunking | C | D | 4 |
| [ ] | [W02-05-report-slides.md](W02-05-report-slides.md) | Failure cases, report, README, slides, demo | A, D | Cả nhóm | 4–5 |
| [ ] | [carryover-w01.md](carryover-w01.md) | Việc chuyển từ tuần 1 | E, C, B | A | 1–4 |

## Phụ thuộc

```
00-setup ─┬─ W02-01a fixtures ──┐
          ├─ W02-02a schema ────┼─ 02b tables / 02c ocr / 02d text ─┬─ 02e version
          ├─ W02-01 inventory   │                                   ├─ 02f pii
          └─ W02-01b questions ─┘                                   ├─ 02g dedup/review
                                                                    └─ 02h validate
                                    02* xong ─ W02-03 quality report, W02-04 chunking ─ W02-05 report
```

## Quy tắc chung

- Mỗi PR có reviewer **khác** tác giả; nhánh con từ `feat/team-4.2/w02-ingestion`.
- Người cài lỗi (B) không viết detector; nhãn commit **trước** khi chạy detector.
- Mọi số trong report phải có thư mục kết quả trong `evals/team-4.2/results/w02-*`.
- Dữ liệu tuần 2 ingest vào `DATA_DIR` riêng, không ghi đè snapshot 6 Bộ luật.
