# Hiệu lực: phạm vi hỗ trợ và chốt chuyển review

Code: [effectivity_guard.py](../src/rag/versioning/effectivity_guard.py).

Luồng hiện tại dùng một `effective_from` đã xác nhận cho các unit trong một yêu cầu thay đổi. `ApplicabilityRecord` lưu hiệu lực từng revision, nhưng planner chưa xử lý nhiều ngày/điều kiện khác nhau trong cùng input. Chốt này ngăn metadata một ngày che mất dấu hiệu phức tạp trong nguồn.

## Những trường hợp bị chặn

| Nguồn giả lập | Lý do review |
|---|---|
| Điều 1, 2 hiệu lực 01/07/2026; Điều 3 hiệu lực 01/01/2027 | `effectivity.multiple_dates` |
| Hiệu lực 01/07/2026; riêng Điều 3 từ 01/01/2027 | `effectivity.unit_exception` |
| Có hiệu lực sau 45 ngày kể từ ngày ký | `effectivity.relative_date` |
| Có hiệu lực kể từ ngày ký | `effectivity.relative_date` |
| Hồ sơ nộp trước một mốc tiếp tục áp dụng quy định cũ | `effectivity.transition` |
| Điều 5 bị đình chỉ thi hành trong một khoảng thời gian | `effectivity.suspension` |
| Có hiệu lực khi văn bản hướng dẫn được ban hành | `effectivity.conditional` |
| Nguồn ghi hiệu lực 01/01/2027 nhưng caller điền 01/07/2026 | `effectivity.date_mismatch` |
| Nguồn ghi ngày hiệu lực không hợp lệ, ví dụ 31/02/2026 | `effectivity.invalid_date` |

Các lý do là mã/chuỗi cố định, không sao chép text nguồn có thể chứa PII. Nhiều lý do có thể xuất hiện cùng lúc.

## Những trường hợp vẫn hỗ trợ

```text
Điều mới thay Điều cũ từ ngày 01/07/2026.
Caller cung cấp effective_from = 2026-07-01.
Không có dấu hiệu thời gian/điều kiện chưa hỗ trợ.
```

- Một ngày rõ ràng, nhất quán với metadata; định dạng nhận biết gồm `01/07/2026`, `2026-07-01`, `ngày 01 tháng 07 năm 2026`.
- Nhiều Điều cùng nhắc lại một ngày không bị coi là nhiều ngày khác nhau.
- Ngày ký trước phần hiệu lực hoặc hạn thanh toán/nộp hồ sơ đơn thuần không tự trở thành ngày hiệu lực.
- Nếu caller chưa cung cấp ngày, code không tự điền từ ngày upload hoặc tự tính; planner vẫn trả review do thiếu ngày.

## Luồng chạy

```text
ParseResult + ChangeRequest
    → amendment guard (mảnh sửa Khoản/Điểm)
    → effectivity guard (dấu hiệu hiệu lực chưa hỗ trợ)
    → đủ điều kiện mới lập kế hoạch versioning
    → repository kiểm tra hiệu lực lần nữa trước khi ghi
```

Nếu chốt phát hiện vấn đề:

1. Planner trả `action="review"` kèm lý do, không tạo applicability changes.
2. Caller lưu hồ sơ bằng review queue để người xử lý thấy rõ vấn đề.
3. Nội dung và timeline catalog hiện có không bị thay đổi.
4. Khi reviewer xác nhận, service đọc nguồn đã lưu và replan; chỉ điền ngày hoặc đổi metadata không tự vượt qua chốt. Nếu vẫn có vấn đề, báo `ReviewBlockedError`, hồ sơ giữ open và không lưu quyết định thành công.
5. Repository cũng từ chối nếu caller sửa một plan create hoặc thay extraction để bỏ qua planner; lỗi rollback toàn bộ transaction.

## Cần làm gì khi bị review?

- Đọc nguồn, xác định rõ các Điều/phạm vi/thời gian/đối tượng bị tác động.
- Ngày tương đối cần quy tắc tính đã kiểm chứng và chứng cứ ngày làm mốc; không đoán từ ngày upload.
- Nhiều mốc cần contract/planner nhận ngày theo từng unit và kiểm tra nhất quán với toàn bộ nguồn.
- Chuyển tiếp cần mô hình điều kiện áp dụng, ví dụ ngày nộp hồ sơ; chỉ ngày hỏi chưa đủ.
- Đình chỉ cần thao tác thời gian riêng, không ép thành thay thế hoặc xóa vĩnh viễn.

Các cơ chế giải quyết trên chưa được bổ sung trong thay đổi này. Không xóa câu điều kiện khỏi nguồn hoặc giả lập một extraction khác để vượt chốt. Hồ sơ có thể chuyển `request_correction`/xử lý thủ công trong lúc chờ mô hình và policy phù hợp, nhưng không tự coi dữ liệu pending là hiện hành.

## Giới hạn

- Đây là heuristic nhận diện một số cách diễn đạt thường gặp, không phải bộ phân tích đầy đủ quy định hiệu lực. OCR mất chữ, câu diễn đạt khác, ngày nằm ngoài vùng nhận diện hoặc nguồn thiếu thông tin có thể không bị phát hiện.
- Một số câu trích dẫn/nhắc tới quy định chuyển tiếp hoặc đình chỉ cũng có thể bị chuyển review. Chốt ưu tiên không tự cập nhật khi chưa rõ ngữ nghĩa.
- Không thay đổi schema/bảng SQLite hoặc tự điều chỉnh dữ liệu đã duyệt trước đó.
- Không tự làm phép tính ngày, hợp nhất nhiều ngày, xử lý điều kiện chuyển tiếp hay lập lịch đình chỉ/phục hồi.
- Giữ timeline cũ không chứng minh bản cũ còn áp dụng cho mọi câu hỏi. Huy cần nối các review đang mở với retrieval/answer để cảnh báo hoặc chặn câu hỏi bị ảnh hưởng; phần đó chưa có trong thay đổi này.

## Kiểm thử

Tại `app/team-4.2`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_effectivity_guard.py -q
```

Tests bao gồm các loại điều kiện trên, ngày đơn giản vẫn commit, nhiều lần nhắc cùng ngày, ngày không liên quan, Unicode, bảng, câu qua nhiều block, review không vượt chốt, plan bị sửa và catalog không đổi khi bị từ chối.
