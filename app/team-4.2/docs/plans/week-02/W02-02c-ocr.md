# W02-02c — Nhóm khó: PDF scan + OCR (kèm benchmark OCR)

Owner: C · Reviewer: B · Ngày 1 → ngày 4 · File: `src/rag/ingest/ocr/`, `tests/test_ocr.py`,
`evals/team-4.2/runners/ocr_bench/`, `evals/team-4.2/results/w02-ocr-*`

> Máy dev đã có Tesseract 5.5 + `vie` (`C:\Program Files\Tesseract-OCR`) → baseline chắc chắn chạy được.
> Tham khảo cách làm cũ: `C:\Users\Admin\Desktop\Law-RAG\law_rag\ocr.py` (chỉ ra plain text, mất trang/cấu trúc — không bê nguyên).

---

## Phần A — OCR trong pipeline

### A1. Adapter đa engine

- [ ] Interface `OCREngine.parse(pdf_or_image) -> list[Block]`
      `Block = {page, type: title|text|table|figure|header|footer, level, text | html, bbox, confidence, engine}`
- [ ] Chọn engine qua `.env`: `OCR_ENGINE=tesseract|gemini|mineru|ppstructure`
- [ ] Block → `Page`/`Chunk`: `table` → chunk bảng (dùng chung W02-02b) · `title` → `heading_path` ·
      `header/footer` → bỏ · `figure` → giữ đường dẫn ảnh gốc
- [ ] Phát hiện trang scan theo **từng trang** (có text layer → dùng luôn; không → OCR)

### A2. `TesseractEngine` (baseline, ngày 2)

- [ ] PDF → ảnh (PyMuPDF, zoom 2x) · tiền xử lý: grayscale, threshold, xoay theo OSD
- [ ] Gọi `image_to_data` **một lần** → dựng đoạn/dòng theo `block_num/par_num/line_num` + confidence
- [ ] Mỗi trang là một `Page` (giữ số trang cho citation), `ocr_confidence` theo trang
- [ ] Trang confidence < ngưỡng → `quality_status=needs_review`, issue `ocr_low_confidence`

### A3. `GeminiEngine` (ngày 2–3)

- [ ] Chốt: Google AI Studio hay Vertex AI · model còn được hỗ trợ (kiểm tra 2.5 Flash) · `GEMINI_API_KEY` trong `.env.example`
- [ ] Gửi từng trang · `temperature=0` · prompt chép nguyên văn, không sửa, chỗ mờ ghi `[không đọc được]` · output JSON block
- [ ] Retry/rate-limit · phát hiện output bị cắt / `RECITATION`
- [ ] Gắn `content_origin=vlm_ocr`, `engine`, `prompt_version`, ngày chạy
- [ ] Ghi rõ hạn chế: ảnh chứa PII bị gửi ra ngoài trước khi mask (chỉ dùng với fixtures giả)

### A4. Engine cấu trúc local (ngày 3, chọn 1 sau khi đo nhanh)

- [ ] Thử MinerU **và** PP-StructureV3 trên 2–3 trang tiếng Việt có bảng → chọn 1 (tiêu chí: giữ dấu, bảng, cài được trên Windows, vừa 6 GB VRAM)
- [ ] Map output (`content_list.json` / JSON PP-Structure) → `Block`

### A5. Đối chiếu chéo = điểm chất lượng (bonus)

- [ ] So số, ngày, "Điều N" giữa 2 engine trên cùng trang → lệch ⇒ `needs_review` + mục review queue
- [ ] Cache kết quả OCR theo checksum + engine (không OCR lại khi ingest lặp)

---

## Phần B — Benchmark OCR (2 bộ chính + kiểm tra chéo)

Engine chạy trên mọi bộ: Tesseract · Gemini Flash · MinerU **hoặc** PP-StructureV3.
Chuẩn hoá chung trước khi chấm: NFC · `hoà`≡`hòa`, `thuý`≡`thúy` · gộp khoảng trắng · gỡ gạch nối cuối dòng.

### Dung lượng nguồn (đo từ Hugging Face API, 05/11/2026)

| Bộ | Toàn bộ | Phần dùng | Ghi chú |
|---|---|---|---|
| [nrl-ai/vn-ocr-documents-eval](https://huggingface.co/datasets/nrl-ai/vn-ocr-documents-eval) | **0.31 GB**, 373 file | Tải hết | 9 scan thật + hợp đồng/biểu mẫu/biên lai tổng hợp; GT plain text |
| [opendatalab/OmniDocBench](https://huggingface.co/datasets/opendatalab/OmniDocBench) | **1.55 GB** (1.651 ảnh 1.45 GB + `OmniDocBench.json` 42 MB) | Tập con 30 trang ≈ 0.03 GB + json | EN/ZH, có script chấm chính thức |
| [Delores-Lin/MDPBench](https://huggingface.co/datasets/Delores-Lin/MDPBench) | **7.52 GB** (17 ngôn ngữ × 160 ảnh) | 40 `vi_*` gốc + 40 ảnh chụp ≈ **0.4 GB** + `MDPBench_public.json` 73 MB | Trang VI gốc: textbook 14, academic 7, slide 6, exam 5, khác 8 |
| [niits/vietnamese-legal-ocr](https://huggingface.co/datasets/niits/vietnamese-legal-ocr) (tuỳ chọn) | ~1.3 MB theo card | 300 ảnh dòng | Ảnh dòng tổng hợp từ văn bản luật, nhãn text |
| [Meddies/meddies-ocr](https://huggingface.co/datasets/Meddies/meddies-ocr) | **16.19 GB** (`images.zip` 16.1 GB) | **Không dùng tuần này** | GT HTML + bbox nhưng không rõ nguồn GT; parquet 53 MB nếu muốn xem nhãn |

Tổng cần tải ≈ **0.8 GB** (không tải Meddies; OmniDocBench/MDPBench chỉ tải đúng file của trang đã chọn). Lưu tại `data/team-4.2/ocr_bench/` (gitignore), chỉ commit script tải + danh sách ID trang đã chọn.

### B0. Ngân sách API: tối đa 2 USD (chỉ Gemini tốn tiền; engine local miễn phí)

Ước tính (giá bên thứ ba cho 2.5 Flash: 0.30 USD/1M input, 2.50 USD/1M output, Batch API −50%; **kiểm tra lại trên ai.google.dev**):
mỗi trang ≈ 1.800 token input (ảnh + prompt) + ≈ 3.000 token output ⇒ **≈ 0.008 USD/trang**, Batch ≈ 0.004 USD/trang.
Output chiếm ~90% chi phí, nên **tắt thinking** là việc quan trọng nhất.

Ưu tiên: **OCR đúng chữ tiếng Việt** (Bộ 1) lấy phần lớn ngân sách; cấu trúc (Bộ 2) và kiểm tra chéo chỉ cần ít trang.

| Phần | Gemini chạy | Engine local chạy | Batch |
|---|---|---|---|
| Bộ 1: OCR tiếng Việt | **~170 trang** (toàn bộ nrl-ai ~156 + 12–15 trang luật) | toàn bộ | ~0.68 USD |
| Bộ 1 (tuỳ chọn): dòng chữ luật niits | 300 ảnh dòng (output ngắn) | 300 | ~0.05 USD |
| Bộ 2: cấu trúc | 20 trang | 30 trang | ~0.08 USD |
| Kiểm tra chéo MDPBench-VI | 20 trang (10 gốc + 10 ảnh chụp) | 40 trang gốc + 40 ảnh chụp | ~0.08 USD |
| **Tổng** | **~210 trang + 300 dòng** | | **~0.9 USD** (giá thường ~1.8) |

Phân bổ: pilot 5 trang (~0.05) · thử prompt 10 trang × 3 lần (~0.25) · chạy chính bằng Batch (~0.9) · dự phòng chạy lại (~0.5) · **ngưỡng dừng cứng 1.8 USD**.
Nếu không dùng được Batch: bỏ phần niits và cắt nrl-ai synthetic xuống 60 trang để giữ dưới 1.8 USD.

- [ ] Kiểm tra giá chính thức, model còn hỗ trợ, free tier (nếu còn: dùng free tier để thử prompt; chỉ với dữ liệu public, vì free tier có thể bị dùng để huấn luyện)
- [ ] `thinking_budget=0` (thinking tính phí như output)
- [ ] Pilot 5 trang → đọc `usage_metadata` lấy token thật/trang → tính lại bảng trên trước khi chạy tiếp
- [ ] Cache response theo `(sha256 ảnh, model, prompt_version)`: không bao giờ trả tiền 2 lần cho cùng một trang
- [ ] Bộ đếm chi phí cộng dồn từ `usage_metadata`, ghi `cost_log.jsonl`; **dừng khi vượt 1.8 USD**
- [ ] Chạy chính bằng Batch API; ảnh resize cạnh dài ~1.600 px (đủ đọc dấu, ít token)
- [ ] Nếu pilot cho > 0.006 USD/trang (giá Batch) → cắt phần synthetic của nrl-ai trước (giữ nguyên 9 `real` + trang luật), hoặc thêm Flash-Lite làm engine phụ
- [ ] Báo chi phí thực tế + USD/trang trong bảng tổng hợp B4

### B1. Bộ 1 — OCR tiếng Việt có tốt không (ngày 2–3)

- [ ] Script tải nrl-ai → `data/team-4.2/ocr_bench/vi/`
- [ ] Kiểm tra mâu thuẫn số trang của card (107/156/165) → chốt danh sách trang dùng
- [ ] Mọi engine (kể cả Gemini) chạy **toàn bộ** nrl-ai + trang luật tự làm
- [ ] Lớp **critical info luật** tự làm (12–15 trang):
  - [ ] 8–10 trang vbpl: render PDF text-layer → ảnh → làm hỏng theo 3 mức (sạch / photocopy / scan mờ-nghiêng); GT = text gốc
  - [ ] 2 trang có bảng số liệu (lương tối thiểu vùng, mức phạt) để đo số trong bảng
  - [ ] 3–4 **trang bẫy**: Điều luật nổi tiếng đã **sửa số / bỏ chữ "không" / đổi "Điều N"** (vd. Điều 173 BLHS 2.000.000 → 3.000.000) — bắt engine "sửa theo trí nhớ"
  - [ ] Annotate ~120–150 critical field có **offset** trong GT: số, ngày, "Điều N/Khoản N", phủ định, ngoại lệ, điều kiện ngưỡng; guideline 1 trang; người thứ hai review ≥5 trang
- [ ] (Tuỳ chọn) 300 ảnh dòng từ [niits/vietnamese-legal-ocr](https://huggingface.co/datasets/niits/vietnamese-legal-ocr) (từ vựng luật, nhiều font/nhiễu) → đo riêng lỗi dấu ở mức dòng
- [ ] Báo kết quả **theo nhóm**: `real` (scan thật) · synthetic theo loại (contract/form/receipt/…) · trang luật theo mức hỏng · trang bẫy
- [ ] Metric: CER/WER · **tỉ lệ lỗi dấu** (tách: mất dấu / sai dấu / sai chữ cái gốc) · độ đúng số/ngày/"Điều N" · **CEM** theo nhóm field + **Page Pass Rate** (hard gate) trên trang luật
- [ ] Đếm riêng lỗi **"trông hợp lệ"** (OCR ra từ/số có nghĩa nhưng sai: `không`→`có`, `03`→`08`) — nguy hiểm hơn lỗi ra chữ vô nghĩa
- [ ] Căn chỉnh OCR↔GT bằng edit distance (`rapidfuzz`/`edlib`); critical field chấm tại vị trí đã căn, không dùng "chứa chuỗi"
- [ ] Sanity check: Tesseract trên 9 trang `real` ≈ CER 12.62% như card công bố
- [ ] Kết quả → `evals/team-4.2/results/w02-ocr-vi/`

### B2. Bộ 2 — OCR có giữ đúng cấu trúc không (ngày 3)

- [ ] Script tải OmniDocBench (json + ảnh tập con)
- [ ] Chọn **30 trang** loại gần mình, ưu tiên có bảng và nhiều cột (báo cáo, báo cáo tài chính, sách); commit danh sách ID
- [ ] Gemini chạy **20 trang** trong số đó (cùng danh sách cho mọi engine khi so sánh với Gemini)
- [ ] Ghi rõ trong report: cỡ mẫu nhỏ → chỉ để định hướng, báo số đếm thay vì kết luận mạnh
- [ ] Chạy bằng script chấm chính thức của OmniDocBench
- [ ] Chỉ báo metric **không phụ thuộc ngôn ngữ**: TEDS-S (cấu trúc bảng) · loại block/cấp heading · reading order · tách cột, bỏ header/footer
- [ ] Tesseract: ghi "không áp dụng" cho bảng/heading (không cho 0 điểm)
- [ ] Kết quả → `evals/team-4.2/results/w02-ocr-struct/`

### B3. Kiểm tra chéo — tiếng Việt + cấu trúc (ngày 4)

- [ ] Tải riêng `vi_*` của MDPBench public + `MDPBench_public.json`
- [ ] Chạy script chấm MDPBench; báo riêng digital (40) và ảnh chụp (120)
- [ ] Gemini: 10 trang gốc + 10 ảnh chụp của chính 10 trang đó = 20 trang; engine local chạy 40 gốc + 40 ảnh chụp
- [ ] Kiểm tra lỗi "nhận tiếng Việt thành tiếng Trung" (đặc biệt MinerU)
- [ ] Đối chiếu với leaderboard công khai cột VI
- [ ] Kết quả → `evals/team-4.2/results/w02-ocr-cross/`

### B4. Tổng hợp (ngày 4)

- [ ] Bảng so sánh engine: Bộ 1 · Bộ 2 · kiểm tra chéo · giây/trang · VRAM · chi phí API
- [ ] ≥2 failure case OCR (ưu tiên: trang bẫy, lỗi số/phủ định "trông hợp lệ") → đưa sang W02-05
- [ ] Downstream (tuỳ chọn): ingest text GT vs text OCR → ΔR@5
- [ ] Quyết định engine mặc định cho pipeline + lý do (ghi vào report)

---

## Tiêu chí nghiệm thu

- PDF scan ingest được, hỏi đáp có citation trang; trang OCR kém / lệch giữa engine nằm trong review queue.
- Có bảng so sánh ≥3 engine trên Bộ 1 và Bộ 2, mọi số có thư mục kết quả + lệnh chạy lại.
- Không điền số giả; trang "không áp dụng" ghi rõ.

## Ghi chú

-
