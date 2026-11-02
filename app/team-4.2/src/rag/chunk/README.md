# Module Chunking & Parsing (TV1) — Team 4.2 Sprint 1

Module chịu trách nhiệm Ingestion trong kiến trúc RAG của Team 4.2:
1. **Parsing:** Đọc tài liệu (PDF, URL, Plain Text) $\rightarrow$ `list[Page]`.
2. **Chunking:** Nhận `list[Page]` $\rightarrow$ sinh danh sách `list[Chunk]` chuẩn hoá theo `rag.schema`.

---

## 1. Hợp đồng dữ liệu (Data Contract)

Tuân thủ nghiêm ngặt theo `rag.schema`:

### `Page`
```python
@dataclass(frozen=True)
class Page:
    doc_id: str          # hash nội dung (make_doc_id), ổn định khi ingest lại
    source: str          # tên tệp hoặc URL
    page: int | None     # 1-indexed đối với PDF; None đối với URL/TXT
    text: str            # Chuẩn hoá Unicode NFC
```

### `Chunk`
```python
@dataclass(frozen=True)
class Chunk:
    chunk_id: str             # Định dạng: f"{doc_id}:{index:04d}" (make_chunk_id)
    doc_id: str               # Khớp với doc_id của Page
    source: str               # Tên tệp hoặc URL
    page_start: int | None    # Trang bắt đầu (None với URL/TXT)
    page_end: int | None      # Trang kết thúc (page_start == page_end nếu nằm gọn 1 trang)
    section: str | None       # Tiêu đề mục / Điều / Chương gần nhất
    text: str                 # Văn bản chunk (chuẩn hoá NFC)
```

---

## 2. Các tính năng chính

- **Bảo toàn ranh giới câu (Sentence Integrity):** Không cắt ngang câu giữa chừng trừ khi một câu vượt quá `size`.
- **Nối câu vắt qua trang (Cross-page Stitching):** Khi câu ở cuối trang $N$ chưa có dấu kết thúc (`.`, `!`, `?`, `:`) và đầu trang $N+1$ không phải tiêu đề mới, parser/chunker tự động ghép nối và gán `page_start=N, page_end=N+1`.
- **Nhận diện Heading/Section:** Tự động bắt tiêu đề Điều, Chương, Mục (`Điều 1`, `Chương I`, v.v.) và gắn vào `section`.
- **Lọc nhiễu:** Tự động loại bỏ số trang đơn độc ở đầu trang (header) hoặc chân trang (footer).
- **Fallback linh hoạt:**
  - PDF: Ưu tiên PyMuPDF (`fitz`), tự động fallback sang `pypdf`.
  - Web: Ưu tiên `trafilatura`, tự động fallback sang `BeautifulSoup`.

---

## 3. Cách sử dụng

```python
from rag.chunk import load_pdf, load_url, load_text, chunk_document

# 1. Parse PDF thành list[Page]
pages = load_pdf("data/luat_dien_luc.pdf")

# 2. Chunking thành list[Chunk]
chunks = chunk_document(pages, size=1200, overlap=200)

for chunk in chunks:
    print(chunk.chunk_id, chunk.page_start, chunk.page_end, chunk.section)
```

---

## 4. Chạy kiểm thử & Demo

```bash
# Chạy demo tích hợp
python -m rag.chunk.demo

# Chạy demo với tệp PDF cục bộ
python -m rag.chunk.demo "D:/tailieu.pdf"

# Chạy unit tests
pytest tests/test_chunk.py -p no:cacheprovider
```
