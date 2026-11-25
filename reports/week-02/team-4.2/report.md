# Báo cáo tuần 2 — Team 4.2

## Scope and version

- **Team:** 4.2 — hỏi đáp văn bản luật Việt Nam (6 Bộ luật + kho luật có phiên bản, crawl từ vbpl.vn).
- **Thành viên và đóng góp** (**cần team xác nhận**; phần của Tùng theo `PHAN-CONG.md`, các phần còn lại suy từ commit và ghi chú tuần 2):

| Ký hiệu | Họ tên | Đóng góp chính tuần 2 |
|---|---|---|
| A | Mai Phan Anh Tùng | Fixture + nhãn lỗi cài sẵn (30 file), OCR (benchmark 3 engine, wiring vào pipeline, trang `/upload`), kiểm tra chất lượng và báo cáo phát hiện/bỏ sót/báo nhầm |
| B | Nguyễn Gia Khánh | Ingest bảng CSV/XLSX/DOCX, giữ header/đơn vị/kỳ, validate số liệu |
| C | Lương Quang Huy | Kho luật có phiên bản (Legal Version Builder, `/review`), hỏi đáp theo mốc thời gian, multihop agent, so sánh chunking |
| D | Nguyễn Quốc Tuấn | Schema, versioning + quy trình chất lượng dữ liệu, mask PII, near-duplicate, UI Starlette |
| E | Nguyễn Anh Tú | UI chat (SSE streaming, citation drawer), dedup/review, slides |

- **Mục tiêu tuần:** data ingestion + data quality: không để "garbage in" vào index. Ba nhóm bắt buộc là văn bản, bảng/CSV, scan/OCR; thêm version theo ngày hiệu lực.
- **Đã hoàn thành:**
  - 30 fixture có lỗi cài sẵn (duplicate, near duplicate, conflict, version cũ/mới, sai đơn vị, OCR kém, PII giả) + nhãn `labels.jsonl` tách dev/test; [data inventory](data_inventory.md).
  - Ingest bảng CSV/XLSX/DOCX: mỗi chunk bảng lặp caption + đơn vị + header. Parser tuần 1 không đọc được CSV/XLSX; bảng DOCX 60 hàng chỉ 1/2 chunk có header, nay 3/3.
  - OCR: benchmark Tesseract / Gemini 2.5 Flash / MinerU trên 159 + 80 trang; PDF scan/PNG đi qua OCR, giữ ảnh gốc và `origin="ocr"`.
  - Mask PII trước embedding/BM25/log; exact dedup khi ingest lặp; near-duplicate có đường review; kho luật có phiên bản.
  - So sánh chunk cố định vs theo cấu trúc: [chunking_fixed_vs_structural.md](chunking_fixed_vs_structural.md).
  - Bonus: hỏi đáp theo mốc thời gian (18 câu bất động sản), multihop agent, trang `/upload` và `/review`.
- **Chưa hoàn thành:** detector cho `dedup.near`, `version.ambiguous`, `flow.structure_loss` chưa nằm trong detector pipeline (xem bảng quality); HTML/PDF có text layer/slide/org chart/biểu đồ mới chỉ khảo sát, chưa có fixture; video demo.
- **Commit / snapshot / cấu hình:**
  - Nhánh làm việc `feat/team-4.2/w03-labor-contract-kg-v2` (chứa toàn bộ commit tuần 2); các mốc: `f90c4eb` (fixture), `0ed3a35` (OCR), `4cfb565` (kho luật có phiên bản), `ebbc41a` (temporal QA), `e85894d` (slides W02).
  - Dữ liệu: `data/team-4.2/fixtures/` (30 fixture), 6 Bộ luật 3.422 chunk (structural) và 2.125 chunk (fixed) khi so chunking.
  - Model: embedding `jina-embeddings-v5-text-small`, rerank Jev (`RERANK_N=20`), LLM `gpt-6-luna`; OCR `google/gemini-2.5-flash`, Tesseract 5.5 `vie`, MinerU 4.1.7.
- **Chạy lại:** README mỗi thư mục kết quả trong `evals/team-4.2/results/w02-*`, ví dụ:

  ```bash
  cd app/team-4.2
  python -m scripts.eval_near_duplicate           # near-duplicate baseline vs v2
  python -m rag.legal crawl && python -m rag.legal build && python -m rag.legal report
  python evals/team-4.2/runners/run_temporal_eval.py
  ```

  Slides: [slide.pdf](slide.pdf). Demo/video: chưa có.

## Design decisions

| Bài toán | Lựa chọn | Phương án đã cân nhắc | Trade-off |
|---|---|---|---|
| Biểu diễn bảng | `ParsedTable` → chunk Markdown, lặp caption + đơn vị + header ở mỗi chunk | Làm phẳng thành dòng `a \| b \| c` (tuần 1) | Tốn token hơn; chunk sau vẫn biết cột và đơn vị |
| Nguồn vs mô tả sinh | `Block` giữ text nguồn, `GeneratedContext` ở lớp riêng, không ghi đè | Gộp mô tả LLM vào text | Phải qua thêm một lớp khi truy xuất; tránh LLM "sửa" nguồn |
| OCR | Gemini 2.5 Flash cho trang scan/ảnh chụp; Tesseract/MinerU làm fallback local | Chỉ MinerU; chỉ Tesseract | Gemini CER thấp nhất (3.95% so với 5.79% / 7.09%) nhưng gửi ảnh ra ngoài, bị `RECITATION` ở 1 trang và mất bảng dày; MinerU tốt nhất cho bảng (TEDS 93.0) nhưng sai dấu "hợp lệ" |
| PII | Mask trước mọi bước embed/log/index; raw PII không đi vào answer path | Mask lúc hiển thị | Mất thông tin gốc ở index; đổi lại không lộ qua embedding/log/Qdrant |
| Dedup | Exact dedup tự động theo checksum; near duplicate/conflict vào hàng đợi review, không tự xoá | Tự xoá bản gần giống | Tốn công người duyệt; không mất bản khác biệt quan trọng (ví dụ khác phiên bản/phạm vi) |
| Version | Văn bản luật lưu theo phiên bản + ngày hiệu lực; mỗi nhánh retrieval chỉ thấy chunk còn hiệu lực tại mốc (`ValidityFilteredArm`) | Lọc sau khi rerank | Dựng index lâu hơn (~8 phút lần đầu); chunk cũ không lọt vào truy vấn hiện hành |
| Chunking | Giữ chunk theo cấu trúc (Điều/khoản/điểm, ≤300 âm tiết) | Cửa sổ cố định 300 âm tiết, overlap 50 | Chunk không đều độ dài; thắng ở hybrid + rerank (R@5 0,859 vs 0,826) |

## Evaluation

**Dataset**

- Fixture chất lượng: 30 file, chia `dev`/`test`, nhãn trong `data/team-4.2/fixtures/labels.jsonl` (detector không được đọc file này).
- Near-duplicate: 12 cặp mỗi split, tổng hợp do người viết; cùng họ mẫu xuất hiện ở dev và test, đã được nhìn thấy khi cài đặt nên không phải kiểm chứng độc lập.
- Chunking: `benchmark_doi_thuong_w02.jsonl` — 64 câu trong phạm vi (37 paraphrase, 27 multi), tập test 36 câu; 6 câu `out_of_scope` không có gold nên không tính.
- Temporal QA: 18 câu bất động sản (Luật Nhà ở/KDBĐS/Đất đai 2013–2024), mốc chuyển giao 01/08/2024.
- OCR: nrl-ai 159 trang, OmniDocBench 20 trang chung, MDPBench-VI 80 trang.

**Data quality: phát hiện / bỏ sót / báo nhầm** (split `test`, nguồn [`w02-quality/summary.md`](../../../evals/team-4.2/results/w02-quality/summary.md), commit `db7d3cf-dirty`)

| Phạm vi | TP | FN (bỏ sót) | FP (báo nhầm) | Precision | Recall |
|---|---:|---:|---:|---:|---:|
| Detector có trong pipeline (pii/numeric/table/ocr) | 8 | 0 | 0 | 1.00 | 1.00 |
| Toàn bộ mã lỗi trong nhãn | 8 | 3 | 0 | 1.00 | 0.73 |
| Toàn bộ mã lỗi (dev) | 3 | 3 | 0 | 1.00 | 0.50 |

Bỏ sót: `dedup.near` (w02-05, 07, 08), `version.ambiguous` (w02-17, 18), `flow.structure_loss` (w02-23) — chưa có detector trong pipeline.

**Near-duplicate** ([`w02-near-duplicate`](../../../evals/team-4.2/results/w02-near-duplicate/README.md), ngưỡng 0,85, 12 cặp/split)

| Policy | TP | FP | FN | TN | Precision | Recall |
|---|---:|---:|---:|---:|---:|---:|
| Baseline v1 | 6 | 4 | 1 | 1 | 0,600 | 0,857 |
| V2 | 7 | 2 | 0 | 3 | 0,778 | 1,000 |

| Cấu hình | Nhóm / số câu | Recall@5 | MRR@5 | Độ đúng/citation | Latency | Chi phí |
|---|---|---|---|---|---|---|
| Hybrid, chunk cố định | 64 câu (tất cả) | 0,589 | 0,503 | N/A | N/A | N/A |
| Hybrid, chunk theo cấu trúc | 64 | 0,677 | 0,515 | N/A | N/A | N/A |
| Hybrid + rerank Jev, chunk cố định | 64 | 0,826 | 0,785 | N/A | N/A | N/A |
| **Hybrid + rerank Jev, chunk theo cấu trúc** | 64 | **0,859** | **0,840** | N/A | N/A | N/A |
| Hybrid + rerank, cố định / cấu trúc | test / 36 | 0,745 / **0,806** | 0,773 / **0,817** | N/A | N/A | N/A |
| BM25, cố định / cấu trúc | 64 | **0,328** / 0,258 | **0,226** / 0,157 | N/A | N/A | N/A |
| Dense, cố định / cấu trúc | 64 | **0,810** / 0,805 | 0,686 / **0,715** | N/A | N/A | N/A |

Nguồn: [`w02-chunk-compare`](../../../evals/team-4.2/results/w02-chunk-compare/summary.md). Chấm theo vị trí văn bản (`span_match.py`) để công bằng với chunk không có `section`; khớp chấm theo `section` 256/256 lượt.

**Hỏi đáp theo mốc thời gian** (18 câu, kho thật, nguồn [`w02-temporal-qa`](../../../evals/team-4.2/results/w02-temporal-qa/README.md))

| Cấu hình | Độ đúng mốc | Độ đúng phiên bản (top-10) | `cannot_conclude` | Latency TB/câu |
|---|---|---|---|---|
| BM25 | 18/18 | 17/18 | 11 | không đo |
| Hybrid + HyDE + rerank | 18/18 | **18/18** | 6 | 16,7 s |

Không có lần nào văn bản hết/chưa hiệu lực lọt vào ngữ cảnh; số câu `firm` dựa trên căn cứ chưa xác minh: 0.

**OCR** ([`w02-ocr-summary`](../../../evals/team-4.2/results/w02-ocr-summary/README.md), Tesseract / Gemini / MinerU)

| Chỉ số | Tesseract | Gemini 2.5 Flash | MinerU |
|---|---|---|---|
| CER toàn bộ (159 trang) | 5.79 % | **3.95 %** | 7.09 % |
| TEDS bảng (OmniDocBench, 52 bảng) | N/A | 59.2 % | **93.0 %** |
| Giây/trang (trung vị) | **1.2–3.7** | 3.3–8.2 | 3.8–8.9 |
| Chi phí | 0 | 0.247 USD / 199 trang | 0 |

Chỉ mục: 3.422 chunk (cấu trúc, ingest 386 s) so với 2.125 chunk (cố định, ingest 452 s); 83% chunk cố định (1.763) vắt qua ≥2 Điều, chunk cấu trúc 0.

## Failure analysis

| Case | Kỳ vọng / thực tế | Bằng chứng | Bước gây lỗi | Cách sửa / kết quả chạy lại |
|---|---|---|---|---|
| Parser tuần 1 với bảng | Giữ header/đơn vị; thực tế `.csv`/`.xlsx` báo `UnsupportedSourceError`, bảng DOCX 60 hàng chỉ 1/2 chunk có header, 1/2 có đơn vị | [`data_inventory.md`](data_inventory.md), mục "Thông tin bị mất" | Parse: làm phẳng bảng thành dòng, chunk sau mất ngữ cảnh | `ParsedTable` lặp caption + đơn vị + header: 3/3 chunk có cả hai |
| Near-duplicate vẫn báo nhầm | Cặp khác phiên bản/phạm vi không được coi là trùng; v2 còn 2 FP trên 12 cặp | `w02-near-duplicate/evaluation.json` | Dedup: độ giống văn bản cao nhưng khác định danh/phạm vi | v2 giữ cả hai ở review khi thiếu bằng chứng định danh (bảo thủ); FP 4 → 2, FN 1 → 0 |
| Detector còn thiếu | `dedup.near`, `version.ambiguous`, `flow.structure_loss` phải được phát hiện; thực tế bỏ sót 3/11 mã (test) | `w02-quality/summary.md` mục "Từng bỏ sót" | Validation: pipeline chưa có detector cho 3 mã này | Chưa sửa; recall tổng test 0,73 dù recall trên detector hiện có 1,00 |
| Gemini bị `RECITATION` | Phải OCR đủ trang; `vi_textbook_38` chỉ trả ~1/3 trang, block_ned 0,76 | `w02-ocr-summary` mục Failure case 1 | OCR: nhà cung cấp dừng sinh với nội dung giống sách | Runner gắn cờ `truncated_or_recitation`; chuyển sang engine local |
| OCR sai số "trông hợp lệ" | `Số: 115/NQ-CP` đọc thành `445`; `64/2025/QH15` → `64/2023`; `năm 2026` → `2096` (Tesseract, scan thật) | `w02-ocr-summary` Failure case 3 | OCR: lỗi số không bị bắt bởi kiểm tra định dạng | Số/ngày đúng tại vị trí trên scan thật: Tesseract 85,97% vs Gemini 94,60%; chuyển trang scan qua engine tốt hơn |
| BM25 thắng chunk cố định | Kỳ vọng chunk cấu trúc ≥ cố định; thực tế BM25 R@5 0,258 < 0,328 (multi: 0,093 vs 0,259) | `w02-chunk-compare/summary.md` | Retrieval: chunk cố định dài gần gấp đôi (299,7 vs 163,0 âm tiết) nên chứa nhiều từ khoá hơn | Không sửa; kết luận lợi thế đến từ độ dài, vẫn giữ chunk cấu trúc vì thắng ở cấu hình chạy thật |
| Temporal BM25 chọn sai phiên bản | Câu t17 phải trả văn bản đúng mốc; BM25 17/18 | `w02-temporal-qa/README.md` | Retrieval: BM25 không xếp được văn bản đúng hiệu lực vào top-10 | Chạy lại bằng Hybrid + HyDE + rerank: 18/18, `cannot_conclude` 11 → 6 |

## Findings and limitations

**Được dữ liệu hỗ trợ**

- Chunk theo cấu trúc tốt hơn ở cấu hình chạy thật: R@5 0,859 vs 0,826, MRR@5 0,840 vs 0,785 trên 64 câu; trên test 0,806 vs 0,745. Mỗi chunk cấu trúc thuộc một Điều; 83% chunk cố định trộn ≥2 Điều làm rerank nhiễu.
- Giữ header, đơn vị, kỳ ở mỗi chunk bảng khắc phục lỗi mất ngữ cảnh của parser tuần 1.
- Lọc theo hiệu lực trước rerank đủ để chunk sai phiên bản không lọt vào ngữ cảnh (0/18 câu).
- Không có engine OCR nào thắng toàn bộ: Gemini tốt nhất về chữ và ảnh chụp, MinerU tốt nhất về bảng và chạy cục bộ.

**Không được hỗ trợ / chưa kiểm chứng**

- Lợi thế BM25 của chunk cố định không phải do cách cắt mà do độ dài; chưa có thí nghiệm kiểm soát độ dài.
- "Mask PII làm sạch log" mới kiểm bằng quét embedding/BM25/contextual LLM/log/`chunks.jsonl`/file Qdrant trên fixture giả lập (0 kết quả), chưa trên dữ liệu thật.

**Giới hạn**

- 30 fixture và 12 cặp near-duplicate do chính nhóm soạn; cùng họ mẫu giữa dev và test, precision/recall 1,00 có thể lạc quan. Kết quả near-duplicate đã được nhìn thấy khi cài đặt.
- Mẫu nhỏ: temporal QA 18 câu, một lĩnh vực; 1 câu ≈ 5,6 điểm phần trăm.
- OCR đo trên 20 trang chung giữa ba engine; Gemini gửi ảnh ra ngoài (OpenRouter), không dùng cho tài liệu nhạy cảm nếu chưa che.
- Latency/chi phí đo cho OCR và temporal QA; chưa đo cho chunking và dedup.
- HTML, PDF có text layer, slide, org chart, biểu đồ: mới khảo sát, chưa có fixture.
- Nhất quán số học (tổng khớp) không chứng minh nguồn đúng; conflict chỉ là tín hiệu để review.

**Hành động tiếp theo**

| Việc | Owner |
|---|---|
| Viết detector cho `dedup.near`, `version.ambiguous`, `flow.structure_loss` | A — Mai Phan Anh Tùng |
| Thêm fixture HTML / PDF có text layer; tách dev/test theo họ mẫu để đo near-duplicate độc lập | D — Nguyễn Quốc Tuấn |
| Chạy lại temporal QA trên lĩnh vực thứ hai; thêm câu ngoài phạm vi | C — Lương Quang Huy |
| Thử chunk cố định có độ dài bằng chunk cấu trúc để tách hiệu ứng độ dài | C — Lương Quang Huy |
| Quay demo ingest lặp + cập nhật phiên bản | E — Nguyễn Anh Tú |
