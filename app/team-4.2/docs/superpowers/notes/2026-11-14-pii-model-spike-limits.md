# PII bằng mô hình OpenMed: kết quả chạy thử và phần còn dở

Ngày: 2026-11-14 · Trạng thái: tạm dừng, ghi lại để làm tiếp.
Liên quan: `specs/2026-11-14-pii-model-masking-design.md` (spec, chờ duyệt).

## 1. Tình trạng

- `rag/quality/pii.py` chưa sửa. Chưa có `ModelDetector`, `PII_MODEL`, `PII_BACKEND`, extra `pii`.
- Spec đang ở trạng thái "chờ duyệt".
- Chưa chạy bộ kiểm mục 6 của spec (`evals/team-4.2/`). Số liệu dưới đây chỉ từ script chạy thử.
- Script và kết quả chạy thử nằm trong scratchpad của phiên cũ (thư mục tạm, có thể bị xóa):
  `C:\Users\Admin\AppData\Local\Temp\claude\dff555358a8b4d47\15724923-f73b-4b3c-91f7-b2b6da9fbf9b\scratchpad\`
  gồm `pii_spike.py`, `pii_spike.log`, `pii_spike_result.json`, venv `pii_spike_env`, cache mô hình `hf_cache`.
  **Việc đầu tiên: chép ba file đầu vào repo** (ví dụ `evals/team-4.2/pii/`).

## 2. Phạm vi đã thử

- 2 bản: BigMed-Large-278M, SuperClinical-Large-434M. GPU RTX 3060 6 GB.
- 6 đoạn văn bản giả lập: HĐLĐ mở đầu, HĐLĐ điều khoản, Phụ lục 2, thuê nhà, câu hỏi chat, đoạn BLLĐ 2019.
  Tổng 23 span phải che, 2 span ngày sinh phải tổng quát hóa.

## 3. Kết quả

| Tiêu chí | BigMed-278M | SuperClinical-434M |
|---|---|---|
| Span phải che sót hoàn toàn | 0/23 | 0/23 |
| Span phải che bắt đủ ≥ 90% | 12/23 | 12/23 |
| Ngày sinh bắt đủ | 2/2 | 2/2 |
| CCCD 12 số | 4/4 | 4/4 |
| Điện thoại, tài khoản, email | đủ | đủ |
| Tên người | bắt ở mọi đoạn | bắt ở mọi đoạn; "Trần Văn Minh" chỉ 38% |
| Ngày cấp CCCD | `DATEOFBIRTH`, bắt đủ ở HĐLĐ, 80% ở thuê nhà | `DATE`, 80% ở cả hai đoạn |
| Ranh giới span | theo từ, sạch | vỡ giữa từ ("Ph", "ạ", "m") |
| "10/2012/QH13" | `DATE` | `ACCOUNTNAME` + `MASKEDNUMBER` (sẽ che nhầm) |
| Tốc độ một đoạn | 10–30 ms | 50–300 ms |
| Thời gian nạp | 125 s | 427 s |

**Kết luận tạm: BigMed-Large-278M tốt hơn** (ngang độ bắt, span sạch, không che nhầm số hiệu luật, nhanh hơn 3–5 lần,
nhẹ hơn). Điểm F1 công bố không dùng để chọn. BigMed-Large-560M có F1 cao nhất nhưng không tải được (HTTP 401).

Lưu ý khi đọc số:
- Phần lớn "bắt một phần" là do khoảng trắng giữa các từ của tên (mô hình gán nhãn từng từ). Spec đã định gộp span tên liền nhau.
- Hai địa chỉ thường trú chỉ đạt 68–85%, chưa rõ lý do, cần kiểm riêng.
- Số "BỊ GẮN NHÃN" trong log (25/28 với BigMed) là nhãn thô **trước** quy tắc ngữ cảnh, không phải tỉ lệ che nhầm.

## 4. Giới hạn của mô hình (nên quy tắc ngữ cảnh ở mục 4 spec là bắt buộc)

- `DATEOFBIRTH`/`DATE` gán cả cho ngày ký và ngày hiệu lực luật.
- Địa chỉ công ty và nơi làm việc bị gán nhãn địa chỉ như địa chỉ cá nhân.
- Gán nhãn cho thứ phân tích cần giữ: lương và số tiền (`CURRENCY`/`AMOUNT`), "90 ngày"/"60 ngày" (`AGE`),
  chức danh, tên công ty, tên luật ("Luật Doanh nghiệp" thành `JOBDEPARTMENT`).
- BigMed gán `ACCOUNTNAME` cho mã số thuế công ty.

## 5. Còn thiếu / việc làm tiếp

1. **Bộ kiểm có đáp án đầy đủ** (spec mục 6): 3 văn bản HĐLĐ, thuê nhà, fixture `w02-27`, đoạn luật thật, câu hỏi chat.
   Đo "che nhầm sau khi áp quy tắc ngữ cảnh" (chỉ số quan trọng nhất), sót theo loại, tổng quát hóa ngày sinh.
2. Mới 6 đoạn, 2 bản. Thêm **mSuperClinical-Large-279M** (nền mDeBERTa) làm đối chứng; so luôn với regex cũ.
3. **Chốt ngưỡng tin cậy.** Nhiều span đúng chỉ có điểm 0,4–0,6 (tên, địa chỉ); ngưỡng cao sẽ làm sót.
4. **Đo trên CPU** (chưa đo).
5. `.venv` gốc chưa có `torch` và `transformers`; lần thử dùng venv riêng. Cần thêm extra `pii` trong `pyproject.toml`.
6. Tìm nguyên nhân hai địa chỉ thường trú bắt thiếu (68–85%).
7. Viết `ModelDetector` + dự phòng regex, quy tắc ngữ cảnh, gộp span tên, cửa sổ chồng lấn, cache theo nội dung.
8. Sửa lỗi lộ CCCD khi mở che trong bản tóm tắt (spec mục 5.5).
9. Chạy lại `scripts/trace_contract_pipeline.py` trên hồ sơ lao động, xác nhận tên người không còn trong payload LLM.
10. Chờ người dùng duyệt spec (các lựa chọn ở mục 10 spec chưa được xác nhận).
