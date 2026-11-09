# Chặn mảnh sửa Khoản/Điểm thay toàn bộ Điều

Code: [amendment_guard.py](../src/rag/versioning/amendment_guard.py).

## Tình huống được chặn

Điều 5 cũ:

```text
Điều 5. Phí dịch vụ
1. Khách hàng cá nhân trả 100.000 đồng/tháng.
2. Khách hàng doanh nghiệp trả 200.000 đồng/tháng.
3. Thanh toán trước ngày 10 hằng tháng.
```

Nguồn mới chỉ ghi:

```text
Sửa đổi khoản 2 Điều 5 như sau:
“2. Khách hàng doanh nghiệp trả 250.000 đồng/tháng.”
```

Nguồn này không đủ để làm toàn văn Điều 5 mới. Planner trả `action="review"`, có lý do `amendment.fragment`, không tạo applicability changes. Caller đã gắn `complete=True` cũng không bỏ qua chốt.

Một trường hợp khác cũng bị chặn:

```text
Điều 5. Phí dịch vụ
2. Khách hàng doanh nghiệp trả 250.000 đồng/tháng.
```

Dù có heading đúng, khi so với revision đích cũ, Khoản 1 và 3 đã thiếu. Planner trả `amendment.missing_clauses`. Tương tự, bỏ mất Điểm b trong một Khoản trả `amendment.missing_points`; nhãn Điểm được xét theo từng Khoản để Điểm b ở Khoản khác không che mất khác biệt.

## Chốt kiểm tra nằm ở đâu?

1. `FullVersionResolver`: kiểm tra dấu hiệu mảnh sửa đổi trước khi đi tiếp trong luồng toàn tài liệu.
2. `ArticleVersionResolver`: kiểm tra chỉ dẫn sửa Khoản/Điểm, heading Điều đúng assignment và các Khoản/Điểm bị thiếu so với revision đang bị thay.
3. `VersionRepository`: kiểm tra lại nội dung và phạm vi ngay trong transaction trước khi ghi. Một plan `create` được lập từ text khác hoặc bị caller sửa không thể bỏ qua chốt.
4. `SQLiteReviewService`: khi reviewer xác nhận, vẫn replan qua cùng resolver. Chỉ sửa metadata hoặc bật `complete=True` không làm mảnh sửa đổi trở thành toàn văn; review giữ `open` và báo `ReviewBlockedError`.

Kiểm tra sử dụng text nguồn đã normalize NFC/casefold; ghép theo thứ tự block để nhận ra câu lệnh bị tách qua block hoặc dòng. Nội dung trong bảng cũng được kiểm tra. Lý do trả về là chuỗi cố định, không sao chép text nguồn có thể chứa PII vào message.

## Xử lý sau khi bị chặn

```text
Input fragment
    → review, giữ nguyên catalog/timeline
    → người xử lý yêu cầu bổ sung hoặc hợp nhất có kiểm chứng
    → tạo processing/input mới có toàn văn Điều sau sửa và provenance
    → chạy lại validation/version planning
    → commit khi đủ điều kiện
```

Ví dụ toàn văn sau sửa có thể đi tiếp:

```text
Điều 5. Phí dịch vụ
1. Khách hàng cá nhân trả 100.000 đồng/tháng.
2. Khách hàng doanh nghiệp trả 250.000 đồng/tháng.
3. Thanh toán trước ngày 10 hằng tháng.
```

Hệ thống không tự tạo nội dung hợp nhất bằng LLM. Reviewer có thể chọn `request_correction` để đóng hồ sơ cũ với yêu cầu sửa; input mới phải có ID/fingerprint phản ánh nội dung mới, không ghi đè extraction cũ.

## Giới hạn cần hiểu rõ

- Đây là chốt heuristic bảo thủ, không phải bộ phân tích mọi hình thức sửa đổi pháp luật. Không tìm thấy dấu hiệu không chứng minh toàn văn đầy đủ, đặc biệt khi OCR sai/mất chữ.
- Một văn bản đầy đủ có trích dẫn chỉ dẫn sửa Khoản/Điểm hoặc thực sự giảm số Khoản/Điểm cũng có thể bị chuyển review. Không tự cho qua chỉ vì caller xác nhận complete; cần xử lý hợp nhất/phạm vi sửa phù hợp trước khi cập nhật.
- Phân tích thiếu Khoản/Điểm dựa trên nhãn số/chữ ở đầu dòng. Nếu parser làm mất cấu trúc này, khả năng phát hiện sẽ giảm.
- Chốt không tự bãi bỏ, thêm mới hay quản lý hiệu lực đến cấp Khoản/Điểm. Nó ngăn thao tác thay cả Điều khi có dấu hiệu input không đủ.
- Dữ liệu đã được duyệt trước khi có chốt không bị sửa ngược tự động.
- Giữ nguyên timeline không chứng minh Điều cũ vẫn đúng cho câu hỏi hiện hành khi đã có sửa đổi chưa xử lý. Huy cần nối trạng thái pending review với retrieval/answer để cảnh báo hoặc chặn câu trả lời bị ảnh hưởng. Phần tích hợp này chưa có trong thay đổi hiện tại.

## Chạy kiểm thử

Tại `app/team-4.2`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_amendment_guard.py -q
```

Các tình huống gồm sửa Khoản, sửa/bãi bỏ Điểm, bổ sung Khoản, thay cụm từ có số tiền, câu lệnh qua nhiều dòng/block, fragment trong bảng, heading giả đủ nhưng thiếu Khoản/Điểm, plan bị thay text, review cố bật complete và trường hợp toàn văn Điều hợp lệ.
