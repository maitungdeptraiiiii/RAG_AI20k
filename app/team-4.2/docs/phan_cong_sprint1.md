# Phân công công việc — Sprint 1: Baseline Hybrid RAG

> **Quy ước đường dẫn (sau khi tái cấu trúc theo repo `agentic-batch-4`):** `src/`, `tests/`, `docs/`, `pyproject.toml` tính từ `app/team-4.2/`; các đường dẫn bắt đầu bằng `app/`, `data/`, `evals/`, `experiments/`, `scripts/`, `reports/` tính từ gốc repo.

> **Mục tiêu sprint:** RAG Agent nhận tài liệu (PDF / URL / TXT) → hybrid search (BM25 + Dense + RRF) → LLM trả lời có citation, từ chối khi thông tin không có trong tài liệu. Đánh giá bằng Recall@5 và MRR@5.
> **Deadline demo:** 17/09 (T5) — Demo + Q&A bảo vệ đồ án nhóm.
> **Phạm vi file này:** baseline bám sát yêu cầu sprint. Phần UI không nằm trong danh sách phân công.
> **Tech stack:** xem `docs/tech_stack.md` (embedding `text-embedding-3-small`, LLM GPT 5.6 Lunar, Qdrant local, eval tự viết + RAGAS).

---
vv
## 1. Nguyên tắc phân công

1. **Ai cũng làm phần core của RAG.** Mỗi thành viên sở hữu ít nhất một module nằm trên luồng dữ liệu chính.
2. **Hai việc của một người phải liên quan đến nhau.** Việc B dùng trực tiếp đầu ra của việc A, nên người làm hiểu trọn một đoạn của pipeline.
3. **Việc khó có nhiều người cùng làm.** Mỗi việc khó có một người chịu trách nhiệm chính và một người hỗ trợ.
4. **Ai có việc dễ thì nhận thêm.** Người có module dễ phải hỗ trợ một module khó.
5. **Không tự chấm module của mình một mình.** Evaluation là trách nhiệm chung, có một người chịu trách nhiệm chính.
6. **Chốt interface trước khi code.** Có schema chung từ ngày 1 thì 5 người mới code song song được.

---

## 2. Các thành phần của hệ thống

| # | Thành phần | Độ khó | Người phụ trách chính | Người hỗ trợ |
|---|---|---|---|---|
| 1 | Parsing (PDF / URL / TXT) | Trung bình | TV1 | — |
| 2 | Chunking + metadata | Trung bình | TV1 | — |
| 3 | BM25 (tách từ tiếng Việt, index, retrieve) | Dễ | TV2 | — |
| 4 | Dense (embedding, vector index, retrieve) | **Khó** | TV3 | TV2 |
| 5 | Fusion RRF | Dễ | TV2 | — |
| 6 | Generation (prompt + LLM) | Trung bình | TV4 | — |
| 7 | Citation | Trung bình | TV4 | — |
| 8 | Schema chung + ghép pipeline | Trung bình | TV5 | — |
| 9 | Guardrail (2 tầng) | **Khó** | TV5 | TV4 |
| 10 | Khung Evaluation + bộ gold | **Khó** | TV3 | TV1 (gán gold), TV2 |
| 11 | Failure analysis | **Khó** | TV5 (phân loại + tổng hợp) | Cả nhóm (theo module) |

**Luồng dữ liệu:**

```
TV1: Tài liệu ──Parsing──► Pages ──Chunking──► Chunks
                                                 │
               ┌─────────────────────────────────┤
               ▼                                 ▼v
TV2:         BM25 ──► Hits              TV3: Dense ──► Hits
               └──────────► TV2: RRF ◄───────────┘
                                │ Fused Hits
                                ▼
TV5:                Guardrail trước LLM (điểm thấp → từ chối)
                                │
TV4:                Generation ──► Citation
                                │
TV5:                Guardrail sau LLM ──► Câu trả lời cuối
                                │
TV3 + cả nhóm:      Evaluation ──► TV5: Failure analysis
```

---

## 3. Interface chung (chốt ngày 1, TV5 viết, cả nhóm review)

### 3.1. Kiểu dữ liệu

```python
@dataclass(frozen=True)
class Page:
    doc_id: str          # hash nội dung, ổn định khi ingest lại
    source: str          # tên file hoặc URL
    page: int | None     # None với URL/TXT
    text: str            # đã chuẩn hoá Unicode NFC

@dataclass(frozen=True)
class Chunk:
    chunk_id: str        # duy nhất toàn hệ thống
    doc_id: str
    source: str
    page_start: int | None
    page_end: int | None
    section: str | None  # heading / mục gần nhất
    text: str

@dataclass(frozen=True)
class Hit:
    chunk_id: str
    score: float
    rank: int            # bắt đầu từ 1
    arm: str             # "bm25" | "dense" | "fused"

@dataclass(frozen=True)
class Citation:
    n: int               # số [n] trong câu trả lời
    chunk_id: str
    source: str
    page: int | None
    quote: str           # trích đoạn

@dataclass
class Answer:
    text: str
    citations: list[Citation]
    refused: bool
    hits: list[Hit]      # để debug / eval
```

### 3.2. Đầu vào / đầu ra của từng module

| Module | Đầu vào | Đầu ra | Owner |
|---|---|---|---|
| Parsing | đường dẫn PDF / TXT, hoặc URL | `list[Page]` | TV1 |
| Chunking | `list[Page]` | `list[Chunk]` | TV1 |
| BM25 | build: `list[Chunk]` · search: `query, k` | `list[Hit]` | TV2 |
| Dense | build: `list[Chunk]` · search: `query, k` | `list[Hit]` | TV3 |
| RRF | `dict[arm, list[Hit]]`, `k=60` | `list[Hit]` (arm=`fused`) | TV2 |
| Guardrail trước LLM | `query`, fused `list[Hit]` | cho qua hoặc `Answer(refused=True)` **không gọi LLM** | TV5 |
| Generation | `query`, context (top chunk, đánh số `[n]`) | text có `[n]` | TV4 |
| Citation | text + context | `Answer` với `list[Citation]` | TV4 |
| Guardrail sau LLM | `Answer` | `Answer` cuối (loại `[n]` sai; không còn citation hợp lệ thì từ chối) | TV5 |
| Pipeline | `ingest(path/url)`, `ask(query)` | `Answer` | TV5 |

### 3.3. Quy ước chung

- Mọi text được chuẩn hoá **Unicode NFC** trước khi xử lý.
- Câu từ chối thống nhất: `"Không có trong tài liệu."`
- Ingest cùng một tài liệu hai lần thì không nhân đôi chunk (dựa vào `doc_id`).
- Mỗi module có unit test riêng và dùng dữ liệu giả để không phải chờ module phía trước.
- Thay đổi schema phải báo cả nhóm và TV5 duyệt.

---

## 4. Phân công chi tiết theo thành viên

### TV1 — Parsing → Chunking

**Liên hệ giữa A và B:** chunker nhận đúng các `Page` do parser trả ra. Số trang và tên nguồn ở A đi thẳng vào metadata của B.

| Việc | Chi tiết | Đầu ra |
|---|---|---|
| A. Parsing | Đọc PDF (PyMuPDF), URL (trafilatura), TXT; chuẩn hoá NFC; đánh số trang từ 1; cảnh báo trang trống (PDF scan) hoặc lỗi font/dấu | `load_pdf`, `load_url`, `load_text` + test |
| B. Chunking | Gom đoạn văn đến khoảng 300 âm tiết, overlap 1 đoạn; giữ `page_start`/`page_end` khi chunk vắt qua trang; gắn `section`; tạo `chunk_id` duy nhất | `chunk_document` + test |
| Hỗ trợ | Cùng TV3 **gán nhãn gold** theo `source` + `page` | nhãn gold |
| Failure analysis | Lỗi parsing/chunking: mất dấu, sai trang, cắt giữa ý, trang rỗng | mục trong report |
| Slide | Ingestion pipeline | 1–2 slide |
| Q&A chính | Chunk size ảnh hưởng thế nào đến retrieval? · So sánh với RAGFlow | |

### TV2 — BM25 → Fusion RRF

**Liên hệ giữa A và B:** RRF nhận danh sách xếp hạng từ BM25 (của chính TV2) và Dense. Người hiểu rank BM25 sẽ debug fusion dễ hơn.

| Việc | Chi tiết | Đầu ra |
|---|---|---|
| A. BM25 | Tách từ tiếng Việt bằng pyvi; BM25 tự viết (k1=1.5, b=0.75, idf dạng `ln(1+…)` luôn dương); chỉ trả hit có score > 0; lưu/tải index | `BM25Index` + test |
| B. RRF | `score(d) = Σ 1 / (k + rank(d))`, k=60; hoà điểm thì xếp theo `chunk_id` để kết quả tất định; ghép thành `HybridRetriever` | `rrf`, `HybridRetriever` + test |
| Hỗ trợ | Cùng TV3 làm **Dense**; cùng TV3 chạy eval retrieval | |
| Eval | So sánh BM25 riêng, Dense riêng, Hybrid | bảng kết quả |
| Failure analysis | Lỗi BM25/RRF: tách từ sai, fusion đẩy kết quả đúng xuống | mục trong report |
| Việc thêm | Viết **README** (cài đặt + chạy lại) | `README.md` |
| Slide | BM25 + RRF | 1–2 slide |
| Q&A chính | BM25 hoạt động thế nào, khác TF-IDF ra sao? · RRF hoạt động ra sao? | |

### TV3 — Dense → Khung Evaluation + bộ gold (người chịu trách nhiệm chính về Eval)

**Liên hệ giữa A và B:** Recall@5 và MRR@5 đo đúng đầu ra retrieval mà TV3 xây. Eval được làm chung với TV2 để tránh tự chấm.

| Việc | Chi tiết | Đầu ra |
|---|---|---|
| A. Dense | Embedding OpenAI `text-embedding-3-small` (1536 chiều, gọi qua `openai`, cache SQLite); Qdrant local, cosine, lưu tên model vào metadata collection; query và doc dùng chung một hàm encode, đưa **text gốc** (không phải text đã tách từ); test dùng embedder giả | `Embedder`, `VectorIndex` + test |
| B. Khung Eval | Định dạng `questions.jsonl`; hàm `recall_at_k`, `mrr_at_k` tự viết; tích hợp **RAGAS** (Faithfulness, Answer Relevancy, Answer Correctness, Context Recall) chạy trên `Answer` của pipeline; script chạy eval cho nhiều cấu hình; xuất bảng kết quả theo từng câu | `evals/team-4.2/` + test |
| B. Bộ gold | Chủ trì gom câu hỏi của cả nhóm; kiểm tra nhãn; viết `evals/team-4.2/runners/draft_references.py` (LLM soạn nháp đáp án mẫu từ trang gold); kiểm tra chéo `reference`; **chốt cố định bộ câu hỏi trước khi chạy eval** | `evals/team-4.2/datasets/questions.jsonl` |
| Eval | Cùng TV2 đánh giá retrieval | bảng kết quả |
| Failure analysis | Lỗi Dense: hiểu sai nghĩa, trả về đoạn giống chữ nhưng sai ý | mục trong report |
| Slide | Dense + kết quả evaluation | 1–2 slide |
| Q&A chính | Vector embedding là gì, vì sao cần? · Recall@5 đạt bao nhiêu, giải thích? | |

### TV4 — Generation → Citation

**Liên hệ giữa A và B:** số `[n]` sinh ra từ prompt của A. B ánh xạ `[n]` về đúng chunk, nguồn và trang.

| Việc | Chi tiết | Đầu ra |
|---|---|---|
| A. Generation | GPT 5.6 Lunar qua `openai`, `temperature=0`, cache kết quả; prompt tiếng Việt: chỉ trả lời dựa trên các đoạn được cung cấp, sau mỗi ý ghi `[n]`, không đủ thông tin thì viết đúng câu từ chối | `LLMClient`, `generate` + test (dùng LLM giả) |
| B. Citation | Format context `[n] (nguồn, trang)`; parse `[n]` trong câu trả lời → `Citation` (source, page, trích đoạn) | `build_citations` + test |
| Hỗ trợ | Cùng TV5 làm **Guardrail** | |
| Eval | Cùng TV5 đánh giá Generation (RAGAS + chấm tay đối chiếu) + Citation (chấm tay) | bảng kết quả |
| Failure analysis | Lỗi Generation/Citation: trả lời sai dù có đúng đoạn, trích dẫn sai đoạn | mục trong report |
| Slide | Generation + citation | 1–2 slide |
| Q&A chính | Reranker khác retriever ra sao? Cross-encoder khác bi-encoder thế nào? (phần lý thuyết) | |

### TV5 — Schema + ghép pipeline → Guardrail

**Liên hệ giữa A và B:** người ghép pipeline nắm toàn bộ luồng, nên đặt guardrail ở đúng hai điểm chặn (trước và sau LLM).

| Việc | Chi tiết | Đầu ra |
|---|---|---|
| A. Schema | Viết file schema chung **ngày 1**; điều phối review interface | `schema.py`, `config.py` |
| A. Pipeline | `ingest(path/url)`, `ask(query)`; xử lý lỗi tích hợp; smoke test end-to-end | `pipeline.py` + test |
| B. Guardrail trước LLM | Điểm retrieval cao nhất thấp hơn ngưỡng, hoặc không có context → từ chối, **không gọi LLM** | + test |
| B. Guardrail sau LLM | Loại `[n]` ngoài phạm vi; không còn citation hợp lệ thì trả câu từ chối | + test |
| Eval | Cùng TV4 đánh giá Guardrail | bảng kết quả |
| Failure analysis | **Phân loại lỗi trước** để giao cho từng chủ module, sau đó **tổng hợp** report | `evals/team-4.2/REPORT.md` |
| Việc thêm | Ghép slides của cả nhóm | `slides` |
| Q&A chính | Khi user hỏi ngoài phạm vi tài liệu, pipeline xử lý ra sao? · Tài liệu tăng 100x cần thay đổi gì? | |

---

## 5. Evaluation

### 5.1. Bộ câu hỏi

- **Mỗi thành viên viết 6–8 câu**, tổng khoảng 30–40 câu (sprint yêu cầu tối thiểu 10).
- Câu hỏi và gold do người viết, không dùng LLM sinh.
- **Đáp án mẫu (`reference`, dùng cho RAGAS)** được phép để LLM soạn nháp, nhưng phải kiểm tra thủ công:
  1. `evals/team-4.2/runners/draft_references.py` (TV3) gửi cho GPT 5.6 Lunar câu hỏi + text của **đúng các trang gold**, không dùng kết quả retrieval của pipeline.
  2. **Người viết câu hỏi** đọc lại từng đáp án nháp, đối chiếu tài liệu gốc, sửa rồi ghi vào `questions.jsonl`.
  3. **TV3** kiểm tra chéo ngẫu nhiên vài câu của mỗi người trước khi chốt.
  4. Câu chưa kiểm tra thì để trống `reference` (RAGAS bỏ qua câu đó). Câu `out_of_scope` không có `reference`.
- Mỗi câu có nhãn `type`: `lookup` (tra cứu trực tiếp) · `paraphrase` (diễn đạt khác văn bản) · `multi` (cần nhiều đoạn) · `out_of_scope` (ngoài phạm vi; tối thiểu 5 câu).
- **Gold trỏ tới `source` + `page` (hoặc `source` + mục), không trỏ tới `chunk_id`.** Khi đổi cách chunk, gold vẫn đúng. Lúc chạy eval mới quy đổi gold sang chunk.
- Một câu có thể có **nhiều đáp án đúng**.
- **Chốt cố định bộ câu hỏi (kể cả `reference`) trước khi chạy eval hay tinh chỉnh tham số.** Sau khi chốt thì không sửa.

Ví dụ một dòng trong `questions.jsonl`:

```json
{"id": "q01", "question": "...", "type": "lookup", "author": "TV1",
 "gold": [{"source": "luat_a.pdf", "page": 12}, {"source": "luat_a.pdf", "page": 13}],
 "reference": "Đáp án mẫu, đã được người viết câu hỏi kiểm tra lại."}
```

### 5.2. Chỉ số đo theo từng lớp

| Lớp | Chỉ số | Cách đo | Người đo |
|---|---|---|---|
| Retrieval — BM25 riêng | Recall@5, MRR@5 | tự động | TV2 + TV3 |
| Retrieval — Dense riêng | Recall@5, MRR@5 | tự động | TV2 + TV3 |
| Retrieval — Hybrid RRF | Recall@5, MRR@5 (**bắt buộc**) | tự động | TV2 + TV3 |
| Retrieval — Hybrid RRF | Context Recall (tham khảo) | RAGAS, cần `reference` | TV2 + TV3 |
| Generation | Faithfulness, Answer Relevancy, Answer Correctness | RAGAS (tự động) | TV4 + TV5 |
| Generation | Tỉ lệ trả lời đúng, để đối chiếu với điểm RAGAS | chấm tay khoảng 15 câu | TV4 + TV5 |
| Citation | Tỉ lệ citation trỏ đúng đoạn chứa thông tin | chấm tay (RAGAS không đo) | TV4 + TV5 |
| Guardrail | Tỉ lệ từ chối đúng với câu ngoài phạm vi; tỉ lệ từ chối nhầm với câu trong phạm vi | tự động | TV4 + TV5 |

Câu `out_of_scope` không tính vào Recall/MRR và RAGAS, chỉ dùng để đo Guardrail.

RAGAS dùng chính GPT 5.6 Lunar để chấm, và đáp án mẫu cũng do model này soạn nháp, nên điểm có thể cao hơn thực tế. `evals/team-4.2/REPORT.md` phải ghi rõ điều này và so điểm RAGAS với kết quả chấm tay. Chi tiết ở `docs/tech_stack.md`, mục 3.

### 5.3. Quy trình failure analysis

1. **TV3** chạy eval và xuất kết quả từng câu.
2. **TV5** xếp mỗi câu sai vào một nhóm lỗi:

   | Nhóm lỗi | Dấu hiệu | Giao cho |
   |---|---|---|
   | Parsing/Chunking | Text bị lỗi, hoặc thông tin đúng bị cắt đôi giữa hai chunk | TV1 |
   | BM25/RRF | BM25 có đoạn đúng nhưng fusion đẩy xuống; tách từ sai | TV2 |
   | Dense | Dense trả về đoạn sai nghĩa | TV3 |
   | Generation/Citation | Có đoạn đúng trong top-5 nhưng trả lời sai hoặc trích dẫn sai | TV4 |
   | Guardrail | Từ chối nhầm, hoặc bịa với câu ngoài phạm vi | TV5 |

3. **Chủ module** phân tích nguyên nhân, mỗi người ít nhất 1–2 case cụ thể.
4. **TV5** tổng hợp vào `evals/team-4.2/REPORT.md`, gồm: case tốt, case xấu, nguyên nhân, hướng cải thiện.

---

## 6. Lịch làm việc

| Ngày | TV1 | TV2 | TV3 | TV4 | TV5 |
|---|---|---|---|---|---|
| **09/09 T4** | Thử PyMuPDF, trafilatura | Thử pyvi, viết thử công thức BM25 | Lấy OpenAI key, thử `text-embedding-3-small` trên vài đoạn tiếng Việt, ước lượng chi phí | Lấy key GPT 5.6 Lunar, nháp prompt | **Viết schema chung** → cả nhóm review |
| **10/09 T5** | **Parsing** | **BM25** | **Dense** (có TV2 hỗ trợ) | Generation với context giả | Khung pipeline với module giả |
| **11/09 T6** | **Chunking** | **RRF + HybridRetriever** | Hoàn thiện Dense; dựng **khung Eval** | **Generation** | Guardrail trước LLM |
| **12/09 T7** | Gán gold cùng TV3 | Hỗ trợ Dense / test Hybrid | Bộ gold + test khung Eval; script `draft_references.py` + tích hợp RAGAS | **Citation** | **Ghép end-to-end** + guardrail sau LLM (có TV4) |
| **13/09 CN** | Nghỉ, hoặc mỗi người viết câu hỏi eval + kiểm tra đáp án mẫu do LLM soạn nháp → **TV3 chốt cố định bộ câu hỏi cuối ngày** | | | | |
| **14/09 T2** | Sửa lỗi ingest | Chạy eval retrieval (BM25 / Dense / Hybrid) | Chạy eval retrieval + RAGAS | Đọc kết quả RAGAS; chấm tay Generation + Citation | Đo Guardrail; **phân loại lỗi** |
| **15/09 T3** | FA Parsing/Chunking + slide | FA BM25/RRF + **README** + slide | FA Dense + slide | FA Generation/Citation + slide | **Tổng hợp REPORT** + ghép slides |
| **16/09 T4** | Dry-run demo + luyện Q&A chéo (cả nhóm) | | | | |
| **17/09 T5** | **DEMO + Q&A** | | | | |

FA = failure analysis.

---

## 7. Review code chéo

Review theo chiều luồng dữ liệu: người review luôn là người dùng đầu ra của module được review, hoặc làm module ngay cạnh nó.

| Người viết | Người review | Lý do |
|---|---|---|
| TV1 (Parsing/Chunking) | TV2 | BM25 dùng trực tiếp `Chunk` |
| TV2 (BM25/RRF) | TV3 | Dense cùng đầu ra `Hit`, cùng đi vào RRF |
| TV3 (Dense/Eval) | TV4 | Generation dùng kết quả retrieval |
| TV4 (Generation/Citation) | TV5 | Guardrail kiểm tra đầu ra của Generation |
| TV5 (Pipeline/Guardrail) | TV1 | Kiểm tra pipeline gọi đúng ingest |

---

## 8. Chuẩn bị Q&A

Sprint ghi rõ: *"mỗi thành viên đều có thể bị hỏi về bất kỳ phần nào"*. Mỗi người trả lời chính 1–2 câu và **phải trả lời được ít nhất 1 câu ngoài phần mình**.

| Câu hỏi | Trả lời chính | Dự phòng |
|---|---|---|
| BM25 hoạt động thế nào? Khác gì TF-IDF? | TV2 | TV1 |
| Vector embedding là gì? Tại sao cần? | TV3 | TV2 |
| RRF fusion hoạt động ra sao? | TV2 | TV3 |
| Reranker khác gì retriever? Cross-encoder vs bi-encoder? | TV4 | TV3 |
| Chunk size ảnh hưởng thế nào đến retrieval? | TV1 | TV2 |
| User hỏi ngoài phạm vi tài liệu thì xử lý ra sao? | TV5 | TV4 |
| Recall@5 đạt bao nhiêu? Giải thích? | TV3 | TV5 |
| Tài liệu tăng 100x cần thay đổi gì? | TV5 | TV3 |
| So sánh pipeline này với RAGFlow? | TV1 | TV4 |

Ngày 16/09: mỗi người hỏi chéo người khác ít nhất 2 câu ngoài phần của họ.

---

## 9. Definition of Done

| Hạng mục | Người chịu trách nhiệm |
|---|---|
| ☐ Ingest được PDF + URL (+ TXT) | TV1 |
| ☐ Chunk có metadata `source`, `page`, `chunk_id` | TV1 |
| ☐ BM25 index + Vector index | TV2, TV3 |
| ☐ Hybrid search BM25 + Dense + RRF hoạt động | TV2 |
| ☐ Câu trả lời dựa trên chunk, có citation (tài liệu, trang, đoạn) | TV4 |
| ☐ Không tìm thấy thông tin → "Không có trong tài liệu." | TV5 |
| ☐ Pipeline chạy end-to-end: ingest → hỏi → trả lời có citation | TV5 |
| ☐ Evaluation report: 10+ câu (mục tiêu 30–40), Recall@5, MRR@5 | TV3 |
| ☐ Failure analysis (bonus) | TV5 + cả nhóm |
| ☐ README hướng dẫn cài đặt & chạy lại | TV2 |
| ☐ Slides 5–10 trang | TV5 + cả nhóm |
| ☐ Unit test mỗi module chạy pass | Chủ module |
