# Data and provenance

## Team workspace

- [Team 4.1](team-4.1/README.md)
- [Team 4.2](team-4.2/README.md)

Hướng dẫn dưới đây áp dụng riêng cho mỗi team; đường dẫn dữ liệu và output nằm trong thư mục team tương ứng.


Commit manifest, schema, fixture giả lập nhỏ; không commit tài liệu riêng tư, PII thực, file lớn hoặc vector index.

Dùng `raw/`, `processed/`, `indexes/` cho dữ liệu local (đã gitignore). Manifest cần URL/nguồn, điều kiện sử dụng, checksum, snapshot, loại dữ liệu, ngày thu thập/xuất bản/hiệu lực và version. Không điền ngày hiệu lực bằng ngày crawl khi nguồn không cung cấp.

Giữ bản gốc để đối chiếu; mapping chunk → nguồn phải reproducible. Nội dung mô hình sinh có provenance riêng. Dùng dữ liệu PII giả lập để thử masking.
