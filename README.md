# Agentic RAG — khóa học thực hành 5 tuần

Khóa học full-time cho **2 team, mỗi team 5 thành viên mới tốt nghiệp: Team 4.1 và Team 4.2**, xây dựng mỗi team một sản phẩm xuyên suốt từ RAG baseline đến Agent có kiểm soát và quy trình cập nhật dữ liệu, phát triển nội dung.

**Thời lượng:** 5 tuần × 5 ngày. **Điều kiện đầu vào:** Python, Git và API cơ bản. Chưa chốt framework; nhóm chọn stack vừa sức và ghi lại lý do.

## Hai team

- [Team 4.1](teams/team-4.1/README.md) — thành viên, sản phẩm và tracker.
- [Team 4.2](teams/team-4.2/README.md) — thành viên, sản phẩm và tracker.

Dùng chung chương trình; mỗi team có code, dữ liệu, evaluation và bài nộp riêng trong thư mục `team-4.1/` hoặc `team-4.2/`.

## Bắt đầu

1. Đọc [chương trình](docs/CURRICULUM.md), [cách làm việc](docs/WORKING-AGREEMENTS.md) và [quy chuẩn đánh giá](docs/EVALUATION.md).
2. Điền tên, vai trò và trạng thái trong [bảng tiến độ](docs/PROGRESS.md).
3. Mở kế hoạch tuần tương ứng và chia checklist thành task/issue có người phụ trách.
4. Xây sản phẩm trong `app/`; giữ bộ đánh giá và phiên bản dữ liệu để so sánh qua các tuần.
5. Cuối tuần cập nhật tracker, nộp báo cáo, demo và đánh dấu mốc Git sau khi nghiệm thu.

## Lộ trình

| Tuần | Chủ đề | Đầu ra chính | Theo dõi |
|---|---|---|---|
| [1](weeks/week-01/README.md) | RAG foundation | App, hybrid search, citations, baseline | [Tracker](weeks/week-01/TRACKER.md) |
| [2](weeks/week-02/README.md) | Ingestion và chất lượng dữ liệu | Parsing, metadata, validation, version | [Tracker](weeks/week-02/TRACKER.md) |
| [3](weeks/week-03/README.md) | Retrieval engineering | Một phương pháp chuyên sâu và ablation | [Tracker](weeks/week-03/TRACKER.md) |
| [4](weeks/week-04/README.md) | Domain Agentic RAG | Sản phẩm chuyên ngành, tool và giới hạn | [Tracker](weeks/week-04/TRACKER.md) |
| [5](weeks/week-05/README.md) | Cập nhật và sáng tạo có giám sát | Monitoring, approval, audit và rollback | [Tracker](weeks/week-05/TRACKER.md) |

## Cấu trúc repository

```text
agentic-rag/
├── README.md                 # Điểm vào chung
├── docs/                     # Chương trình, tiến độ, rubric, quy chuẩn
├── teams/team-4.1..4.2/      # Danh sách thành viên và liên kết mỗi team
├── weeks/week-01..05/         # Yêu cầu tuần + tracker + liên kết bài nộp
├── app/                      # team-4.1/ và team-4.2/: codebase riêng
├── data/                     # Manifest và dữ liệu mẫu không nhạy cảm
├── evals/                    # Dataset, nhãn, cấu hình và mã đánh giá
├── experiments/              # Cấu hình, nhật ký và kết quả thí nghiệm
├── reports/week-01..05/      # Báo cáo, slides, demo và kết quả từng tuần
├── templates/                # Mẫu báo cáo, task, experiment, ADR
├── scripts/                  # Lệnh tái lập ingest, chạy app và evaluation
└── .github/                  # Issue và pull request templates
```

**Code tách theo team, không chia theo tuần.** Dùng thư mục tuần cho kế hoạch và bằng chứng; dùng commit/tag để xác định phiên bản code. Không tạo năm bản sao của ứng dụng.

## Các tài liệu chung

- [Tiến độ toàn khóa](docs/PROGRESS.md)
- [Lịch, phân vai và Git workflow](docs/WORKING-AGREEMENTS.md)
- [Evaluation](docs/EVALUATION.md)
- [Rubric và buổi demo 45 phút](docs/ASSESSMENT.md)
- [Tài liệu tham khảo](docs/REFERENCES.md)

## Trạng thái ban đầu

Repository hiện cung cấp đề cương và mẫu quản lý công việc; **chưa có ứng dụng hay kết quả thực nghiệm**. Các metric để trống cho đến khi nhóm chạy đánh giá. Nhóm bổ sung hướng dẫn cài đặt và chạy trong [app/README.md](app/README.md) ở tuần 1.
