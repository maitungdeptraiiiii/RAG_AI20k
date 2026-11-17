# Đồ thị luật: lớp neo khái niệm (định hướng cho LU)

Ngày: 2026-11-14. Bản nháp 1. Người làm: LU (Huy). Người viết danh mục khái niệm và rule: A (Tùng).

Tài liệu liên quan:
- Đồ thị luật hiện có: `2026-11-13-legal-corpus-graph-design.md` (giữ nguyên, tài liệu này chỉ thêm một lớp mỏng lên trên).
- Đồ thị hợp đồng: `2026-11-12-contract-scale-design.md`.
- Phân công tuần 3: `docs/phan_cong_w03_hop_dong_luat.md`.

## 1. Bối cảnh và mục đích

Đồ thị luật **chỉ** dùng để soát hợp đồng lao động. Chat hỏi luật thông thường vẫn dùng vector / BM25 trên corpus cũ, không đổi.

Khi soát một hợp đồng, hệ thống chạy như sau:

```
Hợp đồng: Điều 5 → khái niệm leave.annual, giá trị 8 ngày     (A: LLM trích + kiểm trích dẫn)
        │ concept_id
        ▼
Đồ thị luật: concept_basis("leave.annual", ngày ký)            (LU: tài liệu này)
        → Đ113, Đ114 BLLĐ: lời văn tại ngày ký, văn bản hướng dẫn, điều khoản liên quan
        ▼
Rule: 12 ngày nếu việc bình thường, đủ 12 tháng → 8 < 12        (A: concepts.yaml + rule engine)
        ▼
Báo cáo: "Điều 5 cho 8 ngày, ít hơn mức tại Đ113 BLLĐ" + lời văn luật làm căn cứ
```

Hai đồ thị gặp nhau ở **một khóa chung đặt trước là `concept_id`**, lấy từ danh mục khái niệm viết tay
(`src/rag/bridge/concepts.yaml`). Không có bước tìm "thực thể bên luật giống thực thể bên hợp đồng".

Việc của đồ thị luật là trả lời: **khái niệm X, tại ngày D, căn cứ vào những điều khoản nào, lời văn ra sao,
có văn bản hướng dẫn và ngoại lệ nào**. Việc so sánh và kết luận đúng / sai là của rule engine.

## 2. Vì sao không dựng đồ thị thực thể (chủ thể → quyền → giá trị) bằng LLM

Hướng "NLĐ → quyền nghỉ phép → 12 ngày" trích bằng LLM trên toàn bộ luật **không làm**, vì:

1. **Tên hai bên không khớp.** LLM đặt tên khác nhau ở hai phía, phải ghép bằng độ giống nghĩa. Ghép trượt thì báo
   nhầm "hợp đồng thiếu quyền" (lỗi nặng nhất của sản phẩm). Law-RAG đã gặp: sinh cạnh `SIMILAR_TO` rồi phải viết
   script xóa.
2. **Giá trị luật phụ thuộc điều kiện.** Phép năm là 12 / 14 / 16 ngày tùy loại công việc, tính theo tỉ lệ nếu chưa
   đủ 12 tháng, cộng thêm theo thâm niên. Một nút "12 ngày" không biểu diễn được; điều kiện viết thành chữ thì máy
   không đánh giá được.
3. **Nút "người lao động" thành hub** nối với hàng trăm quyền; đi dọc đồ thị (kể cả PPR) chỉ xếp hạng, không ra kết
   luận đúng / sai.
4. **Không kiểm thử được.** Sai không biết do trích, do ghép hay do đi đồ thị; chạy lại có thể ra kết quả khác.
   Rule viết tay thì mỗi rule có unit test.
5. **Tốn công.** Trích toàn kho, gộp trùng, duyệt hàng nghìn nút. Hướng ở đây chỉ cần vài chục đến vài trăm cạnh neo.

Spec đồ thị luật ngày 13/11 cũng đã chọn không có lớp ngữ nghĩa bằng LLM (§2, §9). Tài liệu này giữ nguyên lựa chọn đó.

Đồ thị thực thể có ích cho việc **khám phá** ("lao động nữ có những quyền gì", gợi ý quyền ngoài danh mục). Việc
này để sau và kết quả chỉ được hiển thị là gợi ý.

## 3. Mục tiêu, ngoài mục tiêu

**Mục tiêu**
- Mỗi khái niệm trong danh mục có nút `Concept` trong đồ thị luật, nối bằng cạnh `ANCHORED_IN` tới đúng điều /
  khoản / điểm làm căn cứ.
- Một hàm `concept_basis(concept_id, day)` trả về căn cứ pháp lý đầy đủ của khái niệm tại một ngày.
- Báo cáo kiểm tra neo: neo nào không tìm thấy, không hiệu lực tại ngày, hoặc phiên bản chưa xác minh.

**Ngoài mục tiêu**
- Không trích thực thể, quyền, nghĩa vụ bằng LLM. Không dùng embedding ở tầng này.
- Không lưu giá trị số hay điều kiện (12 ngày, 85%, 45 ngày…) thành nút. Chúng nằm trong rule của A.
- Không ghép với đồ thị hợp đồng. Phía A ghép qua `concept_id`.
- Không có tham chiếu xử phạt NĐ 283/2026 ở bản đầu (để sau, §9).

## 4. Nguồn dữ liệu: danh mục khái niệm là nguồn duy nhất

Neo **viết trong `concepts.yaml`**, không viết riêng trong đồ thị (tránh hai nguồn sự thật). Đồ thị đọc file này
và dựng lớp khái niệm, giống cách nó dựng từ snapshot kho luật: xóa đi dựng lại được.

Phần của một khái niệm mà đồ thị luật đọc:

```yaml
- id: termination.employee_unilateral
  label: NLĐ đơn phương chấm dứt HĐLĐ
  scope: core            # core | supporting | out_of_scope
  phase: P0              # P0 | P1 ...
  anchors:
    - {pid: "bo-luat:45/2019/QH14#d35.k1", role: basis}
    - {pid: "bo-luat:45/2019/QH14#d35.k2", role: exception}
  # các trường còn lại (rules, detect, ...) là của A; đồ thị luật bỏ qua
```

- `pid` theo đúng định dạng `keys.provision_id` (`<document_key>#d<điều>.k<khoản>.<điểm>`).
- Neo chỉ trỏ tới **danh tính** điều khoản (`Provision`), không trỏ phiên bản. Phiên bản chọn theo ngày khi truy vấn.
- `role` của neo:
  - `basis`: điều khoản đặt ra quyền / nghĩa vụ / ngưỡng.
  - `exception`: điều khoản loại trừ hoặc ghi đè (Đ35 k2 với Đ35 k1).
  - `value_source`: văn bản chứa giá trị cụ thể thay đổi theo thời kỳ, neo vào **văn bản** (`document_key`) thay vì
    điều khoản, vì giá trị nằm ở văn bản kế tiếp nhau (lương tối thiểu vùng: NĐ 38/2022 → 74/2024 → 293/2025).

**Phân vai:** A viết danh sách khái niệm và neo dự kiến. LU rà từng neo (đúng điều khoản chưa, thiếu ngoại lệ hay
văn bản hướng dẫn nào không) và sửa trực tiếp trong `concepts.yaml`. LU hiểu luật và biết dữ liệu đồ thị nên là
người chốt neo.

## 5. Mô hình thêm vào đồ thị

| Nhãn | Khóa | Thuộc tính |
|---|---|---|
| `Concept` | `node_id` = `concept_id` | `label`, `scope`, `phase`, `catalog_version` |

| Quan hệ | Từ → Tới | Thuộc tính |
|---|---|---|
| `ANCHORED_IN` | Concept → Provision | `role` (`basis` / `exception`) |
| `VALUE_FROM` | Concept → LawDoc | `role = value_source` |

- Nút mang nhãn chung `LGNode` và `build_id` như các nút khác.
- `build_id` = băm của (`snapshot_id`, `GRAPH_VERSION`, checksum của `concepts.yaml`). Sửa danh mục thì dựng lại.
- Thêm vào `schema.json` của đồ thị luật; bước validate từ chối mọi thứ ngoài lược đồ.
- **Không thêm cạnh ngoại lệ hay hướng dẫn mới giữa các điều khoản.** Đồ thị đã có `REFERS_TO` (ví dụ Đ35 k2 điểm
  đ dẫn chiếu khoản 1 Điều 138 được giải tự động) và `REFERS_TO kind=details` / `GUIDES` cho văn bản hướng dẫn.
  `concept_basis` dùng lại các cạnh đó.

## 6. Truy vấn: `concept_basis(concept_id, day)`

Thêm vào lớp `LegalGraph` (chỉ đọc), ghép từ các hàm đã có:

```
concept_basis(concept_id, day) →
{
  "concept_id": "termination.employee_unilateral",
  "day": "2026-01-15",
  "graph": {"build_id": "...", "snapshot_id": "...", "catalog_version": "..."},
  "anchors": [
    {
      "pid": "bo-luat:45/2019/QH14#d35.k1",
      "role": "basis",
      "provision": <kết quả text_at(pid, day)>,       # lời văn + citation, hoặc in_force=False + reason
      "guidance":  <guidance(pid, day)>,              # điều khoản NĐ / TT quy định chi tiết
      "references": <references(pid, day, "out")>     # một bước dẫn chiếu ra ngoài (vd. Đ35 k2 đ → Đ138 k1)
    },
    ...
  ],
  "value_sources": [
    {"document_key": "nghi-dinh:293/2025/NĐ-CP", "applicable": <applicable(key, day)>,
     "appendices": <appendices(key)>}
  ],
  "problems": ["neo X không hiệu lực tại ngày D", "phiên bản Y trạng thái needs_review", ...]
}
```

Quy tắc:
- Neo không hiệu lực tại ngày: vẫn trả về kèm `reason`, đồng thời ghi vào `problems`. Không tự đoán điều khoản thay thế.
- Phiên bản `needs_review` / `conflicted`: trả về kèm trạng thái; phía A quyết định có dùng hay không.
- Đồ thị chưa công bố hoặc lệch snapshot: báo lỗi rõ (`GraphNotPublished` / trạng thái "chưa cập nhật").
- Không dùng LLM trong hàm này. Cùng đầu vào cho cùng kết quả.

Thêm một hàm phụ cho test phía A: `concept_text(concept_id, day) -> str` ghép lời văn mọi neo `basis` tại ngày đó.
Test của A dùng nó để kiểm giá trị chép vào rule có đúng với lời văn luật không (ví dụ "45 ngày" phải xuất hiện
trong Đ35 k1 tại ngày D).

## 7. Báo cáo kiểm tra neo

Lệnh `python -m rag.legal graph check-concepts [--day YYYY-MM-DD]` (tên do LU chọn), in cho từng khái niệm:

- neo không tìm thấy `Provision` (`unknown_provision`) → **lỗi, dừng công bố**;
- neo không hiệu lực tại ngày kiểm (mặc định hôm nay và 01/01/2025);
- neo trỏ tới phiên bản `needs_review` / `conflicted`;
- khái niệm `scope: core` không có neo `basis` nào → **lỗi**;
- `value_source` mà `applicable` trả rỗng hoặc nhiều hơn một văn bản tại ngày kiểm.

## 8. Nghiệm thu

Chạy trên snapshot thật, sau khi giải nén bộ kho mới (`s20261112174549-ca73d5`):

- `graph check-concepts` không có lỗi với danh mục bản đầu (20–30 khái niệm P0 + P1).
- Các ca cụ thể:
  - `concept_basis("termination.employee_unilateral", 2026-01-15)` trả Đ35 k1 (lời văn có "45 ngày"), Đ35 k2 là
    `exception`, và trong `references` của Đ35 k2 có Đ138 k1 BLLĐ.
  - `concept_basis("leave.annual", 2026-01-15)` trả Đ113 và Đ114 BLLĐ.
  - `concept_basis("wage.minimum_regional", d)` với d = 01/01/2024, 01/01/2025, 01/02/2026 có `value_sources`
    lần lượt là NĐ 38/2022, NĐ 74/2024, NĐ 293/2025; với 01/02/2026 có phụ lục danh mục địa bàn.
  - `concept_basis("probation.duration", 2026-01-15)` có `guidance` trỏ tới điều khoản NĐ 145/2020 nếu có.
  - Một khái niệm P1 (`maternity.no_night_overtime_travel`) trả Đ137 k1 BLLĐ.
- Tất định: dựng hai lần cùng snapshot và cùng `concepts.yaml` cho cùng `build_id`.
- Sửa một neo trong `concepts.yaml` thì `build_id` đổi và đồ thị phản ánh neo mới.

## 9. Để sau

1. Neo xử phạt: hành vi vi phạm và mức phạt theo NĐ 283/2026 (thay NĐ 12/2022), chọn theo **ngày vi phạm**, không
   theo ngày ký. Cần thêm `role: sanction`.
2. Neo biện pháp khắc phục hậu quả.
3. Đồ thị thực thể / quyền ngoài danh mục cho tầng gợi ý (§2).
4. Nhóm P2, P3 (chưa thành niên, cao tuổi, khuyết tật, người nước ngoài) khi danh mục mở rộng.
5. Đo độ phủ: tỉ lệ hành vi vi phạm trong nghị định xử phạt đã có khái niệm tương ứng.

## 10. Thứ tự làm

1. Giải nén bộ kho mới, dựng và công bố đồ thị luật hiện có, chạy nghiệm thu của spec 13/11 (nếu chưa xong).
2. A gửi `concepts.yaml` bản đầu với neo dự kiến; LU rà và sửa neo.
3. Dựng lớp `Concept` / `ANCHORED_IN` / `VALUE_FROM`, cập nhật `schema.json` và validate.
4. `concept_basis`, `concept_text`, `graph check-concepts`.
5. Nghiệm thu §8.

## 11. Việc để người dựng tự quyết

Tên hàm, tên lệnh CLI, cách đọc `concepts.yaml` (đường dẫn cấu hình), chỉ mục Neo4j, định dạng báo cáo, cách tổ
chức test. Nếu thấy một neo không thể biểu diễn bằng ba `role` trên, ghi lại ca đó và báo A trước khi thêm `role` mới.
