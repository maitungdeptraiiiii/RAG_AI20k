# Regex → LLM trong bước trích dữ kiện: hiện trạng, nguồn ngoài, kế hoạch đo (23/11)

## 1. Hiện trạng (đọc code, chưa sửa)

Luồng đã là lai: `contracts/facts.py` (LLM, theo lô) -> `quote_ok` (câu trích phải nguyên văn) -> `bridge/facts_map.py`
(chuẩn hóa chuỗi `value` thành số + đơn vị) dùng regex `contracts/values.py` (ngày, tiền, %, thời hạn).
Regex còn ở: chuẩn hóa giá trị (`_duration`, `_salary`, `_percent`), nhận bí danh bên (`_text_aliases`), phát hiện sửa
đổi (`AMEND_RE`), khớp enum/contains (`_p_enum`, `_p_contains`). Phần "tìm giá trị trong văn bản" đã do LLM.
Nghĩa là câu hỏi đúng không phải "bỏ regex" mà là "chỗ nào chuẩn hóa bằng regex thất bại, và LLM hay bộ đọc xác định sửa được chỗ đó".

## 2. Đo thử cách viết (chạy `app/team-4.2/scripts/probe_value_forms.py`)

Thất bại có thật (xem `han_che_va_loi_ton_dong.md` R.1–R.5): "2 năm 6 tháng" ra 24 tháng (sai im lặng);
"24 (hai mươi bốn) tháng", "100.000.000 (một trăm triệu) đồng", số bằng chữ, "5tr", "100.000.000đ", "20 phần trăm",
ngày "01.03.2024" / "mùng 1 tháng 3 năm 2024" đều không đọc được.
Giới hạn: đây là 40 cách viết do mình nghĩ ra, không phải mẫu từ hợp đồng thật; tần suất thật chưa biết.

## 3. Nguồn ngoài (độ tin cậy trung bình, đa số preprint/nhà cung cấp)

- Cách làm phổ biến: LLM trích theo schema JSON rồi kiểm lại (De Jure: 3 LLM chấm 19 tiêu chí, sinh lại khi dưới 0,90, tối đa 3 lần); lai quy tắc + LLM ở lĩnh vực khác (medRxiv 01/2026).
- Model nhỏ tinh chỉnh cho miền hẹp cạnh tranh model lớn (A Few Good Clauses: micro F1 0,842 so với 0,779–0,820, chi phí theo lô $0,018 so với $0,149–0,456 mỗi tài liệu; chỉ 24 hợp đồng SEC tiếng Anh, tác giả liên quan nhà cung cấp, nhãn huấn luyện do model lớn sinh).
- Qwen nhỏ trên CUAD: số liệu tự công bố, tập thử nhỏ.
- Tiếng Việt: không có bài hay bộ dữ liệu trích dữ kiện hợp đồng ra JSON; chỉ có model luật hỏi đáp (ViLegalLM, VLegal-Bench).

## 4. Kế hoạch đo (ba cách, cùng bộ thử)

Bộ thử: giá trị `value` + câu trích trong `facts.yaml` của loan/lease/a1…r1, cộng một bộ biến thể cách viết (mục 2) có nhãn tay.
Ba cách so nhau, trên từng trường (thời hạn, tiền, %, ngày): (A) hiện tại; (B) LLM trả thẳng `{số, đơn vị}` theo schema
(constrained decoding), regex chỉ để đối chiếu; (C) lai: nhận khi B và A khớp, B khi A là None và câu trích chứa số, bất đồng -> UNKNOWN + cảnh báo.
Chỉ số: đúng / sai / bỏ sót / UNKNOWN cho từng trường; riêng "sai im lặng" phải bằng 0 (ưu tiên hơn độ phủ).
Model thử: Qwen nhỏ cục bộ (cấu hình riêng như ghi chú 12/11) so với một model lớn làm mốc; chọn theo số đo, không theo bảng xếp hạng.
Việc cần trước khi đo: có model chạy được (chưa có trong phiên này) và thêm 20–30 chuỗi nhãn tay từ hợp đồng thật.

## 5. Sửa không cần LLM (đề xuất, chờ duyệt)

R.1 (cộng nhiều đơn vị) và R.2 (số kèm chữ trong ngoặc) là lỗi bộ đọc xác định, sửa được bằng quy tắc thuần và có test; không cần chờ đo LLM.
Số bằng chữ (R.3) thì LLM chuẩn hóa hợp lý hơn thêm regex (đúng hướng "không thêm mẫu mới": để LLM đọc, kiểm bằng `quote_ok`).
