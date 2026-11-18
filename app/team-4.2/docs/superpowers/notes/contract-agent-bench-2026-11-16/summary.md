# Đo agent: 5 lần mỗi câu

| Câu | before đúng | after đúng | before bước TB | after bước TB | before `answer` | after `answer` |
|---|---|---|---|---|---|---|
| Q1 | 5/5 | 5/5 | 3.2 | 1.8 | 1/5 | 5/5 |
| Q2 | 5/5 | 5/5 | 3.4 | 2.4 | 4/5 | 5/5 |
| Q3 | 5/5 | 4/5 | 2.6 | 2.4 | 2/5 | 3/5 |
| Q4 | 3/5 | 3/5 | 1.4 | 1.0 | 3/5 | 5/5 |

**before**: đúng 18/20

**after**: đúng 17/20

## Phân tích (2026-11-16)

Cấu hình: Neo4j, cùng một hợp đồng đã soát (build `b435d0a4308bb`), `gpt-6-luna` không cache, 5 lần mỗi ô.

- **Độ đúng gần như không đổi** (18/20 → 17/20); 5 lần mỗi ô quá ít để phân biệt. Lỗi cũ "không sang Điều 2" không
  tái hiện ở cấu hình before trong lần đo này (Q1 before 5/5 có 12.750.000).
- **Cải thiện thật ở độ chắc và số bước**: câu trả lời qua được hậu kiểm (`answer`) 10/20 → 18/20; Q1 1/5 → 5/5.
  Số bước TB Q1 3,2 → 1,8; Q2 3,4 → 2,4. Before bị hạ `partial` 3 lần vì đường đi có nút agent chưa thực sự xem.
- **Q4 sai ở cả hai cấu hình là do tiêu chí chấm quá chặt**: câu "Lương căn bản của tôi là bao nhiêu?" mơ hồ về thời
  điểm; 4 lần sai đều trả 17.000.000 từ 01/07/2025 (đúng cho hiện tại), chỉ thiếu mức 15 triệu ban đầu. Chấm lại
  "có 17 triệu kèm ngày 01/07/2025" thì cả hai 5/5.
- **After Q3 #0 sai thật**: agent chỉ `expand` lần lượt Phụ lục 1, không dùng `find_units` / `cypher_query`, kết luận
  "chưa đủ dữ liệu" (`partial`, trung thực). Q3 #4 đúng nội dung nhưng bị chặn vì dẫn chiếu Điều 2 chưa đọc.
- Ngày soát vẫn 2021-01-01 (lỗi ngày ký, mục 1 danh sách lỗi).
