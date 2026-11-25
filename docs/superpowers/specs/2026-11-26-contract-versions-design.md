# Bổ sung văn bản vào hợp đồng đã phân tích, có phiên bản và đối chiếu

Ngày: 26/11/2026 · Trạng thái: **chờ duyệt**

## 1. Mục đích
Sau khi đã phân tích xong một hợp đồng, người dùng upload thêm văn bản ngay trong màn hình Hợp đồng (không qua Hồ sơ
nhiều văn bản), xem kết quả mới và đối chiếu với kết quả trước đó.

## 2. Phạm vi
**Làm:**
- Hai loại văn bản bổ sung: **phụ lục** (sửa/bổ sung chính hợp đồng này) và **hợp đồng khác** cùng bên.
- Hệ thống đoán loại, người dùng xác nhận.
- Mỗi lần bổ sung tạo một **phiên bản** mới; phiên bản cũ giữ nguyên.
- Bảng đối chiếu giữa phiên bản mới và phiên bản ngay trước.

**Không làm:** sửa/gỡ trang Hồ sơ nhiều văn bản; so sánh hai phiên bản bất kỳ; rẽ nhánh phiên bản; gộp nhiều file trong
một lần bổ sung.

**Coi là thất bại:** mục không liên quan tới văn bản mới lại đổi kết quả do LLM đọc lại; phiên bản cũ bị thay đổi.

## 3. Cách làm đã cân nhắc
| Cách | Được | Mất | |
|---|---|---|---|
| 1. Mỗi lần bổ sung tạo phiên bản mới | So sánh rõ, gỡ bằng cách quay về bản cũ | Thêm khái niệm phiên bản ở nơi lưu và giao diện | **Đã chọn** (cần giữ kết quả trước và sau) |
| 2. Cập nhật thẳng hợp đồng gốc, lưu bản chụp kết quả cũ | Ít việc hơn | Khó gỡ; xác minh trước/sau trộn lẫn | Loại |
| 3. Chuyển ngầm sang Hồ sơ nhiều văn bản | Ít code nhất | Không kiểm lại từng mục khi có phụ lục | Loại |

## 4. Mô hình phiên bản
- Mỗi phiên bản là một `Contract` riêng (id mới), thêm trường lưu trong `contract.json`: `family_id` (id bản gốc),
  `version` (1, 2, …), `parent_id`, `addition` = `{kind: appendix|contract, filename, other_contract_id?, review_date?, same_party?, continuous_employment?}`.
- Hợp đồng đã lưu trước đây = `version 1`, không cần chuyển đổi dữ liệu.
- Chỉ bổ sung được vào **phiên bản mới nhất** và chỉ khi phiên bản đó đã có kết quả phân tích.
- `persist` của phiên bản mới theo bản gốc. Danh sách hợp đồng chỉ hiện bản mới nhất của mỗi `family_id`.
- Xóa phiên bản mới nhất = gỡ văn bản vừa thêm. Xóa bản gốc = xóa cả họ (hỏi xác nhận).
- Lỗi giữa chừng: không lưu phiên bản dở dang; bản cũ không bị đụng tới.

## 5. Phụ lục
1. Đọc file (loader chung). Phiên bản mới = bản sao `parent`: các trang cũ + trang mới; bố cục = các phần đang hiệu lực
   + **một** `PartSpec` phụ lục mới bắt đầu tại đầu trang mới. `uid` của phần cũ phải không đổi (có test).
2. Chép `facts` và nhật ký thao tác sang (đổi `contract_id`, giữ `op_id`).
3. **LLM chỉ đọc phần mới**: trích dữ kiện chỉ trên các đơn vị của phần mới, gộp ứng viên vào `facts.candidates`; gán
   khái niệm chỉ trên các đơn vị của phần mới. Thao tác của phần cũ giữ nguyên.
4. Chạy `check_contract` ở chế độ không trích/gán lại phần cũ. Bước kiểm lại (`recheck`) chỉ cho khái niệm mà kết quả
   phụ thuộc phần mới hoặc phiên bản cũ chưa từng kiểm.
5. Giá trị bị sửa dùng cạnh `AMENDS` + ngày hiệu lực (`graph_facts.py`). Cơ chế này hiện chỉ áp cho dữ kiện cấp hợp
   đồng; cần áp thêm cho slot khái niệm (phát hiện khi lập kế hoạch). Phụ lục không có câu
   sửa đổi nhận ra được mà đưa giá trị khác -> kết quả `CONFLICT`, hiển thị đúng như vậy, không tự chọn.
6. Bảng xác minh: câu trả lời của người dùng ở bản cũ được giữ, **trừ** trường mà phần mới thêm giá trị khác; các
   trường đó phải xác minh lại trước khi soát (qua `check_gate`).

## 6. Hợp đồng khác
1. File mới được tạo thành một hợp đồng thường (đủ luồng đọc, trích, xác minh như upload hiện nay), đánh dấu thuộc
   `family_id` này nên không hiện thành mục riêng trong danh sách.
2. Người dùng xác nhận: cùng người lao động / cùng bên; làm việc liên tục hay không (có thể để "không rõ"). Khác bên
   -> không tạo phiên bản, báo rõ.
3. Phiên bản mới = nội dung hợp đồng chính không đổi (không gọi LLM lại cho nó) + liên kết tới hợp đồng thêm.
4. Quy tắc liên hợp đồng: dựng `Dossier` trong bộ nhớ từ các hợp đồng của phiên bản, dùng **dữ kiện đã lưu** (không
   trích lại), qua `dossier_objects`. Kết quả "trước" = tập văn bản của bản cũ, "sau" = thêm hợp đồng mới, tính bằng
   `session.update(objects=…)` để lấy được các quy tắc đã tính lại.
5. Chỉ gói có `object_types` (hiện: lao động) có quy tắc liên hợp đồng. Gói khác: báo "không có quy tắc liên văn bản".

## 7. Đối chiếu
- Khóa so sánh: `(concept_id, rule_id, object)`. Nhóm: **đổi kết luận**, **mới xuất hiện**, **không còn**, không đổi
  (thu gọn). Mỗi dòng đổi hiện kết luận cũ → mới, giá trị và trích đoạn của hai bên.
- Hai bên phải được đánh giá **cùng một ngày** (mục 9) và cùng bộ dữ kiện người dùng; bên "trước" tính lại bằng
  `rules_only` (không gọi LLM) khi ngày khác ngày đã lưu. Kết quả đã lưu của bản cũ không bị ghi đè.
- Ghi chú khi phiên bản gói luật đã khác giữa hai lần.

## 8. API và giao diện
- `POST /api/contracts/{cid}/additions` (file) -> đọc, đoán loại (`classify_contract` với loại `amendment`).
- `POST /api/contracts/{cid}/additions/{aid}/analyze/stream` (loại đã xác nhận, ngày, bên) -> tiến trình như phân tích
  hiện tại, trả snapshot phiên bản mới. Thiếu xác minh -> trả mục cần xác minh như luồng hiện tại.
- `GET /api/contracts/{cid}/studio/compare` -> đối chiếu với `parent`.
- Màn hình Hợp đồng: nút **"Bổ sung văn bản"** sau khi có kết quả; chọn phiên bản (v1, v2…); tab **"So với bản trước"**.
- Kiểm thử bằng LLM giả: uid cũ không đổi; mục không liên quan giữ nguyên; bản cũ không đổi; phụ lục đổi lương; hợp
  đồng khác cho đúng ba thay đổi như hồ sơ mẫu b4; lỗi giữa chừng không để lại bản dở.

## 9. Ngày đánh giá khi đối chiếu (đã chốt 26/11)
Kiểm một hợp đồng hiện đánh giá tại **ngày ký**, nên phụ lục hiệu lực sau đó không làm đổi kết quả. Đã chọn:
- **Phụ lục:** ngày đánh giá mặc định = ngày phụ lục có hiệu lực, người dùng sửa được. Cả "trước" và "sau" tính tại
  ngày đó (`check_contract` nhận ngày đánh giá; `sign_date` của hợp đồng không đổi). Phụ lục không ghi ngày hiệu lực
  -> người dùng phải nhập. Giao diện ghi rõ ngày đang dùng và báo khi cột "trước" khác kết quả đã lưu của bản cũ.
  Phiên bản mới lưu ngày này trong `addition.review_date`; lần bổ sung sau mặc định không sớm hơn ngày đó.
- **Hợp đồng khác:** ngày soát liên hợp đồng mặc định = hôm nay, sửa được, áp cho cả "trước" và "sau".
- Đã loại: luôn dùng hôm nay cho phụ lục (phụ lục chưa hiệu lực không thấy thay đổi); giữ ngày ký.

## 10. Để người lập trình quyết
Tên hàm trích/gán theo phần, cách chép nhật ký thao tác, bố cục giao diện chi tiết.
