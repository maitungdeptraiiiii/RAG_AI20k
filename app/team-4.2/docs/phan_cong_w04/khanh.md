# Phân công W04 — Khánh: nạp luật mới vào kho · benchmark rule engine · eval · router chat

> Đường dẫn `src/`, `docs/`, `tests/`, `scripts/` tính từ `app/team-4.2/`; `data/`, `reports/` tính từ gốc repo.
> Thiết kế engine (đọc §7 "Interface", §9 "Benchmark", §10 "Kiểm thử"): `docs/superpowers/specs/2026-11-22-rete-rule-engine-design.md`.
> Người quyết định: **Tùng**. Chỗ nào file này không nói rõ → hỏi Tùng, không tự chọn.

## 0. Vai trò trong 5 dòng

- Nhóm muốn chứng minh rule engine mới (mạng phụ thuộc tăng dần, lấy ý tưởng từ Rete, join kiểu TREAT) **chịu được
  khi số rule tăng và khi số hợp đồng/phụ lục mỗi hồ sơ tăng**. Khánh làm phần **đo** — trung thực, tái lập được.
- Khánh chỉ gọi engine qua **interface `Evaluator`** — không cần hiểu bên trong mạng, không sửa engine. Tên evaluator
  là `reference` và `network` (không còn `rete`).
- Khánh nạp các luật mới vào **kho luật có phiên bản** (đúng phần đã làm ở W02).
- Khánh mở rộng router/guardrail của **chat hỏi đáp luật** để nhận câu hỏi về luật mới.
- Không làm gì trên đồ thị (như W03).

## 1. Việc chi tiết

### K1 — Nạp luật mới vào kho có phiên bản (ngày 1–2, Huy cần để dựng đồ thị)

BLDS 91/2015/QH13, Luật Thương mại 36/2005/QH11, Luật Bảo vệ quyền lợi người tiêu dùng 19/2023/QH15, Luật Nhà ở
27/2023/QH15 (+ văn bản sửa đổi nếu có). Dùng đường nạp sẵn có (`src/rag/legal/`, trang `/review`). Kiểm: đủ Điều,
đúng ngày hiệu lực, chuỗi sửa đổi đúng. Ghi danh sách văn bản + trạng thái vào `evals/team-4.2/results/w04-rule-engine/legal_ingest.md`.

### K2 — Benchmark rule engine (ngày 2–4)

`scripts/bench_rule_engine.py` + bộ sinh dữ liệu `src/rag/rules/bench/synth.py`.

Bộ sinh:
- Sinh **pack YAML tổng hợp** theo đúng định dạng pack của Tùng và **nạp bằng loader thật** (`rag.rules.loader`) —
  không dựng đối tượng Rule bằng tay.
- **Trục 1, số rule:** 44 (pack thật `labor`), **ba miền thật nạp cùng lúc** (`labor` + `civil_loan` + `civil_lease`,
  bản 3), 500, 2.000, 10.000; tỉ lệ điều kiện dùng chung (0.2 / 0.5); độ sâu
  kết luận trung gian (0 / 3); số dữ kiện đầu vào (50–500); seed.
- **Trục 2, số đối tượng mỗi hồ sơ:** 1 / 5 / 20 / 100 hợp đồng + phụ lục của một người lao động, với 5–50 rule xuyên
  đối tượng (đếm, ghép cặp, phủ định; spec §5.6). Đối tượng sinh theo kiểu `WorkingObject` (Tùng chốt ngày 1).
- Sinh dữ kiện hợp đồng ngẫu nhiên có cả giá trị thiếu (để có UNKNOWN), thuộc tính đối tượng có cả giá trị chưa biết,
  và chuỗi cập nhật (1 / 5 / 20 dữ kiện; thêm / xóa / đổi đối tượng).

Sáu kịch bản (spec §9), chạy **cả hai** evaluator `reference` và `network`:
1. Biên dịch mạng (một lần cho cả catalog).
2. Lần đánh giá đầu của một hợp đồng.
3. Cập nhật tăng dần 1 / 5 / 20 dữ kiện.
4. 100 hồ sơ dùng chung một mạng.
5. `next_questions()` trên hợp đồng nhiều UNKNOWN.
6. Thêm / xóa một đối tượng trong hồ sơ nhiều đối tượng (trục 2).

Đo: trung vị + p95 (≥20 lần lặp, bỏ lần khởi động), số node tính lại (nếu evaluator báo), bộ nhớ đỉnh
(`tracemalloc`). **Mỗi lần chạy phải kiểm hai evaluator ra kết quả bằng nhau** — khác nhau thì in ca lỗi (seed + dữ
kiện) và báo Tùng ngay, không "bỏ qua".

Đầu ra: `evals/team-4.2/results/w04-rule-engine/bench/<timestamp>.json` + `summary.md` (bảng) + biểu đồ PNG: thời gian theo số rule
(trục 1) và theo số đối tượng (trục 2), mỗi kịch bản một đường cho reference và network, trục log.

*Could* (chỉ khi còn thời gian, hỏi Tùng trước): chạy thêm evaluator `network+beta` nếu Tùng cung cấp, để so trên trục 2.

### K3 — Harness eval theo pack (ngày 3–5)

`scripts/eval_rule_engine.py`:
- Đọc mọi `tests/fixtures/rete/*/gold.yaml` (Tùng gắn nhãn) + `dossier.yaml` (Tùng soạn) của **cả ba miền** (lao
  động, vay, thuê nhà; bản 3). Miền nào chưa có gold thì ghi rõ trong `summary.md`, không âm thầm bỏ.
- Thêm một bảng **chọn gói**: với mỗi hợp đồng mẫu, loại do `classify_contract` (Huy) trả về, gói được chạy, và có
  kết quả nào của gói sai miền không (vd. hợp đồng thuê nhà ra kết quả gói `labor` là lỗi).
- Chạy: (a) engine cũ (`rag.bridge.engine.evaluate`), (b) engine mới `reference`, (c) engine mới `network`.
- Báo theo pack và theo loại rule: đúng / sai / UNKNOWN so với gold; ma trận nhầm PASS/FAIL/UNKNOWN; danh sách ca
  sai kèm `explain()` của engine (nếu có).
- Ngày 1–3 chạy trên stub để dựng khung; số thật lấy ngày 4–5.
- Đầu ra: `evals/team-4.2/results/w04-rule-engine/eval/summary.md`.

### K4 — Router + guardrail chat cho luật mới (ngày 4–5, sau K1–K3)

Mở rộng phần đã làm ở W03 (`src/rag/pipeline.py` và chỗ guardrail đang dùng): câu hỏi về BLDS / thương mại / người
tiêu dùng / nhà ở là **trong phạm vi**; khóa cache vẫn gồm snapshot kho luật + ngày áp dụng. Bổ sung ≥20 câu có nhãn
trong/ngoài phạm vi cho luật mới vào bộ test sẵn có; báo tỉ lệ chặn nhầm.

## 2. Interface engine (Tùng công bố stub ngày 1; đây là chữ ký dự kiến)

```python
# src/rag/rules/evaluator.py
class Evaluator(Protocol):
    def session(self, *, day: date, facts: Facts, present: set[str],
                evidence: dict[str, list[dict]],
                objects: Sequence["WorkingObject"] = ()) -> "Session": ...

class Session(Protocol):
    def results(self) -> list[RuleResult]: ...
    def update(self, changes: dict[str, Fact | None], *, present: set[str] | None = None,
               evidence: dict | None = None, objects: "ObjectChanges | None" = None) -> "Diff": ...
    def fork(self) -> "Session": ...

def make_evaluator(packs: list[str], kind: Literal["reference", "network"]) -> Evaluator: ...
```

Ngày 1–3: stub trả kết quả giả nhưng đúng kiểu → dựng khung benchmark/eval trên stub. Khi Tùng báo engine thật sẵn
sàng thì chỉ đổi import, không đổi khung.

## 3. Không được làm

- Không sửa `src/rag/rules/**` (trừ thư mục `src/rag/rules/bench/` của Khánh), `src/rag/bridge/engine.py`, pack YAML.
- Không chỉnh tham số benchmark để mạng "đẹp hơn"; kịch bản 2 (lần đầu) dự kiến mạng **không** thắng — báo đúng như
  vậy. Bảng kết quả luôn có đủ 6 kịch bản và cả hai trục (số rule, số đối tượng mỗi hồ sơ); không bỏ trục nào dù
  kết quả không đẹp.
- Không bỏ qua ca hai evaluator khác nhau.
- Không đo trên máy đang chạy việc nặng khác; ghi cấu hình máy (CPU, RAM, Python) vào `summary.md`.
- Không làm gì trên đồ thị luật / đồ thị hợp đồng.

## 4. Nghiệm thu

| # | Tiêu chí |
|---|---|
| K1 | Mọi văn bản trong danh sách có trong snapshot, đúng ngày hiệu lực; Huy dựng được đồ thị từ đó |
| K2 | `python scripts/bench_rule_engine.py --seed 0` chạy lại ra cùng bảng (sai số thời gian chấp nhận được); có biểu đồ cho cả hai trục; 0 ca lệch giữa hai evaluator |
| K3 | Bảng eval đủ 3 engine × mọi hồ sơ; mỗi ca sai có dẫn tới hồ sơ + rule |
| K4 | Router không chặn nhầm câu hỏi luật mới trong bộ test; điểm eval chat hiện có không giảm |

## 5. Mốc kiểm tra với Tùng

| Ngày | Mốc |
|---|---|
| 1 (23/11) | Nhận stub `Evaluator`; bắt đầu K1 |
| 2 | K1 xong (báo Huy); bộ sinh pack chạy với loader thật |
| 3 | Benchmark chạy đủ 5 kịch bản trên stub/reference; khung eval |
| 4 | Benchmark + eval trên engine thật; K4 |
| 5 | Biểu đồ + bảng cuối cho slide; chuẩn bị phần trình bày |

## 6. Câu hỏi mở (ghi vào đây, Tùng trả lời)

-

**Trạng thái (23/11):** K1–K3 do Claude làm theo yêu cầu Tùng (kế hoạch `docs/superpowers/plans/2026-11-23-khanh-ingest-bench-eval.md`, kết quả ở `evals/team-4.2/results/w04-rule-engine/`, hạn chế ở mục Q của `app/team-4.2/docs/superpowers/notes/w04-rule-engine/han_che_va_loi_ton_dong.md`). K4 (router chat) chưa làm.
**K1 nghiệm thu (23/11):** 11/11 văn bản có trong kho, ngày hiệu lực khớp (kể cả NQ 01/2014: 02/07/2014), đồ thị luật dựng được cả 11 (0 lỗi kiểm tra). Còn: chuỗi sửa đổi LTM 36/2005, NĐ 95/2024, NĐ 96/2024 (cần crawl vbpl.vn, chưa chạy), kiểm phía Neo4j thật.
