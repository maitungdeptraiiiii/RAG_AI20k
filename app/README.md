# Ứng dụng xuyên suốt khóa học

## Không gian theo team

- [Team 4.1](team-4.1/README.md)
- [Team 4.2](team-4.2/README.md)

Hướng dẫn dưới đây áp dụng riêng cho mỗi team; đường dẫn dữ liệu và output nằm trong thư mục team tương ứng.


Chưa triển khai. Nhóm chọn stack ở tuần 1 và bổ sung các mục sau trước nghiệm thu:

- Runtime/version và cài dependency bằng lockfile.
- Biến môi trường trong `.env.example` (chỉ placeholder).
- Lệnh chạy dịch vụ, ingestion, app và evaluation.
- Dataset mẫu, cách truy cập UI và một câu hỏi demo.
- Troubleshooting, giới hạn và sơ đồ kiến trúc.

Gợi ý module, không bắt buộc framework: `ingestion/`, `retrieval/`, `generation/`, `agents/`, `review/`, `ui/`, `tests/`. Tách parser/indexer/retriever bằng interface rõ ràng. Test các hành vi quan trọng như dedup, version, nguồn citation và approval gate.

Có thể dùng Elasticsearch/Qdrant/Milvus, LLM sẵn có, LangChain/LlamaIndex hoặc code thuần, Streamlit/Gradio hoặc web app. Chọn một stack vừa đủ; ghi phiên bản và lý do trong ADR, không triển khai tất cả.
