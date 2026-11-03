# Tech stack — Sprint 1: Baseline Hybrid RAG

> **Quy ước đường dẫn (sau khi tái cấu trúc theo repo `agentic-batch-4`):** `src/`, `tests/`, `docs/`, `pyproject.toml` tính từ `app/team-4.2/`; các đường dẫn bắt đầu bằng `app/`, `data/`, `evals/`, `experiments/`, `scripts/`, `reports/` tính từ gốc repo.

> **Căn cứ:** mục "Tech stack gợi ý" trong `sprint1.pdf` (đề bài mentor, lưu ở `_local/`, không commit; yêu cầu chính thức xem `weeks/week-01/README.md` của repo) và phân công trong `docs/phan_cong_sprint1.md`.
> **Nguyên tắc chọn:** không cần Docker hay server riêng, mỗi thành viên giải thích được phần mình làm khi Q&A.
> **Thay đổi stack phải báo cả nhóm và TV5 duyệt** (giống quy ước với `src/rag/schema.py`).

---

## 1. Tổng quan

| Lớp | Chọn | Gợi ý của sprint | Owner | Lý do |
|---|---|---|---|---|
| Ngôn ngữ | **Python 3.12** | — | Cả nhóm | Máy dev đang có sẵn 3.12 |
| Framework | **Tự code thuần** | LangChain / LlamaIndex / tự code | Cả nhóm | Xem mục 2 |
| Parsing PDF | **PyMuPDF** (`pymupdf`) | — | TV1 | Trả text theo từng trang, giữ được số trang cho citation, nhanh |
| Parsing URL | **trafilatura** | — | TV1 | Lấy nội dung chính, bỏ menu, quảng cáo, footer |
| Tách từ tiếng Việt | **pyvi** | — | TV2 | Gộp từ ghép ("tài_sản") để BM25 khớp đúng từ |
| BM25 | **Tự viết** Okapi BM25 (k1=1.5, b=0.75, idf `ln(1 + …)`), lưu JSON | BM25 | TV2 | Khoảng 60 dòng, đọc được công thức khi Q&A. Không dùng `rank_bm25` vì idf của nó ≤ 0 khi một từ có trong ≥ nửa số chunk, nên tài liệu nhỏ bị mất kết quả (xem mục 9.1) |
| Embedding | **OpenAI `text-embedding-3-small`** (1536 chiều) qua `openai` | — | TV3 | Gọi API nên không cần GPU và không phải tải model; encode nhanh; giá rẻ |
| Vector DB | **Qdrant (local mode)** qua `qdrant-client`, distance = cosine | Elasticsearch / Qdrant / Milvus | TV3 | Chạy trong tiến trình Python, không cần server |
| Fusion | **RRF tự viết**, k=60 | RRF | TV2 | Khoảng 15 dòng code, phải tự hiểu vì Q&A bắt buộc hỏi |
| Reranker | **Jev** (TypeSafe, API), bật bằng `RERANK_BACKEND=jev` | — (không bắt buộc) | TV2 (đề xuất) | Phần duy nhất thêm ngoài yêu cầu sprint. Giữ hay bỏ quyết định bằng ablation. Xem mục 9 |
| LLM | **GPT 5.6 Lunar** qua `openai`, `temperature=0` | Gemini Flash/Pro / LLM bất kỳ | TV4 | Theo quyết định của nhóm. Tên model đọc từ `LLM_MODEL` |
| Cache API | **SQLite** (thư viện chuẩn `sqlite3`) | — | TV3, TV4 | Cache cả embedding lẫn câu trả lời LLM: chạy lại không tốn tiền, kết quả tất định |
| UI | **Streamlit** | Streamlit / Gradio / web app | **Chưa giao** (xem mục 6) | Có sẵn chat, upload file, ô nhập URL |
| Config | **Thư viện chuẩn** (`dataclass` + đọc `.env`) — `src/rag/config.py` | — | TV5 | Gom key, đường dẫn, k, ngưỡng vào một chỗ. Không dùng pydantic-settings để bớt một phụ thuộc |
| Schema | **dataclasses** (thư viện chuẩn) | — | TV5 | `src/rag/schema.py`, không phụ thuộc thư viện ngoài |
| Test | **pytest** | — | Chủ module | Mỗi module có một file `tests/test_<module>.py`; dùng embedder và LLM giả để không gọi API |
| Eval retrieval | **Tự viết** `recall_at_k`, `hit_at_k`, `mrr_at_k` (`src/rag/eval/`), xuất CSV + Markdown | — | TV3 (+ TV2) | Recall@5, MRR@5 là chỉ số bắt buộc, tính theo gold `source` + `page` |
| Eval generation | **RAGAS** | — | TV4 + TV5 (+ TV3) | Chấm tự động chất lượng câu trả lời và context, xem mục 3 |

---

## 2. Framework: vì sao tự code thuần

**Framework** (LangChain, LlamaIndex) là thư viện dựng sẵn các khối của pipeline RAG: loader, splitter, retriever, vector store, chain sinh câu trả lời. Nhóm chỉ cần gọi hàm có sẵn rồi nối các khối lại.

| Bước | Tự code (stack đã chọn) | LangChain / LlamaIndex có sẵn |
|---|---|---|
| Parsing | PyMuPDF, trafilatura | `PyMuPDFLoader`, `WebBaseLoader` |
| Chunking | Tự gom đoạn đến khoảng 300 âm tiết | `RecursiveCharacterTextSplitter`, `SentenceSplitter` |
| BM25 | Tự viết công thức + pyvi | `BM25Retriever` |
| Dense | `text-embedding-3-small` + Qdrant | `QdrantVectorStore` + `OpenAIEmbeddings` |
| Fusion | Tự viết RRF | `EnsembleRetriever`, `QueryFusionRetriever` |
| Generation + Citation | Tự viết prompt, parse `[n]` | `RetrievalQA`, `CitationQueryEngine` |

**Lý do không dùng framework:**

1. **Q&A kiểm tra hiểu biết thật.** Sprint ghi rõ là kiểm tra "hiểu biết thật sự, không phải khả năng copy-paste". Nếu RRF nằm trong `EnsembleRetriever` thì không có code của mình để chỉ ra khi giải thích.
2. **Tiếng Việt.** `BM25Retriever` mặc định tách từ theo khoảng trắng, nên "tài sản" thành hai token "tài" và "sản". Muốn dùng pyvi vẫn phải tự cài thêm.
3. **Eval cần dữ liệu trung gian.** Để đo Recall@5 riêng cho BM25, Dense và Hybrid, cần lấy được danh sách `Hit` của từng arm. Framework thường chỉ trả kết quả cuối.
4. **Schema chung.** Framework dùng kiểu `Document` riêng, không khớp với `Page`, `Chunk`, `Hit`, `Citation`, `Answer` đã chốt.
5. **Lượng code nhỏ.** Mỗi module khoảng 50–150 dòng, tự viết vẫn kịp trong 8 ngày.

RAGAS là thư viện **đánh giá**, không phải framework dựng pipeline, nên dùng RAGAS không mâu thuẫn với lựa chọn tự code.

---

## 3. Evaluation: tự viết + RAGAS

### 3.1. Chia việc giữa hai công cụ

| Lớp | Chỉ số | Công cụ | Ghi chú |
|---|---|---|---|
| Retrieval (BM25 / Dense / Hybrid) | **Recall@5, MRR@5** (bắt buộc) | Tự viết | Gold trỏ tới `source` + `page`; quy đổi sang chunk bằng `Question.is_relevant(chunk)` trong `schema.py` |
| Retrieval | Context Precision, Context Recall | RAGAS | Tham khảo thêm; Context Recall cần đáp án mẫu (xem 3.3) |
| Generation | **Faithfulness** | RAGAS | Câu trả lời có bám context không, tức là đo hallucination. Thay cho phần lớn việc chấm tay |
| Generation | Answer Relevancy (Response Relevancy) | RAGAS | Câu trả lời có đúng trọng tâm câu hỏi không |
| Generation | Answer Correctness | RAGAS | So với đáp án mẫu; cần trường `reference` (LLM soạn nháp, người kiểm tra, xem 3.3) |
| Citation | Tỉ lệ `[n]` trỏ đúng đoạn chứa thông tin | Chấm tay | RAGAS không có chỉ số cho citation |
| Guardrail | Tỉ lệ từ chối đúng (OOS) / từ chối nhầm (trong phạm vi) | Tự viết | So `Answer.refused` với `Question.in_scope` |
| Context | Tỉ lệ câu có gold nằm trong context đã chọn; số đoạn trung bình | Tự viết | Đo riêng với Recall@5, vì số đoạn context thay đổi theo câu (mục 9.5) |

**Vì sao vẫn tự viết Recall@5/MRR@5:** RAGAS không có MRR, và các chỉ số context của RAGAS chấm bằng LLM chứ không so trực tiếp với gold `source` + `page`. Sprint yêu cầu báo cáo Recall@5 và MRR@5, nên phải tính tất định từ gold.

### 3.2. Cấu hình RAGAS

- **LLM chấm:** dùng GPT 5.6 Lunar qua `openai` (cùng key), `temperature=0`.
- **Embedding cho Answer Relevancy:** dùng luôn `text-embedding-3-small`.
- **Đầu vào mỗi mẫu** lấy từ `Answer` của pipeline: câu hỏi (`user_input`), các chunk trong context (`retrieved_contexts`), câu trả lời (`response`), đáp án mẫu (`reference`, nếu có).
- **Bỏ qua** câu `out_of_scope` và câu bị từ chối khi tính Faithfulness; hai nhóm này đo bằng chỉ số Guardrail.
- **Chốt version RAGAS** trong `pyproject.toml`. API của RAGAS thay đổi khá nhiều giữa các bản (tên trường, cách khai báo LLM), nên cả nhóm phải cài cùng một version.

### 3.3. Ảnh hưởng tới bộ gold và schema

Context Recall và Answer Correctness cần **đáp án mẫu** (`reference`) cho từng câu. `Question` trong `src/rag/schema.py` đã có trường tuỳ chọn `reference`:

```json
{"id": "q01", "question": "...", "type": "lookup", "author": "TV1",
 "gold": [{"source": "luat_a.pdf", "page": 12}],
 "reference": "Đáp án mẫu, đã được người viết câu hỏi kiểm tra lại."}
```

**Quy trình soạn đáp án mẫu (LLM soạn nháp, người kiểm tra):**

1. **Câu hỏi và gold vẫn do người viết.** Chỉ đáp án mẫu được phép để LLM soạn nháp.
2. Script `evals/team-4.2/runners/draft_references.py` gửi cho GPT 5.6 Lunar **câu hỏi + text của đúng các trang gold** (lấy theo `source` + `page`), **không** dùng kết quả retrieval của pipeline. Như vậy đáp án mẫu không bị ảnh hưởng bởi lỗi retrieval mà ta đang muốn đo.
3. Prompt yêu cầu trả lời ngắn, chỉ dựa trên đoạn được cung cấp, không thêm ý ngoài tài liệu.
4. **Người viết câu hỏi** đọc lại từng đáp án nháp, đối chiếu với tài liệu gốc, sửa chỗ sai hoặc thiếu, rồi ghi vào `questions.jsonl`.
5. **TV3** kiểm tra chéo ngẫu nhiên vài câu của mỗi người trước khi chốt bộ câu hỏi. Sau khi chốt thì không sửa `reference` nữa (giống quy tắc với câu hỏi).
6. Câu `out_of_scope` không có `reference`.

Câu nào chưa được kiểm tra thì để `reference` trống: RAGAS sẽ bỏ qua câu đó ở Context Recall và Answer Correctness, thay vì chấm theo một đáp án chưa ai xác nhận.

### 3.4. Lưu ý khi đọc kết quả RAGAS

- **Cùng một LLM vừa trả lời, vừa soạn nháp đáp án mẫu, vừa chấm** (GPT 5.6 Lunar) dễ cho điểm cao hơn thực tế, nhất là Answer Correctness: câu trả lời và đáp án mẫu có thể giống nhau về cách diễn đạt chỉ vì cùng một model viết ra. Bước kiểm tra thủ công ở 3.3 giảm được rủi ro này nhưng không loại bỏ hết. Báo cáo phải ghi rõ điều này, và vẫn **chấm tay khoảng 15 câu** để đối chiếu với điểm RAGAS (đúng nguyên tắc "không tự chấm module của mình một mình").
- RAGAS chấm bằng LLM nên điểm có thể dao động giữa các lần chạy. Cố định `temperature=0`, cache kết quả, và chỉ so sánh các cấu hình được chấm trong cùng một lần chạy.
- Prompt mặc định của RAGAS viết bằng tiếng Anh. Với câu hỏi tiếng Việt vẫn chạy được, nhưng nên xem tay vài mẫu để chắc LLM chấm hiểu đúng.

---

## 4. Ghép stack vào luồng dữ liệu

```
PDF ──PyMuPDF──────┐
URL ──trafilatura──┼─► list[Page] ──chunker (tự viết)──► list[Chunk]
TXT ──open()───────┘                                          │
                         ┌────────────────────────────────────┤
                         ▼                                    ▼
          pyvi + BM25 tự viết ──► Hit(bm25)    text-embedding-3-small
                         │                    + Qdrant ──► Hit(dense)
                         └──────────► RRF (tự viết, k=60) ◄───┘
                                          │ top-20 Hit(fused)
                                          ▼
                          Rerank: none | Jev (lỗi → giữ thứ tự RRF, Hit(fused))
                                          │
                          top-5 để chấm điểm · context 0..8 đoạn theo ngưỡng Jev
                                          │
                          Guardrail trước LLM (ngưỡng RRF hoặc ngưỡng Jev, trong config.py)
                                          │
                          GPT 5.6 Lunar (openai, cache SQLite)
                                          │
                          Citation (parse [n]) ──► Guardrail sau LLM
                                          │
                               Answer ──► Streamlit UI
                                      └─► evals/team-4.2/: Recall@5, MRR@5 (tự viết)
                                                 Faithfulness, Relevancy… (RAGAS)
```

---

## 5. Cài đặt

### 5.1. Yêu cầu hệ thống

- Python 3.12, có module `venv`. Trên Ubuntu nếu thiếu thì cài: `sudo apt install python3.12-venv`
- **Có kết nối mạng** khi ingest, khi hỏi và khi chạy eval (embedding và LLM đều gọi API)
- API key cho OpenAI (embedding) và cho GPT 5.6 Lunar

### 5.2. Thư viện

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pymupdf trafilatura pyvi openai qdrant-client \
            streamlit pandas ragas pytest
```

Reranker Jev là phần tuỳ chọn: `pip install typesafe-sdk` (chỉ cần khi `RERANK_BACKEND=jev`).

Danh sách chính thức nằm trong `pyproject.toml`, Jev để ở nhóm optional `[jev]`. Khi đã chạy ổn, chốt version bằng `pip freeze > requirements.lock` để cả nhóm cài giống nhau, **nhất là `ragas`**.

### 5.3. Biến môi trường (`.env`, không commit)

```bash
OPENAI_API_KEY=...
EMBED_MODEL=text-embedding-3-small
LLM_MODEL=gpt-5.6-lunar
# Nếu GPT 5.6 Lunar dùng endpoint/key riêng (OpenAI-compatible):
# LLM_BASE_URL=...
# LLM_API_KEY=...

RERANK_BACKEND=none            # none | jev
RERANK_N=20                    # số fused hit đưa vào rerank
TYPESAFE_API_KEY=...           # chỉ cần khi RERANK_BACKEND=jev
```

---

## 6. Lưu ý và rủi ro

| # | Vấn đề | Ảnh hưởng | Cách xử lý |
|---|---|---|---|
| 1 | **UI là deliverable bắt buộc (#1)** nhưng `phan_cong_sprint1.md` ghi "Phần UI không nằm trong danh sách phân công" | Thiếu UI thì không đạt Definition of Done | Giao cho TV5 (nắm `pipeline.ask()`) hoặc TV2 (việc nhẹ). Làm ngày 14/09 theo timeline sprint |
| 2 | **Demo phụ thuộc mạng và API** (embedding + LLM) | Mất mạng hoặc API lỗi thì app không trả lời được | Ingest sẵn tài liệu demo trước buổi bảo vệ; cache SQLite giúp các câu đã hỏi vẫn chạy; chuẩn bị video demo dự phòng |
| 3 | Chi phí và rate limit API | Chạy eval nhiều cấu hình × RAGAS tốn nhiều lượt gọi | Cache embedding theo `sha256(model + text)` và câu trả lời theo `sha256(model + prompt)`; test dùng embedder và LLM giả |
| 4 | **Đổi model embedding phải index lại toàn bộ** | Vector cũ và mới không so được với nhau | `VectorIndex.open_qdrant` ghi tên model và số chiều vào `meta.json` cạnh index; mở bằng model khác thì báo `IndexMismatchError`, không trộn |
| 5 | RAGAS dùng cùng LLM để chấm | Điểm có thể cao hơn thực tế | Chấm tay khoảng 15 câu để đối chiếu; ghi rõ trong `evals/team-4.2/REPORT.md` |
| 6 | Lẫn NFC/NFD trong tiếng Việt | BM25 không khớp, gold không khớp | Mọi text đi qua `nfc()` trong `schema.py` |
| 7 | PDF scan, không có lớp text | Index text rỗng mà không ai biết | Parser cảnh báo khi `Page.is_empty` |
| 8 | Qdrant local mode chỉ cho **một tiến trình** mở cùng thư mục | Streamlit và script eval chạy song song sẽ lỗi khoá thư mục | Không chạy eval khi app đang mở, hoặc dùng thư mục index riêng cho eval |
| 9 | Dense phải nhận **text gốc**, không phải text đã tách từ bằng pyvi | Đưa "tài_sản" vào embedding làm giảm chất lượng | Chỉ BM25 dùng text đã tách từ; Dense encode `Chunk.text` |

---

## 7. Mở rộng (bonus, chỉ làm sau khi baseline chạy ổn)

| Bonus | Công cụ | Ghi chú |
|---|---|---|
| #8 Advanced method | **HyDE** dùng GPT 5.6 Lunar | Sinh đoạn trả lời giả rồi embed bằng `text-embedding-3-small`; không cần thêm model. Đo bằng Recall@5/MRR@5 như các arm khác |
| #8 Advanced method | SPLADE / ColBERT | Phải tự chạy model trên máy (CPU chậm); chỉ làm nếu còn thời gian |
| Reranker | Jev | Đã có code ở `src/rag/retrieve/rerank.py`; thiết kế và cách chọn ở mục 9 |
| #9 Failure analysis | pandas + RAGAS + `evals/team-4.2/REPORT.md` | Câu có Faithfulness thấp là ứng viên lỗi Generation; quy trình ở mục 5.3 của `phan_cong_sprint1.md` |

---

## 8. Phương án đã cân nhắc nhưng không chọn

| Thành phần | Phương án | Lý do không chọn |
|---|---|---|
| Embedding | BGE-M3 (chạy local) | Chạy CPU chậm, model khoảng 2.2GB; nhóm chọn API để đơn giản |
| Embedding | `text-embedding-3-large` | Đắt hơn, vector 3072 chiều; với vài nghìn chunk chưa cần |
| LLM | Gemini Flash / Pro (gợi ý của sprint) | Nhóm chọn GPT 5.6 Lunar; dùng chung SDK `openai` với embedding |
| Eval | Chỉ chấm tay | Chậm, khó lặp lại khi đổi cấu hình; RAGAS chấm tự động, chấm tay chỉ để đối chiếu |
| Vector DB | Elasticsearch | Nặng (JVM), cần chạy server, không có analyzer tiếng Việt sẵn |
| Vector DB | Milvus | Cần Docker, quá nặng cho vài nghìn chunk |
| Vector DB | FAISS | Không lưu metadata, phải tự quản lý ánh xạ id ↔ chunk |
| Framework | LangChain / LlamaIndex | Xem mục 2 |
| UI | Gradio | Dùng được. Chọn Streamlit vì layout chat + sidebar upload viết gọn hơn |
| UI | Web app (FastAPI + React) | Tốn thời gian, không cộng điểm so với Streamlit |
| Parsing PDF | pdfplumber | Chậm hơn PyMuPDF. Chỉ dùng để đối chiếu khi nghi lỗi font/dấu |
| BM25 | `rank_bm25` (`BM25Okapi`) | idf ≤ 0 khi một từ có trong ≥ nửa số chunk: với tài liệu nhỏ, từ khoá đúng bị mất điểm. Tự viết chỉ khoảng 60 dòng |
| Reranker | `bge-reranker-v2-m3` (cross-encoder chạy trên máy) | Nhóm giữ phạm vi sprint 1, chỉ thêm Jev. Câu Q&A về cross-encoder vẫn trả lời phần lý thuyết |

---

## 9. Retrieve: BM25, Dense, RRF và rerank Jev

Code trong `src/rag/index/` và `src/rag/retrieve/`; test trong `tests/test_bm25.py`, `test_dense.py`, `test_hybrid.py`, `test_rerank.py`. Bám sát sprint 1, chỉ thêm rerank bằng Jev. Tham khảo phần retrieve của repo `maitungdeptraiiiii/Law_RAG` (BM25 tự viết với idf luôn dương, RRF, OpenAI embedding có retry); không lấy phần graph, rule pháp lý và pin kết quả vì vượt phạm vi sprint.

```
query ─┬─► BM25Index.search(q, 20)   ─► Hit(bm25)  ─┐
       └─► VectorIndex.search(q, 20) ─► Hit(dense) ─┴─► rrf(k=60) ─► top-20 Hit(fused)
                                                                        │
                       JevReranker (RERANK_BACKEND=jev) hoặc NoopReranker (none)
                                                                        ▼
                                             ranked (20 hit, đã rerank nếu có)
                                                ├─► hits = ranked[:5] ─► Recall@5, MRR@5
                                                └─► select_context ─► 0..8 đoạn ─► Guardrail ─► LLM
```

### 9.1. BM25 — `src/rag/index/bm25_index.py` (TV2)

- Tách từ: NFC → pyvi (`tài sản` → `tài_sản`) → bỏ dấu câu → chữ thường. Query và chunk dùng cùng tokenizer. Có `syllable_tokenize` (tách theo âm tiết, không cần pyvi) để test và để so sánh khi eval.
- Công thức: `idf = ln(1 + (N − df + 0.5)/(df + 0.5))`. Dạng gốc của `rank_bm25` là `ln((N − df + 0.5)/(df + 0.5))`, cho idf ≤ 0 khi từ có trong ≥ nửa số chunk; ví dụ tài liệu chỉ có 2 chunk đều chứa "điều" thì tìm "điều" ra 0 kết quả.
- Chỉ trả hit có score > 0; hoà điểm xếp theo `chunk_id`.
- `build` thêm dần, chunk đã có thì bỏ qua. `save`/`load` ra JSON (`data/team-4.2/indexes/bm25.json`), có ghi tên tokenizer; tải bằng tokenizer khác thì báo lỗi.

### 9.2. Dense — `src/rag/index/embedder.py`, `vector_index.py` (TV3)

- `OpenAIEmbedder`: `text-embedding-3-small`, batch 64, retry tối đa 6 lần (chờ 1, 2, 4… tối đa 30 giây) khi gặp rate limit, timeout, lỗi kết nối hoặc lỗi server; kiểm tra số chiều; cache SQLite theo `sha256(model, text)`.
- `HashEmbedder`: embedder giả, tất định, không gọi mạng. Các module khác dùng nó khi viết unit test.
- `VectorIndex`: chỉ embed chunk chưa có trong index. `search` trả `Hit(dense)` với score = cosine.
- `QdrantVectorStore` (local mode, cosine; id điểm = UUID5 từ `chunk_id`) và `InMemoryVectorStore` (cho test). `VectorIndex.open_qdrant(dir, embedder)` ghi `meta.json` (model, số chiều) và từ chối mở index build bằng model khác.

### 9.3. RRF và HybridRetriever — `src/rag/retrieve/fusion.py`, `hybrid.py` (TV2)

- `rrf(ranked, k=60, top_n)`: chỉ dùng thứ hạng; một chunk lặp trong cùng arm chỉ tính lần tốt nhất; hoà điểm xếp theo `chunk_id`.
- `HybridRetriever.retrieve(query, k=5, mode="hybrid" | "bm25" | "dense", rerank=True)` trả `RetrievalResult`:

  | Trường | Nội dung | Dùng cho |
  |---|---|---|
  | `arms` | Top-20 của từng arm | Eval BM25 riêng / Dense riêng |
  | `candidates` | Top-20 fused (hoặc của arm duy nhất) | Recall@20: giới hạn trên của rerank |
  | `hits` | Top-k cuối | Generation, Recall@5, MRR@5 |
  | `errors` | Arm bị lỗi | UI cảnh báo, debug |

- Ở mode `hybrid`, một arm lỗi (vd. mất mạng khi gọi embedding) thì vẫn trả kết quả arm còn lại; cả hai cùng lỗi thì báo `RetrievalError`.
- `build(chunks)` index vào cả hai arm và nhớ text chunk cho reranker; gọi lại không nhân đôi.

### 9.4. Rerank bằng Jev — `src/rag/retrieve/rerank.py`

| Lớp | Vai trò |
|---|---|
| `JevReranker` | Mỗi cặp (câu hỏi, chunk) là một câu hỏi `Noul`: *"Đoạn văn chứa thông tin trả lời trực tiếp câu hỏi"* → xác suất [0, 1]. Gọi song song bằng thread (`max_workers=8`). Model chốt `jev-1.13.0`, không dùng `jev-latest`. Hoà điểm giữ thứ tự RRF |
| `ScoreCache` | SQLite, key = `sha256(model, câu hỏi, chunk_id, text)` |
| `NoopReranker` | `RERANK_BACKEND=none`: giữ nguyên `Hit(fused)`. Dùng cho ablation và làm fallback |
| `FallbackReranker` | Jev lỗi (mạng, API, SDK) → dùng thứ tự RRF, ghi log, lưu `last_error` để UI cảnh báo. Lỗi do đầu vào sai (`RerankInputError`) vẫn được ném ra |
| `make_reranker(backend)` | Tạo reranker theo `RERANK_BACKEND`; mặc định bọc `FallbackReranker` |

**Guardrail:** điểm Jev (xác suất) và điểm RRF khác thang, nên có hai ngưỡng, chọn trên tập dev:

- Có Jev (`arm="rerank"`): từ chối khi **không đoạn nào đạt `CONTEXT_MIN_P`**, tức `select_context(...)` trả context rỗng (mục 9.5). Một ngưỡng dùng chung cho cả chọn context lẫn từ chối.
- Không có Jev hoặc Jev lỗi (`arm="fused"`): từ chối khi điểm RRF cao nhất thấp hơn ngưỡng RRF trong `config.py` (TV5).

Khi Jev lỗi, hit vẫn là `arm="fused"`, nên guardrail tự chuyển sang ngưỡng RRF.

**Giữ hay bỏ Jev (ablation, sau khi baseline chạy end-to-end):** so `RERANK_BACKEND=none` với `jev` trên Recall@5, MRR@5, thời gian mỗi câu, tỉ lệ từ chối đúng/nhầm; báo thêm Recall@20 của RRF. Jev không hơn hẳn `none` thì để `none`. Trước đó thử nhanh Jev với 5 câu hỏi tiếng Việt, vì các nguồn hiện có **chưa xác nhận Jev hỗ trợ tiếng Việt**.

### 9.5. Chọn context: tách khỏi top-k dùng để chấm — `src/rag/retrieve/context.py`

Theo thread Reddit đã đọc khi lên kế hoạch: *"keep top-5 for scoring"*, còn context đưa cho model chọn riêng; *"retrieve wide and let the filter pick"*. Jev đóng vai bộ lọc, rẻ hơn gọi LLM.

| Việc | Lấy từ | Số đoạn |
|---|---|---|
| Chấm retrieval | `RetrievalResult.hits` | **Cố định** `TOP_K=5` → Recall@5, MRR@5 (sprint bắt buộc). Báo thêm Recall@20 trên `candidates` |
| Context cho LLM | `select_context(result.ranked, retriever.chunks, cfg)` | **Thay đổi theo câu hỏi** |

`HybridRetriever` cho Jev chấm **toàn bộ** 20 ứng viên và giữ trong `RetrievalResult.ranked` (không tốn thêm lượt gọi: Jev vốn phải chấm hết để sắp xếp). `hits = ranked[:TOP_K]`.

| Chế độ | Khi nào | Cách chọn |
|---|---|---|
| `threshold` | Hit đã được Jev chấm (`arm="rerank"`) | Giữ đoạn có `p ≥ CONTEXT_MIN_P` (mặc định 0.7) theo thứ tự xếp hạng, tối đa `CONTEXT_MAX_BLOCKS=8` đoạn và `CONTEXT_MAX_WORDS=2400` từ. Không đoạn nào đạt ngưỡng → context rỗng → từ chối, không gọi LLM |
| `fixed` | Không rerank hoặc Jev lỗi | Điểm RRF không phải xác suất nên không đặt ngưỡng → lấy `TOP_K` đoạn đầu như baseline, vẫn tuân trần `CONTEXT_MAX_WORDS` |

Quy tắc chung: đánh số `[1]…[n]` theo thứ tự xếp hạng (TV4 dùng cho citation); hết ngân sách thì dừng, không nhảy cóc sang đoạn ngắn hơn ở dưới; đoạn đầu tiên luôn được lấy. `ContextSelection` ghi `below_threshold` và `cut_by_limit` để failure analysis biết đoạn đúng bị loại vì ngưỡng hay vì trần.

**Chọn tham số trên tập dev:** thử `CONTEXT_MIN_P` ∈ {0.5, 0.7, 0.85} quanh giá trị mặc định 0.7; ghi tỉ lệ từ chối đúng/nhầm, tỉ lệ câu có gold trong context, và số đoạn trung bình. So với context top-5 cố định bằng bảng chấm Generation (RAGAS + chấm tay) trên cùng bộ câu hỏi.

**Chưa làm (để các tuần sau):** dựng context theo cấu trúc luật (lấy nguyên Điều, Chương, các Điều được viện dẫn) như tác giả thread đề xuất. Việc này cần chunker hiểu cấu trúc văn bản luật, vượt phạm vi baseline sprint 1.

### 9.6. Chưa kiểm chứng

- Toàn bộ test chạy với client giả, chưa gọi API thật và chưa cài `pyvi`, `openai`, `qdrant-client`, `typesafe-sdk` trên máy dev.
- Cách gọi Jev (`TypeSafeClient(model=...)`, `system_one(state=..., questions=...)`, `answers[...].noul`) lấy theo tutorial của DataCamp. Nếu SDK khác thì chỉ sửa `JevReranker._get_client`, `_get_question`, `_score_one`.
- Chưa xác nhận client đồng bộ của `typesafe-sdk` an toàn khi dùng chung giữa nhiều thread. Nếu gặp lỗi, đặt `max_workers=1`.
- `QdrantVectorStore` dùng `collection_exists`, `get_collection`, `retrieve`, `upsert`, `query_points`, `count` của `qdrant-client`; cần chạy thử một lần với bản đã cài.

---

## 10. Phương pháp nâng cao dạng plugin (bonus #8) — `src/rag/advanced/`

Mỗi phương pháp là một module riêng, đăng ký vào registry và bật bằng biến `ADVANCED` trong `.env`. Pipeline chính không phải sửa khi thêm, bớt hay đổi phương pháp.

| Điểm gắn | Chạy khi nào | Tác dụng | Ví dụ |
|---|---|---|---|
| `index_enhancer` | Lúc ingest, sau chunking, trước khi index | Thêm `Chunk.context`. BM25/Dense index `context + text` (`Chunk.index_text`); text gốc giữ nguyên để hiển thị, đưa cho LLM và trích dẫn | Contextual Retrieval |
| `arms` | Lúc truy vấn | Thêm arm retrieval vào `HybridRetriever`, gộp cùng BM25 + Dense bằng RRF | HyDE |

```bash
ADVANCED=                                  # baseline sprint 1
ADVANCED=hyde                              # thêm arm HyDE
ADVANCED=contextual_header,hyde            # nhiều phương pháp, theo đúng thứ tự
```

**Thêm phương pháp mới:** tạo file trong `src/rag/advanced/`, viết hàm factory có `@register("tên")` nhận `Components` (settings, llm, embedder, index Dense) và trả `Enhancement(index_enhancer=..., arms=...)`, thêm một dòng import vào `advanced/__init__.py`, rồi bật bằng `ADVANCED`. **Bỏ:** xoá tên khỏi `ADVANCED` (hoặc xoá file và dòng import).

### 10.1. HyDE — `advanced/hyde.py` (`ADVANCED=hyde`)

- GPT 5.6 Lunar viết một đoạn trả lời **giả** 3–5 câu theo văn phong văn bản luật. Embed `câu hỏi + đoạn giả`, rồi tìm trên chính index Dense. Kết quả thành arm `hyde`, gộp với BM25 + Dense bằng RRF.
- Chỉ áp dụng cho Dense. BM25 vẫn tìm bằng câu hỏi gốc, để số Điều hay thuật ngữ LLM bịa ra không làm lệch kết quả keyword.
- Mỗi câu hỏi tốn thêm 1 lần gọi LLM, có cache. LLM lỗi thì arm `hyde` lỗi, BM25 + Dense vẫn chạy.
- **Rủi ro:** câu ngoài phạm vi cũng sinh được đoạn giả nghe hợp lý, nên phải đo cả tỉ lệ từ chối nhầm.

### 10.2. Contextual Retrieval — `advanced/contextual.py`

| Biến thể | Cách làm | Chi phí |
|---|---|---|
| `contextual_header` | Bối cảnh = tên tài liệu + heading (`section`) | Không gọi LLM, nên thử trước |
| `contextual` | GPT 5.6 Lunar viết 1–2 câu bối cảnh cho từng chunk, dựa trên phần đầu tài liệu (4000 ký tự) + heading + đoạn liền trước/sau. Chạy song song 8 luồng | 1 lần gọi LLM mỗi chunk lúc ingest, có cache. Chunk lưu kèm `context` trong `chunks.jsonl` nên khởi động lại không gọi lại |

- Bài gốc của Anthropic đưa **toàn bộ** tài liệu vào prompt cho mỗi chunk. Văn bản luật dài hàng trăm trang nên ở đây chỉ dùng phần đầu tài liệu và các đoạn lân cận. Phần đầu tài liệu đứng đầu prompt và giống nhau cho mọi chunk, để tận dụng prompt caching tự động nếu API hỗ trợ.
- LLM lỗi ở một số chunk thì các chunk đó không có bối cảnh (ghi cảnh báo). Lỗi ở mọi chunk thì ingest báo lỗi (thường do sai key, model hoặc mất mạng).
- Một người trên thread Reddit thử ghép metadata vào text embed và không thấy cải thiện. Phải đo, không mặc định là tốt hơn.

### 10.3. Bảo vệ index và cách làm ablation

- `data/team-4.2/indexes/index_config.json` ghi model embedding, `MAX_SYLLABLES` và các phương pháp chạy lúc index. Mở index bằng cấu hình khác thì pipeline báo `IndexConfigMismatchError`, không trộn chunk có và không có bối cảnh.
- **HyDE** (lúc truy vấn): cùng một index, so bằng `run_eval.py --configs hybrid hybrid+hyde hyde`.
- **Contextual** (lúc index): mỗi biến thể một `DATA_DIR` riêng, ingest cùng bộ tài liệu, chạy `run_eval.py` cho từng thư mục rồi so từng câu:

  ```bash
  DATA_DIR=data/team-4.2            ADVANCED=                   python scripts/team-4.2/ingest.py data/team-4.2/raw/
  DATA_DIR=data/team-4.2/ablation/ctxheader  ADVANCED=contextual_header  python scripts/team-4.2/ingest.py data/team-4.2/raw/
  DATA_DIR=data/team-4.2/ablation/ctx        ADVANCED=contextual         python scripts/team-4.2/ingest.py data/team-4.2/raw/
  ```

  Thư mục `raw/` dùng chung; `data/team-4.2/ablation/` đã nằm trong `data/team-4.2/.gitignore`.

