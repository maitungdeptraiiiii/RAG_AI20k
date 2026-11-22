# Rule engine giai đoạn 7: đối tượng, đếm, phủ định (TREAT) — Kế hoạch

> Thực thi: superpowers:executing-plans (Native). Spec §5.6, §6.1 phần 2, §6.2, §6.3, §10, §11 giai đoạn 7. Checklist D23–D29 (D30 Could: không làm).

**Goal:** Rule xuyên đối tượng (`over` / `group_by` / `check.count|exists|not_exists`) ở cả Reference và Network; Network tính lại kiểu TREAT (chỉ ứng viên của đối tượng đổi, không lưu kết quả nối); dữ kiện suy ra theo kiểu đối tượng; rule xuyên văn bản cho gói labor; soát theo kỳ; đối chiếu ngẫu nhiên có đối tượng.

**Gate** như giai đoạn 3–5, cả hai evaluator; golden giữ nguyên.

## Quyết định của kế hoạch

- `WorkingObject(id, type, attrs: {tên: Fact}, valid_from, valid_to, refs)`; `valid_from=None` = chưa biết (thành viên U), mặc định `date.min`; `valid_to=None` = còn hiệu lực. `ObjectChanges(added, removed, changed)`; `added`/`changed` đều là ghi đè theo `id`, `removed` là danh sách id.
- **Một biến** trong `over` (`{c: {type, where, history?}}`); phép "ghép cặp" của spec viết bằng `group_by` nhiều khóa (vd. `employee` + `job`). Nối nhiều biến để sau (ghi bảng hạn chế).
- `history: true`: thành viên = `valid_from ≤ day` (bỏ `valid_to`), dùng để đếm số lần đã ký; mặc định theo đúng spec (`valid_from ≤ day ≤ valid_to`).
- Đếm theo khoảng `[n_T, n_T + n_U]` đúng §5.6; `exists` = `count ≥ 1`; `not_exists` = phủ định ba trị. Ngưỡng là `value` hoặc `law: <tên>`.
- Nhóm: các khóa đã biết của mọi đối tượng cùng kiểu (kể cả ứng viên F) tạo nhóm; ứng viên khóa chưa biết (T/U) cộng U vào mọi nhóm; chỉ có ứng viên khóa chưa biết thì một nhóm `object=None`. Thứ tự kết quả: theo nhãn nhóm.
- **Không có đối tượng của kiểu đó → một kết quả `NOT_APPLICABLE`, reason `no_objects`** (không biến thiếu hồ sơ thành vi phạm; hợp đồng đơn lẻ không bị nhiễu).
- Rule xuyên đối tượng được coi là có mặt (cấp hồ sơ, không phụ thuộc điều khoản được gắn khái niệm).
- Rule xuyên đối tượng **không tham gia** `exception_of` (bộ nạp từ chối cả hai chiều); ngoại lệ viết bằng `applicability` trên dữ kiện người dùng.
- `RuleResult.object: str | None = None` (field cuối); `RuleChange.object`. Golden so sánh bỏ khóa `object` khi `None` (engine cũ không có trường này).
- `pack.yaml` có `object_types: {Kiểu: {attrs: [...], refs: [...]}}`; `derived` có thể khai `object_type`.
- Diff: theo `(concept, rule, object)`, nhóm theo slot rule; trong một slot theo thứ tự kết quả mới, rồi các nhóm biến mất.

## Task 1 — `rules/objects.py` + model + bộ nạp (D23, D24)
## Task 2 — Reference nhận `objects` (D25), bảng chân lý §5.6
## Task 3 — Network: `ObjectMemory` + ứng viên theo đối tượng đổi (D27), đối chiếu ngẫu nhiên (D29)
## Task 4 — Rule xuyên văn bản gói labor (D26): Đ20.2.c đếm HĐ, Đ20.2.b theo từng HĐ, Đ22.2 phụ lục sửa thời hạn, Đ25 thử việc một lần một công việc
## Task 5 — Soát theo kỳ (D28) `rules/timeline.py`; tài liệu, checklist, bảng hạn chế
