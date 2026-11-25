# Demo "Bổ sung văn bản": hợp đồng lao động gốc + phụ lục

Dữ liệu **hư cấu**. Sinh lại file: `python tao_ho_so.py <thư mục>` (cần `python-docx`). **Không** upload README này.

| File | Nội dung |
|---|---|
| `01-hop-dong-goc.docx` | HĐLĐ 24 tháng ký 05/01/2026, cố ý sai: lương 4.500.000, làm 10 giờ/ngày 60 giờ/tuần, nghỉ năm 10 ngày, thử việc 90 ngày hưởng 70%, không có chế độ nâng lương |
| `02-phu-luc-01.docx` | Phụ lục ký 16/02/2026, hiệu lực 01/03/2026: nâng lương 8.000.000, làm 8 giờ/48 giờ, nghỉ năm 12 ngày, thêm nâng lương hằng năm, **thêm điều cấm**: đặt cọc 10.000.000 và giữ bằng tốt nghiệp. Không sửa thử việc |

## Các bước (Contract Studio, `/contract-studio/`)

1. **Upload hợp đồng** `01-hop-dong-goc.docx`.
2. Xác minh thông tin (bên: chọn "Người sử dụng lao động" hoặc "Người lao động"). Ở "Thông tin thêm" chọn
   **Vùng lương = I**. Bấm **Xác nhận & Phân tích**.
3. Bấm **Bổ sung văn bản**, chọn `02-phu-luc-01.docx`. Loại được gợi ý "Phụ lục của hợp đồng này" → **Đọc văn bản
   bổ sung**.
4. Xác minh trường được hỏi lại (nếu có). Ngày đánh giá để mặc định **01/03/2026** → **Xác nhận và đối chiếu**.
5. Xem bảng **So với bản trước (v1)**; đổi ô **Phiên bản** để mở lại v1 (chỉ đọc).

## Kết quả (chạy thật 26/11/2026 qua API, LLM của app): đổi 6 mục, giữ 49

| Mục | v1 | v2 | Ý nghĩa |
|---|---|---|---|
| Lương tối thiểu vùng | Vi phạm (4,5 triệu) | Phù hợp (8 triệu) | Phụ lục sửa được lỗi |
| Thời giờ làm việc bình thường | Vi phạm (10 giờ / 60 giờ) | Phù hợp (8 giờ / 48 giờ) | Phụ lục sửa được lỗi |
| Chế độ nâng bậc, nâng lương | Thiếu nội dung | Phù hợp | Phụ lục bổ sung nội dung thiếu |
| Cấm buộc đặt cọc bằng tiền | Phù hợp | **Vi phạm** | Phụ lục gây lỗi mới |
| Cấm giữ bản chính văn bằng | Phù hợp | **Vi phạm** | Phụ lục gây lỗi mới |
| Nghỉ hằng năm | Cần thêm dữ kiện (10 ngày) | Cần thêm dữ kiện (12 ngày) | Giá trị đổi, kết luận còn chờ dữ kiện |

Không đổi, đúng như mong đợi: **Thời gian thử việc** (90 ngày) và **Lương thử việc** (70%) vẫn vi phạm vì phụ lục không
sửa Điều 2.

## Điểm cần nói trước
- Không chọn vùng lương thì mục lương chỉ hiện "cần thêm dữ kiện" ở cả hai bản.
- Mục nghỉ hằng năm vẫn "cần thêm dữ kiện" dù đã chọn điều kiện làm việc bình thường (đã thử).
- Kết quả phụ thuộc LLM đọc văn bản; mới chạy qua API, chưa bấm trên trình duyệt. Chạy thử trước buổi demo.

Đáp án trong bảng là kết luận của hệ thống, **chưa được người rà theo luật**.
