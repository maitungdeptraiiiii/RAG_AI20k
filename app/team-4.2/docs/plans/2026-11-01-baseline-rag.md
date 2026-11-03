# Baseline Hybrid RAG (Luật Việt Nam) — Implementation Plan

> **Quy ước đường dẫn (sau khi tái cấu trúc theo repo `agentic-batch-4`):** `src/`, `tests/`, `docs/`, `pyproject.toml` tính từ `app/team-4.2/`; các đường dẫn bắt đầu bằng `app/`, `data/`, `evals/`, `experiments/`, `scripts/`, `reports/` tính từ gốc repo.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ứng dụng RAG Agent có UI chat: ingest PDF/URL/TXT → hybrid search (BM25 + Dense + RRF, kèm literal arm + reranker) → Gemini trả lời có citation, từ chối khi ngoài tài liệu; có bộ eval Recall@5/MRR@5 với ablation từng thành phần và failure analysis.

**Architecture:** Thư viện Python thuần `src/rag/` chia theo trách nhiệm (ingest → index → retrieve → generate), một `RAGPipeline` ghép lại, Streamlit UI gọi pipeline, bộ `evals/team-4.2/` chạy cùng pipeline với nhiều cấu hình để làm ablation. Chunk theo cấu trúc luật (Chương/Mục/Điều/Khoản) với `article_id` chuẩn hoá, vì mọi thành phần phía sau (literal arm, cross-ref, metric theo Điều) đều dựa vào ID này. Mọi arm được hợp nhất bằng **weighted RRF theo rank** nên thêm/bớt arm không phải chỉnh thang điểm.

**Tech Stack:** Python 3.12, PyMuPDF + pdfplumber (đối chiếu), trafilatura (URL), pyvi (tách từ), rank_bm25, FlagEmbedding (BGE-M3 dense/sparse/ColBERT + bge-reranker-v2-m3, chạy CPU), qdrant-client (local mode), google-genai (Gemini), Streamlit, pytest.

**Spec:** `sprint1.pdf` (yêu cầu sprint) + `_local/references/reddit_thread.txt (chỉ lưu local, không commit)` (36 bình luận tư vấn, trích từ file HTML đã lưu). Người thực thi đọc cả hai.

---

## Từ bình luận Reddit → quyết định trong plan

Thread đồng thuận khá rõ: **đừng chồng component để "trông có đổi mới"; build baseline, đo, phân loại lỗi, rồi chỉ thêm thứ sửa được một lỗi có tên.** "Đổi mới" để trình bày với mentor nằm ở chỗ làm đúng cho tiếng Việt và văn bản luật, kèm ablation chứng minh từng bước có tác dụng. Không cần graph hay agent.

| Lời khuyên (tác giả) | Quyết định | Task |
|---|---|---|
| Tách từ tiếng Việt bằng pyvi/underthesea trước khi index BM25, có thể quan trọng hơn reranker (Away-Raspberry4977) | BM25 dùng pyvi; giữ thêm BM25 theo âm tiết làm ablation B0 | 1, 4, 10 |
| Chunk theo cấu trúc: mỗi Điều 1 chunk, header có chương + tiêu đề, cap cứng không cắt im lặng, ID Điều chuẩn hoá (No-Afternoon-4057) | `legal_chunker` theo Điều → tách theo Khoản khi quá cap; `article_id` = `{doc_id}:D{số}` | 3 |
| Thêm "literal arm" khớp chính xác "Điều 174", đừng bắt BM25/embedding gánh việc đó (No-Afternoon-4057) | Arm `literal` bằng regex, fuse bằng weighted RRF | 6 |
| Fuse theo rank (weighted RRF), không trộn thang điểm; tune k (No-Afternoon-4057, kitkatz69) | `weighted_rrf(k=60)`, tune k ∈ {10, 30, 60} chỉ trên split dev | 6, 10 |
| Một tuần thì giữ hybrid + reranker, xem lỗi ở đâu (Lonely-Bullfrog5230, scott_codie) | bge-reranker-v2-m3 rerank top-20 sau fusion | 7 |
| Cross-reference tất định ("khoản 2 Điều 174") dùng làm chú thích/mở rộng context, không làm ranker; không tính vào Recall@5 (MemStrata, No-Afternoon-4057, OP) | `xref.expand_context`, chỉ thêm vào context cho LLM | 3, 7 |
| Tách "top-5 để chấm điểm" khỏi "context đưa cho LLM" (LawfulnessOptimal597, OP) | `RetrievalTrace.final` (5, để đo) ≠ `RetrievalTrace.context` (tối đa 8 block) | 7 |
| Không embed metadata hành chính (ngày hiệu lực, cơ quan ban hành) vào text; để làm filter (OP tự đo thấy kết quả tệ hơn) | `index_text` = tiêu đề Điều + chương + nội dung; metadata khác chỉ nằm trong payload | 3, 5 |
| Bỏ non-determinism trước khi đo: temperature 0, cache LLM, bỏ query-rewrite khỏi đường eval (No-Afternoon-4057, OP thấy 4 case bị lật kết quả) | Không có query rewrite; `LLMClient` temp 0 và cache SQLite | 8 |
| So sánh bằng paired test theo từng câu hỏi, không dùng CI riêng từng hệ; tách metric theo loại câu (Away-Raspberry4977, No-Afternoon-4057) | `paired_bootstrap` + win/loss/tie, bảng theo `type` | 10 |
| Oracle test: đưa gold passage thẳng vào LLM để tách lỗi retrieval và lỗi reader (MemStrata, jylusdev) | `evals/team-4.2/runners/oracle.py` để phân loại lỗi (bonus #9) | 11 |
| Không tin PyMuPDF trích một lần là đúng; tạo bộ test trích xuất nhỏ (qua trang, phủ định, điều sửa đổi) (caprica71, Unsiloed-AI) | `extraction_check` đối chiếu PyMuPDF với pdfplumber, cộng fixture 3 tình huống | 2 |
| BGE-M3 có sẵn sparse weights; multi-vector / late interaction mạnh (OP, scott_codie, No-Afternoon-4057) | Bonus #8: arm `m3_sparse` và rescoring ColBERT của BGE-M3 | 12 |
| Câu mô tả bằng ngôn ngữ thường giúp nối từ ngữ đời thường với từ ngữ luật, nhưng chỉ dùng cho retrieval, không đưa vào context; nên làm chunk riêng trỏ về Điều (MemStrata, No-Afternoon-4057) | Stretch 12b, chỉ làm nếu còn thời gian | 12 |
| Lệch ngôn ngữ query/corpus và prefix sai là "silent degraders" (No-Afternoon-4057) | Test: input cho dense không chứa `_` từ pyvi; query và doc đi chung một hàm encode | 5 |

**Cố tình KHÔNG làm trong 8 ngày** (thread khuyên bỏ, hoặc chưa có lỗi nào chứng minh cần): fine-tune GPL, KG trích triple bằng LLM ("practically useless", inanotherclass), router/classifier, agent loop, LLM filter giữa retrieval và answer. Ghi những thứ này vào slide "Hướng phát triển", mỗi mục gắn với một loại lỗi từ failure analysis.

---

## Global Constraints

- Nguồn hỗ trợ: **PDF + URL + plain text** (sprint yêu cầu tối thiểu PDF + URL).
- Mỗi chunk có metadata: `source`, `page`/`section`, `chunk_id`.
- Phải có **2 index**: BM25 (keyword) và vector (embedding).
- Fusion: **RRF**; công thức `score(d) = Σ_arm w_arm / (k + rank_arm(d))`, rank tính từ 1, mặc định `k = 60`.
- Câu trả lời chỉ dựa trên chunk đã retrieve; mỗi câu trả lời có citation (tài liệu, trang, đoạn/Điều).
- Không tìm thấy thông tin → trả về đúng chuỗi `REFUSAL = "Không có trong tài liệu."`
- UI chat (Streamlit): upload PDF/TXT, nhập URL, hỏi đáp trực tiếp trên app.
- Eval: **≥ 10 câu** (mục tiêu 40+, có nhãn loại câu), báo cáo **Recall@5** và **MRR@5**, phân tích case tốt/xấu.
- Deliverables: README cài đặt & chạy lại; slides 5–10 trang.
- Toàn bộ text chuẩn hoá Unicode **NFC** trước mọi xử lý (tiếng Việt dễ bị lẫn NFC/NFD).
- LLM: Gemini, model đọc từ env `LLM_MODEL` (mặc định `gemini-2.5-flash`), `temperature=0`, key ở env `GEMINI_API_KEY`.
- Máy dev: **chỉ CPU** (12 nhân, 15GB RAM): `use_fp16=False`, reranker chỉ chạy trên top-20.

## Review Focus

1. **PDF scan / không có text layer, hoặc lỗi dấu** → không index rác một cách im lặng; trang đó bị đánh cờ và UI cảnh báo. *(test ở Task 2)*
2. **Ingest cùng một tài liệu hai lần** → không nhân đôi chunk; `doc_id` lấy theo hash nội dung. *(test ở Task 4)*
3. **Query nhắc tới Điều không tồn tại ("Điều 999") hoặc Điều của luật khác** → literal arm trả về rỗng, không crash, các arm khác vẫn chạy. *(test ở Task 6)*
4. **Câu ngoài phạm vi nhưng trùng từ khoá** ("Điều 174 luật hình sự Mỹ quy định gì?") → từ chối, không bịa. *(test ở Task 8)*
5. **LLM trả citation sai** (`[7]` khi chỉ có 5 block, hoặc không có citation nào) → citation không hợp lệ bị loại; nếu không còn citation hợp lệ thì trả về REFUSAL. *(test ở Task 8)*

---

## File Structure

```
app/team-4.2/
  pyproject.toml, .env.example, README.md
  src/rag/
    config.py            Settings (đường dẫn, model, k, weights, ngưỡng)
    schema.py            Page, Chunk, Hit, ContextBlock, RetrievalTrace, Citation, Answer
    text_vi.py           nfc, segment, bm25_tokens (word | syllable)
    ingest/loaders.py    load_pdf, load_url, load_text → list[Page]
    ingest/extraction_check.py  compare_extractors → list[PageIssue]
    ingest/chunker.py    chunk_document (legal theo Điều | generic theo đoạn)
    ingest/xref.py       extract_refs (regex viện dẫn Điều/khoản)
    index/store.py       ChunkStore (jsonl, idempotent theo doc_id)
    index/bm25_index.py  BM25Index (rank_bm25, pickle)
    index/embedder.py    Embedder protocol, BGEM3Embedder, HashEmbedder (test)
    index/vector_index.py VectorIndex (Qdrant local)
    retrieve/literal.py  literal_search
    retrieve/fusion.py   weighted_rrf
    retrieve/rerank.py   Reranker protocol, BGEReranker
    retrieve/hybrid.py   RetrieverConfig, HybridRetriever
    retrieve/context.py  build_context (mở rộng Điều đầy đủ + xref)
    generate/llm.py      LLMClient (Gemini, cache SQLite)
    generate/answer.py   PROMPT, REFUSAL, generate_answer, validate_citations
    pipeline.py          RAGPipeline (ingest_path, ingest_url, ask)
  app/team-4.2/ui/streamlit_app.py
  evals/team-4.2/datasets/questions.jsonl, evals/team-4.2/runners/metrics.py, evals/team-4.2/runners/stats.py, evals/team-4.2/runners/configs.py,
  evals/team-4.2/runners/run_eval.py, evals/team-4.2/runners/oracle.py, evals/team-4.2/REPORT.md
  tests/...  (mỗi module một file test_<module>.py), tests/fixtures/make_fixtures.py
  reports/week-01/team-4.2/slides.md, reports/week-01/team-4.2/qa_prep.md
  data/team-4.2/raw/ (tài liệu), data/team-4.2/indexes/ (sinh ra, gitignore), data/team-4.2/cache/
```

## Interfaces dùng chung (`src/rag/schema.py`, Task 0)

```python
@dataclass(frozen=True)
class Page:
    doc_id: str; source: str; page: int | None; text: str   # page=None cho URL/TXT

@dataclass(frozen=True)
class Chunk:
    chunk_id: str          # f"{doc_id}:{article_key or 'p'+str(page_start)}:{i}"
    doc_id: str            # f"{slug(source)[:24]}-{sha1(raw_bytes)[:8]}"
    source: str            # tên file hoặc URL
    text: str              # nguyên văn, dùng cho context/citation
    index_text: str        # header + text; BM25 & embedding dùng trường này
    page_start: int | None; page_end: int | None
    section: str | None    # "Chương XIV > Mục 1"
    article_id: str | None # f"{doc_id}:D{num}"  (num giữ hậu tố chữ, vd "292a")
    article_title: str | None
    refs: tuple[str, ...] = ()   # article_id được viện dẫn (cùng tài liệu)
    part: int = 0                # thứ tự sub-chunk khi Điều bị tách
    @property
    def unit(self) -> str: return self.article_id or f"{self.doc_id}:p{self.page_start}"

@dataclass(frozen=True)
class Hit: chunk_id: str; score: float; rank: int; arm: str   # rank từ 1

@dataclass
class ContextBlock: n: int; chunk: Chunk; text: str; role: str  # role: "retrieved" | "xref"

@dataclass
class RetrievalTrace:
    query: str
    arms: dict[str, list[Hit]]   # "bm25", "dense", "literal", ("m3_sparse")
    fused: list[Hit]             # ≤ 50 (pool để đo Recall@50)
    reranked: list[Hit]          # = fused nếu tắt rerank
    final: list[Chunk]           # top-5, dedupe theo unit → dùng tính metric
    context: list[ContextBlock]  # ≤ 8 block đưa cho LLM
    top_score: float             # điểm reranker cao nhất (hoặc RRF nếu tắt rerank)

@dataclass(frozen=True)
class Citation: n: int; chunk_id: str; source: str; page_start: int | None; article_id: str | None; quote: str

@dataclass
class Answer: text: str; citations: list[Citation]; refused: bool; trace: RetrievalTrace
```

---

## Lịch 8 ngày (khớp timeline sprint)

| Ngày | Task | Song song |
|---|---|---|
| 1 (T4) | 0, 1, 2 | 1 người bắt đầu viết `evals/team-4.2/datasets/questions.jsonl` **ngay từ đầu** (đóng băng trước khi tune) |
| 2 (T5) | 3, 4, 5 | |
| 3 (T6) | 6, 7 | |
| 4 (T7) | 8, 9 | |
| 5 (CN) | nghỉ / hoàn thiện bộ câu hỏi | |
| 6 (T2) | 10, 11 | 1 người làm Task 12 (bonus) |
| 7 (T3) | 12, 13 | |
| 8 (T4) | Dry-run demo theo `reports/week-01/team-4.2/slides.md`, luyện Q&A theo `reports/week-01/team-4.2/qa_prep.md` | |

---

### Task 0: Scaffold, config, schema

**Files:** Create `pyproject.toml`, `.gitignore`, `.env.example`, `src/rag/__init__.py`, `src/rag/config.py`, `src/rag/schema.py`, `tests/test_schema.py`

**Interfaces:**
- Produces: mọi dataclass ở mục "Interfaces dùng chung"; `Settings` (pydantic-settings, prefix rỗng, đọc `.env`) với các trường `data_dir=Path("data/team-4.2")`, `index_dir=Path("data/team-4.2/indexes")`, `cache_dir=Path("data/team-4.2/cache")`, `embed_model="BAAI/bge-m3"`, `rerank_model="BAAI/bge-reranker-v2-m3"`, `llm_model="gemini-2.5-flash"`, `gemini_api_key: str = ""`, `rrf_k=60`, `top_k=5`, `pool_size=50`, `rerank_n=20`, `max_context_blocks=8`, `max_syllables=300`, `refuse_below=0.1`; hàm `get_settings() -> Settings` (lru_cache).

- [ ] **Step 1:** `git init`; tạo venv: `python3 -m venv .venv` (nếu lỗi thì `sudo apt install python3.12-venv`, hoặc cài `uv`). Trong `pyproject.toml` khai báo dependencies: `pymupdf pdfplumber trafilatura pyvi rank-bm25 FlagEmbedding qdrant-client google-genai streamlit pydantic-settings numpy pandas pytest`; package `src/rag` (setuptools, `package-dir = {"" = "src"}`). `.gitignore` gồm `.venv/ data/team-4.2/indexes/ data/team-4.2/cache/ .env *.html *_files/`.
- [ ] **Step 2: Viết test**
```python
def test_chunk_unit_prefers_article_id():
    c = Chunk("d:D174:0","d","a.pdf","t","t",3,3,None,"d:D174","Tội lừa đảo")
    assert c.unit == "d:D174"
def test_chunk_unit_falls_back_to_page():
    c = Chunk("d:p3:0","d","a.pdf","t","t",3,3,None,None,None)
    assert c.unit == "d:p3"
```
- [ ] **Step 3:** `pip install -e app/team-4.2 && pytest tests/test_schema.py -v` → FAIL (chưa có module) → viết `schema.py`, `config.py` → PASS.
- [ ] **Step 4:** Commit `chore: scaffold project, settings and schema`.

### Task 1: Xử lý text tiếng Việt

**Files:** Create `src/rag/text_vi.py`, `tests/test_text_vi.py`

**Interfaces:**
- Produces: `nfc(s: str) -> str`; `segment(s: str) -> str` (pyvi `ViTokenizer.tokenize` trên text **giữ nguyên hoa/thường**, trả về chuỗi có `_` nối từ ghép); `bm25_tokens(s: str, mode: Literal["word","syllable"]="word") -> list[str]` (nfc → nếu mode word thì segment → lower → tách theo khoảng trắng → bỏ token không chứa ký tự `\w`).

- [ ] **Step 1: Viết test**
```python
def test_nfc_merges_decomposed_diacritics():
    assert nfc("tiếng") == "tiếng"
def test_word_tokens_join_compounds():
    toks = bm25_tokens("Tội lừa đảo chiếm đoạt tài sản")
    assert "lừa_đảo" in toks and "tài_sản" in toks
def test_syllable_tokens_do_not_join():
    assert bm25_tokens("tài sản", mode="syllable") == ["tài", "sản"]
def test_punctuation_dropped():
    assert bm25_tokens("Điều 174.", mode="syllable") == ["điều", "174"]
```
- [ ] **Step 2:** Chạy → FAIL; implement; chạy `pytest tests/test_text_vi.py -v` → PASS.
- [ ] **Step 3:** Commit `feat: vietnamese normalization and bm25 tokenization`.

### Task 2: Loaders + kiểm tra trích xuất

**Files:** Create `src/rag/ingest/loaders.py`, `src/rag/ingest/extraction_check.py`, `tests/fixtures/make_fixtures.py`, `tests/test_loaders.py`

**Interfaces:**
- Consumes: `nfc`, `Page`.
- Produces: `make_doc_id(source: str, raw: bytes) -> str`; `load_pdf(path: Path) -> list[Page]` (PyMuPDF `page.get_text("text", sort=True)`, page đánh số từ 1, text đã NFC); `load_url(url: str) -> list[Page]` (trafilatura `fetch_url` + `extract(output_format="markdown", include_tables=True)`, raise `LoadError` khi kết quả rỗng hoặc < 200 ký tự); `load_text(path: Path) -> list[Page]`; `@dataclass PageIssue(page: int, kind: Literal["empty","mismatch","bad_chars"], detail: str)`; `compare_extractors(path: Path, tol: float = 0.05) -> list[PageIssue]` (so số từ giữa PyMuPDF và pdfplumber theo từng trang; `empty` khi < 20 ký tự; `bad_chars` khi có `�` hoặc ký tự điều khiển, dấu hiệu font TCVN3/VNI).

- [ ] **Step 1:** `make_fixtures.py` dùng PyMuPDF `insert_text(..., fontfile="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")` để sinh `tests/fixtures/mini_law.pdf` gồm 3 trang: trang 1 có `Chương I`, `Điều 1.`, `Điều 2.`, và khoản 2 của Điều 2 bị **cắt ngang sang trang 2**; trang 2 có một Điều chứa câu phủ định ("không bị coi là tội phạm") và "theo quy định tại khoản 1 Điều 1"; trang 3 **để trống** (giả lập trang scan). Lưu thêm `mini.txt`.
- [ ] **Step 2: Viết test**
```python
def test_load_pdf_pages_numbered_from_1(): assert [p.page for p in load_pdf(MINI)] == [1,2,3]
def test_load_pdf_keeps_diacritics(): assert "Điều 2." in load_pdf(MINI)[0].text
def test_doc_id_stable_for_same_bytes(): assert make_doc_id("a.pdf", b"x") == make_doc_id("a.pdf", b"x")
def test_flags_pages_without_text():      # Review Focus #1
    assert any(i.page == 3 and i.kind == "empty" for i in compare_extractors(MINI))
def test_load_url_raises_on_empty(monkeypatch):
    monkeypatch.setattr(loaders.trafilatura, "fetch_url", lambda u: "<html></html>")
    with pytest.raises(LoadError): load_url("https://example.com")
```
- [ ] **Step 3:** FAIL → implement → `pytest tests/test_loaders.py -v` → PASS.
- [ ] **Step 4:** Chạy `compare_extractors` trên **từng PDF thật** trong `data/team-4.2/raw/` và dán kết quả vào `evals/team-4.2/REPORT.md` mục "Chất lượng trích xuất". Mở ảnh trang của ít nhất 3 trang (một trang có điều khoản vắt qua trang, một trang có phủ định, một trang có điều sửa đổi 2017) để đối chiếu bằng mắt.
- [ ] **Step 5:** Commit `feat: pdf/url/text loaders with extraction check`.

### Task 3: Chunker theo cấu trúc luật + trích viện dẫn

**Files:** Create `src/rag/ingest/chunker.py`, `src/rag/ingest/xref.py`, `tests/test_chunker.py`, `tests/test_xref.py`

**Interfaces:**
- Consumes: `Page`, `Chunk`, `nfc`.
- Produces: `chunk_document(pages: list[Page], max_syllables: int = 300) -> list[Chunk]`; `extract_refs(text: str, doc_id: str, self_num: str | None) -> tuple[str, ...]`.

Quyết định:
- Nối các trang thành một chuỗi, kèm bảng offset để tính `page_start`/`page_end` cho từng chunk.
- **Chế độ legal** khi có ≥ 3 heading khớp `^\s*Điều\s+(\d+[a-z]?)\.\s*(.*)$` (multiline). Heading `^\s*Chương\s+([IVXLCDM]+)` và `^\s*Mục\s+(\d+)` cập nhật `section`.
- `index_text = f"{article_title_line}\n{section}\n{body}"`. Không đưa ngày hiệu lực hay cơ quan ban hành vào đây.
- Điều dài quá `max_syllables` âm tiết thì tách tại ranh giới khoản `^\s*\d+\.\s`. Nếu một khoản vẫn quá dài thì tách tiếp theo câu. Mọi sub-chunk lặp lại header; `part` = 0, 1, 2… **Không bao giờ cắt bỏ text.**
- **Chế độ generic** (URL, tài liệu không phải luật): gom đoạn văn đến tối đa `max_syllables`, overlap 1 đoạn. `section` lấy heading markdown gần nhất (`#`).
- `extract_refs`: regex `(?:khoản\s+\d+\s+)?Điều\s+(\d+[a-z]?)` nhưng loại trường hợp ngay sau là `(của\s+)?(Bộ luật|Luật|Nghị định)` (viện dẫn sang văn bản khác). Loại tham chiếu tới chính Điều đó, bỏ trùng, giữ thứ tự.

- [ ] **Step 1: Viết test**
```python
def test_one_chunk_per_article(): assert [c.article_id.split(":")[1] for c in chunks(MINI)] == ["D1","D2","D3"]
def test_article_spanning_pages(): d2 = by_article(chunks(MINI),"D2"); assert (d2.page_start, d2.page_end) == (1, 2)
def test_index_text_has_title_and_section(): assert "Chương I" in by_article(chunks(MINI),"D1").index_text
def test_long_article_split_without_loss():
    cs = chunk_document([Page("d","x.pdf",1,LONG_ARTICLE)], max_syllables=50)
    assert len(cs) > 1 and norm_ws("".join(c.text for c in cs)) == norm_ws(LONG_ARTICLE_BODY)
    assert all(c.article_id == "d:D5" for c in cs) and [c.part for c in cs] == list(range(len(cs)))
def test_generic_mode_for_non_legal(): assert all(c.article_id is None for c in chunk_document(NEWS_PAGES))
def test_refs_same_doc_only():
    t = "theo khoản 2 Điều 174 và Điều 466 Bộ luật Dân sự, Điều 175"
    assert extract_refs(t, "d", self_num="175") == ("d:D174",)
```
- [ ] **Step 2:** FAIL → implement → `pytest tests/test_chunker.py tests/test_xref.py -v` → PASS.
- [ ] **Step 3:** Chạy chunker trên tài liệu thật và in ra: số Điều, Điều dài nhất, số Điều bị tách. Kiểm tra số Điều có khớp mục lục không (BLHS 2015 có 426 Điều, cộng các Điều "a" do sửa đổi 2017).
- [ ] **Step 4:** Commit `feat: structure-aware legal chunker with cross-references`.

### Task 4: ChunkStore + BM25 index

**Files:** Create `src/rag/index/store.py`, `src/rag/index/bm25_index.py`, `tests/test_store_bm25.py`

**Interfaces:**
- Consumes: `Chunk`, `bm25_tokens`.
- Produces: `ChunkStore(path: Path)` với `add(chunks) -> int` (trả về số chunk mới; **bỏ qua nếu `doc_id` đã có**), `remove_doc(doc_id)`, `get(chunk_id) -> Chunk`, `all() -> list[Chunk]`, `by_article(article_id) -> list[Chunk]` (sắp theo `part`), `docs() -> list[tuple[doc_id, source, n_chunks]]`; lưu `chunks.jsonl`. `BM25Index(mode: Literal["word","syllable"])` với `build(chunks)`, `search(query, k) -> list[Hit]` (arm=`"bm25"` hoặc `"bm25_syl"`, chỉ trả về hit có score > 0), `save(path)`, `load(path)`; dùng `rank_bm25.BM25Okapi(k1=1.5, b=0.75)` trên `index_text`.

- [ ] **Step 1: Viết test**
```python
def test_add_same_document_twice_is_idempotent(tmp_path):   # Review Focus #2
    s = ChunkStore(tmp_path); assert s.add(CHUNKS) == len(CHUNKS); assert s.add(CHUNKS) == 0
def test_store_roundtrip(tmp_path): ChunkStore(tmp_path).add(CHUNKS); assert ChunkStore(tmp_path).get(CHUNKS[0].chunk_id) == CHUNKS[0]
def test_bm25_word_mode_ranks_exact_term_first():
    idx = BM25Index("word"); idx.build(CHUNKS_LAW)
    assert idx.search("lừa đảo chiếm đoạt tài sản", 5)[0].chunk_id == CHUNK_D174.chunk_id
def test_bm25_no_zero_score_hits():
    idx = BM25Index("word"); idx.build(CHUNKS_LAW); assert idx.search("xyzxyz", 5) == []
```
- [ ] **Step 2:** FAIL → implement → PASS.
- [ ] **Step 3:** Commit `feat: chunk store and bm25 index (word + syllable)`.

### Task 5: Embedder + Vector index (Qdrant local)

**Files:** Create `src/rag/index/embedder.py`, `src/rag/index/vector_index.py`, `tests/test_vector_index.py`

**Interfaces:**
- Produces: `class Embedder(Protocol): dim: int; def encode(self, texts: list[str]) -> np.ndarray` (đã L2-normalize; **query và doc đi chung một hàm**, BGE-M3 không cần prefix); `BGEM3Embedder(model_name, batch_size=8)` dùng `FlagEmbedding.BGEM3FlagModel(use_fp16=False)`, `encode(...)["dense_vecs"]`, `max_length=1024`; `HashEmbedder(dim=64)` cho test (bag-of-syllables băm, tất định). `VectorIndex(path: Path, embedder: Embedder, collection="chunks")` với `add(chunks)` (point id `uuid5(NAMESPACE_URL, chunk_id)`, payload `chunk_id/doc_id/article_id/source`), `search(query, k) -> list[Hit]` (arm `"dense"`), `remove_doc(doc_id)`.
- Lưu ý cho Task 9: Qdrant local mode chỉ cho **một client trên một path**. Trong Streamlit phải tạo bằng `st.cache_resource`.

- [ ] **Step 1: Viết test**
```python
def test_dense_input_is_raw_text(monkeypatch, tmp_path):     # silent degrader: không đưa text đã tách từ cho embedder
    seen = []; emb = HashEmbedder(); monkeypatch.setattr(emb, "encode", lambda t: seen.extend(t) or np.zeros((len(t),64)))
    VectorIndex(tmp_path, emb).add(CHUNKS_LAW); assert not any("_" in t for t in seen)
def test_vector_search_returns_ranked_hits(tmp_path):
    vi = VectorIndex(tmp_path, HashEmbedder()); vi.add(CHUNKS_LAW)
    hits = vi.search("tội lừa đảo chiếm đoạt tài sản", 3); assert [h.rank for h in hits] == [1,2,3]
def test_remove_doc(tmp_path): vi = VectorIndex(tmp_path, HashEmbedder()); vi.add(CHUNKS_LAW); vi.remove_doc("d"); assert vi.search("tài sản", 3) == []
```
- [ ] **Step 2:** FAIL → implement → PASS.
- [ ] **Step 3:** Đo thời gian encode toàn bộ corpus thật bằng `BGEM3Embedder` trên CPU và ghi vào README (ước tính vài phút cho khoảng 2k chunk).
- [ ] **Step 4:** Commit `feat: bge-m3 embedder and qdrant vector index`.

### Task 6: Literal arm + weighted RRF + HybridRetriever

**Files:** Create `src/rag/retrieve/literal.py`, `src/rag/retrieve/fusion.py`, `src/rag/retrieve/hybrid.py`, `tests/test_fusion.py`, `tests/test_hybrid.py`

**Interfaces:**
- Consumes: `ChunkStore`, `BM25Index`, `VectorIndex`, `Hit`, `RetrievalTrace`.
- Produces:
  - `literal_search(query: str, store: ChunkStore, k: int) -> list[Hit]`: regex `(?i)(?:điều|đ\.|art\.?)\s*(\d+[a-z]?)` → các chunk có Điều số đó (mọi tài liệu, `part` 0 trước), arm `"literal"`, score 1.0.
  - `weighted_rrf(arms: dict[str, list[Hit]], weights: dict[str, float], k: int = 60, limit: int = 50) -> list[Hit]`: arm `"fused"`; khi hoà điểm thì xếp theo `chunk_id` cho tất định.
  - `@dataclass RetrieverConfig(name: str, bm25_mode: Literal["word","syllable"] | None = "word", dense: bool = True, literal: bool = True, m3_sparse: bool = False, colbert: bool = False, rerank: bool = True, rrf_k: int = 60, weights: dict[str,float] = {"bm25":1.0,"bm25_syl":1.0,"dense":1.0,"literal":2.0,"m3_sparse":1.0,"colbert":1.0})` (dùng `field(default_factory=...)`).
  - `HybridRetriever(store, bm25: dict[str, BM25Index], vector: VectorIndex | None, reranker: Reranker | None, cfg: RetrieverConfig, settings: Settings)` với `retrieve(query: str) -> RetrievalTrace`. Mỗi arm lấy `pool_size` → fuse → (rerank ở Task 7) → `final` = top `top_k` sau khi dedupe theo `chunk.unit`.

- [ ] **Step 1: Viết test**
```python
def test_rrf_formula():
    f = weighted_rrf({"a":[H("x",1),H("y",2)], "b":[H("y",1)]}, {"a":1,"b":1}, k=60)
    assert f[0].chunk_id == "y" and f[0].score == pytest.approx(1/62 + 1/61)
def test_rrf_weight_changes_order():
    f = weighted_rrf({"a":[H("x",1)], "b":[H("y",1)]}, {"a":1,"b":3}, k=60); assert f[0].chunk_id == "y"
def test_literal_hits_article_number(): assert unit(literal_search("Điều 174 quy định gì", store, 5)[0]).endswith("D174")
def test_literal_unknown_article_is_empty(): assert literal_search("Điều 999 nói gì", store, 5) == []   # Review Focus #3
def test_hybrid_trace_has_all_arms(): t = retriever.retrieve("lừa đảo"); assert set(t.arms) == {"bm25","dense","literal"}
def test_final_is_deduped_by_unit(): units = [c.unit for c in retriever.retrieve("tài sản").final]; assert len(units) == len(set(units)) <= 5
```
- [ ] **Step 2:** FAIL → implement → PASS (test dùng `HashEmbedder`, `rerank=False`).
- [ ] **Step 3:** Commit `feat: literal arm, weighted rrf and hybrid retriever`.

### Task 7: Reranker + build context (mở rộng Điều + viện dẫn)

**Files:** Create `src/rag/retrieve/rerank.py`, `src/rag/retrieve/context.py`; Modify `src/rag/retrieve/hybrid.py`; Test `tests/test_rerank_context.py`

**Interfaces:**
- Produces: `class Reranker(Protocol): def score(self, query: str, texts: list[str]) -> list[float]` (trong [0,1]); `BGEReranker(model_name)` dùng `FlagReranker(use_fp16=False).compute_score(pairs, normalize=True, max_length=512)`; `build_context(final: list[Chunk], store: ChunkStore, max_blocks: int = 8) -> list[ContextBlock]`.
- Rerank: chấm `rerank_n` (20) chunk đầu của `fused` trên `index_text`, sắp lại, `top_score` = điểm cao nhất.
- `build_context`: mỗi chunk trong `final` tạo một block `role="retrieved"`. Nếu chunk là một phần của Điều bị tách và cả Điều ≤ 2×`max_syllables` thì dùng toàn văn Điều. Sau đó, với `refs` của 3 chunk đầu, thêm block `role="xref"` cho Điều được viện dẫn mà chưa có trong context, đến khi đủ `max_blocks`. Block xref **không tính** vào `final` và metric.

- [ ] **Step 1: Viết test**
```python
def test_rerank_reorders():  # FakeReranker cho điểm cao nhất với chunk Điều 175
    assert retriever.retrieve("q").final[0].article_id.endswith("D175")
def test_rerank_off_keeps_fused_order(): t = retriever_no_rerank.retrieve("q"); assert [h.chunk_id for h in t.reranked] == [h.chunk_id for h in t.fused]
def test_context_adds_xref_block():
    ctx = build_context([chunk_D2_refs_D1], store); assert [b.role for b in ctx] == ["retrieved","xref"] and ctx[1].chunk.article_id.endswith("D1")
def test_context_caps_blocks(): assert len(build_context(many_chunks_with_refs, store, max_blocks=8)) == 8
def test_xref_not_in_final(): t = retriever.retrieve("q"); assert all(b.chunk in t.final for b in t.context if b.role=="retrieved")
```
- [ ] **Step 2:** FAIL → implement → PASS.
- [ ] **Step 3:** Commit `feat: cross-encoder rerank and context expansion`.

### Task 8: Generation có citation + guardrail

**Files:** Create `src/rag/generate/llm.py`, `src/rag/generate/answer.py`, `tests/test_answer.py`

**Interfaces:**
- Produces: `LLMClient(model: str, api_key: str, cache_path: Path)` với `complete(prompt: str) -> str` (`google.genai.Client().models.generate_content(..., config=GenerateContentConfig(temperature=0))`, cache SQLite theo key `sha256(model + prompt)`); `REFUSAL = "Không có trong tài liệu."`; `format_context(blocks) -> str`; `validate_citations(text: str, blocks: list[ContextBlock]) -> tuple[str, list[Citation]]`; `generate_answer(query: str, trace: RetrievalTrace, llm, refuse_below: float) -> Answer`.

Quyết định:
- Guardrail 1, trước LLM: `trace.top_score < refuse_below` hoặc `context` rỗng → `Answer(REFUSAL, [], refused=True)` và **không gọi LLM**.
- Prompt (tiếng Việt). Mỗi block có dạng `[n] (nguồn: {source}, trang {page_start}, Điều {num} – {title})\n{text}`. Block xref ghi thêm "(điều được viện dẫn)". Quy tắc trong prompt, giữ nguyên câu chữ: *"Chỉ trả lời dựa trên các đoạn được cung cấp. Sau mỗi ý phải ghi số đoạn nguồn dạng [n]. Nếu các đoạn không chứa thông tin để trả lời, chỉ viết đúng: Không có trong tài liệu."*
- Guardrail 2, sau LLM: tìm các `\[(\d+)\]`, loại số ngoài khoảng `1..len(blocks)` (xoá khỏi text). Nếu câu trả lời không phải REFUSAL mà **không còn citation hợp lệ nào** thì trả về REFUSAL. `Citation.quote` = 200 ký tự đầu của block.

- [ ] **Step 1: Viết test** (dùng `FakeLLM(returns=...)`)
```python
def test_low_score_refuses_without_llm():          # Review Focus #4
    llm = FakeLLM(returns="bịa"); a = generate_answer("Điều 174 luật hình sự Mỹ?", trace(top_score=0.02), llm, 0.1)
    assert a.refused and a.text == REFUSAL and llm.calls == 0
def test_out_of_range_citation_removed():          # Review Focus #5
    a = generate_answer("q", trace_with_blocks(5), FakeLLM("Ý A [1]. Ý B [7]."), 0.1)
    assert [c.n for c in a.citations] == [1] and "[7]" not in a.text
def test_no_valid_citation_becomes_refusal():
    assert generate_answer("q", trace_with_blocks(5), FakeLLM("Câu trả lời không trích dẫn."), 0.1).refused
def test_llm_refusal_passthrough():
    a = generate_answer("q", trace_with_blocks(5), FakeLLM("Không có trong tài liệu."), 0.1); assert a.refused and a.citations == []
def test_citation_carries_source_page_article():
    c = generate_answer("q", trace_with_blocks(5), FakeLLM("A [2]."), 0.1).citations[0]
    assert (c.source, c.page_start, c.article_id) == ("a.pdf", 12, "d:D174")
def test_llm_cache_hit(tmp_path, monkeypatch): ...  # gọi complete 2 lần với cùng prompt → API chỉ được gọi 1 lần
```
- [ ] **Step 2:** FAIL → implement → PASS.
- [ ] **Step 3:** Smoke test với key thật: `python -c "from rag.pipeline import ...; print(p.ask('Tội lừa đảo chiếm đoạt tài sản bị phạt thế nào?'))"` (sau Task 9). Câu trả lời phải có `[n]`.
- [ ] **Step 4:** Commit `feat: grounded generation with citation validation and refusal guardrails`.

### Task 9: RAGPipeline + Streamlit app

**Files:** Create `src/rag/pipeline.py`, `app/team-4.2/ui/streamlit_app.py`, `tests/test_pipeline.py`

**Interfaces:**
- Produces: `RAGPipeline.from_settings(settings, cfg: RetrieverConfig, embedder: Embedder | None = None, reranker: Reranker | None = None, llm=None)`; `ingest_path(path: Path) -> IngestReport` (load theo đuôi `.pdf`/`.txt`/`.md` → `compare_extractors` nếu là PDF → chunk → store.add → nếu có chunk mới thì **build lại BM25 cả 2 mode** và thêm vào vector); `ingest_url(url) -> IngestReport`; `remove_doc(doc_id)`; `ask(query) -> Answer`; `@dataclass IngestReport(doc_id, source, n_chunks, n_new, issues: list[PageIssue], skipped: bool)`.
- UI:
  - Sidebar: `file_uploader(type=["pdf","txt","md"], accept_multiple_files=True)` lưu vào `data/team-4.2/raw/`; ô URL + nút "Thêm"; bảng tài liệu đã ingest kèm nút xoá; hiển thị `issues` dạng `st.warning`.
  - Khung chat (`st.chat_message`): câu trả lời có citation hiển thị `[n] source — Điều X, tr. Y`, mỗi citation có một `st.expander` chứa trích đoạn.
  - Expander "🔍 Retrieval trace": một bảng cho mỗi arm trong `trace.arms` cộng **Fused** và **Reranked** (top-5 kèm score), dùng để chứng minh khi demo rằng cả ba thành phần đều chạy.
  - Pipeline tạo bằng `st.cache_resource`.

- [ ] **Step 1: Viết test** (fake embedder, reranker, LLM)
```python
def test_ingest_then_ask_end_to_end(tmp_path):
    p = make_pipeline(tmp_path); r = p.ingest_path(MINI); assert r.n_new > 0 and not r.skipped
    a = p.ask("Điều 1 quy định gì?"); assert a.citations and a.trace.arms["bm25"]
def test_reingest_skipped(tmp_path): p.ingest_path(MINI); assert p.ingest_path(MINI).skipped
def test_remove_doc_removes_from_all_indexes(tmp_path): ...  # sau remove, ask không còn hit nào từ doc đó
```
- [ ] **Step 2:** FAIL → implement → PASS.
- [ ] **Step 3:** `streamlit run app/team-4.2/ui/streamlit_app.py`: upload một PDF luật thật, thêm một URL, hỏi 3 câu (một câu có số Điều, một câu diễn đạt đời thường, một câu ngoài phạm vi). Chụp màn hình để dùng cho slide.
- [ ] **Step 4:** Commit `feat: rag pipeline and streamlit chat app`.

### Task 10: Bộ câu hỏi, metrics, ablation, paired test

**Files:** Create `evals/team-4.2/datasets/questions.jsonl`, `evals/team-4.2/runners/metrics.py`, `evals/team-4.2/runners/stats.py`, `evals/team-4.2/runners/configs.py`, `evals/team-4.2/runners/run_eval.py`, `tests/test_eval.py`

**Interfaces:**
- Câu hỏi (JSONL): `{"id":"q01","question":"...","type":"lookup|article_number|lay_paraphrase|multi_article|out_of_scope","split":"dev|test","gold":[{"source":"blhs_2015.pdf","article":"175"}]}`. Gold theo **tên file + số Điều** (không theo `doc_id` vì hash có thể đổi); tài liệu không phải luật dùng `{"source":..., "page": n}`.
- Produces: `gold_units(q, store) -> set[str]`; `recall_at_k(ranked_units: list[str], gold: set[str], k=5) -> float`; `mrr_at_k(ranked_units, gold, k=5) -> float`; `paired_bootstrap(a: list[float], b: list[float], n=10_000, seed=0) -> tuple[float, float, float]` (mean diff b−a, CI 2.5%, CI 97.5%); `win_loss_tie(a, b) -> tuple[int,int,int]`; `CONFIGS: list[RetrieverConfig]`.
- Ablation (mỗi bước chỉ thêm đúng một thứ):

| Config | Thay đổi |
|---|---|
| B0 | BM25 theo âm tiết |
| B1 | BM25 tách từ (pyvi) |
| B2 | chỉ Dense (BGE-M3) |
| B3 | B1 + B2, RRF k=60 (**baseline sprint**) |
| B4 | B3 + literal arm |
| B5 | B4 + reranker |
| B6 | B5 + m3_sparse + colbert (Task 12) |

- CLI: `python evals/team-4.2/runners/run_eval.py --split test --configs B0,B1,B2,B3,B4,B5 --out evals/team-4.2/results/`. Xuất `per_question.csv` (id, type, config, recall@5, mrr@5, recall@50, top5_units) và `summary.md` gồm: bảng config × (Recall@5, MRR@5, Recall@50) cho toàn bộ và theo từng `type`; bảng so sánh cặp bước liền kề (B_i so với B_{i−1}) có Δ, CI 95%, W/L/T. Câu `out_of_scope` không tính Recall/MRR; tính **tỉ lệ từ chối đúng** qua `pipeline.ask` cho cả câu OOS lẫn câu trong phạm vi.

- [ ] **Step 1: Viết test**
```python
def test_recall_mrr_values():
    r = ["a","b","c","d","e"]; assert recall_at_k(r, {"c","z"}) == 0.5 and mrr_at_k(r, {"c","z"}) == pytest.approx(1/3)
def test_miss_is_zero(): assert recall_at_k(["a"], {"f"}) == 0 and mrr_at_k(["a"], {"f"}) == 0
def test_cutoff_respected(): assert mrr_at_k(["a","b","c","d","e","g"], {"g"}) == 0
def test_bootstrap_identical_is_zero(): assert paired_bootstrap([.5,1,0],[.5,1,0]) == (0.0, 0.0, 0.0)
def test_bootstrap_clear_gain_positive(): assert paired_bootstrap([0]*20,[1]*20)[1] > 0
def test_questions_file_valid():
    qs = load_questions("evals/team-4.2/datasets/questions.jsonl"); assert len(qs) >= 10 and all(q["gold"] or q["type"]=="out_of_scope" for q in qs)
```
- [ ] **Step 2:** FAIL → implement → PASS.
- [ ] **Step 3: Bộ câu hỏi.** Người viết là con người, không dùng LLM sinh. Mục tiêu ≥ 40 câu, mỗi `type` ≥ 6 câu, có ≥ 6 câu OOS (trong đó ≥ 2 câu trùng từ khoá như Review Focus #4). Nên có thêm các cặp "dễ nhầm" (175 ↔ 174, 353 ↔ 175). Khoảng 1/3 vào `dev`, còn lại `test`. **Commit file này trước khi chạy bất kỳ tuning nào và không sửa nữa** (thread: đóng băng trước, tránh tự chấm cho mình).
- [ ] **Step 4: Tune trên dev.** Thử `rrf_k` ∈ {10, 30, 60} và trọng số literal ∈ {1, 2}; chọn `refuse_below` trên dev sao cho tách được câu OOS khỏi câu trong phạm vi (ghi lại cả hai tỉ lệ). Ghi giá trị đã chọn vào `config.py`.
- [ ] **Step 5:** Chạy B0–B5 trên `test` và commit `evals/team-4.2/results/` cùng `feat: evaluation harness with ablation and paired bootstrap`.

### Task 11: Failure analysis + oracle test (bonus #9)

**Files:** Create `evals/team-4.2/runners/oracle.py`; Write `evals/team-4.2/REPORT.md`

**Interfaces:**
- Consumes: `RAGPipeline`, `LLMClient`, `gold_units`, `per_question.csv`.
- Produces: `python evals/team-4.2/runners/oracle.py --split test` → `evals/team-4.2/results/oracle.csv` (id, oracle_correct, pipeline_correct, gold_in_top5, bucket). Oracle: context = toàn văn các Điều gold → `generate_answer` với `top_score=1`. Judge: Gemini với prompt chấm riêng (temp 0) → `{"correct": bool, "reason": str}`. **Kiểm tra judge bằng tay trên 10 câu** và ghi tỉ lệ đồng ý vào báo cáo.
- Bucket: `ok` (cả hai đúng) · `retrieval_miss` (oracle đúng, pipeline sai, gold không nằm trong top-5) · `ranking` (gold có trong top-5 nhưng xếp sau Điều dễ nhầm) · `reader_fail` (oracle sai) · `false_refusal` / `hallucination` (với OOS).

- [ ] **Step 1:** Implement `oracle.py` (logic bucket là hàm thuần `bucket(row) -> str`, có test trong `tests/test_eval.py`: `assert bucket(dict(oracle_correct=True, pipeline_correct=False, gold_in_top5=False)) == "retrieval_miss"`).
- [ ] **Step 2:** Chạy → PASS test → chạy oracle trên test.
- [ ] **Step 3:** Viết `evals/team-4.2/REPORT.md`: (1) setup và corpus, (2) bảng ablation kèm Δ/CI, (3) bảng theo `type`, (4) bucket counts, (5) **5–8 case phân tích cụ thể**: tốt ở đâu (câu có số Điều nhờ literal arm), xấu ở đâu (lệch từ ngữ đời thường và từ ngữ luật, Điều dễ nhầm), kèm *tại sao*, (6) chất lượng trích xuất (Task 2), (7) hạn chế (ít câu hỏi, gold tự viết, judge là LLM), (8) "bước tiếp theo", mỗi bước gắn với một bucket lỗi.
- [ ] **Step 4:** Commit `docs: evaluation report with failure analysis`.

### Task 12: Advanced method (bonus #8): BGE-M3 sparse + ColBERT

**Files:** Modify `src/rag/index/embedder.py`, `src/rag/retrieve/hybrid.py`; Create `src/rag/index/m3_multi.py`, `tests/test_m3_multi.py`

**Interfaces:**
- Produces: `M3MultiIndex(path)` với `build(chunks, model)` (một lần `encode(return_dense=False, return_sparse=True, return_colbert_vecs=True)`; lưu sparse dạng `dict[token_id, weight]` trong pickle, ColBERT vecs float16 trong `.npz` theo `chunk_id`), `sparse_search(query, k) -> list[Hit]` (arm `"m3_sparse"`, quét hết corpus bằng tích vô hướng sparse), `colbert_rescore(query, chunk_ids) -> list[Hit]` (MaxSim **chỉ trên pool fused top-50**, arm `"colbert"`, rồi đưa vào RRF như một arm).
- Kích hoạt khi `cfg.m3_sparse` / `cfg.colbert`; chạy ablation B6 so với B5 bằng paired test.

- [ ] **Step 1: Viết test**
```python
def test_maxsim_prefers_token_overlap(): assert maxsim(q=[[1,0]], d1=[[1,0],[0,1]], d2=[[0,1]]) == (1.0, 0.0)
def test_sparse_score_dot(): assert sparse_dot({1:.5, 2:.5}, {2:1.0}) == .5
def test_hybrid_includes_m3_arms_when_enabled(): assert {"m3_sparse","colbert"} <= set(retriever_b6.retrieve("q").arms)
```
- [ ] **Step 2:** FAIL → implement → PASS → chạy B6 và cập nhật REPORT.
- [ ] **Step 3 (stretch, chỉ làm khi B5 còn bucket "lệch từ ngữ" lớn):** Mô tả ngôn ngữ thường cho mỗi Điều. Dùng Gemini sinh 1–2 câu, cache lại; index thành **chunk riêng** `kind="desc"` trỏ về `article_id`; hit được map về Điều gốc; **không bao giờ** đưa vào context. Đánh giá B7 so với B5 bằng paired test.
- [ ] **Step 4:** Commit `feat: bge-m3 sparse and colbert late-interaction arms`.

### Task 13: README, slides, chuẩn bị Q&A

**Files:** Create `README.md`, `reports/week-01/team-4.2/slides.md`, `reports/week-01/team-4.2/qa_prep.md`, `.env.example`

- [ ] **Step 1: README.** Gồm: yêu cầu hệ thống (CPU OK, thời gian tải model ~2.3GB BGE-M3 + ~2.2GB reranker); `python3 -m venv .venv && . .venv/bin/activate && pip install -e app/team-4.2`; `cp .env.example .env` (điền `GEMINI_API_KEY`); `streamlit run app/team-4.2/ui/streamlit_app.py`; `python evals/team-4.2/runners/run_eval.py ...`; `python evals/team-4.2/runners/oracle.py ...`; `pytest`; sơ đồ kiến trúc; bảng kết quả rút từ REPORT.
- [ ] **Step 2: Slides (8 trang)** trong `reports/week-01/team-4.2/slides.md`: (1) bài toán và corpus, (2) kiến trúc pipeline, (3) ingestion: chunk theo Điều + kiểm tra trích xuất, (4) hybrid: BM25 tách từ + dense + literal + RRF + reranker, (5) citation và guardrail, (6) bảng ablation B0→B6 có CI, (7) failure analysis và oracle, (8) trả lời câu hỏi "baseline quá cơ bản?": đổi mới dựa trên bằng chứng, kèm những gì cố tình không làm và lý do.
- [ ] **Step 3: `reports/week-01/team-4.2/qa_prep.md`.** Mỗi câu Q&A của sprint có 3–5 dòng trả lời **gắn với số liệu của chính dự án**: BM25 vs TF-IDF (saturation k1, length norm b, và vì sao tách từ tiếng Việt quan trọng: B0 so với B1); embedding và vì sao cần (B2, các câu lay_paraphrase); RRF (công thức, k, vì sao fuse theo rank); bi-encoder vs cross-encoder (B4 so với B5, độ trễ trên CPU); chunk size (theo Điều, cap 300 âm tiết, hậu quả nếu cắt sai); ngoài phạm vi (2 tầng guardrail, tỉ lệ từ chối đúng); Recall@5 (số liệu và giải thích); tăng 100x (Qdrant server/HNSW, BM25 → Elasticsearch/OpenSearch với analyzer tiếng Việt, encode theo batch trên GPU, cache); so với RAGFlow (deepdoc parsing, template chunking, GraphRAG, có gì và thiếu gì); thêm một mục phản biện quan điểm "BM25 không hợp với luật" từ thread (bag-of-words bỏ qua thứ tự → bù bằng dense/ColBERT + reranker; BM25 vẫn mạnh với thuật ngữ hiếm và số Điều).
- [ ] **Step 4:** Chạy lại toàn bộ trên máy sạch theo README (`pytest` pass, app chạy, eval ra số khớp REPORT). Commit `docs: readme, slides and q&a prep`.
