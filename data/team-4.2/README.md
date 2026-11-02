# data — Team 4.2

[Trang team](../../teams/team-4.2/README.md) · [Quy chuẩn chung](../README.md)

Chỉ commit manifest, schema và fixture nhỏ không nhạy cảm. Dữ liệu local (đã gitignore):

| Thư mục | Nội dung |
|---|---|
| `raw/` | Tài liệu gốc (PDF/URL/TXT) đã tải |
| `processed/` | Pages/chunks sau parse |
| `indexes/` | `bm25.json`, `vector/` (Qdrant local + `meta.json`) |
| `cache/` | SQLite cache embedding/LLM/rerank |

## Manifest

Chưa có. Mỗi tài liệu cần: nguồn/URL, điều kiện sử dụng, checksum, snapshot, loại dữ liệu, ngày thu thập/ban hành/hiệu lực, version.
