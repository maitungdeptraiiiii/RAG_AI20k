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

- Mỗi team làm trong `app/team-4.x/`, `data/team-4.x/`, `evals/team-4.x/`, `experiments/team-4.x/` và `scripts/team-4.x/`. Đề cương và quy chuẩn dùng chung.
- `main`: phiên bản tích hợp chạy được; không dùng nhánh tuần để giữ các codebase tách biệt.
- Nhánh task ngắn: `feat/team-4.1/w02-table-parser`, `fix/team-4.2/w03-version-filter`.
- PR nhỏ, có reviewer, mô tả cách kiểm tra và liên kết task.
- Không commit API key, `.env`, tài liệu riêng tư, vector index, model weights hoặc log nhạy cảm.
- Sau nghiệm thu, tạo annotated tag `team-4.1/week-01-demo` ... `team-4.1/week-05-demo` (tương tự cho `team-4.2`) và ghi commit/tag trong báo cáo. Không ghi đè tag nghiệm thu; nếu cần sửa dùng hậu tố `-v2`.

Ví dụ sau khi thay đổi đã được review và commit:

```bash
git tag -a team-4.1/week-01-demo -m "Team 4.1 Week 1 accepted demo"
```

Chỉ push khi đã cấu hình remote phù hợp. GitHub/GitLab không bắt buộc; các tracker Markdown vẫn dùng được khi làm local.

## Definition of Done

- Đáp ứng acceptance criteria; có cách chạy lại và bằng chứng kiểm tra.
- Cập nhật README/config nếu hành vi thay đổi.
- Có reviewer; không để dữ liệu bí mật trong diff hay log.
- Nếu ảnh hưởng chất lượng, có evaluation và phân tích trade-off.
- Task và tracker đã cập nhật; tồn đọng được ghi thành việc tiếp theo.

## Progress tracking

`docs/PROGRESS.md` chỉ ghi trạng thái và liên kết tổng quan. Tracker tuần là nguồn tiến độ chi tiết mặc định. Nếu dùng GitHub Issues, ghi issue URL vào tracker và cập nhật trạng thái từ issue trước mỗi demo; nội dung kỹ thuật dài nằm trong PR/báo cáo, không sao chép ở mọi nơi.
