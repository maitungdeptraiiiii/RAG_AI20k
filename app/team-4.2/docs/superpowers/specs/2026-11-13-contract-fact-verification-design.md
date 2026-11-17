# Xác minh dữ kiện hợp đồng và trích xuất theo lô (bản nháp 1)

Ngày: 2026-11-13. Phạm vi: **chỉ phía hợp đồng**. Lớp cầu nối (khái niệm, rule, ngưỡng) có bản thiết kế riêng, viết sau.
Liên quan: `2026-11-12-contract-scale-design.md` §9.1 (soát theo lô), §7.2 (dữ kiện là thao tác trong nhật ký), H1, H6, H16.

## 1. Vì sao

- Mọi kết luận pháp lý phụ thuộc vài dữ kiện nền: người dùng là bên nào, ngày ký, loại hợp đồng, chức danh, nơi làm
  việc… Hiện LLM trích một lần, người dùng chỉ sửa được bên và ngày ký, các dữ kiện khác sai thì không ai biết (H16).
- Hợp đồng dài: bước trích dữ kiện và bước soát chỉ gửi LLM 30 Điều đầu (H1, H6). Dữ kiện nằm ở Điều 35 bị bỏ sót.
- Trong lúc soát, có kết luận cần thông tin hợp đồng không ghi (trình độ công việc để biết hạn thử việc). Hiện LLM
  tự đoán hoặc bỏ qua.

## 2. Mục tiêu

1. Sau khi tải hợp đồng, hệ thống đưa người dùng **bảng xác minh**: mỗi dòng là một dữ kiện, giá trị đọc được, câu
   trích làm căn cứ, trạng thái. Người dùng xác nhận, sửa, hoặc chọn "không biết".
2. **Soát (toàn bộ / một phần / đối chiếu luật mới / viết lại) bị chặn** tới khi mọi dữ kiện bắt buộc đã được xác minh.
3. Trong lúc soát, khi kết luận cần thông tin chưa có, LLM **trả câu hỏi kèm lựa chọn** thay vì đoán; kết luận đó ghi
   "cần thông tin" và liệt kê kết luận theo từng trường hợp. Người dùng trả lời, rồi soát lại riêng các điều khoản liên quan.
4. **Trích dữ kiện và soát theo lô** trên toàn bộ hợp đồng, không còn giới hạn 30 Điều.

Ngoài mục tiêu: rule và ngưỡng pháp lý tất định (lớp cầu nối); tóm tắt và hỏi đáp vẫn dùng 30 Điều đầu (làm sau).

## 3. Danh mục dữ kiện

File dữ liệu `src/rag/contracts/fact_catalog.json`, có số phiên bản. Mỗi loại hợp đồng một danh sách; loại được chọn
theo dữ kiện `type` (chứa "lao động" → `labor`, chứa "thuê" → `lease`, còn lại `common`).

Mỗi dữ kiện: `key`, `label`, `kind` (text / date / enum / duration / money / percent), `options` (với enum),
`required` (chặn soát), `hint` (gợi ý cho LLM biết tìm gì).

| Loại | Bắt buộc | Nên xác nhận |
|---|---|---|
| chung | bạn là bên nào, ngày ký, loại hợp đồng | ngày hiệu lực, thời hạn, giá trị |
| lao động | + loại HĐLĐ, chức danh / công việc, nơi làm việc | ngày bắt đầu, thời hạn, mức lương, nhóm trình độ công việc, thời gian thử việc, lương thử việc, thời giờ làm việc |
| thuê | + tài sản thuê, mục đích thuê | giá thuê, tiền cọc, thời hạn, ngày bàn giao |

"Bạn là bên nào" lấy lựa chọn từ các bên đã trích, cộng "Trung lập / tư vấn". "Nhóm trình độ công việc" là các nhánh
của BLLĐ Điều 25 (người quản lý doanh nghiệp / cao đẳng trở lên / trung cấp, công nhân kỹ thuật / công việc khác).

## 4. Trích dữ kiện theo lô

- **Lô:** các đơn vị cấp cao nhất liền nhau, tổng tối đa 12.000 ký tự. Một Điều dài hơn ngân sách đi một mình; dài
  hơn 24.000 ký tự thì cắt thành nhiều mảnh cùng `uid`.
- **Ngữ cảnh chung mỗi lô** (đánh dấu "chỉ để tham khảo"): phần mở đầu (các bên), Điều định nghĩa / giải thích từ
  ngữ nếu có, mỗi thứ tối đa 3.000 ký tự.
- **Đơn vị được dẫn chiếu** (từ dẫn chiếu nội bộ của bộ tách): nguyên văn các Điều mà lô dẫn chiếu tới nhưng không nằm
  trong lô, tối đa 3.000 ký tự, đánh dấu "chỉ để tham khảo".
- **Kiểm trích dẫn chặt hơn:** câu trích phải nằm trong **chính đơn vị** mà LLM ghi là nguồn, không chỉ ở đâu đó trong
  hợp đồng.
- **Gộp:** mỗi dữ kiện gom ứng viên của mọi lô. Cùng một giá trị → `found`. Khác giá trị → `conflict`, giữ mọi ứng viên
  kèm trích dẫn, buộc người dùng chọn. Không có → `missing`.
- **Lô lỗi:** thử lại một lần; vẫn lỗi thì ghi vào cảnh báo "chưa đọc được Điều x–y". Không lô nào thành công →
  lỗi như hiện nay.

## 5. Trạng thái và xác minh

| Trạng thái | Nghĩa | Đã xác minh? |
|---|---|---|
| `found` | Máy đọc được, một giá trị, có trích dẫn | Chưa |
| `conflict` | Máy đọc được nhiều giá trị khác nhau | Chưa |
| `missing` | Không tìm thấy | Chưa |
| `confirmed` | Người dùng xác nhận giá trị máy đọc | Rồi |
| `corrected` | Người dùng nhập giá trị khác | Rồi |
| `unknown` | Người dùng chọn "không biết" | Rồi; rule phụ thuộc sẽ liệt kê theo trường hợp |

- Mỗi xác nhận / sửa / "không biết" là một thao tác `SET_FIELD` của người trong nhật ký, đích `fact:<key>`, thay thế
  thao tác trước cùng đích. Bên và ngày ký đồng bộ với `party`, `sign_date` như hiện nay.
- API mới `POST /api/contracts/{id}/facts` nhận `{"answers": {key: {"action": "confirm" | "set" | "unknown",
  "value"?}}}`; kiểm kiểu (ngày ISO, enum thuộc lựa chọn). Câu hỏi trong lúc soát dùng chung API với khóa `q:<id>`.
- Đổi loại hợp đồng → danh sách dữ kiện đổi theo; dữ kiện mới hiện `missing`, giá trị đã xác minh của dữ kiện trùng
  khóa được giữ.
- Hợp đồng lưu trước bản này: dựng bảng xác minh từ dữ kiện cũ (trạng thái `found`), không gọi LLM.

## 6. Chặn soát

`run` với `review`, `partial`, `law_changes`, `redline` trả 409 kèm danh sách dữ kiện bắt buộc chưa xác minh.
`summary` và hỏi đáp không bị chặn (chúng không đưa ra kết luận pháp lý về điều khoản), nhưng thẻ hợp đồng nhắc
"chưa xác minh".

## 7. Câu hỏi trong lúc soát

- Payload soát gửi kèm `known_facts`: mọi dữ kiện đã xác minh và mọi câu hỏi đã trả lời. LLM được dặn không hỏi lại
  những gì đã có.
- LLM trả thêm `questions`: `{question, options[], unit, quote?, finding_refs[]}`. Câu hỏi phải gắn với một đơn vị có
  trong lô; trích dẫn sai thì bỏ trích dẫn, giữ câu hỏi. Trùng câu hỏi (sau chuẩn hóa) thì gộp.
- Phát hiện phụ thuộc thông tin chưa có: `needs_info = true`, `cases = [{"if", "conclusion"}]`. Thẻ báo cáo hiện các
  trường hợp, không đưa ra một kết luận duy nhất.
- Câu hỏi lưu ở `facts.questions` (mở / đã trả lời). Trả lời xong, giao diện đưa nút "Soát lại các điều khoản liên
  quan" (soát một phần trên các đơn vị của câu hỏi).

## 8. Soát theo lô

Bước tìm vấn đề (`FIND`) chạy trên từng lô (cùng cách dựng lô ở §4); các bước sau (tìm căn cứ, kiểm căn cứ) giữ nguyên.
Độ phủ báo cáo: số đơn vị trong các lô thành công / tổng; lô lỗi ghi vào cảnh báo. Soát một phần chạy trên các đơn vị
được chọn, cũng theo lô, không còn giới hạn 30.

## 9. Giới hạn

- Giá trị kiểu tiền / thời hạn / phần trăm lưu dạng chữ người dùng nhập, chưa chuẩn hóa thành số (lớp cầu nối sẽ cần).
- Câu hỏi do LLM sinh: có thể hỏi thừa; không có danh mục câu hỏi cố định cho tới khi có lớp cầu nối.
- Đổi bố cục phần làm đổi `uid`; trích dẫn của dữ kiện vẫn đúng nhưng `unit` có thể trỏ sai, không tự sửa.
- Tóm tắt và hỏi đáp vẫn 30 Điều đầu.

## 10. Thứ tự làm

1. Danh mục dữ kiện + dựng lô (`batches.py`) + trích dữ kiện theo lô, gộp, trạng thái.
2. Xác minh: áp câu trả lời, ghi nhật ký, đồng bộ bên / ngày ký, chặn soát; API `facts`; thẻ có `verification`.
3. Soát theo lô + `known_facts` + câu hỏi + `cases`.
4. Giao diện: bảng xác minh trong thẻ, câu hỏi và trường hợp trong báo cáo, nút soát lại.
