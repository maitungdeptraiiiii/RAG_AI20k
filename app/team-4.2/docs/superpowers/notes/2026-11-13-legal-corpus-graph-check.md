# Đồ thị corpus luật — kết quả nghiệm thu

Ngày: 2026-11-13. Spec: `specs/2026-11-13-legal-corpus-graph-design.md`. Kế hoạch: `plans/2026-11-13-legal-corpus-graph.md`.

Đồ thị đang công bố: snapshot `s20261112174549-ca73d5`, build `51cdbb888d7eca95`, Neo4j 5.26 (Docker, cùng instance
với đồ thị hợp đồng).

## 1. Số đo trên snapshot thật

| | Số lượng |
|---|---|
| Văn bản (`LawDoc`) | 92 |
| Điều khoản (`Provision`) | 50.347 |
| Phiên bản (`ProvisionVersion`) | 59.382 |
| Phụ lục (`Appendix`) | 28 |
| `REFERS_TO` | 13.920 |
| `CHANGED_BY` | 2.654 |
| `GUIDES` / `BASED_ON` | 30 / 49 |
| `REPLACES` / `AMENDS` / `REPEALS` / `CONSOLIDATES` | 54 / 27 / 5 / 1 |

Kho tăng từ 56 lên 92 văn bản: sau khi sửa §7.1, crawler lần theo câu "… hết hiệu lực" của nghị định / thông tư và
tải cả các văn bản bị thay thế (chủ yếu nghị định lao động 2013–2019 bị NĐ 145/2020 thay thế).

**Dẫn chiếu** (9.784 dẫn chiếu được phân tích, một dẫn chiếu có thể có nhiều đích):

| Kết quả | Số đích |
|---|---|
| Giải được | 14.187 (trong đó 1.706 sang văn bản khác) |
| `provision_not_found` | 814 |
| `doc_not_in_store` | 374 |
| Bỏ qua trong văn bản sửa đổi | 1.552 |

Tỉ lệ giải được: 14.187 / 15.375 = 92,3% số đích. `kind = details`: 47 cạnh (NĐ 145/2020, TT 10/2020, NĐ 158/2025).

Văn bản ngoài kho bị dẫn chiếu nhiều nhất (ứng viên thêm vào seeds): Luật Người lao động Việt Nam đi làm việc ở
nước ngoài theo hợp đồng, Luật Giáo dục, Luật Xử lý vi phạm hành chính, NĐ 219/2025/NĐ-CP, Luật Công đoàn.

## 2. Năm câu hỏi (spec §8)

| Ca | Kết quả |
|---|---|
| `text_at` Điều 25 BLLĐ tại 01/03/2025 | Đạt: trả lời văn thời gian thử việc (180 / 60 / 30 / 6 ngày). Trạng thái `needs_review` (xem §4). |
| `text_at` Điều 26 BLLĐ | Đạt: "ít nhất phải bằng 85%". |
| `applicable` lương tối thiểu tại 01/01/2024, 01/01/2025, 01/02/2026 | Đạt: NĐ 38/2022, NĐ 74/2024, NĐ 293/2025. |
| `applicable` hôm nay từ NĐ 115/2015 và NĐ 12/2022 | Đạt: NĐ 158/2025 và NĐ 283/2026. |
| `guidance` khoản 4 Điều 21 BLLĐ | Đạt: khoản 2 Điều 1 NĐ 145/2020. Ở cấp Điều 21 còn ra khoản 1 Điều 1 TT 10/2020. |
| `changes` | Đạt trên BLHS Điều 192 (hai phiên bản, kèm điều khoản của Luật 12/2017 và Luật 86/2025 đã sửa). **Không chạy được trên Luật BHXH 41/2024**: kho chưa có phiên bản sửa đổi nào của luật này. |
| `appendices` NĐ 293/2025 | **Không đạt**: xem §3. |
| Văn bản hết hiệu lực | Đạt: `text_at` NĐ 74/2024 hôm nay trả `no_longer_in_force`, đến 01/01/2026. Nghị định lao động còn hiệu lực hôm nay: 135/2020, 145/2020, 158/2025, 283/2026, 293/2025, 337/2025. |
| Tất định | Đạt (test `test_build_is_deterministic`). |
| Công bố bị ngắt giữa chừng | Đạt (test live): con trỏ vẫn ở build cũ, truy vấn vẫn chạy. |
| Neo4j sập | Đạt ở mức hàm: `sync_legal_graph` trả `unavailable`, không ném lỗi. Chưa thử tắt Docker khi server đang chạy. |

## 3. Không đạt / thiếu dữ liệu

- **Danh mục địa bàn vùng lương của NĐ 74/2024 và NĐ 293/2025 không có trong nội dung vbpl.** Raw text của hai
  nghị định này kết thúc ở khối chữ ký; phụ lục nằm trong file đính kèm mà API không trả. Chỉ NĐ 38/2022 có phụ lục
  (6.157 ký tự). Hệ quả: chưa tra được vùng lương cho hợp đồng ký từ 07/2024. Cần nguồn khác (tải file phụ lục lên
  qua chức năng upload của kho, hoặc nhập tay danh mục).
- **Mẫu 100 dẫn chiếu chưa được người kiểm.** File: `notes/2026-11-13-legal-graph-ref-sample.csv` (lấy ngẫu nhiên từ
  2.192 cạnh của 9 văn bản lao động đang hiệu lực; cột `dung_sai`, `ghi_chu` để điền).

## 4. Giới hạn còn lại

- **BLLĐ 45/2019 có trạng thái `needs_review`.** vbpl ghi "hết hiệu lực một phần" nhưng kho không tìm được văn bản sửa
  đổi; VBHN 2026 của BLLĐ cũng chưa có trên vbpl. Lời văn Điều 25, 26 đang là bản gốc 2019.
- **Nghị định sửa đổi nghị định chưa được áp.** Kho đã nhận thay thế / bãi bỏ giữa văn bản dưới luật, nhưng chỉ dẫn
  sửa từng điều khoản của nghị định (`directives.py`) vẫn chỉ hiểu Luật. NĐ 145/2020 và NĐ 135/2020 vì thế còn
  `needs_review`.
- **Đồ thị chỉ tự đồng bộ sau `python -m rag.legal crawl|build`.** Snapshot do server công bố (upload, duyệt) không
  tự dựng lại đồ thị; `graph status` báo `stale: true` và cần chạy `python -m rag.legal graph build`.
- **`body_end_offset` nằm trên `LawDoc`** (vị trí trong raw text), không nằm trên phiên bản Điều cuối như spec §7.2.
- **`heading_path` nằm trên `Provision`**, không nằm trên phiên bản (kho không lưu Chương / Mục theo phiên bản).
- **Dẫn chiếu trong văn bản sửa đổi bị bỏ qua** khi không ghi tên văn bản (1.552 chỗ): chúng nhắc điều khoản của luật
  đích, quan hệ đó đã có ở `CHANGED_BY`.
- **Dạng dẫn chiếu chưa phủ:** khoảng ("từ Điều 5 đến Điều 9"), "điểm a và điểm b khoản 1 Điều 5" (mất điểm a),
  dẫn chiếu viết tự do không có số Điều.
- **814 `provision_not_found`** chưa được phân loại: gồm điều khoản đã bị bãi bỏ, số Điều của đời luật khác, và lỗi
  phân tích. Cần xem cùng với mẫu kiểm tay.

## 5. Cách chạy lại

```
docker compose --env-file .env -f docker/neo4j-compose.yml up -d
python -m rag.legal graph status     # so snapshot của kho với snapshot đồ thị đang phản ánh
python -m rag.legal graph check      # dựng + kiểm tra, không ghi
python -m rag.legal graph build      # dựng, kiểm tra, công bố
NEO4J_TEST_URI=bolt://localhost:7687 NEO4J_TEST_PASSWORD=... pytest tests/test_legal_graph_neo4j.py
```
