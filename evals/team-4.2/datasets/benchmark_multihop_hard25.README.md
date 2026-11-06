# Multi-hop hard25

25 tình huống mới, văn phong đời thường, toàn bộ `type=multi`. Mỗi câu cần liên kết 3–5 Điều thuộc ít nhất hai bộ luật trong corpus sáu bộ luật của project. Đây là tập thử thách do tác giả rà soát theo snapshot repo, chưa có vòng duyệt độc lập của chuyên gia pháp lý.

- Dataset: [benchmark_multihop_hard25.jsonl](benchmark_multihop_hard25.jsonl).
- Kết quả xác nhận và phân tích: [REPORT.md](../results/multihop-hard25-current-20261106-verified/REPORT.md).
- Bộ 64 câu cũ `benchmark_doi_thuong.jsonl` giữ nguyên. Không lấy câu cũ để đổi tên, con số hoặc diễn đạt lại; chỉ tham khảo văn phong và so sánh loại trừ nội dung.

Các trường `id`, `question`, `type`, `author`, `gold`, `reference` tương thích trực tiếp `rag.schema.Question.from_dict` và `rag.eval.metrics.load_questions`. Gold dùng `source` + đường dẫn `section` lấy nguyên văn từ corpus, không dùng chunk ID làm tiêu chuẩn chấm chính. Các trường bổ sung được loader hiện tại bỏ qua:

| Trường | Mục đích |
|---|---|
| `topic` | Bài toán pháp lý riêng của tình huống |
| `gold_articles` | Danh sách Điều dễ đọc |
| `gold_chunk_ids` | Toàn bộ chunk khớp các gold, để đối chiếu snapshot |
| `reasoning_steps` | Mắt xích cần thiết, gắn với chỉ số gold bắt đầu từ 0 |
| `evidence` | Tên nguồn, section, chunk ID và nội dung corpus làm căn cứ |
| `corpus_scope` | Giới hạn đánh giá theo dữ liệu repo |

Các câu đòi suy luận từ sự kiện sang điều kiện/ngoại lệ, hậu quả và cách thực hiện quyền. Chỉ thêm căn cứ thủ tục khi câu hỏi thực sự hỏi về thủ tục hoặc chứng minh. `reference` là đáp án mẫu điều kiện, không dùng để sinh câu trả lời hoặc truy xuất khi benchmark. Chỉ chuỗi `question` được truyền cho retriever.

Kiểm tra chất lượng gồm: loader/schema, ID duy nhất, mọi gold khớp corpus, evidence đúng nội dung, mọi chunk ID liên quan được xác nhận, không trùng nguyên văn, không trùng toàn bộ bộ gold với 64 câu cũ, sàng lọc Jaccard và rà soát tình huống gần về lĩnh vực. Điểm tương đồng từ vựng thấp không tự chứng minh độc lập ngữ nghĩa; đánh giá nội dung vẫn cần người rà soát.

Phạm vi: đánh giá truy xuất trong snapshot luật của repo; không khẳng định đây là các văn bản pháp luật hiện hành tại thời điểm sử dụng. Các quy định nền tảng có thể xuất hiện ở nhiều câu vì phục vụ các chuỗi suy luận khác nhau.

Tạo lại từ nội dung đã soạn trong `evals/team-4.2/runners/build_multihop_hard25.py`; builder chỉ ghi file mới này, không ghi bộ cũ. Runner `run_multihop_hard25.py` giữ các bước LLM hỗ trợ retrieval theo `.env`, chỉ cấm generation trả lời cuối. Xem báo cáo để lấy lệnh chạy và config đầy đủ.
