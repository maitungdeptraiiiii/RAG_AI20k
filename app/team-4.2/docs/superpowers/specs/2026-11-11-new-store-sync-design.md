# Thiết kế: Đồng bộ sang kho luật có phiên bản

Ngày: 11/11/2026 · Trạng thái: đã duyệt trong chat · Phụ thuộc: phần 1–4.

## Ý định

Người dùng thấy danh sách tài liệu chỉ có 6 bộ luật của kho cũ, trong khi hỏi đáp đã tra ra luật của kho mới. Quyết định
(người dùng): **mọi văn bản pháp luật dùng kho mới**; **kho cũ giữ riêng cho "Tài liệu thường"** (upload ở `/upload`, chế
độ Tài liệu thường).

## Mục tiêu

1. 6 bộ luật (Dân sự 91/2015, Hàng hải 95/2015, Hình sự 100/2015, Lao động 45/2019, Tố tụng dân sự 92/2015, Tố tụng hình
   sự 101/2015) được nạp vào kho mới bằng crawler (`seeds.yaml`), kèm văn bản sửa đổi crawler tự tìm, qua snapshot.
2. 6 bộ luật trong kho cũ (danh sách `data/team-4.2/legal/legacy_map.yaml`) **bị loại khỏi mọi kết quả tìm kiếm** — dữ
   liệu trên đĩa giữ nguyên. Kho cũ chỉ còn trả tài liệu thường, gắn nhãn "Tài liệu (không phải văn bản pháp luật)".
3. Danh sách tài liệu: hai nhóm — **Văn bản pháp luật** (kho mới, kèm tình trạng hiệu lực hôm nay) và **Tài liệu thường**
   (kho cũ trừ 6 bộ luật). `/api/info` báo số văn bản / chunk của cả hai.
4. Hỏi đáp theo mốc, soát hợp đồng: căn cứ luật chỉ từ kho mới; tài liệu thường là nguồn tham khảo không phải luật.
5. Think tự do: agent tìm trong kho mới tại mốc (ngày người dùng chọn, không có thì hôm nay) + tài liệu thường; câu hỏi và
   lịch sử được che PII trước khi vào agent, mở che ở đầu ra (dùng lại `ContractAgentRetriever` của phần 4 khi không có
   hợp đồng).
6. Kho mới lỗi / chưa sẵn sàng → chat báo rõ "Kho luật có phiên bản chưa sẵn sàng…" — **không** lặng lẽ trả lời bằng kho cũ.

## Không làm

- Xoá dữ liệu kho cũ; bỏ chế độ Tài liệu thường.
- Đổi quy tắc dựng phiên bản (phần 1) hay quy tắc trả lời theo mốc (phần 2).

## Quyết định của Claude

- Loại **mọi** nguồn trong `legacy_map.yaml` khỏi kho cũ (không chỉ những bộ luật đã có trong kho mới): nếu crawler thiếu
  một bộ luật thì câu hỏi về nó nhận "kho chưa có" thay vì căn cứ không phiên bản — đúng ý "chuyển hẳn".
- Mốc cho Think tự do = ngày chọn trên ô "Mốc pháp lý", không có thì hôm nay.
