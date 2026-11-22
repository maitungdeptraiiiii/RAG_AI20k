# Phân công W04 — Huy: dữ liệu hồ sơ theo đối tượng · trích dữ kiện đa loại hợp đồng · đồ thị luật mới

> Đường dẫn `src/`, `docs/`, `tests/` tính từ `app/team-4.2/`; `data/`, `reports/` tính từ gốc repo.
> Thiết kế engine (đọc trước khi làm): `docs/superpowers/specs/2026-11-22-rete-rule-engine-design.md`.
> Người quyết định: **Tùng**. Chỗ nào file này không nói rõ → hỏi Tùng, không tự chọn.

## 0. Bối cảnh trong 5 dòng

- W04 mở rộng từ HĐLĐ sang nhiều loại hợp đồng (trước mắt: BLDS phần chung hợp đồng + hợp đồng vay).
- Tùng viết lại rule engine (`src/rag/rules/`): ngữ nghĩa ba trị + ngoại lệ + kết luận trung gian, hai evaluator
  (Reference, Network). Rule viết trong domain pack YAML.
- Mạng cần **join** (kiểu TREAT): soát từng phụ lục / nhiều hợp đồng của cùng một NLĐ, không chỉ bảng dữ kiện phẳng như hiện nay.
- Phần của Huy là mọi thứ **cấp dữ liệu đúng** cho engine: dữ kiện theo đối tượng, trích dữ kiện cho loại hợp đồng
  mới, và đồ thị luật cho luật mới.
- Engine (join, ngữ nghĩa, mạng tăng dần) là của Tùng. Huy không sửa `src/rag/rules/`.

## 1. Việc chi tiết (theo thứ tự ưu tiên)

### H1 — Dữ kiện theo đối tượng + hồ sơ nhiều văn bản (ưu tiên 1, điều kiện để demo join)

Hiện tại `src/rag/bridge/facts_map.py::_resolve` gộp mọi phụ lục thành MỘT giá trị tại ngày soát (giá trị mới nhất
thắng, cũ vào `amended_from`). Giữ nguyên đường này (tương thích). Thêm đường mới xuất **đối tượng**:

```python
# src/rag/contracts/dossier.py  (file mới)
@dataclass(frozen=True)
class WorkingObject:
    id: str                         # "hd1_2022", "hd1_2022/pl2", "e1"
    type: Literal["Employee", "Contract", "Amendment"]
    attrs: dict[str, Fact]          # Fact của rag.bridge.engine (value, unit, source, uid, quote)
    valid_from: date | None         # Contract: ngày hiệu lực; Amendment: "hiệu lực kể từ ngày" (amendments._effective)
    valid_to: date | None           # Contract: ngày hết hạn nếu có
    refs: dict[str, str]            # {"contract": "hd1_2022"} cho Amendment; {"employee": "e1"} cho Contract

def dossier_objects(dossier: Dossier) -> list[WorkingObject]: ...
def load_dossier(path: Path) -> Dossier: ...      # đọc dossier.yaml (định dạng §3)
```

Yêu cầu:
- Một `Contract` mang dữ kiện của **văn bản gốc**; mỗi phụ lục là một `Amendment` chỉ mang **các dữ kiện nó sửa/bổ
  sung** (từ `rag.contracts.amendments.find_amendments`: `src_uid → dst_uid`, `kind`, `valid_from`).
- Thêm thuộc tính phái sinh tối thiểu cho rule xuyên văn bản: `Amendment.modifies` (danh sách tên dữ kiện bị sửa),
  `Contract.contract_kind`, `Contract.job_title`, `Contract.has_probation`, `Contract.sign_date`, `Contract.end_date`.
  Danh sách cuối cùng chốt với Tùng ngày 1 theo bản liệt kê rule của Tùng.
- Gom văn bản về cùng NLĐ: **bản đầu dùng khai báo tay trong `dossier.yaml`**. Tự nhận diện theo CCCD/tên qua
  `party_ops` là bước 2, chỉ làm khi bước 1 xong và có test.
- Không đổi kết quả của luồng hiện tại (`check_contract` trên một hợp đồng).

### H2 — Trích dữ kiện cho loại hợp đồng mới (ưu tiên 2)

- **Nhận diện loại hợp đồng**: `classify_contract(contract) -> {"kind": "labor_contract" | "loan_contract" | ... |
  "unknown", "confidence": float, "evidence": [uid, quote]}`. Trả `unknown` khi không chắc — không đoán.
  Danh sách loại = `document_kinds` trong các `pack.yaml` Tùng công bố.
- **Tagger theo `kind`**: `kind` (payment, time_limit, notice, rate_cap, termination, penalty, …; danh sách do Tùng
  đề xuất, Tùng chốt) có slot chung. Prompt trích dựng **từ slot của kind**, không viết prompt riêng cho từng concept.
  Tagger chỉ gửi cho LLM các concept của pack áp dụng cho loại hợp đồng đã nhận diện.
- Giữ nguyên quy tắc hiện có của tagger: quote phải chép nguyên văn và được kiểm (`check_item`), slot không chắc thì
  bỏ trống, LLM không đánh giá đúng/sai luật.

### H3 — Đồ thị luật cho luật mới (ưu tiên 3 — bỏ trước nếu quá tải, báo Tùng)

- Khánh nạp văn bản vào kho luật có phiên bản (BLDS 91/2015/QH13, LTM 36/2005/QH11, Luật BVQLNTD 19/2023/QH15,
  Luật Nhà ở 27/2023/QH15). Huy dựng cấu trúc + `REFERS_TO` + hướng dẫn trên đồ thị như đã làm cho lao động.
- Mọi `anchors` / `value_sources` trong `packs/civil_*/concepts.yaml` phải giải được (`text_at(pid, date)`).
- Rà neo trong pack mới giống vai trò LU ở W03: neo sai → sửa thẳng và ghi `note:`.

## 2. Không được làm

- Không sửa `src/rag/rules/**`, `src/rag/bridge/engine.py`, các file `pack.yaml` / phần `rules` trong
  `concepts.yaml`. Cần engine đổi gì → mở issue / nhắn Tùng kèm ví dụ dữ kiện.
- Không thêm regex / heuristic mới để "vá" trích dữ kiện; nếu trích sai, sửa ở mô tả slot / kind hoặc báo Tùng.
- Không để LLM tự quyết văn bản nào thuộc hồ sơ nào ở bản đầu (khai báo tay).
- Không đổi định dạng `dossier.yaml`, `WorkingObject` sau ngày 1 khi chưa có Tùng đồng ý (hồ sơ demo và engine dùng chung).
- Không làm thay đổi kết quả soát HĐLĐ hiện tại (chạy `scripts/score_concept_check.py` trước/sau và ghi số).

## 3. Định dạng dùng chung (chốt ngày 1 với Tùng)

`tests/fixtures/rete/<dossier_id>/dossier.yaml`:

```yaml
dossier_id: b1
review_date: 2024-03-01            # ngày soát mặc định của kịch bản
employee: {id: e1, name: "Nguyễn Văn A", cccd: "0010xxxxxxx", birth_date: 1990-05-01}
documents:
  - {doc_id: hd1_2022, file: hd1_2022.txt, kind: labor_contract, employee: e1}
  - {doc_id: hd2_2023, file: hd2_2023.txt, kind: labor_contract, employee: e1}
  - {doc_id: hd2_2023/pl1, file: hd2_2023_pl1.txt, kind: amendment, contract: hd2_2023}
user_facts: {wage_region: I}
```

## 4. Nghiệm thu

| # | Tiêu chí |
|---|---|
| H1 | `dossier_objects` chạy đúng trên mọi hồ sơ của Tùng (bộ A, B1–B5); test so từng đối tượng với bảng kỳ vọng viết tay; luồng một hợp đồng không đổi kết quả |
| H2 | Nhận diện đúng loại trên toàn bộ hợp đồng mẫu (HĐLĐ, vay, thuê nhà sẵn có `hop_dong_thue_nha_2023.txt`); điểm `score_concept_check.py` của HĐLĐ không giảm; trên hợp đồng vay mẫu, dữ kiện trích có quote kiểm được |
| H3 | 100% anchor của pack mới giải được; ghi lại số neo phải sửa |

## 5. Mốc kiểm tra với Tùng

| Ngày | Mốc |
|---|---|
| 1 (23/11) | Chốt `dossier.yaml`, `WorkingObject`, danh sách thuộc tính đối tượng. |
| 2 | Demo `dossier_objects` trên bộ A của Tùng |
| 3 | Demo trên B1–B5; bắt đầu H2 |
| 4 | Nối vào engine thật của Tùng (join); H2 trên hợp đồng vay |
| 5 | H3 nếu còn thời gian; chuẩn bị phần trình bày của mình |

## 6. Câu hỏi mở (ghi vào đây, Tùng trả lời)

-
