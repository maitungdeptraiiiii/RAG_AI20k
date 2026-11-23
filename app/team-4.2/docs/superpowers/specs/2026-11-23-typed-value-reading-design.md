# Đọc giá trị số theo kiểu (thay chuẩn hóa bằng regex) — thiết kế (23/11, Tùng duyệt)

## Vì sao

Luồng cũ: LLM trả chuỗi tự do ("2 năm 6 tháng"), regex `contracts/values.py` đoán nghĩa và lấy mẫu khớp ĐẦU TIÊN.
Mỗi cách viết mới cần mẫu mới; đọc thiếu thì sai im lặng ("2 năm 6 tháng" -> 24 tháng). Tùng: không vá từng cách
viết, sửa tổng quát. Đo thử: `reports/team-4.2/w04/regex_vs_llm_plan.md`, `han_che_va_loi_ton_dong.md` V.1–V.6.

## Thiết kế (đã duyệt)

Tách ba việc:
1. **LLM đọc** — trả giá trị có kiểu kèm chữ nguyên văn:
   - thời hạn: `{"parts": [{"n": 2, "unit": "year"}, {"n": 6, "unit": "month"}]}` (unit: hour, day, workday, week, month, year)
   - tiền: `{"amount": 100000000, "currency": "VND"}`
   - tỉ lệ: `{"value": 1.5, "per": "month"}` (per: null, day, month, year)
2. **Code tính** — cộng các phần, quy đổi bằng bảng `conversions` của gói (`Units.convert`). LLM không tính.
3. **Kiểm có căn cứ** — câu trích phải nguyên văn (`quote_ok`, như cũ) VÀ mỗi số LLM trả phải có trong câu trích /
   chữ nguyên văn, viết bằng chữ số hoặc bằng chữ, cho phép nhân 10^3, 10^6, 10^9 (nghìn / triệu / tỷ: "5tr",
   "100 triệu"). Số bằng chữ đọc bằng MỘT bộ đọc số tiếng Việt theo ngữ pháp đóng (không…chín, mươi, trăm, nghìn,
   triệu, tỷ, lẻ/linh, mốt, lăm, tư, phẩy) — không phải mẫu theo cách viết. Không có căn cứ -> không nhận (UNKNOWN,
   slot `bad`), không bao giờ sai im lặng.

Regex cũ chỉ còn để: (a) kiểm chéo — chuỗi chỉ chứa MỘT số (đếm bằng bộ quét số chung) mà regex đọc ra khác LLM ->
không nhận; (b) dự phòng khi LLM chưa trả dạng có kiểu (fixture cũ, model cũ) — cũng chỉ khi chuỗi chứa đúng một
số; nhiều số mà không có dạng có kiểu -> không đọc (trước đây lấy số đầu).

## Phạm vi

- Mới: `src/rag/contracts/quantity.py` (bộ quét số: chữ số + chữ; đọc dạng có kiểu; kiểm căn cứ).
- Sửa: `bridge/facts_map.py` (`normalize_slot`, bộ đọc `duration`/`duration_to_unit`/`money`/`percent` nhận `norm`),
  `bridge/tagger.py` (prompt + kiểm slot nhận dạng có kiểu), `contracts/facts.py` (prompt xin `norm` cho giá trị số).
- Không đụng: engine, gói luật, gold, giao diện (chuỗi `value` nguyên văn vẫn giữ để hiển thị).
- Ngoài phạm vi (ghi hạn chế): bộ đọc `contains` / `enum` (phân loại theo cụm chữ), nhận bí danh bên, `AMEND_RE`, ngày
  (đã ISO do LLM trả; bộ đọc ngày regex chỉ còn ở chỗ khác).

## Cái giá

- Hợp đồng có "2 năm 6 tháng" trước ra 24 nay ra 30 hoặc UNKNOWN — đổi đúng.
- Chuỗi nhiều số không có dạng có kiểu nay là UNKNOWN thay vì lấy số đầu — có thể làm vài ca từng PASS/FAIL thành UNKNOWN.
- Model nhỏ cần constrained decoding để trả JSON có kiểu ổn định (chưa làm; ghi hạn chế).
