# RAG Parsing & Chunking Module

Thư mục này chứa toàn bộ mã nguồn xử lý độc lập cho giai đoạn **Document Parsing** và **Chunking** trong hệ thống RAG:

---

## 1. Cấu trúc thư mục

```text
chunk/
├── __init__.py      # Re-export các hàm và class chính
├── models.py        # Định nghĩa TextUnit (hỗ trợ single-page & multi-page span) và ParseError
├── pdf_parser.py    # Xử lý PDF với lọc số trang rác & nối câu xuyên trang (cross-page stitching)
├── web_parser.py    # Xử lý bóc tách HTML/Web theo đề mục h1-h6 (dùng BeautifulSoup)
├── chunker.py       # Thuật toán Recursive Sentence-Aware Chunking với semantic overlap
├── demo.py          # Script chạy thử nghiệm độc lập (in trực quan các chunks)
└── README.md        # Tài liệu hướng dẫn
```

---

## 2. Phương pháp Chunking: Recursive Sentence-Aware với Cross-Page Stitching

### A. Vấn đề của cách chunk theo trang cũ:
- Câu văn vắt qua 2 trang bị cắt đứt đôi giữa chừng.
- Dính rác số trang hoặc header/footer độc lập (ví dụ số `2` đơn độc ở đầu trang).
- Cắt cứng theo số ký tự làm câu văn bị chém ngang từ (như `và L` -> `bổ sung...`).

### B. Giải pháp cải tiến mới:
1. **Lọc rác số trang & Header/Footer ([`pdf_parser.py`](pdf_parser.py)):**
   * Tự động phát hiện và loại bỏ các dòng số trang độc lập ở đầu/cuối mỗi trang.
2. **Nối câu xuyên trang (Cross-page Stitching):**
   * Nếu dòng cuối trang $N$ chưa kết thúc câu (không có dấu chấm, chấm than, hỏi, hai chấm) và đầu trang $N+1$ là văn bản tiếp diễn, hệ thống tự động nối liền mạch.
   * Gán nhãn `pages=(3, 4)` để biết chính xác đoạn văn vắt qua những trang nào.
3. **Cắt phân cấp theo ranh giới câu ([`chunker.py`](chunker.py)):**
   * Gom các câu hoàn chỉnh (`.`, `!`, `?`, `;`, `\n`) cho đến khi đạt `size` mong muốn.
   * **Tuyệt đối không cắt ngang một câu** (trừ phi câu đó dài hơn toàn bộ kích thước chunk).
   * Overlap lấy trọn vẹn câu trước đó để giữ ngữ cảnh liền mạch cho câu tiếp theo.

---

## 3. Cách chạy thử nghiệm độc lập

Không cần khởi động backend FastAPI hay frontend React:

```bash
# 1. Chạy với dữ liệu mẫu HTML có sẵn:
python demo.py

# 2. Chạy với tệp PDF của riêng bạn:
python demo.py "D:\duong_dan_file.pdf"
```

---

## 4. Cách import và sử dụng trong code Python

```python
from chunk import parse_pdf, parse_web, make_chunks

# Với PDF:
units = parse_pdf(pdf_bytes)

# Với HTML:
title, units = parse_web(html_bytes)

# Cắt chunks:
chunks = make_chunks(
    document_id="doc_001",
    units=units,
    size=800,       # Kích thước chunk mục tiêu
    overlap=150     # Kích thước overlap giữa các câu
)

for chunk in chunks:
    print(chunk["chunk_id"], chunk["pages"], chunk["text"][:60])
```
