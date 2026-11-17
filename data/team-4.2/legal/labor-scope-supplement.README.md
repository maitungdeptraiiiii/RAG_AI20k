# Phần tải bổ sung 26 tài liệu HĐLĐ

Đã tải 26/26 tài liệu trong `labor-scope-fetch-queue.json`, không còn lỗi tải.
23 tài liệu lấy từ API công khai VBPL; 3 tài liệu dùng PDF từ Công báo/Cổng Chính
phủ/BHXH khi API thiếu nội dung. Có 4 PDF trong gói, gồm cả phụ lục của NĐ 399/2026.

- `labor-scope-supplement-26.tar.gz`: gói bổ sung độc lập, 87 file.
- `labor-scope-supplement-26.manifest.json`: checksum từng file và checksum archive.
- `labor-scope-download-report.json`: receipt từng văn bản, metadata, nguồn, đường
  dẫn text/HTML/JSON/PDF, checksum và trạng thái review/import.

Các file local nằm dưới `app/team-4.2/data/team-4.2/legal/raw/` và
`app/team-4.2/data/team-4.2/legal/supplements/labor-scope-v1-26/`.
Gói bổ sung không chứa CURRENT/catalog và không thay thế corpus-bundle.tar.gz cũ.
Chưa nhập 26 nguồn vào snapshot, chưa dựng graph mới. Text PDF có cờ needs_review;
phụ lục chưa được rà nội dung/độ chính xác bảng. Không coi tải thành công là duyệt pháp lý.

Chạy lại tại gốc repo:

```powershell
python scripts/team-4.2/fetch_labor_scope.py
python scripts/team-4.2/fetch_labor_scope.py --pack-only
```

Crawler đối chiếu loại/số hiệu, lưu nguồn bất biến theo checksum và tái sử dụng
receipt hợp lệ; không gọi LLM. Phần fallback dùng PyMuPDF để trích text tự động,
giữ PDF nguồn nguyên trạng và kiểm số hiệu qua tập PDF/metadata chính thức.

Claude được khai báo trong `.env` cục bộ ở gốc repo và mẫu
`app/team-4.2/.env.example`:

```dotenv
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-haiku-5-5
ANTHROPIC_BASE_URL=https://api.anthropic.com
```

Điền key chỉ trong `.env` cục bộ. Đây là cấu hình cho tích hợp extraction tiếp theo;
chưa bổ sung Claude client hoặc đổi provider của pipeline hỏi đáp hiện có.
Model ID đối chiếu tại [tài liệu Anthropic](https://platform.claude.com/docs/en/models/haiku-5-5/migration-guide).
