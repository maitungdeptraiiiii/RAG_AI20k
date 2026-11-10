# Kho luật có phiên bản — chạy thật nhóm bất động sản (09/11/2026)

Thiết kế: `app/team-4.2/docs/superpowers/specs/2026-11-09-legal-version-builder-design.md` ·
Kế hoạch: `app/team-4.2/docs/superpowers/plans/2026-11-09-legal-version-builder.md`

## Lệnh chạy lại

Từ `app/team-4.2`, với `DATA_DIR` riêng (không ghi đè snapshot 6 Bộ luật):

```powershell
$env:DATA_DIR = "<thư mục tạm>"; $env:PYTHONPATH = "src"
python -m rag.legal crawl      # seed: data/team-4.2/legal/seeds.yaml
python -m rag.legal build
python -m rag.legal report
python -m rag.legal show luat:27/2023/QH15 --as-of 2024-08-01 --provision d197.k1
```

Kiểm thử không cần mạng (văn bản đã lưu ở `tests/fixtures/legal/realestate/`):
`python -m pytest -q tests/test_legal_realestate.py`

## Kết quả crawl (seed: Luật Đất đai 31/2024, Luật Nhà ở 27/2023, Luật KDBĐS 29/2023, BLDS 91/2015)

| | Số lượng |
|---|---|
| Văn bản được thêm tự động (đã xác nhận bằng nội dung) | 9 |
| Ứng viên bị loại: nội dung không xác nhận quan hệ | 42 |
| Ứng viên bị loại: văn bản dưới luật (Nghị định, Thông tư, QĐ UBND) | 34 |
| Ứng viên bị loại: vbpl không có nội dung (gồm VBHN-VPQH của Luật Đất đai, Luật Nhà ở) | 15 |

Văn bản được thêm: 43/2024/QH15 (sửa 3 luật BĐS), 03/2022/QH15 (sửa Luật Nhà ở 2014), chuỗi luật bị thay thế
Đất đai 13/2003 → 45/2013 → 31/2024, Nhà ở 56/2005 → 65/2014 → 27/2023, KDBĐS 63/2006 → 66/2014 → 29/2023,
BLDS 33/2005 → 91/2015.

## Kết quả dựng

| | Số lượng |
|---|---|
| Thao tác tự xác minh (`exact/auto_accepted`) | 14 |
| Thao tác chờ duyệt (`pending`) — chủ yếu luật đích ngoài phạm vi kho (03/2022 sửa 9 luật) | 64 + 3 unsupported |
| Mục duyệt mở | 67 |
| Phiên bản điều khoản `verified` | ~16.900 |
| `needs_review` — BLDS 2005 (vbpl thiếu Điều hiệu lực) | 3.291 |
| `needs_review` — luật cũ mà văn bản thay thế nêu rõ "đã được sửa đổi theo Luật số …" nhưng kho chưa có các luật sửa đổi đó (Đất đai 2013 từ 2018; Nhà ở 2005 từ 2009; Nhà ở 2014 từ 2019; KDBĐS 2014 từ 2020) | ~7.100 |
| `needs_review` — khoản 9 Điều 60 Luật Đất đai (hiệu lực theo sự kiện); 03/2022, 43/2024 (vbpl "hết hiệu lực một phần") | 1 + 74 |

Kiểm chứng pháp lý (test `test_legal_realestate.py`):

- Luật Đất đai 2024 có hiệu lực từ **01/8/2024** (theo Luật 43/2024 sửa Điều 252), vbpl vẫn ghi 01/01/2025;
  Điều 190, 248 từ **01/4/2024**.
- Luật Nhà ở, Luật KDBĐS: ngày 31/7/2024 → luật 2014; từ 01/8/2024 → luật 2023.
- Luật Đất đai 2013, Nhà ở 2014, KDBĐS 2014 kết thúc đúng 01/8/2024 (không có giai đoạn hai luật cùng hiệu lực
  ngoài Điều 190, 248 Luật Đất đai 2024 có hiệu lực sớm theo luật định).
- Khoản 1 Điều 23 Luật Nhà ở 2014 đổi nội dung từ 01/3/2022 theo Luật 03/2022.

## Lỗi chạy thật phát hiện và đã sửa (mỗi lỗi có test tái hiện)

1. HTML vbpl bọc từng mẩu chữ trong `<span>` → chữ bị cắt vụn; thêm `rag.legal.text.html_to_legal_text`.
2. Chọn nhầm "Điều 62. Hiệu lực nghị quyết…" làm Điều hiệu lực; Luật Doanh nghiệp dùng "Điều khoản thi hành".
3. Câu "Luật X đã được sửa đổi, bổ sung theo Luật số A, Luật số B … hết hiệu lực" bị đọc thành A, B hết hiệu lực
   (lần chạy đầu thêm nhầm 48 văn bản, gồm cả Luật Nhà ở 2023 "bị thay thế").
4. Nghị định / Thông tư / VBHN của Bộ được nhận là văn bản sửa đổi luật.
5. Ngoại lệ hiệu lực liệt kê nhiều Điều; đơn vị có hiệu lực theo sự kiện; "khổ đầu khoản".
6. Ngày "hết hiệu lực kể từ ngày Luật này có hiệu lực" phải theo ngày đã sửa của luật mới.
7. Đánh giá của máy cho thao tác chưa được duyệt nay được cập nhật khi parser cải thiện (quyết định của người giữ nguyên).

## Review độc lập và lượt sửa (mỗi lỗi có test RED→GREEN, `tests/test_legal_review_fixes.py` + các file liên quan)

Review toàn nhánh tìm 5 lỗi nghiêm trọng (đều tạo phiên bản sai mà vẫn `verified`) và 6 lỗi quan trọng; đã sửa hết:
danh sách đích nhiều Điều; "bãi bỏ cụm từ" bị hiểu là xoá cả khoản; ngày hiệu lực riêng không rõ đơn vị; duyệt thao
tác không áp dụng được; luật sửa đổi đã biết nhưng thiếu trong kho; dấu đóng ngoặc bên trong nội dung trích dẫn; thao
tác cũ không bị loại khi lập lại; mục duyệt không mở lại được / chấp nhận lệch VBHN / hạ cấp; bản sửa không được kiểm
tra; câu "Kể từ ngày Luật này có hiệu lực, Luật X hết hiệu lực"; effTo của vbpl không được đối chiếu.

## Tăng độ phủ sửa đổi

Crawler giờ tự tải các luật được nêu trong câu "<luật cũ> đã được sửa đổi, bổ sung theo Luật số …" và xác nhận bằng
nội dung, kể cả khi sửa đổi nằm trong luật khác (Luật Đầu tư 61/2020 Điều 75, Luật PPP 64/2020, Luật Kiến trúc
40/2019). Parser hỗ trợ thêm: luật đích ở cấp khoản/điểm, đuôi "đã được sửa đổi … theo Luật số …", câu bị động
("Điều 126 của Luật nhà ở được sửa đổi, bổ sung như sau"), thay cả chương ("Sửa đổi, bổ sung Chương IV") thành từng
thao tác thay Điều chờ duyệt, số hiệu trùng giữa Luật và Nghị quyết.

| Luật | `needs_review` trước | sau |
|---|---|---|
| Nhà ở 65/2014 | 2.763 | 42 |
| KDBĐS 66/2014 | 673 | 13 |
| Đất đai 45/2013 | 1.969 | 235 (chỉ các Điều thuộc Chương IV do 35/2018 thay, chờ duyệt) |
| Nhà ở 56/2005 | 1.686 | 850 (Nghị quyết 19/2008 thí điểm — không có chỉ dẫn sửa đổi, giữ cờ) |

Luật sửa đổi được thêm: 40/2019, 61/2020, 62/2020, 64/2020, 35/2018, 34/2009, 38/2009. Hàng đợi duyệt: 31 mục mở
(thao tác vào luật ngoài kho không tạo mục duyệt; mục của thao tác bị thay khi lập lại được hệ thống đóng).

## Giới hạn đã biết

- Sửa đổi nằm trong luật khác chỉ được tìm khi có gợi ý (câu "đã được sửa đổi theo Luật số …" hoặc tiêu đề); sửa đổi
  không được nhắc ở đâu vẫn có thể sót. Các luật sửa đổi được thêm (vd. Luật Đầu tư 2020) cũng trở thành văn bản trong kho.
- VBHN-VPQH của các luật BĐS không có nội dung trên API công khai → chưa đối chiếu được.
- Bãi bỏ một phần ("khoản 3 Điều X của Luật Y hết hiệu lực") trong Điều hiệu lực của luật khác chưa thành thao tác DELETE.
- Văn bản sửa đổi nhiều luật cho thao tác `pending` với luật đích ngoài kho (đúng thiết kế, nhưng làm hàng đợi dài).
