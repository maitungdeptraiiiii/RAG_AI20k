# Rule engine W04 — cách gọi (cho Khánh: benchmark / eval; Huy: `dossier_objects`)

Nhánh `feat/team-4.2/w04-rules-engine` (chưa merge). Thiết kế: `app/team-4.2/docs/superpowers/specs/2026-11-22-rete-rule-engine-design.md`.
Chỉ gọi qua các hàm dưới đây; không sửa `src/rag/rules/**` (trừ `src/rag/rules/bench/` của Khánh).

## Tạo evaluator và phiên

```python
from datetime import date
from rag.rules.evaluator import make_evaluator, evaluator_for
from rag.rules.loader import load_packs
from rag.rules.objects import WorkingObject, ObjectChanges
from rag.rules.semantics import Fact

ev = make_evaluator(["labor"], "network")          # hoặc "reference"; bỏ trống -> RAG_RULE_EVALUATOR (mặc định network)
# hoặc: cat = load_packs(["civil_loan"]); ev = evaluator_for(cat, "network")
s = ev.session(day=date(2025, 3, 1), facts={"contract_kind": Fact("xac_dinh_thoi_han")},
               present={"content.term"}, evidence={}, objects=[...])
s.results()        # list[RuleResult]; rule xuyên đối tượng cho một kết quả mỗi nhóm (RuleResult.object, vd "employee=E1")
s.update({"worked_after_expiry_days": Fact(45, "day")}, objects=ObjectChanges(added=(...,), removed=("id",)))  # -> Diff
s.fork()           # bản sao độc lập (dùng cho next_questions)
s.stats            # chỉ network: nodes_recomputed, rules_recomputed, objects_recomputed
```

- `Diff.changes`: `RuleChange(concept_id, rule_id, before, after, object)`; nhóm mới có `before=None`, nhóm biến mất có `after=None`.
- Hai evaluator phải cho `results()` và `Diff` giống hệt (so bằng `json.dumps(asdict(...), default=str)`); lệch là lỗi engine, báo Tùng.

## Đối tượng hồ sơ (`WorkingObject`) — Huy cấp, theo `packs/labor/pack.yaml` `object_types`

```python
WorkingObject(id="h1", type="Contract",
              attrs={"kind": Fact("xac_dinh_thoi_han"), "worked_after_expiry_days": Fact(45, "day"),
                     "new_contract_signed": Fact(False), "has_probation": Fact(True), "job": Fact("ke_toan")},
              valid_from=date(2023, 1, 1), valid_to=date(2024, 12, 31),   # valid_from=None: chưa biết; valid_to=None: còn hiệu lực
              refs={"employee": "E1"})
WorkingObject(id="p2", type="Amendment", attrs={"modifies_term": Fact(True)}, valid_from=date(2024, 6, 1),
              refs={"contract": "h1"})
```

Thuộc tính thiếu thì để vắng (không ghi `Fact(None)`); thuộc tính hai nguồn mâu thuẫn dùng `semantics.CONFLICT`.
Ngày, đơn vị phải đúng (vd. `worked_after_expiry_days` đơn vị `day`), nếu không phép so ra U (UNKNOWN), không bao giờ ra vi phạm.

## Khác

- `rag.rules.questions.next_questions(catalog, session)` -> câu hỏi xếp hạng (`guaranteed`, `possible`).
- `rag.rules.explain.explain(catalog, session, concept_id, rule_id, obj=None)` -> cây; `.to_json()`, `.to_markdown()`.
- `rag.rules.timeline.review_days(catalog, objects, start, end)` + `review_timeline(...)` + `periods(...)`: soát theo kỳ.
- `rag.rules.events.diff_event(diff, stats)`: sự kiện `evaluation_diff` cho UI.
- Gói có sẵn: `labor` (39 concept, 54 rule, 4 rule xuyên đối tượng), `civil_general`, `civil_loan`.
- Không có `network+beta` (D30, Could): chưa làm.
