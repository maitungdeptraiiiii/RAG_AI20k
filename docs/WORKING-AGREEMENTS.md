# Working agreements

## Role rotation

Điền tên tại [Team 4.1](../teams/team-4.1/README.md) và [Team 4.2](../teams/team-4.2/README.md). Bảng dưới áp dụng độc lập cho từng team. A–E là ký hiệu chỗ trống trong mỗi team, không phải 5 người dùng chung cho cả khóa.

| Tuần | Ingestion | Retrieval | Generation/Agent | Evaluation | UI/tích hợp |
|---|---|---|---|---|---|
| 1 | A | B | C | D | E |
| 2 | E | A | B | C | D |
| 3 | D | E | A | B | C |
| 4 | C | D | E | A | B |
| 5 | B | C | D | E | A |

Mỗi task có một owner và một reviewer khác người. Vai trò là trách nhiệm tích hợp, không phải độc quyền kiến thức. Cả nhóm gán nhãn và kiểm tra chéo evaluation; mỗi người phải hiểu toàn pipeline.

## Working cadence

- Đầu tuần: chốt phạm vi, acceptance criteria, owner và reviewer.
- Hằng ngày: cập nhật tracker về việc hoàn thành, bằng chứng, blocker và bước tiếp theo.
- Giữa tuần: demo phiên bản chạy được, kiểm tra rủi ro tích hợp.
- Cuối tuần: nộp báo cáo, trình bày 45 phút, quiz cá nhân và retrospective.

## Git workflow

Áp dụng [Git workflow and review policy](GIT-WORKFLOW.md): branch riêng cho từng task, PR vào `main`, reviewer theo ownership matrix và Squash and merge. Tài liệu này quy định command walkthrough, conflict resolution, remote protection, weekly tags và rollback.

Mỗi team chỉ định integration owner và backup mỗi tuần. Team PR cần reviewer khác author; shared/cross-team PR cần các approval bổ sung theo matrix. Remote settings chỉ có hiệu lực sau khi maintainer cấu hình, không tự được bật bởi tài liệu.

## Definition of Done

- Đáp ứng acceptance criteria; có cách chạy lại và bằng chứng kiểm tra.
- Cập nhật README/config nếu hành vi thay đổi.
- Có reviewer; không để dữ liệu bí mật trong diff hay log.
- Nếu ảnh hưởng chất lượng, có evaluation và phân tích trade-off.
- Task và tracker đã cập nhật; tồn đọng được ghi thành việc tiếp theo.

## Progress tracking

`docs/PROGRESS.md` chỉ ghi trạng thái và liên kết tổng quan. Tracker tuần là nguồn tiến độ chi tiết mặc định. Nếu dùng GitHub Issues, ghi issue URL vào tracker và cập nhật trạng thái từ issue trước mỗi demo; nội dung kỹ thuật dài nằm trong PR/báo cáo, không sao chép ở mọi nơi.
