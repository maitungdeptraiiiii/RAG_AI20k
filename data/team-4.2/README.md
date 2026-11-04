# data — Team 4.2

[Trang team](../../teams/team-4.2/README.md) · [Quy chuẩn chung](../README.md)

Chỉ commit manifest, schema và fixture nhỏ không nhạy cảm. Ngoại lệ: snapshot corpus 6 Bộ luật bên dưới được
commit (force-add) để clone về dùng ngay. Dữ liệu local (đã gitignore):

| Thư mục | Nội dung |
|---|---|
| `raw/` | Tài liệu gốc (PDF/URL/TXT) đã tải |
| `processed/` | Pages/chunks sau parse |
| `indexes/` | `index_config.json`, `vector/` (Qdrant local + `meta.json`); BM25 dựng lại từ `chunks.jsonl` khi chạy |
| `cache/` | SQLite cache embedding/LLM/rerank |

## Manifest

Văn bản crawl bằng `scripts/team-4.2/crawl_vbpl.py` nằm ở `raw/vbpl/`, có `manifest.json` (vbpl_id → số hiệu,
loại, cơ quan, ngày ban hành/hiệu lực, tình trạng hiệu lực, nguồn, sha256, ngày crawl) và `<tên>.meta.json` cho từng
văn bản. 6 Bộ luật trong snapshot chưa có manifest (crawl lại bằng số hiệu nếu cần). Mỗi tài liệu cần: nguồn/URL, điều kiện sử dụng, checksum, snapshot, loại dữ liệu, ngày thu thập/ban hành/hiệu lực, version.

## Snapshot đã commit: 6 Bộ luật

| File | Nội dung |
|---|---|
| `raw/bo_luat_*.txt` | Phần "NỘI DUNG VĂN BẢN" của 6 Bộ luật crawl từ vbpl.vn: Hình sự 100/2015/QH13, Tố tụng hình sự 101/2015/QH13, Lao động 45/2019/QH14, Dân sự 91/2015/QH13, Tố tụng dân sự 92/2015/QH13, Hàng hải 95/2015/QH13 |
| `processed/chunks.jsonl` | 3.422 chunk (`MAX_SYLLABLES=300`) |
| `indexes/` | Qdrant local, `text-embedding-3-small` 1536 chiều |

Clone về, điền `OPENAI_API_KEY` vào `app/team-4.2/.env` là chạy được `ask.py`, UI và eval (query vẫn cần
gọi OpenAI để embed câu hỏi). Không cần ingest lại. Đổi `EMBED_MODEL` cũng không cần ingest lại: vector index của model mới nằm ở
`indexes/vector/<model>/` và được tự build từ `chunks.jsonl` ở lần chạy đầu. Đổi `MAX_SYLLABLES` thì phải
ingest lại vào `DATA_DIR` khác. `cache/` không commit (tự tạo khi chạy).

