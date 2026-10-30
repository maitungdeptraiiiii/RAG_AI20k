# Chương trình 5 tuần full-time

Khóa học có **Team 4.1 và Team 4.2, mỗi team 5 thành viên**, làm việc full-time. Mỗi team phát triển một sản phẩm và nộp kết quả riêng, dùng chung chương trình và tiêu chí.

## Learning outcomes

Mỗi thành viên giải thích và vận hành được toàn bộ pipeline: ingestion → tổ chức dữ liệu → retrieval → generation → evaluation → Agent và human review. Nhóm chứng minh quyết định kỹ thuật bằng thí nghiệm, biết phân biệt lỗi dữ liệu, retrieval và generation.

## Nguyên tắc phạm vi

- Một repository chung, mỗi team một sản phẩm xuyên suốt trong thư mục riêng; chọn lĩnh vực sơ bộ cuối tuần 1, xác nhận ở tuần 4.
- Khảo sát rộng nhưng chỉ triển khai sâu phần có giá trị đối với dữ liệu đã chọn.
- Tuần 1 là RAG baseline; chat có retrieval chưa tự động trở thành Agent.
- Một Agent có công cụ và điều kiện dừng là đủ. Multi-agent không bắt buộc.
- Failure analysis bắt buộc mỗi tuần; không đặt yêu cầu không thể kiểm chứng như “không bao giờ hallucinate”.
- Dữ liệu gốc, nội dung mô hình sinh và nội dung đã được duyệt phải phân biệt được.
- Dùng dữ liệu công khai phù hợp hoặc dữ liệu giả lập; không commit bí mật hay thông tin cá nhân thực.

## Acceptance milestones

| Tuần | Câu hỏi trọng tâm | Mốc |
|---|---|---|
| 1 | Có trả lời từ tài liệu và chỉ ra bằng chứng được không? | Upload → ingest → hybrid retrieve → answer + citation |
| 2 | Dữ liệu đầu vào đáng tin và có cấu trúc không? | Ba nhóm dữ liệu, quality checks, version và provenance |
| 3 | Retrieval nào phù hợp với từng câu hỏi? | Baseline, phương pháp chuyên sâu, ablation và trade-off |
| 4 | Agent cải thiện tác vụ chuyên ngành nào? | Tools, trace, giới hạn, hỏi lại và human review |
| 5 | Cập nhật và tạo nội dung có kiểm soát được không? | Regression gate, approval, audit và rollback |

Bộ câu hỏi tích lũy: tuần 1 ≥10/bộ tài liệu; tuần 3 ≥40 tổng cộng; tuần 4 ≥50, có phần giữ lại chưa dùng tuning; tuần 5 dùng lại để kiểm tra regression và bổ sung tình huống cập nhật.

## Nhịp học đề xuất

Mỗi ngày: khoảng 1 giờ đọc/thảo luận, 4–5 giờ thực hành, 1 giờ review và cập nhật tài liệu. Điều chỉnh theo tiến độ; ngày 5 dành thời gian đóng gói và trình bày. Mentor hỗ trợ tháo gỡ vướng mắc giữa tuần và nghiệm thu cuối tuần.
