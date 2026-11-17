# W02-04 — So sánh chunk cố định và chunk theo cấu trúc

Team 4.2 · Ngày 11/11/2026 · Kết quả gốc: [`evals/team-4.2/results/w02-chunk-compare/`](../../../evals/team-4.2/results/w02-chunk-compare/)

## Tóm tắt

Ở cấu hình đang chạy thật (**hybrid + rerank**), **chunk theo cấu trúc tốt hơn ở mọi chỉ số**: R@5 0,859 so với
0,826, MRR@5 0,840 so với 0,785 (tập test: 0,806 so với 0,745 và 0,817 so với 0,773). Chunk cố định chỉ thắng khi dùng
**BM25 đơn lẻ**, và lợi thế đó chủ yếu đến từ việc chunk cố định **dài gần gấp đôi**, không phải từ cách cắt.
**Đề xuất: giữ chunk theo cấu trúc làm mặc định.**

## 1. Mục tiêu

Kiểm tra theo yêu cầu tuần 2 (W02-04): cắt văn bản luật theo **cấu trúc** (theo Điều / khoản) có tốt hơn cắt theo
**cửa sổ cố định** không, khi mọi yếu tố khác giữ nguyên.

## 2. Thiết lập

| Yếu tố | Giá trị (chung cho hai chiến lược) |
|---|---|
| Nguồn | 6 bộ luật gốc trong `data/team-4.2/raw/`: Dân sự 2015, Hàng hải 2015, Hình sự 2015, Lao động 2019, Tố tụng dân sự 2015, Tố tụng hình sự 2015 |
| Bộ câu | `evals/team-4.2/datasets/benchmark_doi_thuong_w02.jsonl` — 64 câu trong phạm vi (37 `paraphrase`, 27 `multi`); tập `test` 36 câu. 6 câu `out_of_scope` không có gold nên không tính |
| Embedding | `jina-embeddings-v5-text-small` (1024 chiều) |
| Truy hồi | BM25, Dense (HyDE), Hybrid (RRF), Hybrid + rerank Jev (`RERANK_N=20`) |
| Top-k | 5 |
| Kích thước chunk | `MAX_SYLLABLES=300` |
| Chỉ mục | Mỗi chiến lược một `DATA_DIR` riêng: `data/team-4.2/w02/chunk-structural`, `data/team-4.2/w02/chunk-fixed` |

**Hai chiến lược**

- **Theo cấu trúc** (`CHUNK_STRATEGY=structural`, chunker hiện có): mỗi dòng "Điều N." mở chunk mới; khoản "1." và điểm
  "a)" mở đoạn mới; gom đoạn tới tối đa 300 âm tiết; chồng lấp 1 đoạn nhưng không vượt ranh giới Điều. Mỗi chunk thuộc
  đúng một Điều và mang `section` dạng "Chương … > Điều N. …".
- **Cố định** (`CHUNK_STRATEGY=fixed`, mới thêm): cửa sổ 300 âm tiết, chồng lấp 50 (`CHUNK_OVERLAP=50`), bỏ qua tiêu đề,
  ranh giới Điều và đoạn văn. Chunk không có `section`.

## 3. Cách chấm

Cách chấm cũ (`GoldRef.matches`) khớp chunk với gold theo **tên `section` chính xác**. Chunk cố định không có `section`
nên sẽ luôn trượt — so sánh không công bằng.

Vì vậy chấm **theo vị trí văn bản** (`app/team-4.2/src/rag/eval/span_match.py`), dùng chung cho cả hai chiến lược:

1. Gộp khoảng trắng văn bản gốc; định vị từng Điều từ dòng mở đầu "Điều N." (không tính câu dẫn chiếu "theo Điều N").
2. Định vị từng chunk trong văn bản gốc.
3. Chunk "trúng" Điều gold nếu khoảng văn bản của chunk **chồng lên** khoảng của Điều đó.

**Kiểm tra cách chấm**: với chunk theo cấu trúc, chấm theo vị trí cho kết quả **khớp chấm theo `section` ở 256/256
lượt** (64 câu × 4 cấu hình). Toàn bộ 3.422 + 2.125 chunk đều định vị được trong văn bản gốc.

Chỉ số: **R@5** (tỉ lệ Điều gold có trong top-5), **Hit@5** (có ít nhất một Điều gold), **MRR@5** (nghịch đảo thứ hạng
của chunk trúng đầu tiên).

## 4. Chỉ mục

| | Số chunk | Âm tiết trung bình | Trung vị | Chunk vắt ≥2 Điều | Thời gian ingest |
|---|---|---|---|---|---|
| Theo cấu trúc | 3.422 | 163,0 | 154 | 0 | 386 s |
| Cố định | 2.125 | 299,7 | 300 | 1.763 (83%) | 452 s |

Chunk theo cấu trúc ngắn hơn vì bị cắt tại mỗi Điều (Điều ngắn thành chunk ngắn). 83% chunk cố định chứa đoạn của từ hai
Điều trở lên.

## 5. Kết quả

### 5.1 Tất cả câu (n = 64)

| Cấu hình | Chiến lược | R@5 | Hit@5 | MRR@5 |
|---|---|---|---|---|
| BM25 | Cố định | **0,328** | **0,391** | **0,226** |
| BM25 | Theo cấu trúc | 0,258 | 0,281 | 0,157 |
| Dense | Cố định | **0,810** | 0,906 | 0,686 |
| Dense | Theo cấu trúc | 0,805 | 0,906 | **0,715** |
| Hybrid | Cố định | 0,589 | 0,688 | 0,503 |
| Hybrid | Theo cấu trúc | **0,677** | **0,781** | **0,515** |
| Hybrid + rerank | Cố định | 0,826 | 0,906 | 0,785 |
| Hybrid + rerank | Theo cấu trúc | **0,859** | **0,938** | **0,840** |

### 5.2 Tập test (n = 36)

| Cấu hình | Chiến lược | R@5 | Hit@5 | MRR@5 |
|---|---|---|---|---|
| BM25 | Cố định | **0,250** | **0,361** | **0,199** |
| BM25 | Theo cấu trúc | 0,125 | 0,167 | 0,089 |
| Dense | Cố định | **0,718** | 0,889 | **0,668** |
| Dense | Theo cấu trúc | 0,708 | 0,889 | 0,665 |
| Hybrid | Cố định | 0,519 | 0,694 | **0,537** |
| Hybrid | Theo cấu trúc | **0,565** | **0,750** | 0,472 |
| Hybrid + rerank | Cố định | 0,745 | 0,889 | 0,773 |
| Hybrid + rerank | Theo cấu trúc | **0,806** | **0,944** | **0,817** |

### 5.3 Theo loại câu

| Cấu hình | Loại (n) | Cố định R@5 / MRR@5 | Theo cấu trúc R@5 / MRR@5 |
|---|---|---|---|
| BM25 | multi (27) | **0,259** / **0,240** | 0,093 / 0,102 |
| BM25 | paraphrase (37) | 0,378 / **0,215** | 0,378 / 0,197 |
| Dense | multi (27) | **0,698** / **0,693** | 0,685 / 0,671 |
| Dense | paraphrase (37) | 0,892 / 0,681 | 0,892 / **0,748** |
| Hybrid | multi (27) | **0,543** / **0,622** | 0,531 / 0,506 |
| Hybrid | paraphrase (37) | 0,622 / 0,416 | **0,784** / **0,522** |
| Hybrid + rerank | multi (27) | 0,735 / **0,796** | **0,778** / 0,793 |
| Hybrid + rerank | paraphrase (37) | 0,892 / 0,777 | **0,919** / **0,874** |

## 6. Phân tích

- **Cấu hình chạy thật (hybrid + rerank): chunk theo cấu trúc thắng.** Rerank Jev chấm từng chunk với câu hỏi; chunk chỉ
  chứa một Điều cho tín hiệu sạch hơn chunk trộn 2–3 Điều, nên gold được xếp cao hơn (MRR@5 0,840 so với 0,785).
- **Hybrid không rerank: chunk theo cấu trúc thắng rõ ở câu `paraphrase`** (R@5 0,784 so với 0,622). Khi gộp BM25 và
  Dense bằng RRF, chunk cố định lẫn nhiều chủ đề bị đẩy lên nhờ khớp từ khoá rải rác.
- **Dense: gần như hoà.** Chunk theo cấu trúc xếp gold cao hơn ở `paraphrase` (MRR 0,748 so với 0,681).
- **BM25: chunk cố định thắng**, rõ nhất ở câu `multi` (R@5 0,259 so với 0,093). Nguyên nhân chính là **độ dài**: top-5
  chunk cố định phủ khoảng 1.500 âm tiết, top-5 chunk theo cấu trúc chỉ khoảng 815 — nhiều từ khoá hơn và một chunk có
  thể trúng 2–3 Điều cùng lúc. Đây là lợi thế của "nhiều chữ hơn", không phải của cách cắt.

## 7. Ví dụ định tính

Chunk cố định cắt ngang Điều (trích từ `examples.md`, Bộ luật Dân sự 2015):

- `d4825a1af3d31c64:0001` — vắt qua **Điều 3 và 4**: mở đầu giữa khoản 1 Điều 3 ("…đều bình đẳng, không được lấy bất kỳ
  lý do nào để phân biệt đối xử…") rồi chạy sang Điều 4. Khi đưa vào ngữ cảnh, LLM nhận phần cuối Điều 3 không có tiêu
  đề và phần đầu Điều 4 không có phần sau.
- `d4825a1af3d31c64:0002` — vắt qua **Điều 4, 5 và 6**: bắt đầu bằng "…vi phạm khoản 2 Điều này thì…" — câu dẫn chiếu
  "Điều này" mất ngữ cảnh vì chunk không cho biết "Điều này" là Điều nào.

Chunk theo cấu trúc luôn bắt đầu bằng "Điều N. <tên điều>" và mang đường dẫn Chương / Mục, nên trích dẫn rõ ràng và
khớp được với kho luật có phiên bản (theo Điều).

## 8. Giới hạn

- **Bộ câu nhỏ**: 64 câu (test 36). Chênh 3–6 điểm tương đương 2–4 câu — chưa đủ để khẳng định có ý nghĩa thống kê.
- **Chưa cân bằng ngân sách văn bản**: so top-5 chunk, nhưng chunk cố định dài ~1,8 lần. Cách chấm "trúng Điều" thiên vị
  chunk dài; một phép so công bằng hơn là cân bằng theo số âm tiết đưa vào ngữ cảnh.
- **Chỉ đo truy hồi**, chưa đo chất lượng câu trả lời của LLM.
- **Chưa làm phần bảng / OCR / phiên bản** của checklist W02-04 (bộ `w02_quality.jsonl`); lần này chỉ dùng bộ câu đời
  thường.

## 9. Kết luận

Giữ **chunk theo cấu trúc** làm mặc định: tốt hơn ở cấu hình đang chạy thật (hybrid + rerank) trên cả tập đầy đủ và tập
test, mỗi chunk thuộc đúng một Điều (trích dẫn sạch, khớp kho có phiên bản), và lợi thế của chunk cố định chỉ xuất hiện
ở BM25 đơn lẻ, chủ yếu do chunk dài hơn. Chunk cố định vẫn có thể chọn bằng `CHUNK_STRATEGY=fixed` cho thí nghiệm.

## 10. Chạy lại

Tại gốc repo:

```bash
PYTHONPATH=app/team-4.2/src python evals/team-4.2/runners/run_chunk_compare.py
```

Script dựng (hoặc dùng lại) hai chỉ mục trong `data/team-4.2/w02/chunk-<chiến lược>`, chạy 4 cấu hình truy hồi và ghi
`summary.md`, `config.json`, `per_question.csv`, `examples.md` vào `evals/team-4.2/results/w02-chunk-compare/`.

Mã liên quan:

- `app/team-4.2/src/rag/ingest/chunker.py` — `chunk_fixed`
- `app/team-4.2/src/rag/config.py` — `CHUNK_STRATEGY`, `CHUNK_OVERLAP`
- `app/team-4.2/src/rag/eval/span_match.py` — chấm theo vị trí văn bản
- `evals/team-4.2/runners/run_chunk_compare.py` — script thí nghiệm
