# Hỏi đáp trên đồ thị hợp đồng ở trang /contracts (thiết kế ngắn)

**Vì sao:** sau Kiểm tra concept / Soát luật, trang demo chưa có chỗ hỏi tiếp. Người dùng muốn hỏi đáp lấy **đồ thị hợp
đồng làm nguồn chính**, dùng agent đã có (`GraphAgent`, gồm Text2Cypher có rào chắn), không dùng `review.answer`.

**Mục tiêu**
- Khung "Hỏi về hợp đồng" cuối bước ③, mở sau khi đã chạy Kiểm tra concept (agent cần ConceptInstance trên đồ thị).
- Stream từng bước agent (công cụ, ý định, tóm tắt kết quả, câu Cypher nằm trong `args`), rồi câu trả lời cuối.
- Câu trả lời hiện: lời đáp + mức tin cậy, đường đi trên đồ thị (nhãn + trích lời văn), căn cứ luật (trích dẫn + lời văn
  từ đồ thị luật), các bước đã đi (gập), cảnh báo.
- Câu hỏi nối tiếp: gửi tối đa 3 lượt trước.

**Không làm:** không đụng "Hỏi với hợp đồng" ở trang chat; không đưa kết quả Soát luật vào ngữ cảnh; không soát lại mỗi
câu hỏi (khác `ask_contract_graph`).

**Cách làm (đã chọn):** mở đồ thị đã dựng (`contract_view`, Neo4j nếu có, không thì bộ nhớ) → `make_tools` →
`GraphAgent.ask(question, history, on_step)`. Endpoint `POST /api/contracts/{cid}/ask/stream`, SSE như concept-check.
Phương án bỏ: gọi `ask_contract_graph` (soát lại ~57 s mỗi câu); dùng `/api/chat` với `contract_id` (không dùng đồ thị).

**Quyết định của người làm**
- Chưa chạy Kiểm tra concept = đồ thị không có ConceptInstance → lỗi 409 "Hãy chạy Kiểm tra concept trước khi hỏi".
- Ngày soát = ngày ký, không có thì `catalog.law_values_valid_from` (như `check_contract`).
- Dữ kiện người dùng ở bước ② gửi kèm để `check_concept` của agent dùng.
